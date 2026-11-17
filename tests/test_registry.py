"""Tests for mdrlens.registry: query shape and response-schema parsing only
-- never live counts, which move daily (see module docstring and PA
direction 2026-11-17). All fixtures below are hand-built, shaped like the
real ClinicalTrials.gov API v2 response (verified against the live API
2026-11-17), not live data.
"""

from __future__ import annotations

from mdrlens.registry import (
    ACTIVE_STATUSES,
    NO_MESH_BUCKET,
    OTHER_MESH_BUCKET,
    PHASE_LABELS,
    PHASES,
    aggregate,
    build_query_params,
    categorize_study,
    parse_study,
    phase_bucket_key,
)


def test_build_query_params_uses_lead_not_spons():
    params = build_query_params("Hoffmann-La Roche")
    assert params["query.lead"] == "Hoffmann-La Roche"
    assert "query.spons" not in params


def test_build_query_params_filter_includes_all_phases_and_statuses():
    params = build_query_params("Genentech")
    filt = params["filter.advanced"]
    for ph in PHASES:
        assert ph in filt
    for st in ACTIVE_STATUSES:
        assert st in filt
    assert filt.startswith("AREA[Phase](")


def test_build_query_params_carries_page_token():
    params = build_query_params("Genentech", page_token="abc123")
    assert params["pageToken"] == "abc123"


def _study_fixture(**overrides) -> dict:
    base = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A Study"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "startDateStruct": {"date": "2024-01-15"},
                "primaryCompletionDateStruct": {"date": "2026-06-30"},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Hoffmann-La Roche"}},
            "conditionsModule": {"conditions": ["Breast Cancer"]},
            "designModule": {"phases": ["PHASE1"]},
        },
        "derivedSection": {
            "conditionBrowseModule": {
                "meshes": [{"term": "Breast Neoplasms"}],
                "ancestors": [{"term": "Neoplasms"}, {"term": "Breast Diseases"}],
            }
        },
    }
    for path, value in overrides.items():
        base[path] = value
    return base


def test_parse_study_extracts_expected_fields():
    parsed = parse_study(_study_fixture())
    assert parsed["nct_id"] == "NCT00000001"
    assert parsed["overall_status"] == "RECRUITING"
    assert parsed["start_date"] == "2024-01-15"
    assert parsed["primary_completion_date"] == "2026-06-30"
    assert parsed["lead_sponsor"] == "Hoffmann-La Roche"
    assert parsed["phases"] == ["PHASE1"]
    assert parsed["mesh_terms"] == ["Breast Neoplasms"]
    assert parsed["ancestor_terms"] == ["Neoplasms", "Breast Diseases"]


def test_parse_study_tolerates_missing_modules():
    parsed = parse_study({"protocolSection": {}, "derivedSection": {}})
    assert parsed["nct_id"] is None
    assert parsed["mesh_terms"] == []
    assert parsed["ancestor_terms"] == []


def test_categorize_study_oncology_from_ancestor():
    study = parse_study(_study_fixture())
    assert categorize_study(study) == "Oncology"


def test_categorize_study_no_mesh_terms_gets_explicit_bucket():
    study = {"mesh_terms": [], "ancestor_terms": []}
    assert categorize_study(study) == NO_MESH_BUCKET


def test_categorize_study_unmatched_mesh_terms_get_other_not_a_guess():
    study = {"mesh_terms": ["Some Obscure Condition"], "ancestor_terms": ["Some Obscure Tree"]}
    assert categorize_study(study) == OTHER_MESH_BUCKET


def test_aggregate_status_phase_counts_and_mesh_categories():
    studies = [
        parse_study(_study_fixture()),
        parse_study(
            _study_fixture(
                protocolSection={
                    "identificationModule": {"nctId": "NCT00000002", "briefTitle": "B Study"},
                    "statusModule": {
                        "overallStatus": "ACTIVE_NOT_RECRUITING",
                        "startDateStruct": {"date": "2023-05-01"},
                        "primaryCompletionDateStruct": {"date": "2025-01-01"},
                    },
                    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Genentech, Inc."}},
                    "conditionsModule": {"conditions": ["Diabetes"]},
                    "designModule": {"phases": ["PHASE2"]},
                },
                derivedSection={"conditionBrowseModule": {"meshes": [], "ancestors": []}},
            )
        ),
    ]
    summary = aggregate(studies)
    assert summary["total_studies"] == 2
    assert summary["status_phase_counts"]["RECRUITING"]["PHASE1"] == 1
    assert summary["status_phase_counts"]["ACTIVE_NOT_RECRUITING"]["PHASE2"] == 1
    assert summary["mesh_categories"]["Oncology"] == 1
    assert summary["mesh_categories"][NO_MESH_BUCKET] == 1
    assert len(summary["timeline_recruiting_or_active"]) == 2


def test_phase_bucket_key_single_phases():
    assert phase_bucket_key(["PHASE1"]) == "PHASE1"
    assert phase_bucket_key(["PHASE2"]) == "PHASE2"


def test_phase_bucket_key_dual_phase_study_is_one_bucket_not_two():
    """Fix 4 (PA direction 2026-11-17): a study registered in both Phase 1
    and Phase 2 is counted once, as "PHASE1_PHASE2" ("Phase 1/2" in the
    legend) -- never double-counted into PHASE1 and PHASE2 separately, and
    never silently folded into just one of them."""
    assert phase_bucket_key(["PHASE1", "PHASE2"]) == "PHASE1_PHASE2"
    assert phase_bucket_key(["PHASE2", "PHASE1"]) == "PHASE1_PHASE2"


def test_phase_bucket_key_unknown_when_neither_phase_present():
    assert phase_bucket_key([]) == "UNKNOWN"
    assert phase_bucket_key(None) == "UNKNOWN"


def test_phase_labels_cover_every_bucket_key_with_plain_text():
    for key in ("PHASE1", "PHASE2", "PHASE1_PHASE2"):
        assert key in PHASE_LABELS
        assert PHASE_LABELS[key][0].isupper()  # "Phase 1" / "Phase 2" / "Phase 1/2", never a raw enum


def test_aggregate_dual_phase_study_counted_once_as_phase1_phase2():
    studies = [
        parse_study(
            _study_fixture(
                protocolSection={
                    "identificationModule": {"nctId": "NCT00000004", "briefTitle": "D Study"},
                    "statusModule": {
                        "overallStatus": "RECRUITING",
                        "startDateStruct": {"date": "2024-02-01"},
                        "primaryCompletionDateStruct": {"date": "2026-02-01"},
                    },
                    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Hoffmann-La Roche"}},
                    "conditionsModule": {"conditions": ["Lymphoma"]},
                    "designModule": {"phases": ["PHASE1", "PHASE2"]},
                },
            )
        ),
    ]
    summary = aggregate(studies)
    assert summary["total_studies"] == 1
    assert summary["status_phase_counts"]["RECRUITING"] == {"PHASE1_PHASE2": 1}
    assert "PHASE1" not in summary["status_phase_counts"]["RECRUITING"]
    assert "PHASE2" not in summary["status_phase_counts"]["RECRUITING"]


def test_aggregate_timeline_sorted_by_start_date():
    studies = [
        parse_study(_study_fixture()),  # 2024-01-15
        parse_study(
            _study_fixture(
                protocolSection={
                    "identificationModule": {"nctId": "NCT00000003", "briefTitle": "C Study"},
                    "statusModule": {
                        "overallStatus": "RECRUITING",
                        "startDateStruct": {"date": "2020-01-01"},
                        "primaryCompletionDateStruct": {"date": "2022-01-01"},
                    },
                    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Hoffmann-La Roche"}},
                    "conditionsModule": {"conditions": []},
                    "designModule": {"phases": ["PHASE1"]},
                }
            )
        ),
    ]
    summary = aggregate(studies)
    starts = [row["start_date"] for row in summary["timeline_recruiting_or_active"]]
    assert starts == sorted(starts)
