"""Site-level key risk indicators (KRIs), RBQM-style.

RBQM = Risk-Based Quality Management, the ICH E6(R2)-era approach of
monitoring trial sites by watching a small set of quantitative KRIs (key
risk indicators) continuously, instead of relying only on periodic 100%
source-data-verification visits. The method follows Gilead-Public/gsm
(Good Statistical Monitoring) and pharmaverse/teal in spirit: compute a
rate per site, compare it to the study-wide pooled rate with limits that
account for each site's own size (see funnel.py), and flag outliers for
human review rather than auto-deciding anything.

Three KRIs, all per site (SITEID in the SDTM DM -- demographics -- domain):

1. AE reporting rate: adverse events per 100 subject-exposure-days.
   Exposure days are approximated as RFENDTC - RFSTDTC per subject (the
   DM domain's reference end/start dates) -- a real program would use the
   EX (exposure) domain's actual dosing dates, which this project does not
   load.
2. Missing-lab rate: share of LB (laboratory test results) records at the
   site with no usable numeric result (LBSTRESN is missing), out of all LB
   records collected at that site.
3. Visit out-of-window rate: share of SV (subject visits) records at the
   site that fall outside a +/- 7 day window around the study-wide median
   day for that protocol visit number -- a stand-in for a real protocol
   visit schedule, which is not published with this public dataset.

Every KRI is reported with the site's n (subjects, or records, as
appropriate) and gsm-style funnel limits (funnel.py) so a 1-subject site
and a 51-subject site are never judged by the same fixed cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .funnel import FunnelLimits, flag_outlier, funnel_limits

VISIT_WINDOW_DAYS = 7.0


@dataclass
class SiteKRI:
    site: str
    n_subjects: int
    n_ae: int
    exposure_days: float
    ae_per_100_subject_days: float
    ae_limits: FunnelLimits
    ae_flag: Optional[str]
    n_lb_records: int
    n_lb_missing: int
    missing_lab_rate: float
    missing_lab_limits: FunnelLimits
    missing_lab_flag: Optional[str]
    n_visits: int
    n_visits_oow: int
    visit_oow_rate: float
    visit_oow_limits: FunnelLimits
    visit_oow_flag: Optional[str]


def _exposure_days(dm: pd.DataFrame) -> pd.Series:
    start = pd.to_datetime(dm["RFSTDTC"], errors="coerce")
    end = pd.to_datetime(dm["RFENDTC"], errors="coerce")
    days = (end - start).dt.days.clip(lower=0)
    return days.fillna(0.0)


def _visit_expected_day(sv: pd.DataFrame, dm: pd.DataFrame) -> pd.DataFrame:
    """Attach a study-day column and each visit's study-wide median day."""
    sv = sv.merge(dm[["USUBJID", "RFSTDTC"]], on="USUBJID", how="left")
    sv_start = pd.to_datetime(sv["SVSTDTC"], errors="coerce")
    ref_start = pd.to_datetime(sv["RFSTDTC"], errors="coerce")
    sv = sv.copy()
    sv["STUDY_DAY"] = (sv_start - ref_start).dt.days
    median_day = sv.groupby("VISITNUM")["STUDY_DAY"].median().rename("EXPECTED_DAY")
    sv = sv.merge(median_day, on="VISITNUM", how="left")
    return sv


def build_site_kris(
    dm: pd.DataFrame,
    ae: pd.DataFrame,
    lb: pd.DataFrame,
    sv: pd.DataFrame,
    z_watch: float = 2.0,
    z_alarm: float = 3.0,
) -> list[SiteKRI]:
    dm = dm.copy()
    dm["EXPOSURE_DAYS"] = _exposure_days(dm)

    ae_by_subject = ae.groupby("USUBJID").size().rename("N_AE")
    dm = dm.merge(ae_by_subject, on="USUBJID", how="left")
    dm["N_AE"] = dm["N_AE"].fillna(0)

    lb_site = lb.merge(dm[["USUBJID", "SITEID"]], on="USUBJID", how="left")
    lb_site = lb_site.copy()
    lb_site["MISSING"] = lb_site["LBSTRESN"].isna()

    sv_day = _visit_expected_day(sv, dm)
    sv_day = sv_day.merge(dm[["USUBJID", "SITEID"]], on="USUBJID", how="left")
    sv_day = sv_day.copy()
    sv_day["OOW"] = (
        sv_day["STUDY_DAY"].notna()
        & sv_day["EXPECTED_DAY"].notna()
        & ((sv_day["STUDY_DAY"] - sv_day["EXPECTED_DAY"]).abs() > VISIT_WINDOW_DAYS)
    )

    # Pooled (study-wide) rates, the funnel center line for every site.
    total_subjects = len(dm)
    total_ae = dm["N_AE"].sum()
    total_exposure_days = dm["EXPOSURE_DAYS"].sum()
    pooled_ae_rate = (total_ae / total_exposure_days * 100) if total_exposure_days else 0.0

    total_lb = len(lb_site)
    total_lb_missing = lb_site["MISSING"].sum()
    pooled_missing_rate = (total_lb_missing / total_lb) if total_lb else 0.0

    total_sv = sv_day["STUDY_DAY"].notna().sum()
    total_sv_oow = sv_day["OOW"].sum()
    pooled_oow_rate = (total_sv_oow / total_sv) if total_sv else 0.0

    results = []
    for site, dm_site in dm.groupby("SITEID"):
        n_subjects = len(dm_site)
        n_ae = int(dm_site["N_AE"].sum())
        exposure_days = float(dm_site["EXPOSURE_DAYS"].sum())
        ae_rate = (n_ae / exposure_days * 100) if exposure_days else 0.0
        # exposure-day denominator, scaled to "per 100 subject-days" units,
        # funnel n uses subject-days/100 so the Poisson SE lines up with
        # the rate's own units.
        ae_n = max(exposure_days / 100.0, 1e-9)
        ae_limits = funnel_limits(n=max(int(round(ae_n)), 1), pooled_rate=pooled_ae_rate, kind="rate")
        ae_flag = flag_outlier(ae_rate, ae_limits)

        lb_this = lb_site[lb_site["SITEID"] == site]
        n_lb_records = len(lb_this)
        n_lb_missing = int(lb_this["MISSING"].sum())
        missing_rate = (n_lb_missing / n_lb_records) if n_lb_records else 0.0
        missing_limits = funnel_limits(
            n=max(n_lb_records, 1), pooled_rate=pooled_missing_rate, kind="proportion"
        )
        missing_flag = flag_outlier(missing_rate, missing_limits) if n_lb_records else None

        sv_this = sv_day[sv_day["SITEID"] == site]
        sv_this_valid = sv_this[sv_this["STUDY_DAY"].notna()]
        n_visits = len(sv_this_valid)
        n_oow = int(sv_this_valid["OOW"].sum())
        oow_rate = (n_oow / n_visits) if n_visits else 0.0
        oow_limits = funnel_limits(n=max(n_visits, 1), pooled_rate=pooled_oow_rate, kind="proportion")
        oow_flag = flag_outlier(oow_rate, oow_limits) if n_visits else None

        results.append(
            SiteKRI(
                site=str(site),
                n_subjects=n_subjects,
                n_ae=n_ae,
                exposure_days=exposure_days,
                ae_per_100_subject_days=ae_rate,
                ae_limits=ae_limits,
                ae_flag=ae_flag,
                n_lb_records=n_lb_records,
                n_lb_missing=n_lb_missing,
                missing_lab_rate=missing_rate,
                missing_lab_limits=missing_limits,
                missing_lab_flag=missing_flag,
                n_visits=n_visits,
                n_visits_oow=n_oow,
                visit_oow_rate=oow_rate,
                visit_oow_limits=oow_limits,
                visit_oow_flag=oow_flag,
            )
        )
    results.sort(key=lambda r: r.site)
    return results
