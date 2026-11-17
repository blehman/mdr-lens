"""Download the public CDISC pilot SDTM domains from pharmaverse/pharmaversesdtm.

Source: https://github.com/pharmaverse/pharmaversesdtm (Apache-2.0).
This is the long-standing CDISC Pilot Project study, redistributed by the
pharmaverse community as ready-to-use SDTM (.rda) tables. No real patients:
it is a public, synthetic/anonymized teaching dataset used across the
industry for exactly this kind of training and tooling work.

Writes raw .rda files to data/raw/ (gitignored -- not committed, and large
domains like lb.rda are a few hundred KB, small but still raw data) and
records the source URL + sha256 of every file in data/manifest.json so
anyone can verify what was downloaded and from where.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

# Fix 7 (PA direction 2026-11-17): pinned to a commit SHA, not the "main"
# branch -- fetching "main" means any upstream change (a rename, a schema
# change, a removed file) could break the daily scheduled job indefinitely
# with no local change to explain why. Re-pin deliberately with:
#   gh api repos/pharmaverse/pharmaversesdtm/commits/main --jq .sha
# SHA below verified live 2026-11-17 (HTTP 200 on the pinned dm.rda URL).
PHARMAVERSESDTM_COMMIT = "7ec53ea88dfe1c168f9efbef59233c4426813b89"
BASE_URL = f"https://raw.githubusercontent.com/pharmaverse/pharmaversesdtm/{PHARMAVERSESDTM_COMMIT}/data"
DOMAINS = ["dm", "ae", "lb", "sv", "ds"]

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
MANIFEST_PATH = ROOT / "data" / "manifest.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_domain(domain: str) -> dict:
    url = f"{BASE_URL}/{domain}.rda"
    dest = RAW_DIR / f"{domain}.rda"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "mdr-lens-fetch-script"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (public, pinned https URL)
        data = resp.read()
    dest.write_bytes(data)
    digest = sha256_of(dest)
    print(f"  {domain}.rda: {len(data)} bytes, sha256={digest}")
    return {"domain": domain, "url": url, "bytes": len(data), "sha256": digest}


def main() -> None:
    manifest = {
        "source_repo": "https://github.com/pharmaverse/pharmaversesdtm",
        "license": "Apache-2.0",
        "description": (
            "CDISC Pilot Project SDTM study (public, synthetic/anonymized "
            "teaching dataset), redistributed by the pharmaverse community."
        ),
        "domains": [],
    }
    for domain in DOMAINS:
        try:
            manifest["domains"].append(fetch_domain(domain))
        except Exception as exc:  # pragma: no cover - network path
            print(f"  FAILED to fetch {domain}: {exc}", file=sys.stderr)
            raise

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
