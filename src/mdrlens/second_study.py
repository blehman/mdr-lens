"""Reusable-template demo: proves mdrlens.studyconfig.SECOND_STUDY plugs a
separately packaged SDTM (Study Data Tabulation Model) dataset into this
project's labs & liver-panel method -- the same mdrlens.uln.peak_x_uln_by_test
primitive mdrlens.hyslaw uses for the primary study's eDISH view -- on that
dataset's own DM (demographics) and LB (labs) domains only. SECOND_STUDY is
pharmaversesdtm's "metabolic" subset: the same CDISC pilot study's own 5
subjects already in the primary DM (same STUDYID, USUBJID, AGE/SEX/RFSTDTC),
not a second study.

Run via `scripts/fetch_second_study.py` then `scripts/build_second_study.py`
(same two-step fetch-then-build shape as the primary study's
scripts/fetch_data.py + scripts/build.py). Unlike the primary study, this
is a static, one-time demo of the template, not something
.github/workflows/refresh.yml refreshes -- see that file and README's
"Live data" section for which views are actually live.
"""

from __future__ import annotations

import pandas as pd

from .lineage import LineageEntry, lineage_table
from .studyconfig import StudyConfig
from .uln import peak_x_uln_by_test


def build_second_study_labs(dm: pd.DataFrame, lb: pd.DataFrame, config: StudyConfig) -> list[dict]:
    """Peak x ULN per subject per liver-panel test this study's LB domain
    actually carries (config.liver_panel_tests), with each row labeled by
    site for display -- the labs and liver-panel view, nothing else."""
    site_by_subject = dm.set_index("USUBJID")["SITEID"]
    subjects = dm["USUBJID"].tolist()
    rows = peak_x_uln_by_test(lb, subjects, list(config.liver_panel_tests))
    for r in rows:
        r["site"] = str(site_by_subject.get(r["usubjid"], ""))
    rows.sort(key=lambda r: (r["usubjid"], r["test"]))
    return rows


def build_second_study_summary(dm: pd.DataFrame, lb: pd.DataFrame, config: StudyConfig) -> dict:
    return {
        "study_key": config.study_key,
        "display_name": config.display_name,
        "source_repo": config.source_repo,
        "source_commit": config.source_commit,
        "domains_used": dict(config.domain_files),
        "liver_panel_tests": list(config.liver_panel_tests),
        "n_subjects": int(len(dm)),
        "n_lb": int(len(lb)),
        "enables": config.enables,
    }


def build_second_study_lineage(config: StudyConfig) -> list[dict]:
    """The same LineageEntry schema mdrlens.lineage uses for the primary
    study's page, applied to this config's two domains -- proving the
    lineage schema itself, not just the labs arithmetic, is reusable."""
    entries = (
        LineageEntry(
            metric_id=f"{config.study_key}.summary",
            label=f"Reusable-template demo summary ({config.display_name})",
            page_section="template",
            domains=tuple(config.domain_files.keys()),
            variables=("USUBJID", "SITEID"),
            join="DM.USUBJID is this study's primary key, same as the primary study's lineage entries.",
            notes=config.enables,
        ),
        LineageEntry(
            metric_id=f"{config.study_key}.labs",
            label=f"Peak x ULN by liver-panel test ({', '.join(config.liver_panel_tests)})",
            page_section="template",
            domains=("lb", "dm"),
            variables=("USUBJID", "LBTESTCD", "LBSTRESN", "LBSTNRHI", "SITEID"),
            join="LB.USUBJID -> DM.USUBJID to attach SITEID, same join shape as the primary study's eDISH entry -- computed by the identical mdrlens.uln.peak_x_uln_by_test primitive.",
        ),
    )
    return lineage_table(entries)
