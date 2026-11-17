"""Traceability / lineage registry: where every number on the page comes
from, in SDTM (Study Data Tabulation Model) terms.

This is a static, hand-maintained map -- not something computed from the
data -- because lineage is a claim about *provenance*, not a statistic:
"this view's numbers come from these domains, these variables, joined this
way" is true regardless of which data cut or which study is loaded. Each
entry below is a `LineageEntry` pinned by tests/test_lineage.py so a future
change to which column a view reads from can't drift from what this page
and docs/MDR_PLAN.md say it reads from.

CRF (case report form) vs. non-CRF labeling follows the same convention the
README's "CRF vs. non-CRF data" section already uses: DM (demographics), AE
(adverse events), SV (subject visits) and DS (disposition) are entered by a
site on a CRF; LB (laboratory test results) arrives as a central-lab feed,
i.e. non-CRF data. §02 (the live ClinicalTrials.gov registry) is not SDTM
at all -- its own entry says so explicitly rather than being left out.

`build_lineage()` writes this registry to data/derived/lineage.json (see
mdrlens.build), the machine-readable form the page's §08 Traceability
section (web/app.js renderLineage()) reads, Python call sites, and anyone
auditing this project without opening a browser.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Every domain actually used anywhere in this project (see scripts/fetch_data.py).
SDTM_DOMAINS = ("dm", "ae", "lb", "sv", "ds")

# Same convention as README's "CRF vs. non-CRF data" section: DM, AE, SV and
# DS are entered by a trial site on a case report form (CRF); LB arrives as
# a central-lab data feed (non-CRF). The registry (§02) is neither -- it is
# not an SDTM domain at all, see the "registry" entry below.
DOMAIN_SOURCE_KIND = {
    "dm": "CRF (site-entered)",
    "ae": "CRF (site-entered)",
    "sv": "CRF (site-entered)",
    "ds": "CRF (site-entered)",
    "lb": "non-CRF (central-lab feed)",
}


@dataclass(frozen=True)
class LineageEntry:
    metric_id: str
    label: str
    page_section: str  # the index.html section id this metric appears in
    domains: tuple[str, ...]  # SDTM domain codes, or () for non-SDTM sources
    variables: tuple[str, ...]  # SDTM variable names read for this metric
    join: str  # how the domains above are joined to produce this metric
    notes: str = ""

    def source_kinds(self) -> tuple[str, ...]:
        return tuple(DOMAIN_SOURCE_KIND.get(d, "n/a") for d in self.domains)


# The primary (full five-domain) study's lineage -- every number family on
# §00 (hero) through §06 of the page, plus §02's non-SDTM registry fetch.
PRIMARY_LINEAGE: tuple[LineageEntry, ...] = (
    LineageEntry(
        metric_id="hero.n_subjects",
        label="Subjects / sites (hero stats, and every per-subject or per-site count below)",
        page_section="hero",
        domains=("dm",),
        variables=("USUBJID", "SITEID"),
        join="DM.USUBJID is this project's primary key; DM.SITEID groups subjects into the 17 sites.",
    ),
    LineageEntry(
        metric_id="ae_events",
        label="Adverse events (hero stat, §04 AE explorer, §01 'what changed')",
        page_section="study",
        domains=("ae", "dm"),
        variables=("USUBJID", "AESEQ", "AETERM", "AEBODSYS", "AESEV", "AESER", "AEOUT", "AESTDTC", "AESTDY", "AEENDY"),
        join="AE.USUBJID -> DM.USUBJID (adds DM.SITEID for display); AESTDY is the study day already supplied on the SDTM record, relative to DM.RFSTDTC.",
        notes="CRF-entered (see DOMAIN_SOURCE_KIND).",
    ),
    LineageEntry(
        metric_id="edish",
        label="Liver-safety peaks & potential Hy's Law flag (§04 eDISH)",
        page_section="study",
        domains=("lb", "dm"),
        variables=("USUBJID", "LBTESTCD", "LBSTRESN", "LBSTNRHI", "SITEID"),
        join="Peak (ALT or AST) x ULN and peak BILI x ULN are computed per LB.USUBJID (mdrlens.hyslaw), then LB.USUBJID -> DM.USUBJID to attach SITEID for the chart tooltip.",
        notes="LB is a central-lab (non-CRF) feed; the Hy's Law flag itself is a lab-pattern screen, not a diagnosis (see README).",
    ),
    LineageEntry(
        metric_id="patient_timeline",
        label="One-patient timeline (§03): AEs, lab spikes, visits, disposition on one axis",
        page_section="patient",
        domains=("dm", "ae", "lb", "sv", "ds"),
        variables=("RFSTDTC", "AESTDTC", "LBDTC", "LBDY", "LBBLFL", "SVSTDTC", "VISITNUM", "VISIT", "DSDECOD", "DSSTDTC", "DSSTDY"),
        join=(
            "Every domain's own date field (AESTDTC/LBDTC/SVSTDTC/DSSTDTC) is expressed as a study "
            "day by subtracting DM.RFSTDTC, for the one USUBJID selected as protagonist -- the CRF "
            "(AE/SV/DS) and non-CRF (LB) join this project's README describes, made concrete for one subject."
        ),
    ),
    LineageEntry(
        metric_id="site_kri",
        label="Site key risk indicators (§05): AE rate, missing-lab rate, visit out-of-window rate",
        page_section="sites",
        domains=("dm", "ae", "lb", "sv"),
        variables=("SITEID", "RFSTDTC", "RFENDTC", "AESEQ", "LBSTRESN", "SVSTDTC", "VISITNUM"),
        join="AE, LB and SV each join to DM on USUBJID to attach SITEID before aggregating per site; exposure days are DM.RFENDTC - DM.RFSTDTC per subject.",
        notes="Funnel-plot control limits (mdrlens.funnel) are a derived statistic, not a lineage join, so they are not listed as a variable here.",
    ),
    LineageEntry(
        metric_id="data_quality",
        label="Data quality by domain (§06): missing required fields, duplicates, visit windows",
        page_section="quality",
        domains=("dm", "ae", "lb", "sv", "ds"),
        variables=("USUBJID", "SITEID", "ARM", "AGE", "SEX", "RFSTDTC", "AETERM", "AESTDTC", "AESEV", "AESER", "LBTESTCD", "LBSTRESN", "LBDTC", "VISITNUM", "SVSTDTC", "DSDECOD", "DSSTDTC"),
        join="Each domain is checked against its own hand-picked required-field list (mdrlens.dataquality.REQUIRED_FIELDS) and its own key fields for duplicates; visit-out-of-window joins SV to DM on USUBJID for RFSTDTC.",
    ),
    LineageEntry(
        metric_id="study_in_flight",
        label="Live study simulator (§01): per-cut counts and 'what changed since the last cut'",
        page_section="inflight",
        domains=("dm", "ae", "lb", "sv", "ds"),
        variables=("RFSTDTC", "AESTDTC", "AESEQ", "LBDTC", "LBSEQ", "LBSTRESN", "LBSTNRHI", "SVSTDTC", "DSSTDTC"),
        join=(
            "A subject is 'enrolled as of' a cut when DM.RFSTDTC <= that cut date; every other "
            "domain's own date field must also be <= the cut date for that record to appear in the "
            "cut. 'What changed' re-keys AE on (USUBJID, AESEQ) and LB excursions on (USUBJID, LBSEQ) "
            "between consecutive cuts."
        ),
    ),
    LineageEntry(
        metric_id="registry",
        label="Live public registry (§02): Roche & Genentech study counts, MeSH categories, timeline",
        page_section="registry",
        domains=(),
        variables=("NCTId", "OverallStatus", "Phase", "StartDate", "PrimaryCompletionDate", "LeadSponsorName", "ConditionMeshTerm", "ConditionAncestorTerm"),
        join="NCT ID is the registry's own primary key. This is a live fetch of the public ClinicalTrials.gov API v2 (see mdrlens.registry) -- not an SDTM domain, so no SDTM join applies.",
        notes="Public registry records only; makes no statement about Roche's or Genentech's internal pipeline (see README).",
    ),
)


def lineage_table(entries: tuple[LineageEntry, ...] = PRIMARY_LINEAGE) -> list[dict]:
    """JSON-serializable rows, each entry plus its derived `source_kinds`,
    for data/derived/lineage.json and the page's §08 Traceability table."""
    rows = []
    for e in entries:
        row = asdict(e)
        row["source_kinds"] = list(e.source_kinds())
        rows.append(row)
    return rows
