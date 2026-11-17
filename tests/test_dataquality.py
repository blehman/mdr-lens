import pandas as pd

from mdrlens.dataquality import (
    build_domain_quality,
    duplicate_records,
    missing_required_fields,
    visit_out_of_window,
)


def test_missing_required_fields_counts_blank_and_null():
    df = pd.DataFrame({"USUBJID": ["A", "B", None, "D"], "AETERM": ["x", "", "y", "z"]})
    out = missing_required_fields(df, ["USUBJID", "AETERM"])
    assert out["USUBJID"] == 1
    assert out["AETERM"] == 1  # empty string counts as missing


def test_missing_required_fields_absent_column_counts_all_rows():
    df = pd.DataFrame({"USUBJID": ["A", "B"]})
    out = missing_required_fields(df, ["USUBJID", "NOTACOLUMN"])
    assert out["NOTACOLUMN"] == 2


def test_duplicate_records_detects_repeated_keys():
    df = pd.DataFrame(
        {
            "USUBJID": ["A", "A", "B", "C"],
            "AESEQ": [1, 1, 1, 1],
        }
    )
    n_dup, keys = duplicate_records(df, ["USUBJID", "AESEQ"])
    assert n_dup == 1
    assert ("A", 1) in keys


def test_duplicate_records_none_found():
    df = pd.DataFrame({"USUBJID": ["A", "B", "C"], "AESEQ": [1, 1, 1]})
    n_dup, keys = duplicate_records(df, ["USUBJID", "AESEQ"])
    assert n_dup == 0
    assert keys == []


def test_build_domain_quality_dm():
    df = pd.DataFrame(
        {
            "USUBJID": ["A", "B"],
            "SITEID": ["701", "701"],
            "ARM": ["Placebo", None],
            "AGE": [60.0, 70.0],
            "SEX": ["F", "M"],
            "RFSTDTC": ["2020-01-01", None],
        }
    )
    dq = build_domain_quality("dm", df)
    assert dq.n_records == 2
    assert dq.missing_required["ARM"] == 1
    assert dq.missing_required["RFSTDTC"] == 1
    assert dq.n_duplicates == 0


def test_visit_out_of_window_flags_deviation_from_median():
    dm = pd.DataFrame({"USUBJID": ["A", "B", "C"], "RFSTDTC": ["2020-01-01"] * 3})
    sv = pd.DataFrame(
        {
            "USUBJID": ["A", "B", "C"],
            "VISITNUM": [1, 1, 1],
            # study days 0, 0, 30 -> median 0, subject C is 30 days out (>7)
            "SVSTDTC": ["2020-01-01", "2020-01-01", "2020-01-31"],
        }
    )
    out = visit_out_of_window(sv, dm, window_days=7.0)
    assert out["n_visits_evaluated"] == 3
    assert out["n_out_of_window"] == 1
    assert out["rate"] == 1 / 3
