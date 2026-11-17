"""Pin every clinical claim made about subject 01-705-1186 (the one-patient
protagonist) to the raw SDTM tables, with its own simple code path --
independent of mdrlens.timeline -- so the callout text on the page can't
drift from what the source data actually says.

This exists because a medical data reviewer's first move on a claim like
"this subject was on placebo with a pre-existing elevation" is to go back to
the raw DM (demographics) and LB (laboratory test results) domains and check
it personally, not take the page's word for it.

Requires data/raw/{dm,lb}.rda (gitignored, fetched by scripts/fetch_data.py).
Skips with a clear message if they are not present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyreadr
import pytest

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"

PROTAGONIST = "01-705-1186"
REQUIRED_RAW = ["dm.rda", "lb.rda"]
_missing_raw = [f for f in REQUIRED_RAW if not (RAW_DIR / f).exists()]

pytestmark = pytest.mark.skipif(
    bool(_missing_raw),
    reason=f"Needs raw SDTM: uv run python scripts/fetch_data.py (missing={_missing_raw})",
)


def _load_raw(domain: str) -> pd.DataFrame:
    return pyreadr.read_r(str(RAW_DIR / f"{domain}.rda"))[domain]


# Hand-checked, independent of mdrlens.uln.x_uln: value / ULN for the five
# baseline (day -5, LBBLFL == "Y") liver-panel draws for 01-705-1186.
EXPECTED_DAY_MINUS5_X_ULN = {
    "ALT": 50.0 / 32.0,       # 1.5625
    "AST": 54.0 / 34.0,       # 1.588235...
    "ALP": 565.0 / 115.0,     # 4.913043...
    "GGT": 466.0 / 50.0,      # 9.32
    "BILI": 25.65 / 21.0,     # 1.221428... -- below the 1.5x "spike" cutoff
}


def test_protagonist_is_on_placebo_arm():
    dm = _load_raw("dm")
    row = dm[dm["USUBJID"] == PROTAGONIST].iloc[0]
    assert row["ARM"] == "Placebo"
    assert row["ACTARM"] == "Placebo"


def test_protagonist_day_minus5_liver_panel_matches_raw_lb():
    """Every baseline x-ULN value quoted in the patient callout, recomputed
    straight from raw lb.rda with plain arithmetic (no shared helper)."""
    lb = _load_raw("lb")
    sub = lb[
        (lb["USUBJID"] == PROTAGONIST)
        & (lb["LBDY"] == -5.0)
        & (lb["LBTESTCD"].isin(EXPECTED_DAY_MINUS5_X_ULN.keys()))
    ]
    assert len(sub) == 5  # exactly the five liver-panel tests, once each
    assert set(sub["LBTESTCD"]) == set(EXPECTED_DAY_MINUS5_X_ULN.keys())

    for _, r in sub.iterrows():
        test = r["LBTESTCD"]
        assert test in EXPECTED_DAY_MINUS5_X_ULN, f"unexpected test {test} on day -5"
        observed = r["LBSTRESN"] / r["LBSTNRHI"]
        assert observed == pytest.approx(EXPECTED_DAY_MINUS5_X_ULN[test], rel=1e-9)
        # all five day -5 draws are flagged as the baseline record
        assert r["LBBLFL"] == "Y"


def test_bili_day_minus5_is_present_but_below_spike_threshold():
    """Pins the exact reason bilirubin used to show no point before day 16:
    not "not collected", not "collected but missing LBSTRESN" -- present,
    numeric, and real (1.22x ULN), just below the 1.5x ULN cutoff this
    project's own timeline pipeline used to use for what counts as a
    plot-worthy "spike". mdrlens.timeline now always keeps the baseline
    (LBBLFL == "Y") draw regardless of that cutoff; this test pins why the
    gap existed in the first place, straight from the raw table.
    """
    lb = _load_raw("lb")
    row = lb[
        (lb["USUBJID"] == PROTAGONIST) & (lb["LBDY"] == -5.0) & (lb["LBTESTCD"] == "BILI")
    ].iloc[0]
    assert pd.notna(row["LBSTRESN"])  # collected, not missing
    assert row["LBSTRESN"] == pytest.approx(25.65)
    x_uln = row["LBSTRESN"] / row["LBSTNRHI"]
    assert x_uln == pytest.approx(1.2214285714285713, rel=1e-9)
    assert x_uln < 1.5  # below the old spike-only cutoff -- that's the gap


def test_no_bili_record_at_all_between_day_minus5_and_day_16():
    """Separately confirms there is a genuine ~3-week collection gap (no
    BILI draw of any kind between day -5 and day 16) -- distinct from the
    day -5 point itself, which is present. Both facts matter: the point at
    day -5 was wrongly dropped by our own threshold; the gap after it is
    real and should stay a straight line, never a smoothed curve implying
    data that was never collected.
    """
    lb = _load_raw("lb")
    sub = lb[(lb["USUBJID"] == PROTAGONIST) & (lb["LBTESTCD"] == "BILI")]
    between = sub[(sub["LBDY"] > -5.0) & (sub["LBDY"] < 16.0)]
    assert len(between) == 0


def test_derived_patient_timeline_includes_day_minus5_bili_point():
    """End-to-end: after the pipeline fix, the derived JSON the page reads
    actually carries the day -5 BILI point (skips if build hasn't run yet).
    """
    path = DERIVED_DIR / "patient_timeline.json"
    if not path.exists():
        pytest.skip("run scripts/build.py first")
    timeline = json.loads(path.read_text())
    if timeline["usubjid"] != PROTAGONIST:
        pytest.skip("protagonist changed; this pin is specific to 01-705-1186")
    bili_minus5 = [s for s in timeline["lab_spikes"] if s["test"] == "BILI" and s["day"] == -5.0]
    assert len(bili_minus5) == 1
    assert bili_minus5[0]["x_uln"] == pytest.approx(1.22, abs=0.01)
    assert bili_minus5[0]["baseline"] is True
