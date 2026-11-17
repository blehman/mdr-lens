"""Pin mdrlens.lineage's PRIMARY_LINEAGE mapping: this is the test that
keeps "every number on the page traces back to its source SDTM domain and
variables" true as the code changes, independent of any generated file
(these assertions run against the registry in code, not data/derived/
lineage.json, so they always run -- no raw/derived data required).
"""

from __future__ import annotations

from mdrlens.lineage import (
    DOMAIN_SOURCE_KIND,
    PRIMARY_LINEAGE,
    SDTM_DOMAINS,
    LineageEntry,
    lineage_table,
)

# Every SDTM variable this project's own code actually reads, per domain
# (see mdrlens.build, mdrlens.cuts, mdrlens.dataquality, mdrlens.hyslaw,
# mdrlens.site_kri, mdrlens.timeline) -- the ground truth a lineage entry's
# `variables` must be a subset of for that domain.
KNOWN_COLUMNS = {
    "dm": {"USUBJID", "SITEID", "ARM", "AGE", "SEX", "RFSTDTC", "RFENDTC"},
    "ae": {"USUBJID", "AESEQ", "AETERM", "AEBODSYS", "AESEV", "AESER", "AEOUT", "AESTDTC", "AESTDY", "AEENDY"},
    "lb": {"USUBJID", "LBSEQ", "LBTESTCD", "LBSTRESN", "LBSTNRHI", "LBDTC", "LBDY", "LBBLFL", "LBSTRESU"},
    "sv": {"USUBJID", "VISITNUM", "VISIT", "SVSTDTC"},
    "ds": {"USUBJID", "DSSEQ", "DSDECOD", "DSCAT", "DSSTDTC", "DSSTDY"},
}

# Variables that aren't SDTM domain columns at all (the registry entry's
# ClinicalTrials.gov API v2 field names), kept separate from KNOWN_COLUMNS
# so a real SDTM variable typo can't hide behind this allowance.
NON_SDTM_VARIABLES = {
    "NCTId", "OverallStatus", "Phase", "StartDate", "PrimaryCompletionDate",
    "LeadSponsorName", "ConditionMeshTerm", "ConditionAncestorTerm",
}

EXPECTED_PAGE_SECTIONS = {"hero", "inflight", "registry", "patient", "study", "sites", "quality"}


def test_every_domain_is_a_real_sdtm_domain_or_the_non_sdtm_registry():
    for entry in PRIMARY_LINEAGE:
        for d in entry.domains:
            assert d in SDTM_DOMAINS, f"{entry.metric_id}: unknown domain {d!r}"
    registry_entries = [e for e in PRIMARY_LINEAGE if e.metric_id == "registry"]
    assert len(registry_entries) == 1
    assert registry_entries[0].domains == ()


def test_every_variable_is_a_known_column_of_its_domain():
    for entry in PRIMARY_LINEAGE:
        if not entry.domains:
            assert set(entry.variables) <= NON_SDTM_VARIABLES, (
                f"{entry.metric_id}: non-SDTM entry uses an unrecognized variable"
            )
            continue
        known = set().union(*(KNOWN_COLUMNS[d] for d in entry.domains))
        unknown = set(entry.variables) - known
        assert not unknown, f"{entry.metric_id}: variables {unknown} not a known column of {entry.domains}"


def test_every_entry_has_a_nonempty_join_description():
    for entry in PRIMARY_LINEAGE:
        assert entry.join, f"{entry.metric_id}: join description is empty"


def test_usubjid_anchors_every_sdtm_entry():
    """Every SDTM-backed metric's join must name USUBJID -- the key every
    domain joins on -- somewhere in its join description."""
    for entry in PRIMARY_LINEAGE:
        if entry.domains:
            assert "USUBJID" in entry.join, f"{entry.metric_id}: join doesn't mention USUBJID"


def test_crf_vs_non_crf_labeling_matches_readme_convention():
    """DM, AE, SV, DS are CRF (site-entered); LB is non-CRF (central-lab
    feed) -- the same split README's 'CRF vs. non-CRF data' section uses."""
    assert DOMAIN_SOURCE_KIND["lb"].startswith("non-CRF")
    for d in ("dm", "ae", "sv", "ds"):
        assert DOMAIN_SOURCE_KIND[d].startswith("CRF")


def test_patient_timeline_entry_documents_the_crf_non_crf_join():
    """The one-patient timeline (§03) is where this project's CRF (AE/SV/DS)
    and non-CRF (LB) data are shown joined on one axis -- pin that its
    lineage entry actually says so, not just lists both domain groups."""
    entry = next(e for e in PRIMARY_LINEAGE if e.metric_id == "patient_timeline")
    assert "lb" in entry.domains and "ae" in entry.domains
    assert "non-CRF" in entry.join or "CRF" in entry.join


def test_source_kinds_derived_correctly():
    entry = next(e for e in PRIMARY_LINEAGE if e.metric_id == "edish")
    assert entry.source_kinds() == tuple(DOMAIN_SOURCE_KIND[d] for d in entry.domains)


def test_every_page_section_with_a_number_has_at_least_one_lineage_entry():
    covered = {e.page_section for e in PRIMARY_LINEAGE}
    missing = EXPECTED_PAGE_SECTIONS - covered
    assert not missing, f"page sections with no lineage entry: {missing}"


def test_lineage_table_is_json_serializable_and_round_trips():
    import json

    rows = lineage_table(PRIMARY_LINEAGE)
    text = json.dumps(rows)
    reloaded = json.loads(text)
    assert len(reloaded) == len(PRIMARY_LINEAGE)
    assert reloaded[0]["metric_id"] == PRIMARY_LINEAGE[0].metric_id
    assert isinstance(reloaded[0]["source_kinds"], list)


def test_metric_ids_are_unique():
    ids = [e.metric_id for e in PRIMARY_LINEAGE]
    assert len(ids) == len(set(ids))


def test_lineage_entry_is_a_frozen_dataclass_instance():
    entry = PRIMARY_LINEAGE[0]
    assert isinstance(entry, LineageEntry)
