#!/usr/bin/env python
"""Fetch the live public ClinicalTrials.gov registry view: Roche
("Hoffmann-La Roche") and Genentech Phase 1/2 studies in an actively
enrolling-or-running status, aggregate them, and write
data/derived/registry_summary.json.

This script talks to the network; mdrlens.registry (query shape, parsing,
aggregation) does not, so those pieces stay unit-testable offline.

Failure mode (binding, see README / docs/OPS.md): on ANY failure --
network error, non-200 response, a response that does not parse as the
expected schema, or zero studies returned for a sponsor that should have
some -- this script prints a clear message to stderr and exits non-zero,
and never writes a partial or empty file over the last good
registry_summary.json. The GitHub Action that calls this script treats a
non-zero exit as a failed job, so a broken fetch never reaches Pages;
the previous deployment keeps serving. The file is only replaced after a
full, validated fetch, via a temp-file-then-rename (atomic on POSIX).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from mdrlens.registry import (  # noqa: E402
    BASE_URL,
    LEAD_SPONSORS,
    MAX_RECORDS_PER_SPONSOR,
    MIN_SECONDS_BETWEEN_REQUESTS,
    aggregate,
    build_query_params,
    parse_study,
)

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "derived" / "registry_summary.json"
USER_AGENT = "mdr-lens-fetch-script (public demo; https://github.com/blehman/mdr-lens)"

MAX_RETRIES_ON_429 = 5


def _get(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    backoff = 2.0
    for attempt in range(MAX_RETRIES_ON_429 + 1):
        req = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < MAX_RETRIES_ON_429:
                print(f"  429 rate-limited, backing off {backoff:.0f}s (attempt {attempt + 1})", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"HTTP {e.code} fetching {full_url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"network error fetching {full_url}: {e.reason}") from e


def fetch_sponsor(lead_sponsor: str) -> list[dict]:
    studies: list[dict] = []
    page_token = None
    last_request_time = 0.0
    while True:
        elapsed = time.monotonic() - last_request_time
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
        params = build_query_params(lead_sponsor, page_token)
        last_request_time = time.monotonic()
        payload = _get(BASE_URL, params)

        if "studies" not in payload:
            raise RuntimeError(f"unexpected response shape for {lead_sponsor!r}: missing 'studies' key")

        page_studies = payload["studies"]
        studies.extend(parse_study(s) for s in page_studies)

        if len(studies) > MAX_RECORDS_PER_SPONSOR:
            raise RuntimeError(
                f"{lead_sponsor!r} returned more than the {MAX_RECORDS_PER_SPONSOR}-record cap; "
                "aborting rather than fetching an unbounded result set"
            )

        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return studies


def main() -> int:
    fetch_time = dt.datetime.now(dt.timezone.utc)
    all_studies: list[dict] = []
    per_sponsor_counts: dict[str, int] = {}

    try:
        for sponsor in LEAD_SPONSORS:
            print(f"Fetching lead sponsor={sponsor!r} ...")
            sponsor_studies = fetch_sponsor(sponsor)
            print(f"  {len(sponsor_studies)} studies")
            per_sponsor_counts[sponsor] = len(sponsor_studies)
            all_studies.extend(sponsor_studies)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: ANY failure must fail loudly, not partially write
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        print(f"Leaving the last good {OUT_PATH.relative_to(ROOT)} in place (not overwritten).", file=sys.stderr)
        return 1

    if not all_studies:
        print("FETCH FAILED: zero studies returned across all sponsors -- treating as a bad fetch, not a real zero.", file=sys.stderr)
        return 1

    summary = aggregate(all_studies)
    summary["fetched_at_utc"] = fetch_time.isoformat()
    summary["source_url"] = BASE_URL
    summary["lead_sponsors_queried"] = LEAD_SPONSORS
    summary["per_sponsor_counts"] = per_sponsor_counts
    summary["note"] = (
        "Public ClinicalTrials.gov registry records as of the fetch time above. "
        "This reflects only what sponsors have posted to the public registry -- "
        "it is not, and does not represent, Roche's or Genentech's internal "
        "development pipeline."
    )

    tmp_path = OUT_PATH.with_suffix(".json.tmp")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(json.dumps(summary, indent=2) + "\n")
    tmp_path.replace(OUT_PATH)  # atomic rename on POSIX; only touches the real file on full success
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {len(all_studies)} studies, fetched {fetch_time.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
