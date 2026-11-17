import math

from mdrlens.uln import peak_x_uln, x_uln


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
