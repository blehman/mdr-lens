"""Build every derived JSON file the static HTML page reads, from raw SDTM.

Run via `scripts/build.py` (thin CLI wrapper) after `scripts/fetch_data.py`.
Nothing here talks to the network; it only reads data/raw/*.rda and writes
data/derived/*.json.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyreadr

from .dataquality import build_data_quality
from .funnel import funnel_curve
from .hyslaw import PHL_BILI_X_ULN, PHL_TRANSAMINASE_X_ULN, build_liver_profiles
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

    written = [
        _write_json("edish.json", edish),
        _write_json("site_kri.json", site_kris),
        _write_json("site_kri_funnel.json", funnel_curves),
        _write_json("data_quality.json", dq),
        _write_json("patient_timeline.json", timeline),
        _write_json("ae_events.json", ae_events),
        _write_json("study_summary.json", summary),
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
    ]:
        path = DERIVED_DIR / f"{name}.json"
        bundle[name] = json.loads(path.read_text())

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
