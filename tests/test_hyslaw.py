import math

import pandas as pd

from mdrlens.hyslaw import (
    PHL_BILI_X_ULN,
    PHL_TRANSAMINASE_X_ULN,
    SubjectLiverProfile,
    build_liver_profiles,
)


def test_flag_true_when_both_thresholds_met():
    p = SubjectLiverProfile("S1", peak_alt_xuln=3.5, peak_ast_xuln=1.0, peak_bili_xuln=2.1)
    assert p.peak_transaminase_xuln == 3.5
    assert p.hy_flag is True


def test_flag_false_when_only_transaminase_elevated():
    p = SubjectLiverProfile("S2", peak_alt_xuln=5.0, peak_ast_xuln=4.0, peak_bili_xuln=1.0)
    assert p.hy_flag is False


def test_flag_false_when_only_bili_elevated():
    p = SubjectLiverProfile("S3", peak_alt_xuln=1.0, peak_ast_xuln=1.2, peak_bili_xuln=3.0)
    assert p.hy_flag is False


def test_flag_uses_higher_of_alt_or_ast():
    p = SubjectLiverProfile("S4", peak_alt_xuln=1.0, peak_ast_xuln=3.0, peak_bili_xuln=2.0)
    assert p.peak_transaminase_xuln == 3.0
    assert p.hy_flag is True


def test_thresholds_are_inclusive_at_the_boundary():
    p = SubjectLiverProfile(
        "S5", peak_alt_xuln=PHL_TRANSAMINASE_X_ULN, peak_ast_xuln=None, peak_bili_xuln=PHL_BILI_X_ULN
    )
    assert p.hy_flag is True


def test_flag_false_when_missing_data():
    p = SubjectLiverProfile("S6", peak_alt_xuln=None, peak_ast_xuln=None, peak_bili_xuln=5.0)
    assert p.peak_transaminase_xuln is None
    assert p.hy_flag is False


def test_build_liver_profiles_includes_subjects_with_no_lb_records():
    lb = pd.DataFrame(
        [{"USUBJID": "S1", "LBTESTCD": "ALT", "LBSTRESN": 20.0, "LBSTNRHI": 32.0}]
    )
    profiles = build_liver_profiles(lb, subjects=["S1", "S2"])
    by_id = {p.usubjid: p for p in profiles}
    assert set(by_id) == {"S1", "S2"}
    assert by_id["S2"].peak_alt_xuln is None
    assert by_id["S2"].hy_flag is False


def test_build_liver_profiles_hand_checked_subject():
    # Minimal synthetic LB frame reproducing subject 01-705-1186's real
    # ALT/AST/BILI draws (see test_uln.py for the hand check).
    rows = []
    for day, alt, ast, bili in [
        (-5.0, 50.0, 54.0, 25.65),
        (16.0, 104.0, 118.0, 116.28),
        (19.0, 95.0, 115.0, 124.83),
        (25.0, 92.0, 114.0, 99.18),
        (22.0, 107.0, 135.0, 124.83),
        (31.0, 73.0, 92.0, 71.82),
    ]:
        rows.append({"USUBJID": "01-705-1186", "LBTESTCD": "ALT", "LBSTRESN": alt, "LBSTNRHI": 32.0})
        rows.append({"USUBJID": "01-705-1186", "LBTESTCD": "AST", "LBSTRESN": ast, "LBSTNRHI": 34.0})
        rows.append({"USUBJID": "01-705-1186", "LBTESTCD": "BILI", "LBSTRESN": bili, "LBSTNRHI": 21.0})
    lb = pd.DataFrame(rows)

    profiles = build_liver_profiles(lb)
    assert len(profiles) == 1
    p = profiles[0]
    assert math.isclose(p.peak_alt_xuln, 3.34375)
    assert math.isclose(p.peak_ast_xuln, 3.9705882352941178)
    assert math.isclose(p.peak_bili_xuln, 5.944285714285714)
    assert p.hy_flag is True
