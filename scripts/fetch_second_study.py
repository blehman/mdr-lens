#!/usr/bin/env python
"""Fetch the second-study demo's raw SDTM domains (DM + LB only), proving
mdrlens.studyconfig.SECOND_STUDY's template on pharmaversesdtm's
"metabolic" subset -- the same pinned commit scripts/fetch_data.py uses,
redistributed by the same pharmaverse/pharmaversesdtm community source
(Apache-2.0). See mdrlens.second_study for what this subset's demographics
(DM) and labs (LB) domains are used for: the labs and liver-panel view
only.

Writes raw .rda files to data/raw/second_study/ (gitignored, same as
data/raw/) and records the source URL + sha256 of every file in
data/manifest_second_study.json (committed, parallel to data/manifest.json)
so anyone can verify what was downloaded and from where.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from mdrlens.studyconfig import SECOND_STUDY

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "second_study"
MANIFEST_PATH = ROOT / "data" / "manifest_second_study.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_domain(domain: str, file_stem: str) -> dict:
    url = SECOND_STUDY.domain_url(domain)
    dest = RAW_DIR / f"{file_stem}.rda"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "mdr-lens-fetch-script"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (public, pinned https URL)
        data = resp.read()
    dest.write_bytes(data)
    digest = sha256_of(dest)
    print(f"  {file_stem}.rda: {len(data)} bytes, sha256={digest}")
    return {"domain": domain, "file_stem": file_stem, "url": url, "bytes": len(data), "sha256": digest}


def main() -> None:
    manifest = {
        "study_key": SECOND_STUDY.study_key,
        "display_name": SECOND_STUDY.display_name,
        "source_repo": SECOND_STUDY.source_repo,
        "source_commit": SECOND_STUDY.source_commit,
        "license": "Apache-2.0",
        "enables": SECOND_STUDY.enables,
        "domains": [],
    }
    for domain, file_stem in SECOND_STUDY.domain_files.items():
        try:
            manifest["domains"].append(fetch_domain(domain, file_stem))
        except Exception as exc:  # pragma: no cover - network path
            print(f"  FAILED to fetch {domain} ({file_stem}): {exc}", file=sys.stderr)
            raise

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
