import math

import pandas as pd

from mdrlens.uln import peak_x_uln, peak_x_uln_by_test, x_uln


def test_x_uln_basic():
    assert x_uln(107.0, 32.0) == 107.0 / 32.0
    assert x_uln(34.0, 34.0) == 1.0


def test_x_uln_missing_value_or_uln_returns_none():
    assert x_uln(None, 32.0) is None
    assert x_uln(107.0, None) is None
    assert x_uln(float("nan"), 32.0) is None
    assert x_uln(107.0, float("nan")) is None


def test_x_uln_zero_or_negative_uln_returns_none():
    assert x_uln(107.0, 0.0) is None
    assert x_uln(107.0, -1.0) is None


def test_peak_x_uln_picks_the_max_and_skips_missing():
    records = [(50.0, 32.0), (None, 32.0), (107.0, 32.0), (73.0, 32.0)]
    peak = peak_x_uln(records)
    assert math.isclose(peak, 107.0 / 32.0)


def test_peak_x_uln_all_missing_returns_none():
    assert peak_x_uln([(None, 32.0), (float("nan"), 32.0)]) is None


# --- hand-checked against real subject 01-705-1186 in the CDISC pilot ---
# (see data/raw/lb.rda; ALT/AST/BILI rows pulled and multiplied by hand)
#   ALT:  peak result 107 U/L, site ULN 32 U/L  -> 107/32  = 3.34375
#   AST:  peak result 135 U/L, site ULN 34 U/L  -> 135/34  = 3.9705882352941178
#   BILI: peak result 124.83 umol/L, ULN 21 umol/L -> 124.83/21 = 5.944285714285714


def test_hand_checked_subject_01_705_1186_alt():
    records = [(50.0, 32.0), (104.0, 32.0), (95.0, 32.0), (92.0, 32.0), (107.0, 32.0), (73.0, 32.0)]
    assert math.isclose(peak_x_uln(records), 3.34375)


def test_hand_checked_subject_01_705_1186_ast():
    records = [(54.0, 34.0), (118.0, 34.0), (115.0, 34.0), (114.0, 34.0), (135.0, 34.0), (92.0, 34.0)]
    assert math.isclose(peak_x_uln(records), 3.9705882352941178)


def test_hand_checked_subject_01_705_1186_bili():
    records = [
        (25.65, 21.0),
        (116.28, 21.0),
        (124.83, 21.0),
        (99.18, 21.0),
        (124.83, 21.0),
        (71.82, 21.0),
    ]
    assert math.isclose(peak_x_uln(records), 5.944285714285714)


# --- peak_x_uln_by_test: the reusable primitive mdrlens.second_study plugs
# a different study's LB domain into, generalized from the ALT/AST/BILI
# triple above to an arbitrary list of LBTESTCD values ---


def test_peak_x_uln_by_test_picks_peak_per_subject_per_test():
    lb = pd.DataFrame(
        [
            {"USUBJID": "S1", "LBTESTCD": "AST", "LBSTRESN": 54.0, "LBSTNRHI": 34.0},
            {"USUBJID": "S1", "LBTESTCD": "AST", "LBSTRESN": 135.0, "LBSTNRHI": 34.0},
            {"USUBJID": "S1", "LBTESTCD": "ALP", "LBSTRESN": 100.0, "LBSTNRHI": 115.0},
        ]
    )
    rows = peak_x_uln_by_test(lb, ["S1"], ["AST", "ALP"])
    by_test = {r["test"]: r["peak_x_uln"] for r in rows}
    # peak_x_uln_by_test rounds to 4 decimal places for the derived JSON
    # (see its docstring); compare against the same rounding, not raw floats.
    assert by_test["AST"] == round(135.0 / 34.0, 4)
    assert by_test["ALP"] == round(100.0 / 115.0, 4)


def test_peak_x_uln_by_test_omits_rows_for_a_test_never_run():
    """A study whose LB domain never ran one of `tests` (e.g. no BILI draws
    at all, like the second-study metabolic subset) yields no row for that
    test -- never a fabricated zero or null row."""
    lb = pd.DataFrame([{"USUBJID": "S1", "LBTESTCD": "AST", "LBSTRESN": 54.0, "LBSTNRHI": 34.0}])
    rows = peak_x_uln_by_test(lb, ["S1"], ["AST", "BILI"])
    assert {r["test"] for r in rows} == {"AST"}


def test_peak_x_uln_by_test_covers_multiple_subjects_independently():
    lb = pd.DataFrame(
        [
            {"USUBJID": "S1", "LBTESTCD": "AST", "LBSTRESN": 68.0, "LBSTNRHI": 34.0},
            {"USUBJID": "S2", "LBTESTCD": "AST", "LBSTRESN": 34.0, "LBSTNRHI": 34.0},
        ]
    )
    rows = peak_x_uln_by_test(lb, ["S1", "S2"], ["AST"])
    by_subject = {r["usubjid"]: r["peak_x_uln"] for r in rows}
    assert by_subject == {"S1": 2.0, "S2": 1.0}


def test_hand_checked_against_second_study_metabolic_subject_01_701_1015_ast():
    """Hand-checked against the real pharmaversesdtm metabolic subset
    (data/raw/second_study/lb_metabolic.rda, same pinned commit as
    scripts/fetch_data.py): subject 01-701-1015's single AST draw, 40 U/L
    against a 34 U/L site ULN."""
    lb = pd.DataFrame([{"USUBJID": "01-701-1015", "LBTESTCD": "AST", "LBSTRESN": 40.0, "LBSTNRHI": 34.0}])
    rows = peak_x_uln_by_test(lb, ["01-701-1015"], ["AST"])
    assert rows[0]["peak_x_uln"] == round(40.0 / 34.0, 4)
