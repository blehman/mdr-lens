"""Pin mdrlens.second_study, the reusable-template demo built on
mdrlens.studyconfig.SECOND_STUDY (pharmaversesdtm's metabolic-panel
subset): the labs and liver-panel view only, computed by the same
peak-x-ULN primitive the primary study's eDISH view uses.

The synthetic-fixture tests below always run (no raw/derived data
required). The independent-recount test at the bottom checks the
committed data/raw/second_study/*.rda + data/derived/second_study_*.json
the same "trust an independent pass over the raw table" way
tests/test_independent_recount.py does for the primary study -- it skips
with a clear message if either is missing, rather than failing a bare
clone that hasn't run scripts/fetch_second_study.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mdrlens.second_study import (
    build_second_study_labs,
    build_second_study_lineage,
    build_second_study_summary,
)
from mdrlens.studyconfig import SECOND_STUDY, StudyConfig

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "second_study"
DERIVED_DIR = ROOT / "data" / "derived"


def _tiny_fixture():
    dm = pd.DataFrame(
        [
            {"USUBJID": "S1", "SITEID": "701"},
            {"USUBJID": "S2", "SITEID": "702"},
        ]
    )
    lb = pd.DataFrame(
        [
            {"USUBJID": "S1", "LBTESTCD": "AST", "LBSTRESN": 68.0, "LBSTNRHI": 34.0},
            {"USUBJID": "S1", "LBTESTCD": "ALP", "LBSTRESN": 115.0, "LBSTNRHI": 115.0},
            {"USUBJID": "S2", "LBTESTCD": "AST", "LBSTRESN": 17.0, "LBSTNRHI": 34.0},
        ]
    )
    config = StudyConfig(
        study_key="fixture_demo",
        display_name="fixture demo study",
        source_repo="https://example.invalid/repo",
        source_commit="deadbeef",
        domain_files={"dm": "dm_fixture", "lb": "lb_fixture"},
        liver_panel_tests=("AST", "ALP", "GGT"),
        crf_domains=("dm",),
        non_crf_domains=("lb",),
        enables="fixture enables text",
    )
    return dm, lb, config


def test_build_second_study_labs_computes_peak_x_uln_per_subject_and_test():
    dm, lb, config = _tiny_fixture()
    rows = build_second_study_labs(dm, lb, config)
    by_key = {(r["usubjid"], r["test"]): r["peak_x_uln"] for r in rows}
    assert by_key[("S1", "AST")] == pytest.approx(2.0)
    assert by_key[("S1", "ALP")] == pytest.approx(1.0)
    assert by_key[("S2", "AST")] == pytest.approx(17.0 / 34.0)
    assert ("S1", "GGT") not in by_key  # never run for S1, no fabricated row


def test_build_second_study_labs_attaches_site_from_dm():
    dm, lb, config = _tiny_fixture()
    rows = build_second_study_labs(dm, lb, config)
    sites = {r["usubjid"]: r["site"] for r in rows}
    assert sites["S1"] == "701"
    assert sites["S2"] == "702"


def test_build_second_study_summary_reports_config_and_counts():
    dm, lb, config = _tiny_fixture()
    summary = build_second_study_summary(dm, lb, config)
    assert summary["study_key"] == "fixture_demo"
    assert summary["n_subjects"] == 2
    assert summary["n_lb"] == 3
    assert summary["liver_panel_tests"] == ["AST", "ALP", "GGT"]
    assert summary["domains_used"] == {"dm": "dm_fixture", "lb": "lb_fixture"}
    assert summary["enables"] == "fixture enables text"


def test_build_second_study_lineage_reuses_the_lineage_schema():
    _, _, config = _tiny_fixture()
    rows = build_second_study_lineage(config)
    assert len(rows) == 2
    assert all(r["page_section"] == "template" for r in rows)
    labs_entry = next(r for r in rows if r["metric_id"].endswith(".labs"))
    assert "lb" in labs_entry["domains"] and "dm" in labs_entry["domains"]
    assert "USUBJID" in labs_entry["join"]


def test_second_study_config_is_the_real_one_used_by_the_scripts():
    """mdrlens.studyconfig.SECOND_STUDY itself (not a fixture) must declare
    exactly DM + LB and the AST/ALP/GGT liver-panel subset -- pinned again
    here since this module's build_* functions are the ones that actually
    consume it end to end."""
    assert set(SECOND_STUDY.domain_files) == {"dm", "lb"}
    assert SECOND_STUDY.liver_panel_tests == ("AST", "ALP", "GGT")


# --- independent recount against the committed raw + derived second-study
# files, same pattern as tests/test_independent_recount.py ---

_missing_raw = [f for f in ("dm_metabolic.rda", "lb_metabolic.rda") if not (RAW_DIR / f).exists()]
_missing_derived = [
    f for f in ("second_study_summary.json", "second_study_labs.json") if not (DERIVED_DIR / f).exists()
]


@pytest.mark.skipif(
    bool(_missing_raw or _missing_derived),
    reason=(
        "Second-study independent recount needs both raw SDTM and derived JSON. Run: "
        "uv run python scripts/fetch_second_study.py && uv run python scripts/build_second_study.py "
        f"(missing raw={_missing_raw}, missing derived={_missing_derived})"
    ),
)
def test_second_study_labs_json_matches_independent_recount_from_raw():
    import pyreadr

    dm = pyreadr.read_r(str(RAW_DIR / "dm_metabolic.rda"))["dm_metabolic"]
    lb = pyreadr.read_r(str(RAW_DIR / "lb_metabolic.rda"))["lb_metabolic"]

    independent = {}
    for usubjid, sub in lb.groupby("USUBJID"):
        for test in SECOND_STUDY.liver_panel_tests:
            test_rows = sub[sub["LBTESTCD"] == test]
            ratios = [
                r / u
                for r, u in zip(test_rows["LBSTRESN"], test_rows["LBSTNRHI"])
                if pd.notna(r) and pd.notna(u) and u > 0
            ]
            if ratios:
                independent[(usubjid, test)] = max(ratios)

    labs = json.loads((DERIVED_DIR / "second_study_labs.json").read_text())
    derived = {(r["usubjid"], r["test"]): r["peak_x_uln"] for r in labs}

    assert set(derived.keys()) == set(independent.keys())
    for key, value in independent.items():
        # the derived JSON rounds peak_x_uln to 4 decimal places (see
        # mdrlens.uln.peak_x_uln_by_test); compare against the same rounding
        assert derived[key] == round(value, 4)

    summary = json.loads((DERIVED_DIR / "second_study_summary.json").read_text())
    assert summary["n_subjects"] == len(dm)
    assert summary["n_lb"] == len(lb)
