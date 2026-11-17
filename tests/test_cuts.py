"""Tests for mdrlens.cuts: the study-in-flight replay mechanics. Uses
small hand-built DataFrames shaped like the SDTM domains (not the full
pilot dataset) so these run without data/raw/*.rda being present.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from mdrlens.cuts import (
    build_cut_calendar,
    current_cut_index,
    diff_ae,
    diff_hy_flags,
    diff_lab_excursions,
    diff_site_flags,
    enrollment_curve,
    filter_to_cut,
    first_patient_in,
    last_observed_date,
    monthly_cuts,
    review_meeting_cuts,
)


def _dm():
    return pd.DataFrame(
        {
            "USUBJID": ["S1", "S2", "S3"],
            "SITEID": ["01", "01", "02"],
            "RFSTDTC": ["2020-01-10", "2020-03-05", "2020-06-20"],
            "RFENDTC": ["2020-07-01", "2020-08-01", "2020-09-01"],
        }
    )


def _ae():
    return pd.DataFrame(
        {
            "USUBJID": ["S1", "S1", "S2"],
            "AESEQ": [1, 2, 1],
            "AESTDTC": ["2020-02-01", "2020-07-15", "2020-04-01"],
        }
    )


def _lb():
    return pd.DataFrame(
        {
            "USUBJID": ["S1", "S2"],
            "LBSEQ": [1, 1],
            "LBDTC": ["2020-02-01", "2020-04-01"],
            "LBSTRESN": [100.0, 50.0],
            "LBSTNRHI": [40.0, 40.0],
        }
    )


def _sv():
    return pd.DataFrame({"USUBJID": ["S1", "S2"], "SVSTDTC": ["2020-02-01", "2020-04-01"]})


def _ds():
    return pd.DataFrame({"USUBJID": ["S1"], "DSSTDTC": ["2020-07-01"]})


def test_first_patient_in():
    assert first_patient_in(_dm()) == dt.date(2020, 1, 10)


def test_last_observed_date_is_max_across_domains():
    d = last_observed_date(_dm(), _ae(), _lb(), _sv(), _ds())
    assert d == dt.date(2020, 9, 1)  # DM.RFENDTC for S3


def test_monthly_cuts_spans_inclusive_and_ends_exactly_at_end_date():
    cuts = monthly_cuts(dt.date(2020, 1, 10), dt.date(2020, 3, 15))
    assert cuts[0] == dt.date(2020, 1, 1)
    assert cuts[-1] == dt.date(2020, 3, 15)
    assert dt.date(2020, 2, 1) in cuts


def test_monthly_cuts_rejects_end_before_start():
    with pytest.raises(ValueError):
        monthly_cuts(dt.date(2020, 5, 1), dt.date(2020, 1, 1))


def test_build_cut_calendar():
    cal = build_cut_calendar(_dm(), _ae(), _lb(), _sv(), _ds())
    assert cal["first_patient_in"] == dt.date(2020, 1, 10)
    assert cal["replay_window_end"] == dt.date(2020, 9, 1)
    assert cal["cuts"][0] == dt.date(2020, 1, 1)
    assert cal["cuts"][-1] == dt.date(2020, 9, 1)


def test_current_cut_index_is_deterministic_and_cycles():
    epoch = dt.date(2026, 11, 17)
    assert current_cut_index(5, epoch) == 0
    assert current_cut_index(5, epoch + dt.timedelta(days=1)) == 1
    assert current_cut_index(5, epoch + dt.timedelta(days=5)) == 0  # wraps
    assert current_cut_index(5, epoch + dt.timedelta(days=37)) == current_cut_index(5, epoch + dt.timedelta(days=37))


def test_current_cut_index_rejects_zero_cuts():
    with pytest.raises(ValueError):
        current_cut_index(0, dt.date(2026, 11, 17))


def test_filter_to_cut_excludes_not_yet_enrolled_subjects():
    out = filter_to_cut(_dm(), _ae(), _lb(), _sv(), _ds(), dt.date(2020, 2, 1))
    assert set(out["dm"]["USUBJID"]) == {"S1"}  # S2 enrolls 03-05, S3 enrolls 06-20
    assert set(out["ae"]["USUBJID"]) == {"S1"}
    assert len(out["ae"]) == 1  # S1's AESEQ=2 is dated 2020-07-15, after this cut


def test_filter_to_cut_at_final_date_includes_everything():
    out = filter_to_cut(_dm(), _ae(), _lb(), _sv(), _ds(), dt.date(2020, 9, 1))
    assert len(out["dm"]) == 3
    assert len(out["ae"]) == 3
    assert len(out["lb"]) == 2


def test_enrollment_curve_is_cumulative_and_monotonic():
    cuts = [dt.date(2020, 1, 1), dt.date(2020, 3, 1), dt.date(2020, 6, 1), dt.date(2020, 9, 1)]
    curve = enrollment_curve(_dm(), cuts)
    values = [r["cumulative_subjects"] for r in curve]
    assert values == sorted(values)
    assert values[-1] == 3
    assert values[0] == 0  # before S1 enrolls (S1 enrolls 01-10, cut is 01-01)


def test_review_meeting_cuts_hits_each_threshold_once():
    cuts = [dt.date(2020, 1, 1), dt.date(2020, 3, 1), dt.date(2020, 6, 1), dt.date(2020, 9, 1)]
    curve = enrollment_curve(_dm(), cuts)
    reviews = review_meeting_cuts(curve)
    thresholds_seen = [r["threshold"] for r in reviews]
    assert thresholds_seen == sorted(thresholds_seen)
    assert reviews[-1]["cumulative_subjects"] == 3  # 100% threshold cut reaches full enrollment


def test_diff_ae_finds_only_new_keys():
    prev = _ae()[_ae()["AESEQ"] == 1]
    curr = _ae()
    new = diff_ae(prev, curr)
    assert new == [("S1", 2)] or ("S1", 2) in new
    assert ("S1", 1) not in new


def test_diff_lab_excursions_only_above_threshold_and_only_new():
    prev_lb = _lb()[_lb()["USUBJID"] == "S2"]  # S2's 50/40=1.25x, below 3x anyway
    curr_lb = _lb()
    new = diff_lab_excursions(prev_lb, curr_lb, x_uln_threshold=2.0)
    # S1: 100/40 = 2.5x >= 2.0 threshold, newly present
    assert ("S1", 1) in new
    assert ("S2", 1) not in new  # 1.25x, below threshold


def test_diff_hy_flags():
    prev = {"S1"}
    curr = {"S1", "S2"}
    assert diff_hy_flags(prev, curr) == ["S2"]


def test_diff_site_flags_only_newly_crossed():
    class FakeSite:
        def __init__(self, site, ae_flag):
            self.site = site
            self.ae_flag = ae_flag
            self.missing_lab_flag = None
            self.visit_oow_flag = None

    prev = [FakeSite("01", None), FakeSite("02", "high")]
    curr = [FakeSite("01", "high"), FakeSite("02", "high")]
    diffs = diff_site_flags(prev, curr)
    assert len(diffs) == 1
    assert diffs[0]["site"] == "01"
    assert diffs[0]["kri"] == "ae_flag"
