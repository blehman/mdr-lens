#!/usr/bin/env python
"""Build the reusable-template demo's derived JSON from its raw SDTM
domains (run scripts/fetch_second_study.py first). Proves mdrlens.studyconfig's
StudyConfig template end to end: fetch -> build -> page section (§09),
the same fetch-then-build shape scripts/fetch_data.py + scripts/build.py
use for the primary study.

Unlike scripts/build.py, this is NOT part of the daily refresh
(.github/workflows/refresh.yml) -- it is a one-time proof that the
template plugs in, re-run by hand when the demo needs updating, same as
§03-06's static look back at the primary study (see README's "Live data").

Writes data/derived/second_study_summary.json, data/derived/second_study_labs.json
and data/derived/second_study_lineage.json, then re-runs scripts/build.py's
pack_web_data() so web/data.js picks up the refreshed bundle in one step.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyreadr

from mdrlens.build import DERIVED_DIR, ROOT, _clean, pack_web_data
from mdrlens.second_study import (
    build_second_study_labs,
    build_second_study_lineage,
    build_second_study_summary,
)
from mdrlens.studyconfig import SECOND_STUDY

RAW_DIR = ROOT / "data" / "raw" / "second_study"


def _load(domain: str) -> "object":
    file_stem = SECOND_STUDY.domain_files[domain]
    path = RAW_DIR / f"{file_stem}.rda"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `uv run python scripts/fetch_second_study.py` first"
        )
    result = pyreadr.read_r(str(path))
    return result[file_stem]


def _write_json(name: str, data) -> Path:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    path = DERIVED_DIR / name
    path.write_text(json.dumps(_clean(data), indent=2, default=str) + "\n")
    return path


def main() -> None:
    dm = _load("dm")
    lb = _load("lb")

    summary = build_second_study_summary(dm, lb, SECOND_STUDY)
    labs = build_second_study_labs(dm, lb, SECOND_STUDY)
    lineage = build_second_study_lineage(SECOND_STUDY)

    for path in [
        _write_json("second_study_summary.json", summary),
        _write_json("second_study_labs.json", labs),
        _write_json("second_study_lineage.json", lineage),
    ]:
        print(f"wrote {path.relative_to(ROOT)}")

    print(f"reusable-template demo: {summary['n_subjects']} subjects, {len(labs)} liver-panel lab peaks")
    pack_web_data()


if __name__ == "__main__":
    main()
