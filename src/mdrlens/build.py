"""Build every derived JSON file the static HTML page reads, from raw SDTM.

Run via `scripts/build.py` (thin CLI wrapper) after `scripts/fetch_data.py`.
Nothing here talks to the network; it only reads data/raw/*.rda and writes
data/derived/*.json.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyreadr

from .cuts import (
    CYCLE_EPOCH,
    LAB_EXCURSION_X_ULN,
    build_cut_calendar,
    current_cut_index,
    cycle_window_start_index,
    diff_ae,
    diff_hy_flags,
    diff_lab_excursions,
    diff_site_flags,
    enrollment_curve,
    filter_to_cut,
    review_meeting_cuts,
)
from .dataquality import build_data_quality
from .funnel import funnel_curve
from .hyslaw import PHL_BILI_X_ULN, PHL_TRANSAMINASE_X_ULN, build_liver_profiles
from .lineage import PRIMARY_LINEAGE, lineage_table
from .site_kri import build_site_kris
from .timeline import build_patient_timeline

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"
WEB_DIR = ROOT / "web"


def _load(domain: str) -> pd.DataFrame:
    path = RAW_DIR / f"{domain}.rda"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `uv run python scripts/fetch_data.py` first"
        )
    result = pyreadr.read_r(str(path))
    return result[domain]


def load_all() -> dict[str, pd.DataFrame]:
    return {d: _load(d) for d in ("dm", "ae", "lb", "sv", "ds")}


def _clean(obj: Any) -> Any:
    """Make dataclasses / numpy / pandas scalars JSON-serializable."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _clean(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if hasattr(obj, "item"):  # numpy scalar
        return _clean(obj.item())
    return obj


def _write_json(name: str, data: Any) -> Path:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    path = DERIVED_DIR / name
    path.write_text(json.dumps(_clean(data), indent=2, default=str) + "\n")
    return path


def pick_protagonist(liver_profiles, ae: pd.DataFrame) -> str:
    """Pick the one gold patient: prefer a potential Hy's Law subject with
    the richest story (most AEs among the flagged subjects), else fall back
    to whichever subject in the whole study has the most AEs recorded.
    """
    flagged = [p for p in liver_profiles if p.hy_flag]
    ae_counts = ae.groupby("USUBJID").size()
    if flagged:
        flagged_sorted = sorted(
            flagged, key=lambda p: ae_counts.get(p.usubjid, 0), reverse=True
        )
        return flagged_sorted[0].usubjid
    return ae_counts.sort_values(ascending=False).index[0]


def build_edish(dm: pd.DataFrame, lb: pd.DataFrame, protagonist: str | None):
    profiles = build_liver_profiles(lb, subjects=dm["USUBJID"].tolist())
    site_by_subject = dm.set_index("USUBJID")["SITEID"]
    out = []
    for p in profiles:
        out.append(
            {
                "usubjid": p.usubjid,
                "site": str(site_by_subject.get(p.usubjid, "")),
                "peak_alt_xuln": p.peak_alt_xuln,
                "peak_ast_xuln": p.peak_ast_xuln,
                "peak_transaminase_xuln": p.peak_transaminase_xuln,
                "peak_bili_xuln": p.peak_bili_xuln,
                "hy_flag": p.hy_flag,
                "protagonist": p.usubjid == protagonist,
            }
        )
    return out, profiles


def build_ae_events(ae: pd.DataFrame, dm: pd.DataFrame) -> list[dict]:
    site_by_subject = dm.set_index("USUBJID")["SITEID"]
    out = []
    for _, r in ae.iterrows():
        out.append(
            {
                "usubjid": r["USUBJID"],
                "site": str(site_by_subject.get(r["USUBJID"], "")),
                "term": r["AETERM"],
                "body_system": r["AEBODSYS"],
                "severity": r["AESEV"],
                "serious": r["AESER"] == "Y",
                "outcome": r.get("AEOUT"),
                "start_day": None if pd.isna(r["AESTDY"]) else float(r["AESTDY"]),
                "end_day": None if pd.isna(r["AEENDY"]) else float(r["AEENDY"]),
            }
        )
    return out


def build_funnel_curves(site_kris) -> dict:
    """Smooth funnel-band curves for each KRI, for the site view's funnel
    plots. Reuses each site's own `.center` (the pooled, study-wide rate
    stored on every site's limits) rather than recomputing it, so the
    curve and the per-site dots are guaranteed to agree.
    """
    if not site_kris:
        return {}
    exposure_ns = [max(int(round(s.exposure_days / 100.0)), 1) for s in site_kris]
    lb_ns = [max(s.n_lb_records, 1) for s in site_kris]
    visit_ns = [max(s.n_visits, 1) for s in site_kris]

    def with_x(curve: list[dict], scale: float) -> list[dict]:
        for row in curve:
            row["x"] = row["n"] * scale
        return curve

    return {
        "ae": {
            "pooled_rate": site_kris[0].ae_limits.center,
            "kind": "rate",
            "x_label": "exposure days at site",
            "curve": with_x(
                funnel_curve(site_kris[0].ae_limits.center, "rate", max(exposure_ns), n_min=min(exposure_ns)),
                100.0,
            ),
        },
        "missing_lab": {
            "pooled_rate": site_kris[0].missing_lab_limits.center,
            "kind": "proportion",
            "x_label": "lab records at site",
            "curve": with_x(
                funnel_curve(
                    site_kris[0].missing_lab_limits.center, "proportion", max(lb_ns), n_min=min(lb_ns)
                ),
                1.0,
            ),
        },
        "visit_oow": {
            "pooled_rate": site_kris[0].visit_oow_limits.center,
            "kind": "proportion",
            "x_label": "visits evaluated at site",
            "curve": with_x(
                funnel_curve(
                    site_kris[0].visit_oow_limits.center, "proportion", max(visit_ns), n_min=min(visit_ns)
                ),
                1.0,
            ),
        },
    }


def build_study_summary(
    dm: pd.DataFrame,
    ae: pd.DataFrame,
    lb: pd.DataFrame,
    sv: pd.DataFrame,
    ds: pd.DataFrame,
    liver_profiles,
    protagonist: str,
) -> dict:
    n_hy_flag = sum(1 for p in liver_profiles if p.hy_flag)
    return {
        "n_subjects": int(len(dm)),
        "n_sites": int(dm["SITEID"].nunique()),
        "n_ae": int(len(ae)),
        "n_lb": int(len(lb)),
        "n_sv": int(len(sv)),
        "n_ds": int(len(ds)),
        "n_potential_hys_law": int(n_hy_flag),
        "hys_law_transaminase_threshold_x_uln": PHL_TRANSAMINASE_X_ULN,
        "hys_law_bili_threshold_x_uln": PHL_BILI_X_ULN,
        "protagonist_usubjid": protagonist,
        "source": "pharmaverse/pharmaversesdtm CDISC pilot study (Apache-2.0)",
    }


CUT_DETAIL_CAP = 15


def _ae_detail(ae: pd.DataFrame, keys: list[tuple]) -> list[dict]:
    out = []
    for usubjid, aeseq in keys:
        match = ae[(ae["USUBJID"] == usubjid) & (ae["AESEQ"] == aeseq)]
        if match.empty:
            continue
        row = match.iloc[0]
        out.append(
            {
                "usubjid": usubjid,
                "term": row["AETERM"],
                "day": None if pd.isna(row["AESTDY"]) else float(row["AESTDY"]),
            }
        )
    return out


def _lab_excursion_detail(lb: pd.DataFrame, keys: list[tuple]) -> list[dict]:
    from .uln import x_uln

    out = []
    for usubjid, lbseq in keys:
        match = lb[(lb["USUBJID"] == usubjid) & (lb["LBSEQ"] == lbseq)]
        if match.empty:
            continue
        row = match.iloc[0]
        out.append(
            {
                "usubjid": usubjid,
                "test": row["LBTESTCD"],
                "day": None if pd.isna(row["LBDY"]) else float(row["LBDY"]),
                "x_uln": round(x_uln(row["LBSTRESN"], row["LBSTNRHI"]) or 0.0, 2),
            }
        )
    return out


def build_study_in_flight(
    dm: pd.DataFrame,
    ae: pd.DataFrame,
    lb: pd.DataFrame,
    sv: pd.DataFrame,
    ds: pd.DataFrame,
    run_date: dt.date | None = None,
) -> dict:
    """The "live study simulator": this completed public study (see
    README), replayed by deterministic monthly data cuts to show the kind
    of screen a Real-Time Visual Analytics dashboard provides -- advancing
    to First Patient In, cohort-style milestones, and a "what changed
    since the last cut" view. Labeled on screen plainly as a simulator
    built on one completed public study, replayed by data cut.

    Per PA direction 2026-11-17 (blocker 2), the full cut list (cut 1 =
    First Patient In, through the final cut) is always built below and
    stays fully reachable via the stepper, but the auto-selected "current"
    cut only cycles over the window from the 25% enrollment milestone
    through the final cut -- so the cut a first-time visitor actually
    lands on is never the near-empty cut right at First Patient In.
    """
    if run_date is None:
        run_date = dt.datetime.now(dt.timezone.utc).date()

    cal = build_cut_calendar(dm, ae, lb, sv, ds)
    cuts = cal["cuts"]
    enrollment = enrollment_curve(dm, cuts)
    reviews = review_meeting_cuts(enrollment)
    cycle_start_index = cycle_window_start_index(cuts, reviews, start_threshold=0.25)
    cycle_length = len(cuts) - cycle_start_index
    cycle_index = current_cut_index(cycle_length, run_date)
    idx = cycle_start_index + cycle_index

    per_cut = []
    prev_filtered = None
    prev_hy_flagged: set[str] = set()
    prev_site_kris: list = []
    for i, cut_date in enumerate(cuts):
        filtered = filter_to_cut(dm, ae, lb, sv, ds, cut_date)
        profiles = build_liver_profiles(filtered["lb"], subjects=filtered["dm"]["USUBJID"].tolist())
        hy_flagged = {p.usubjid for p in profiles if p.hy_flag}
        site_kris = (
            build_site_kris(filtered["dm"], filtered["ae"], filtered["lb"], filtered["sv"])
            if len(filtered["dm"])
            else []
        )
        n_sites_flagged = sum(1 for s in site_kris if s.ae_flag or s.missing_lab_flag or s.visit_oow_flag)

        what_changed = None
        if i > 0:
            new_ae_keys = diff_ae(prev_filtered["ae"], filtered["ae"])
            new_lab_keys = diff_lab_excursions(prev_filtered["lb"], filtered["lb"], x_uln_threshold=LAB_EXCURSION_X_ULN)
            newly_hy = diff_hy_flags(prev_hy_flagged, hy_flagged)
            newly_flagged_sites = diff_site_flags(prev_site_kris, site_kris)
            what_changed = {
                "n_new_ae": len(new_ae_keys),
                "new_ae": _ae_detail(filtered["ae"], new_ae_keys[:CUT_DETAIL_CAP]),
                "n_new_lab_excursions": len(new_lab_keys),
                "new_lab_excursions": _lab_excursion_detail(filtered["lb"], new_lab_keys[:CUT_DETAIL_CAP]),
                "newly_hy_flagged": sorted(newly_hy),
                "newly_flagged_sites": newly_flagged_sites[:CUT_DETAIL_CAP],
            }

        per_cut.append(
            {
                "cut": cut_date.isoformat(),
                "index": i,
                "n_subjects": int(len(filtered["dm"])),
                "n_ae": int(len(filtered["ae"])),
                "n_lb": int(len(filtered["lb"])),
                "n_potential_hys_law": len(hy_flagged),
                "n_sites_flagged": n_sites_flagged,
                "what_changed": what_changed,
            }
        )

        prev_filtered = filtered
        prev_hy_flagged = hy_flagged
        prev_site_kris = site_kris

    return {
        "cycle_epoch": CYCLE_EPOCH.isoformat(),
        "run_date": run_date.isoformat(),
        "last_refresh_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "first_patient_in": cal["first_patient_in"].isoformat(),
        "replay_window_end": cal["replay_window_end"].isoformat(),
        "n_cuts": len(cuts),
        "cycle_start_index": cycle_start_index,
        "cycle_length": cycle_length,
        "current_cut_index": idx,
        "current_cut": cuts[idx].isoformat(),
        "cycle_restarted": cycle_index == 0,
        "enrollment_curve": enrollment,
        "review_meeting_cuts": reviews,
        "per_cut": per_cut,
        "lab_excursion_x_uln_threshold": LAB_EXCURSION_X_ULN,
    }


def main() -> None:
    data = load_all()
    dm, ae, lb, sv, ds = data["dm"], data["ae"], data["lb"], data["sv"], data["ds"]

    edish_preview, liver_profiles = build_edish(dm, lb, None)
    protagonist = pick_protagonist(liver_profiles, ae)
    edish, liver_profiles = build_edish(dm, lb, protagonist)

    site_kris = build_site_kris(dm, ae, lb, sv)
    funnel_curves = build_funnel_curves(site_kris)
    dq = build_data_quality(dm, ae, lb, sv, ds)
    timeline = build_patient_timeline(protagonist, dm, ae, lb, sv, ds)
    ae_events = build_ae_events(ae, dm)
    summary = build_study_summary(dm, ae, lb, sv, ds, liver_profiles, protagonist)
    study_in_flight = build_study_in_flight(dm, ae, lb, sv, ds)
    lineage = lineage_table(PRIMARY_LINEAGE)

    written = [
        _write_json("edish.json", edish),
        _write_json("site_kri.json", site_kris),
        _write_json("site_kri_funnel.json", funnel_curves),
        _write_json("data_quality.json", dq),
        _write_json("patient_timeline.json", timeline),
        _write_json("ae_events.json", ae_events),
        _write_json("study_summary.json", summary),
        _write_json("study_in_flight.json", study_in_flight),
        _write_json("lineage.json", lineage),
    ]
    for p in written:
        print(f"wrote {p.relative_to(ROOT)}")

    n_flagged_sites = sum(
        1
        for s in site_kris
        if s.ae_flag or s.missing_lab_flag or s.visit_oow_flag
    )
    print(f"protagonist: {protagonist}")
    print(f"potential Hy's Law subjects: {summary['n_potential_hys_law']} / {summary['n_subjects']}")
    print(f"sites flagged on at least one KRI: {n_flagged_sites} / {len(site_kris)}")
    print(
        f"study in flight: {study_in_flight['n_cuts']} cuts, FPI {study_in_flight['first_patient_in']}, "
        f"current cut {study_in_flight['current_cut']} (index {study_in_flight['current_cut_index']})"
    )

    pack_web_data()


def pack_web_data() -> Path:
    """Bundle every derived JSON into web/data.js as one `window.MDR_DATA`
    object, loaded by index.html via a plain relative <script src>. This is
    what lets the page be a genuinely offline, double-click-to-open file:
    fetch() of local JSON is blocked by same-origin rules under file://,
    but a <script src="data.js"> is not.
    """
    bundle = {}
    for name in [
        "edish",
        "site_kri",
        "site_kri_funnel",
        "data_quality",
        "patient_timeline",
        "ae_events",
        "study_summary",
        "study_in_flight",
        "lineage",
    ]:
        path = DERIVED_DIR / f"{name}.json"
        bundle[name] = json.loads(path.read_text())

    # Live registry snapshot: written by scripts/fetch_registry.py, which
    # talks to the network (this module never does). Bundled if present so
    # the static page can show it; if it hasn't been fetched yet (e.g. a
    # bare clone that only ran scripts/build.py), the registry section's
    # own JS renders an explicit "not fetched yet" state instead of KeyError.
    registry_path = DERIVED_DIR / "registry_summary.json"
    if registry_path.exists():
        bundle["registry_summary"] = json.loads(registry_path.read_text())
    else:
        bundle["registry_summary"] = None
        print(f"NOTE: {registry_path.relative_to(ROOT)} not found -- run scripts/fetch_registry.py. "
              "Bundling registry_summary=null so the page still builds.")

    # Reusable-template demo: written by scripts/build_second_study.py,
    # a one-time proof of mdrlens.studyconfig's reusable template, not part
    # of the daily refresh (see that script's docstring). Bundled the same
    # optional way as the registry above: if a bare clone hasn't run it
    # yet, §09's own JS renders an explicit "not generated yet" state.
    for name in ["second_study_summary", "second_study_labs", "second_study_lineage"]:
        path = DERIVED_DIR / f"{name}.json"
        if path.exists():
            bundle[name] = json.loads(path.read_text())
        else:
            bundle[name] = None
    if bundle["second_study_summary"] is None:
        print("NOTE: data/derived/second_study_*.json not found -- run "
              "scripts/fetch_second_study.py && scripts/build_second_study.py. "
              "Bundling second_study_*=null so the page still builds.")

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEB_DIR / "data.js"
    out_path.write_text(
        "// Generated by scripts/build.py from data/derived/*.json. Do not hand-edit.\n"
        "window.MDR_DATA = " + json.dumps(bundle, indent=2) + ";\n"
    )
    print(f"wrote {out_path.relative_to(ROOT)}")
    return out_path


if __name__ == "__main__":
    main()
