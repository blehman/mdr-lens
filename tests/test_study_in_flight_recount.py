"""Independent recount for the study-in-flight replay: check the numbers
in data/derived/study_in_flight.json against the raw SDTM tables and
against a from-scratch recomputation of the cycling cut index, the same
"trust the independent path" pattern as test_independent_recount.py.

Requires data/raw/*.rda and data/derived/study_in_flight.json. Skips with
a clear message if either is missing.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pyreadr
import pytest

from mdrlens.cuts import current_cut_index

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"

_missing_raw = [f for f in ("dm.rda", "ae.rda", "lb.rda") if not (RAW_DIR / f).exists()]
_missing_derived = [] if (DERIVED_DIR / "study_in_flight.json").exists() else ["study_in_flight.json"]

pytestmark = pytest.mark.skipif(
    bool(_missing_raw or _missing_derived),
    reason=(
        "Study-in-flight recount needs both raw SDTM and derived JSON. Run: "
        "uv run python scripts/fetch_data.py && uv run python scripts/build.py "
        f"(missing raw={_missing_raw}, missing derived={_missing_derived})"
    ),
)


def _load_raw(domain: str) -> pd.DataFrame:
    return pyreadr.read_r(str(RAW_DIR / f"{domain}.rda"))[domain]


@pytest.fixture(scope="module")
def si() -> dict:
    return json.loads((DERIVED_DIR / "study_in_flight.json").read_text())


def test_final_cut_matches_raw_record_counts(si):
    """The final cut's date is the latest date seen across any domain, so
    it must include every record for every subject who was ever actually
    placed on the enrollment timeline (DM.RFSTDTC present and parseable).
    Screen failures with no RFSTDTC (52 of 306 in this dataset -- they
    never reached a reference start date) have no enrollment date to be
    cut against, so they -- and any of their AE/LB records with no
    parseable onset/collection date -- are correctly absent from every
    cut including the final one; they still appear in the whole-study
    figures elsewhere on the page (see study_summary.json, which counts
    the full DM/AE/LB domains regardless of date)."""
    dm = _load_raw("dm")
    ae = _load_raw("ae")
    lb = _load_raw("lb")
    enrolled = dm[pd.to_datetime(dm["RFSTDTC"], errors="coerce").notna()]
    enrolled_ids = set(enrolled["USUBJID"])
    final = si["per_cut"][-1]
    assert final["n_subjects"] == len(enrolled)

    ae_in_study = ae[ae["USUBJID"].isin(enrolled_ids)]
    ae_datable = pd.to_datetime(ae_in_study["AESTDTC"], errors="coerce").notna()
    assert final["n_ae"] == int(ae_datable.sum())

    lb_in_study = lb[lb["USUBJID"].isin(enrolled_ids)]
    lb_datable = pd.to_datetime(lb_in_study["LBDTC"], errors="coerce").notna()
    assert final["n_lb"] == int(lb_datable.sum())


def test_first_patient_in_matches_independent_min_rfstdtc(si):
    dm = _load_raw("dm")
    fpi = pd.to_datetime(dm["RFSTDTC"], errors="coerce").min().date()
    assert si["first_patient_in"] == fpi.isoformat()


def test_cumulative_counts_are_monotonic_non_decreasing(si):
    per_cut = si["per_cut"]
    for key in ("n_subjects", "n_ae", "n_lb"):
        values = [c[key] for c in per_cut]
        assert values == sorted(values), f"{key} is not monotonic non-decreasing across cuts"


def test_new_ae_counts_sum_to_the_final_total():
    """Because filter_to_cut only ever includes MORE records as the cut
    date advances (an enrolled subject stays enrolled; a dated record once
    on-or-before a cut stays on-or-before every later cut), every AE can
    become "new" at most once. So the first cut's own count, plus every
    later cut's "new since last cut" count, must sum exactly to the final
    cut's total -- recomputed here with no shared helper from build.py.
    """
    si = json.loads((DERIVED_DIR / "study_in_flight.json").read_text())
    per_cut = si["per_cut"]
    total_new = sum(c["what_changed"]["n_new_ae"] for c in per_cut if c["what_changed"] is not None)
    assert per_cut[0]["n_ae"] + total_new == per_cut[-1]["n_ae"]


def test_current_cut_index_recomputes_independently(si):
    """B2 fix: the auto-selected 'current' cut only cycles over the window
    from the 25% enrollment milestone (cycle_start_index) through the last
    cut (cycle_length cuts total) -- recomputed here from scratch, with no
    shared helper from build.py beyond the generic current_cut_index."""
    run_date = dt.date.fromisoformat(si["run_date"])
    independent_cycle_idx = current_cut_index(si["cycle_length"], run_date)
    independent_idx = si["cycle_start_index"] + independent_cycle_idx
    assert independent_idx == si["current_cut_index"]
    assert si["per_cut"][independent_idx]["cut"] == si["current_cut"]


def test_current_cut_index_never_before_cycle_start(si):
    """The auto-selected 'current' cut index must never be inside the
    pre-25%-milestone window (cut 1 through cycle_start_index - 1)."""
    assert si["current_cut_index"] >= si["cycle_start_index"]


def test_current_cut_is_not_empty(si):
    """B2 blocker: today's 'current' cut must not be the near-empty cut
    right at First Patient In -- it must show real, non-zero enrollment."""
    current = si["per_cut"][si["current_cut_index"]]
    assert current["n_subjects"] > 0


def test_review_meeting_cuts_reach_full_enrollment(si):
    dm = _load_raw("dm")
    enrolled = dm[pd.to_datetime(dm["RFSTDTC"], errors="coerce").notna()]
    final_review = si["review_meeting_cuts"][-1]
    assert final_review["cumulative_subjects"] == len(enrolled)
