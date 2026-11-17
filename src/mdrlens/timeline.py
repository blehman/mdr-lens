"""One-patient timeline: AEs, lab spikes, visits, and disposition on one axis.

This is the "start with one atomic unit" view: before looking at the whole
study or all 17 sites, look at a single subject's story end to end, the way
a medical data reviewer actually reads a case. Everything is expressed as a
study day relative to that subject's RFSTDTC (reference start date, SDTM
DM domain) so adverse events (AE domain), lab results (LB domain), visits
(SV domain) and disposition events (DS domain, e.g. randomized, completed,
withdrawn) all share one timeline.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .uln import x_uln

LAB_SPIKE_X_ULN = 1.5

# The timeline's liver panel -- the only tests for which a baseline draw is
# always kept regardless of the spike threshold (see build_patient_timeline).
# Every other lab test still only appears here if it crosses the general
# spike threshold on its own, same as before.
LIVER_PANEL_TESTS = {"ALT", "AST", "BILI", "ALP", "GGT"}


def _study_day(dtc: pd.Series, ref_start: str) -> pd.Series:
    start = pd.to_datetime(ref_start, errors="coerce")
    dt = pd.to_datetime(dtc, errors="coerce")
    return (dt - start).dt.days


def build_patient_timeline(
    usubjid: str,
    dm: pd.DataFrame,
    ae: pd.DataFrame,
    lb: pd.DataFrame,
    sv: pd.DataFrame,
    ds: pd.DataFrame,
) -> Optional[dict]:
    subj = dm[dm["USUBJID"] == usubjid]
    if subj.empty:
        return None
    row = subj.iloc[0]
    ref_start = row["RFSTDTC"]

    ae_sub = ae[ae["USUBJID"] == usubjid]
    ae_events = []
    for _, r in ae_sub.iterrows():
        ae_events.append(
            {
                "term": r["AETERM"],
                "body_system": r["AEBODSYS"],
                "severity": r["AESEV"],
                "serious": r["AESER"] == "Y",
                "outcome": r.get("AEOUT"),
                "start_day": None if pd.isna(r["AESTDY"]) else float(r["AESTDY"]),
                "end_day": None if pd.isna(r["AEENDY"]) else float(r["AEENDY"]),
            }
        )

    lb_sub = lb[lb["USUBJID"] == usubjid].copy()
    lb_sub["x_uln"] = [
        x_uln(v, u) for v, u in zip(lb_sub["LBSTRESN"], lb_sub["LBSTNRHI"])
    ]
    # Always keep the baseline (LBBLFL == "Y") draw for the liver panel
    # tests this view is built around, even if a given test is below the
    # "spike" threshold -- a reviewer needs the pre-dose value to tell a
    # pre-existing abnormality from a drug-induced one, and dropping it
    # silently because it happens to read as unremarkable on its own would
    # hide exactly the context that matters (see README / the
    # patient-context note on subject 01-705-1186, whose baseline bilirubin
    # was present and already slightly high -- 1.22x ULN -- but below this
    # 1.5x threshold, so earlier versions of this view omitted the point
    # and made it look like no bilirubin was drawn before day 16 at all).
    # Scoped to the liver panel only, so this doesn't flood the view with
    # every other baseline lab (electrolytes, CBC, etc.) that was never
    # part of this story.
    is_liver_panel = lb_sub["LBTESTCD"].isin(LIVER_PANEL_TESTS)
    is_baseline = (lb_sub["LBBLFL"] == "Y") if "LBBLFL" in lb_sub.columns else False
    is_spike = lb_sub["x_uln"].notna() & (lb_sub["x_uln"] >= LAB_SPIKE_X_ULN)
    keep = is_spike | (is_baseline & is_liver_panel)
    spikes = lb_sub[lb_sub["x_uln"].notna() & keep]
    lab_spikes = []
    for _, r in spikes.iterrows():
        lab_spikes.append(
            {
                "test": r["LBTESTCD"],
                "day": None if pd.isna(r["LBDY"]) else float(r["LBDY"]),
                "x_uln": round(float(r["x_uln"]), 2),
                "value": float(r["LBSTRESN"]),
                "unit": r.get("LBSTRESU"),
                "baseline": bool(r.get("LBBLFL") == "Y"),
            }
        )

    sv_sub = sv[sv["USUBJID"] == usubjid].copy()
    sv_sub["study_day"] = _study_day(sv_sub["SVSTDTC"], ref_start)
    visits = [
        {
            "visit": r["VISIT"],
            "visitnum": float(r["VISITNUM"]) if not pd.isna(r["VISITNUM"]) else None,
            "day": None if pd.isna(r["study_day"]) else float(r["study_day"]),
        }
        for _, r in sv_sub.iterrows()
    ]

    ds_sub = ds[ds["USUBJID"] == usubjid]
    disposition = [
        {
            "event": r["DSDECOD"],
            "category": r.get("DSCAT"),
            "day": None if pd.isna(r["DSSTDY"]) else float(r["DSSTDY"]),
        }
        for _, r in ds_sub.iterrows()
    ]

    return {
        "usubjid": usubjid,
        "site": str(row["SITEID"]),
        "arm": row.get("ARM"),
        "age": None if pd.isna(row.get("AGE")) else float(row["AGE"]),
        "sex": row.get("SEX"),
        "ref_start": ref_start,
        "ae_events": sorted(ae_events, key=lambda e: (e["start_day"] is None, e["start_day"])),
        "lab_spikes": sorted(lab_spikes, key=lambda e: (e["day"] is None, e["day"])),
        "visits": sorted(visits, key=lambda e: (e["day"] is None, e["day"])),
        "disposition": sorted(disposition, key=lambda e: (e["day"] is None, e["day"])),
    }
