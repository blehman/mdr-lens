import math

import pytest

from mdrlens.funnel import flag_outlier, funnel_curve, funnel_limits


def test_limits_widen_for_smaller_n_proportion():
    big = funnel_limits(n=500, pooled_rate=0.1, kind="proportion")
    small = funnel_limits(n=5, pooled_rate=0.1, kind="proportion")
    assert (small.alarm_upper - small.alarm_lower) > (big.alarm_upper - big.alarm_lower)
    assert (small.watch_upper - small.watch_lower) > (big.watch_upper - big.watch_lower)


def test_limits_widen_for_smaller_n_rate():
    big = funnel_limits(n=1000, pooled_rate=5.0, kind="rate")
    small = funnel_limits(n=2, pooled_rate=5.0, kind="rate")
    assert (small.alarm_upper - small.alarm_lower) > (big.alarm_upper - big.alarm_lower)


def test_alarm_band_wider_than_watch_band():
    lim = funnel_limits(n=20, pooled_rate=0.2, kind="proportion")
    assert lim.alarm_lower <= lim.watch_lower
    assert lim.alarm_upper >= lim.watch_upper


def test_proportion_limits_clipped_to_0_1():
    lim = funnel_limits(n=3, pooled_rate=0.95, kind="proportion")
    assert lim.alarm_upper <= 1.0
    assert lim.watch_lower >= 0.0


def test_rate_limits_clipped_at_zero():
    lim = funnel_limits(n=2, pooled_rate=0.5, kind="rate")
    assert lim.alarm_lower >= 0.0


def test_center_equals_pooled_rate():
    lim = funnel_limits(n=10, pooled_rate=0.37, kind="proportion")
    assert math.isclose(lim.center, 0.37)


def test_flag_outlier_high_low_none():
    lim = funnel_limits(n=100, pooled_rate=0.5, kind="proportion")
    assert lim.alarm_lower > 0.0  # sanity: this scenario has room below center
    assert flag_outlier(lim.alarm_upper + 0.1, lim) == "high"
    assert flag_outlier(lim.alarm_lower - 0.1, lim) == "low"
    assert flag_outlier(lim.center, lim) is None


def test_funnel_limits_rejects_non_positive_n():
    with pytest.raises(ValueError):
        funnel_limits(n=0, pooled_rate=0.1)


def test_funnel_curve_widens_toward_small_n():
    curve = funnel_curve(pooled_rate=0.1, kind="proportion", n_max=200, n_points=40)
    assert curve[0]["n"] < curve[-1]["n"]  # sorted ascending by n
    width_small_n = curve[0]["alarm_upper"] - curve[0]["alarm_lower"]
    width_big_n = curve[-1]["alarm_upper"] - curve[-1]["alarm_lower"]
    assert width_small_n > width_big_n


def test_funnel_curve_n_within_requested_range():
    curve = funnel_curve(pooled_rate=0.2, kind="proportion", n_max=100, n_points=25)
    ns = [row["n"] for row in curve]
    assert min(ns) >= 1
    assert max(ns) <= 100


def test_funnel_curve_respects_n_min():
    # A small pooled_rate with n extrapolated down to 1 can blow the alarm
    # band up to values far outside any sensible chart axis (this is what
    # produced a real rendering bug: an SVG path hundreds of pixels taller
    # than its own chart). Honoring n_min keeps every sampled point close
    # to the actual smallest group size.
    curve = funnel_curve(pooled_rate=0.0147, kind="proportion", n_max=10000, n_min=233, n_points=30)
    ns = [row["n"] for row in curve]
    assert min(ns) >= 233
    assert max(row["alarm_upper"] for row in curve) < 0.1
