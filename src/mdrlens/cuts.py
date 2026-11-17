"""Study-in-flight replay: deterministic monthly data cuts over the SDTM
pilot study.

The pilot study (see README) is one already-completed public dataset. To
demonstrate the kind of dashboard a Real-Time Visual Analytics function
builds -- one that advances through milestone data cuts as a trial
actually enrolls, refreshed to First Patient In, cohort reviews, and
safety data review committee meetings -- this module replays that
finished study AS IF it were still enrolling: each monthly cut includes
only the records dated on or before that cut's date, exactly as a live
extract would have looked that month. Every screen built from this module
says, on screen, that it is a completed public study replayed by data
cut -- never a live study.

Cut dates are derived straight from the SDTM dates actually present in the
data: the earliest DM.RFSTDTC (reference start date) across all subjects
is First Patient In (FPI); the latest date across DM.RFENDTC, AE.AESTDTC,
LB.LBDTC, SV.SVSTDTC and DS.DSSTDTC is the end of the replay window. Cuts
fall on the first of each month, FPI's month through the end month,
inclusive.

The "current" cut advances one step per day and cycles forever once the
last cut is reached (CYCLE_EPOCH is cut index 0; shown on screen as the
cycle's start date, per PA direction 11-17 -- no daily commit marks this,
it is recomputed from the clock at build/render time).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

# Cut index 0 of the deterministic cycle. Fixed, not "today", so the cycle
# is reproducible by anyone re-running this on any later date -- advancing
# one cut per calendar day from this date, wrapping after the last cut.
CYCLE_EPOCH = dt.date(2026, 11, 17)

REVIEW_MEETING_THRESHOLDS = (0.25, 0.50, 0.75, 1.00)

# "New lab excursion" for the what-changed view: a lab result newly crossing
# >=3x ULN between one cut and the next (same threshold as the Potential
# Hy's Law transaminase criterion, see hyslaw.py -- this is a general lab
# excursion screen, not limited to liver tests).
LAB_EXCURSION_X_ULN = 3.0

DATE_COLUMNS = {
    "dm_start": ("dm", "RFSTDTC"),
    "dm_end": ("dm", "RFENDTC"),
    "ae": ("ae", "AESTDTC"),
    "lb": ("lb", "LBDTC"),
    "sv": ("sv", "SVSTDTC"),
    "ds": ("ds", "DSSTDTC"),
}


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def first_patient_in(dm: pd.DataFrame) -> dt.date:
    starts = _to_date(dm["RFSTDTC"]).dropna()
    if starts.empty:
        raise ValueError("DM.RFSTDTC has no parseable dates; cannot compute First Patient In")
    return starts.min().date()


def last_observed_date(dm: pd.DataFrame, ae: pd.DataFrame, lb: pd.DataFrame, sv: pd.DataFrame, ds: pd.DataFrame) -> dt.date:
    candidates = [
        _to_date(dm["RFSTDTC"]).max(),
        _to_date(dm["RFENDTC"]).max(),
        _to_date(ae["AESTDTC"]).max(),
        _to_date(lb["LBDTC"]).max(),
        _to_date(sv["SVSTDTC"]).max(),
        _to_date(ds["DSSTDTC"]).max(),
    ]
    candidates = [c for c in candidates if pd.notna(c)]
    if not candidates:
        raise ValueError("no parseable dates found across domains; cannot compute replay window end")
    return max(candidates).date()


def monthly_cuts(start: dt.date, end: dt.date) -> list[dt.date]:
    """First-of-month cut dates from start's month through end's month,
    inclusive, plus the final `end` date itself so the very last cut always
    includes every record (a mid-month end date would otherwise be hidden
    until the following month's cut).
    """
    if end < start:
        raise ValueError("end date precedes start date")
    cuts = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        cuts.append(dt.date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    if cuts[-1] != end:
        cuts.append(end)
    return cuts


def build_cut_calendar(dm: pd.DataFrame, ae: pd.DataFrame, lb: pd.DataFrame, sv: pd.DataFrame, ds: pd.DataFrame) -> dict:
    fpi = first_patient_in(dm)
    end = last_observed_date(dm, ae, lb, sv, ds)
    cuts = monthly_cuts(fpi, end)
    return {"first_patient_in": fpi, "replay_window_end": end, "cuts": cuts}


def current_cut_index(n_cuts: int, run_date: dt.date, epoch: dt.date = CYCLE_EPOCH) -> int:
    """Deterministic, cycling index into a list of n_cuts cuts: one step
    per calendar day since `epoch`, wrapping with modulo so the replay
    loops forever instead of stopping at the last cut.
    """
    if n_cuts <= 0:
        raise ValueError("n_cuts must be positive")
    days_elapsed = (run_date - epoch).days
    return days_elapsed % n_cuts


def filter_to_cut(
    dm: pd.DataFrame, ae: pd.DataFrame, lb: pd.DataFrame, sv: pd.DataFrame, ds: pd.DataFrame, cut_date: dt.date
) -> dict[str, pd.DataFrame]:
    """Every domain filtered to only what a live extract would have shown
    as of `cut_date`: subjects enrolled by then (DM.RFSTDTC <= cut_date),
    and every other domain's records for those subjects dated on or before
    the cut.
    """
    cut_ts = pd.Timestamp(cut_date)
    dm_f = dm[_to_date(dm["RFSTDTC"]) <= cut_ts].copy()
    enrolled = set(dm_f["USUBJID"])

    def _f(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
        in_study = df["USUBJID"].isin(enrolled)
        on_or_before = _to_date(df[date_col]) <= cut_ts
        return df[in_study & on_or_before].copy()

    return {
        "dm": dm_f,
        "ae": _f(ae, "AESTDTC"),
        "lb": _f(lb, "LBDTC"),
        "sv": _f(sv, "SVSTDTC"),
        "ds": _f(ds, "DSSTDTC"),
    }


def enrollment_curve(dm: pd.DataFrame, cuts: list[dt.date]) -> list[dict]:
    """Cumulative subjects enrolled (DM.RFSTDTC <= cut) at each cut."""
    starts = _to_date(dm["RFSTDTC"])
    out = []
    for c in cuts:
        n = int((starts <= pd.Timestamp(c)).sum())
        out.append({"cut": c.isoformat(), "cumulative_subjects": n})
    return out


def review_meeting_cuts(enrollment: list[dict], thresholds=REVIEW_MEETING_THRESHOLDS) -> list[dict]:
    """Pick one cut per enrollment threshold (25/50/75/100%): the first
    cut at which cumulative enrollment reaches that share of final
    enrollment -- a deterministic stand-in for scheduled cohort reviews /
    safety data review committee meetings, which this public dataset does
    not publish a real schedule for.
    """
    if not enrollment:
        return []
    final_n = enrollment[-1]["cumulative_subjects"]
    if final_n <= 0:
        return []
    picked = []
    seen_cuts = set()
    for frac in thresholds:
        target = frac * final_n
        for row in enrollment:
            if row["cumulative_subjects"] >= target:
                if row["cut"] not in seen_cuts:
                    picked.append({"cut": row["cut"], "threshold": frac, "cumulative_subjects": row["cumulative_subjects"]})
                    seen_cuts.add(row["cut"])
                break
    return picked


@dataclass
class WhatChanged:
    cut_from: str
    cut_to: str
    new_ae_keys: list
    new_lab_excursion_keys: list
    newly_hy_flagged: list
    newly_flagged_sites: list


def diff_ae(prev_ae: pd.DataFrame, curr_ae: pd.DataFrame) -> list[tuple]:
    prev_keys = set(zip(prev_ae["USUBJID"], prev_ae["AESEQ"]))
    curr_keys = set(zip(curr_ae["USUBJID"], curr_ae["AESEQ"]))
    return sorted(curr_keys - prev_keys)


def diff_lab_excursions(prev_lb: pd.DataFrame, curr_lb: pd.DataFrame, x_uln_threshold: float = 3.0) -> list[tuple]:
    from .uln import x_uln

    def excursion_keys(lb: pd.DataFrame) -> set:
        keys = set()
        for _, r in lb.iterrows():
            ratio = x_uln(r.get("LBSTRESN"), r.get("LBSTNRHI"))
            if ratio is not None and ratio >= x_uln_threshold:
                keys.add((r["USUBJID"], r["LBSEQ"]))
        return keys

    return sorted(excursion_keys(curr_lb) - excursion_keys(prev_lb))


def diff_hy_flags(prev_flagged: set, curr_flagged: set) -> list:
    return sorted(curr_flagged - prev_flagged)


def diff_site_flags(prev_site_kris: list, curr_site_kris: list) -> list[dict]:
    """Sites that newly cross into a flagged state (ae/missing_lab/visit_oow)
    between two cuts that were not flagged on that KRI at the previous cut.
    """
    prev_by_site = {s.site if hasattr(s, "site") else s["site"]: s for s in prev_site_kris}
    out = []
    for s in curr_site_kris:
        site = s.site if hasattr(s, "site") else s["site"]
        prev = prev_by_site.get(site)
        for kri in ("ae_flag", "missing_lab_flag", "visit_oow_flag"):
            curr_flag = getattr(s, kri) if hasattr(s, kri) else s[kri]
            prev_flag = (getattr(prev, kri) if hasattr(prev, kri) else prev.get(kri)) if prev is not None else None
            if curr_flag and not prev_flag:
                out.append({"site": site, "kri": kri, "flag": curr_flag})
    return out
