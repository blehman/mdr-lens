import pandas as pd

from mdrlens.timeline import build_patient_timeline


def _frames():
    dm = pd.DataFrame(
        {
            "USUBJID": ["S1"],
            "SITEID": ["705"],
            "ARM": ["Placebo"],
            "AGE": [84.0],
            "SEX": ["F"],
            "RFSTDTC": ["2014-01-08"],
        }
    )
    ae = pd.DataFrame(
        {
            "USUBJID": ["S1"],
            "AETERM": ["HYPERBILIRUBINAEMIA"],
            "AEBODSYS": ["HEPATOBILIARY DISORDERS"],
            "AESEV": ["MODERATE"],
            "AESER": ["N"],
            "AEOUT": ["NOT RECOVERED/NOT RESOLVED"],
            "AESTDY": [19.0],
            "AEENDY": [float("nan")],
        }
    )
    lb = pd.DataFrame(
        {
            "USUBJID": ["S1", "S1", "S1"],
            "LBTESTCD": ["ALT", "ALT", "WBC"],
            "LBSTRESN": [107.0, 20.0, 6.0],
            "LBSTNRHI": [32.0, 32.0, 10.0],
            "LBSTRESU": ["U/L", "U/L", "10^9/L"],
            "LBDY": [22.0, 1.0, 1.0],
        }
    )
    sv = pd.DataFrame(
        {
            "USUBJID": ["S1", "S1"],
            "VISITNUM": [1.0, 2.0],
            "VISIT": ["SCREENING", "BASELINE"],
            "SVSTDTC": ["2014-01-01", "2014-01-08"],
        }
    )
    ds = pd.DataFrame(
        {
            "USUBJID": ["S1"],
            "DSDECOD": ["RANDOMIZED"],
            "DSCAT": ["DISPOSITION EVENT"],
            "DSSTDY": [1.0],
        }
    )
    return dm, ae, lb, sv, ds


def test_build_patient_timeline_basic_shape():
    dm, ae, lb, sv, ds = _frames()
    tl = build_patient_timeline("S1", dm, ae, lb, sv, ds)
    assert tl["usubjid"] == "S1"
    assert tl["site"] == "705"
    assert len(tl["ae_events"]) == 1
    assert tl["ae_events"][0]["term"] == "HYPERBILIRUBINAEMIA"
    assert tl["ae_events"][0]["serious"] is False


def test_lab_spikes_only_above_threshold():
    dm, ae, lb, sv, ds = _frames()
    tl = build_patient_timeline("S1", dm, ae, lb, sv, ds)
    tests_flagged = {s["test"] for s in tl["lab_spikes"]}
    assert "ALT" in tests_flagged  # 107/32 = 3.34 >= 1.5
    assert len(tl["lab_spikes"]) == 1  # the 20/32 ALT draw and WBC are both below threshold


def test_visit_study_day_relative_to_ref_start():
    dm, ae, lb, sv, ds = _frames()
    tl = build_patient_timeline("S1", dm, ae, lb, sv, ds)
    days = {v["visit"]: v["day"] for v in tl["visits"]}
    assert days["SCREENING"] == -7.0
    assert days["BASELINE"] == 0.0


def test_unknown_subject_returns_none():
    dm, ae, lb, sv, ds = _frames()
    assert build_patient_timeline("NOPE", dm, ae, lb, sv, ds) is None
