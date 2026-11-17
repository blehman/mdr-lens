"""Data-quality checks, per SDTM domain.

These are the checks a medical/clinical data reviewer runs before trusting
any of the safety views in this project: missing required fields (a form
field that should always be captured but is not: CRF -- case report form,
the document or eCRF screen a site uses to record a subject's data -- or
non-CRF data such as lab feeds), duplicate records (the same event entered
twice under the same key), and visits that fall outside their expected
window (a proxy here, see site_kri.py, since this public dataset ships no
protocol visit schedule).

Everything here is a count against a hand-picked "required" field list per
domain -- a reasonable minimum set for each SDTM (Study Data Tabulation
Model) domain used in this project, not the official CDISC define.xml
validation rules a real study would run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

VISIT_WINDOW_DAYS = 7.0

REQUIRED_FIELDS = {
    "dm": ["USUBJID", "SITEID", "ARM", "AGE", "SEX", "RFSTDTC"],
    "ae": ["USUBJID", "AETERM", "AESTDTC", "AESEV", "AESER"],
    "lb": ["USUBJID", "LBTESTCD", "LBSTRESN", "LBDTC"],
    "sv": ["USUBJID", "VISITNUM", "SVSTDTC"],
    "ds": ["USUBJID", "DSDECOD", "DSSTDTC"],
}

KEY_FIELDS = {
    "dm": ["USUBJID"],
    "ae": ["USUBJID", "AESEQ"],
    "lb": ["USUBJID", "LBSEQ"],
    "sv": ["USUBJID", "VISITNUM"],
    "ds": ["USUBJID", "DSSEQ"],
}


@dataclass
class DomainQuality:
    domain: str
    n_records: int
    missing_required: dict
    n_duplicates: int
    duplicate_keys: list


def missing_required_fields(df: pd.DataFrame, fields: Sequence[str]) -> dict:
    out = {}
    for f in fields:
        if f not in df.columns:
            out[f] = len(df)  # whole field absent from the domain
            continue
        col = df[f]
        if pd.api.types.is_numeric_dtype(col):
            n_missing = int(col.isna().sum())
        else:
            n_missing = int((col.isna() | (col.astype(str).str.strip() == "")).sum())
        out[f] = n_missing
    return out


def duplicate_records(df: pd.DataFrame, key_fields: Sequence[str]) -> tuple[int, list]:
    present = [f for f in key_fields if f in df.columns]
    if not present:
        return 0, []
    dupe_mask = df.duplicated(subset=present, keep=False)
    dupes = df.loc[dupe_mask, present].drop_duplicates()
    n_dup_rows = int(df.duplicated(subset=present, keep="first").sum())
    keys = [tuple(row) for row in dupes.itertuples(index=False, name=None)]
    return n_dup_rows, keys


def build_domain_quality(name: str, df: pd.DataFrame) -> DomainQuality:
    missing = missing_required_fields(df, REQUIRED_FIELDS[name])
    n_dup, dup_keys = duplicate_records(df, KEY_FIELDS[name])
    return DomainQuality(
        domain=name,
        n_records=len(df),
        missing_required=missing,
        n_duplicates=n_dup,
        duplicate_keys=dup_keys[:20],  # cap for the derived JSON
    )


def visit_out_of_window(sv: pd.DataFrame, dm: pd.DataFrame, window_days: float = VISIT_WINDOW_DAYS) -> dict:
    """Study-wide out-of-window visit rate (same method as site_kri.py)."""
    sv = sv.merge(dm[["USUBJID", "RFSTDTC"]], on="USUBJID", how="left")
    sv_start = pd.to_datetime(sv["SVSTDTC"], errors="coerce")
    ref_start = pd.to_datetime(sv["RFSTDTC"], errors="coerce")
    sv = sv.copy()
    sv["STUDY_DAY"] = (sv_start - ref_start).dt.days
    median_day = sv.groupby("VISITNUM")["STUDY_DAY"].median().rename("EXPECTED_DAY")
    sv = sv.merge(median_day, on="VISITNUM", how="left")
    valid = sv[sv["STUDY_DAY"].notna() & sv["EXPECTED_DAY"].notna()]
    oow = (valid["STUDY_DAY"] - valid["EXPECTED_DAY"]).abs() > window_days
    n_valid = len(valid)
    n_oow = int(oow.sum())
    return {
        "n_visits_evaluated": n_valid,
        "n_out_of_window": n_oow,
        "rate": (n_oow / n_valid) if n_valid else 0.0,
        "window_days": window_days,
    }


def build_data_quality(
    dm: pd.DataFrame, ae: pd.DataFrame, lb: pd.DataFrame, sv: pd.DataFrame, ds: pd.DataFrame
) -> dict:
    domains = {"dm": dm, "ae": ae, "lb": lb, "sv": sv, "ds": ds}
    per_domain = {name: build_domain_quality(name, df) for name, df in domains.items()}
    return {
        "per_domain": per_domain,
        "visit_out_of_window": visit_out_of_window(sv, dm),
    }
