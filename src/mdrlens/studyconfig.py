"""StudyConfig: the reusable template that lets a second SDTM (Study Data
Tabulation Model) study plug into this project's labs & liver-panel method
(mdrlens.uln.peak_x_uln_by_test, the same primitive mdrlens.hyslaw uses for
the primary study's eDISH view) without touching that primitive at all.

A StudyConfig names which pharmaverse/pharmaversesdtm file stem backs each
canonical SDTM domain it uses (a study need not supply every domain -- see
SECOND_STUDY below, which plugs in DM and LB only), which of the five
liver-panel tests (ALT, AST, BILI, ALP, GGT) its own LB domain actually
carries, and which of its domains are CRF (case report form, site-entered)
vs. non-CRF (e.g. a central-lab feed) -- the same distinction README's
"CRF vs. non-CRF data" section and mdrlens.lineage use for the primary
study.

PRIMARY_STUDY describes this project's existing five-domain replay (§01-06).
SECOND_STUDY proves the template on pharmaversesdtm's separately packaged
metabolic-panel dataset: the same pinned commit's (see scripts/fetch_data.py)
"metabolic" demographics and labs tables, for the same 5 subjects of the
CDISC pilot study already in the primary DM (same STUDYID, same USUBJIDs,
identical AGE/SEX/RFSTDTC), packaged with their own LB domain. That dataset
plugs in DM (demographics) and LB (labs) only, enabling the labs and
liver-panel view only -- see mdrlens.second_study.
"""

from __future__ import annotations

from dataclasses import dataclass

# Mirrors scripts/fetch_data.py's PHARMAVERSESDTM_COMMIT -- both this
# module and that script pin the same upstream commit, re-pinned together
# deliberately (see that script's docstring for the re-pin command).
PHARMAVERSESDTM_COMMIT = "7ec53ea88dfe1c168f9efbef59233c4426813b89"
PHARMAVERSESDTM_REPO = "https://github.com/pharmaverse/pharmaversesdtm"


@dataclass(frozen=True)
class StudyConfig:
    study_key: str
    display_name: str
    source_repo: str
    source_commit: str
    # canonical SDTM domain code -> pharmaversesdtm file stem (without .rda)
    domain_files: dict[str, str]
    # whichever of the five liver-panel tests (ALT, AST, BILI, ALP, GGT)
    # this study's own LB domain actually carries -- a subset, since an
    # SDTM study need not run every lab test the primary study ran
    liver_panel_tests: tuple[str, ...]
    crf_domains: tuple[str, ...]
    non_crf_domains: tuple[str, ...]
    enables: str  # positive, "what this plugs in/enables" description

    def domain_url(self, domain: str, base_url: str | None = None) -> str:
        base = base_url or f"https://raw.githubusercontent.com/pharmaverse/pharmaversesdtm/{self.source_commit}/data"
        return f"{base}/{self.domain_files[domain]}.rda"


PRIMARY_STUDY = StudyConfig(
    study_key="primary",
    display_name="CDISC Pilot Project study (full replay)",
    source_repo=PHARMAVERSESDTM_REPO,
    source_commit=PHARMAVERSESDTM_COMMIT,
    domain_files={"dm": "dm", "ae": "ae", "lb": "lb", "sv": "sv", "ds": "ds"},
    liver_panel_tests=("ALT", "AST", "BILI", "ALP", "GGT"),
    crf_domains=("dm", "ae", "sv", "ds"),
    non_crf_domains=("lb",),
    enables=(
        "Every view on §01-06 of this page: the full five-domain monthly-cut "
        "replay, one-patient timeline, eDISH liver-safety screen, AE explorer, "
        "site KRIs, and data quality."
    ),
)

# Proves the template on pharmaversesdtm's separately packaged metabolic-
# panel dataset: the same 5 CDISC pilot subjects already in the primary
# DM (identical STUDYID, USUBJID, AGE/SEX/RFSTDTC -- verified against
# data/raw/dm.rda), repackaged by pharmaverse with their own LB domain.
# That LB domain carries AST, ALP and GGT from the liver panel (not ALT or
# BILI), so this config's liver_panel_tests is exactly that subset -- the
# template reports peak x ULN for whichever liver-panel tests a dataset
# actually ran, never a fabricated value for one it didn't.
SECOND_STUDY = StudyConfig(
    study_key="metabolic_demo",
    display_name="pharmaversesdtm metabolic-panel subset",
    source_repo=PHARMAVERSESDTM_REPO,
    source_commit=PHARMAVERSESDTM_COMMIT,
    domain_files={"dm": "dm_metabolic", "lb": "lb_metabolic"},
    liver_panel_tests=("AST", "ALP", "GGT"),
    crf_domains=("dm",),
    non_crf_domains=("lb",),
    enables=(
        "This same template plugs any SDTM study's demographics (DM) and "
        "labs (LB) domains into mdrlens.uln's peak-x-ULN method -- the "
        "identical arithmetic §04's eDISH view uses on the primary study. "
        "Demonstrated on pharmaversesdtm's separately packaged metabolic-"
        "panel dataset (5 CDISC pilot subjects with their own LB domain): "
        "its labs and liver-panel view, by the same peak-x-ULN method "
        "§04's eDISH view uses."
    ),
)
