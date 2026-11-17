"""Independent recount: re-derive the headline numbers straight from the raw
SDTM tables, with a separate, deliberately simple code path that does not
import mdrlens.hyslaw or mdrlens.site_kri, and check them against the
derived JSON the web page actually reads.

This is the test a clinical/medical data reviewer runs first: not "does the
code work" but "do the numbers hold up against the raw source a second,
independent way." If this test and the main metrics module ever disagree,
trust this one less than you'd like to -- it means at least one of the two
is wrong and both need a human to look.

Requires data/raw/*.rda (gitignored, fetched by scripts/fetch_data.py) and
data/derived/*.json (written by scripts/build.py). Skips with a clear
message if either is missing -- see README.md's one-command rebuild+check.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pyreadr
import pytest

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"

REQUIRED_RAW = ["dm.rda", "ae.rda", "lb.rda"]
REQUIRED_DERIVED = ["study_summary.json", "edish.json", "site_kri.json"]

_missing_raw = [f for f in REQUIRED_RAW if not (RAW_DIR / f).exists()]
_missing_derived = [f for f in REQUIRED_DERIVED if not (DERIVED_DIR / f).exists()]

pytestmark = pytest.mark.skipif(
    bool(_missing_raw or _missing_derived),
    reason=(
        "Independent recount needs both raw SDTM and derived JSON. Run: "
        "uv run python scripts/fetch_data.py && uv run python scripts/build.py "
        f"(missing raw={_missing_raw}, missing derived={_missing_derived})"
    ),
)


def _load_raw(domain: str) -> pd.DataFrame:
    result = pyreadr.read_r(str(RAW_DIR / f"{domain}.rda"))
    return result[domain]


def _recount_potential_hys_law() -> set[str]:
    """Own simple pass over raw lb.rda: no shared helpers, no x_uln(), no
    SubjectLiverProfile -- just the arithmetic, spelled out, so a bug shared
    between this test and the main module can't hide both numbers at once.
    """
    lb = _load_raw("lb")
    flagged = set()
    for usubjid, sub in lb.groupby("USUBJID"):
        alt = sub[sub["LBTESTCD"] == "ALT"]
        ast = sub[sub["LBTESTCD"] == "AST"]
        bili = sub[sub["LBTESTCD"] == "BILI"]

        def peak_ratio(frame: pd.DataFrame) -> float | None:
            ratios = []
            for result, uln in zip(frame["LBSTRESN"], frame["LBSTNRHI"]):
                if pd.isna(result) or pd.isna(uln) or uln <= 0:
                    continue
                ratios.append(result / uln)
            return max(ratios) if ratios else None

        peak_alt = peak_ratio(alt)
        peak_ast = peak_ratio(ast)
        peak_bili = peak_ratio(bili)
        candidates = [v for v in (peak_alt, peak_ast) if v is not None]
        peak_transaminase = max(candidates) if candidates else None

        if peak_transaminase is not None and peak_bili is not None:
            if peak_transaminase >= 3.0 and peak_bili >= 2.0:
                flagged.add(usubjid)
    return flagged


def _recount_site_ae_per_100_subject_days() -> dict[str, float]:
    """Own simple pass over raw dm.rda + ae.rda for AE rate per site."""
    dm = _load_raw("dm")
    ae = _load_raw("ae")

    ae_counts = ae.groupby("USUBJID").size().to_dict()

    site_ae = {}
    site_exposure = {}
    for _, row in dm.iterrows():
        site = str(row["SITEID"])
        n_ae = ae_counts.get(row["USUBJID"], 0)
        start = pd.to_datetime(row["RFSTDTC"], errors="coerce")
        end = pd.to_datetime(row["RFENDTC"], errors="coerce")
        days = (end - start).days if pd.notna(start) and pd.notna(end) else 0
        days = max(days, 0)
        site_ae[site] = site_ae.get(site, 0) + n_ae
        site_exposure[site] = site_exposure.get(site, 0.0) + days

    rates = {}
    for site, total_ae in site_ae.items():
        exposure = site_exposure[site]
        rates[site] = (total_ae / exposure * 100) if exposure else 0.0
    return rates


def test_potential_hys_law_count_matches_derived_json():
    independent_flagged = _recount_potential_hys_law()

    summary = json.loads((DERIVED_DIR / "study_summary.json").read_text())
    edish = json.loads((DERIVED_DIR / "edish.json").read_text())
    json_flagged = {row["usubjid"] for row in edish if row["hy_flag"]}

    assert json_flagged == independent_flagged, (
        "Hy's Law flag set from edish.json does not match an independent "
        "recount straight from lb.rda"
    )
    assert summary["n_potential_hys_law"] == len(independent_flagged)


def test_site_ae_rate_matches_derived_json():
    independent_rates = _recount_site_ae_per_100_subject_days()

    site_kri = json.loads((DERIVED_DIR / "site_kri.json").read_text())
    assert len(site_kri) == len(independent_rates)

    for row in site_kri:
        site = row["site"]
        assert site in independent_rates, f"site {site} missing from independent recount"
        assert math.isclose(
            row["ae_per_100_subject_days"], independent_rates[site], rel_tol=1e-9, abs_tol=1e-9
        ), f"site {site}: derived={row['ae_per_100_subject_days']} independent={independent_rates[site]}"


def test_site_subject_counts_match_derived_json():
    dm = _load_raw("dm")
    independent_counts = dm.groupby("SITEID").size()
    independent_counts.index = independent_counts.index.astype(str)

    site_kri = json.loads((DERIVED_DIR / "site_kri.json").read_text())
    for row in site_kri:
        assert row["n_subjects"] == int(independent_counts[row["site"]])

    assert sum(r["n_subjects"] for r in site_kri) == len(dm)
