"""ClinicalTrials.gov API v2 query construction, response parsing, and
aggregation for the live-registry view.

Kept deliberately network-free (the HTTP calls live in
scripts/fetch_registry.py) so query shape and response parsing can be
exercised by tests/test_registry.py against fixture JSON, without
depending on the network or on today's live counts.

Source: https://clinicaltrials.gov/api/v2/studies (official public API,
no key required, no rate-limit published; scripts/fetch_registry.py
self-limits to <=1 request/second and backs off on HTTP 429).

Query shape verified against the live API 2026-11-17 (PA direction,
superseding an earlier draft that used query.spons): query.lead -- not
query.spons, which also matches collaborators, not just the lead sponsor
-- for "Hoffmann-La Roche" and "Genentech" (indexed on the registry as
"Genentech, Inc."), filtered to Phase 1 or Phase 2 and the four
actively-enrolling-or-running statuses below, returned 92 and 33 studies
respectively (~125 combined). Those counts move daily and are NOT
asserted by any test -- only the query parameters and the response schema
are.

This module -- and every on-screen view built from it -- makes NO
statement about Roche's or Genentech's internal development pipeline. It
reflects only what sponsors have put on the public registry, as of
whenever it was fetched, and says so on screen.
"""

from __future__ import annotations

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

LEAD_SPONSORS = ["Hoffmann-La Roche", "Genentech"]

ACTIVE_STATUSES = [
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
]

PHASES = ["PHASE1", "PHASE2"]

# Fix 4 (PA direction 2026-11-17): the registry's own enum values are the
# raw strings above. A study can be registered in BOTH Phase 1 and Phase 2
# at once ("Phase 1/2" studies are common for early-phase oncology, for
# example): phase_bucket_key() below folds that into one explicit bucket,
# "PHASE1_PHASE2", counted once -- never double-counted across the PHASE1
# and PHASE2 buckets, and never silently collapsed into just one of them.
# PHASE_LABELS gives the plain-English legend text ("Phase 1" / "Phase 2" /
# "Phase 1/2") so no screen ever shows a raw enum.
PHASE_LABELS = {"PHASE1": "Phase 1", "PHASE2": "Phase 2", "PHASE1_PHASE2": "Phase 1/2"}


def phase_bucket_key(phases: list[str]) -> str:
    """One bucket key per study for the phase legend/chart: a study
    registered in both Phase 1 and Phase 2 becomes "PHASE1_PHASE2" (counted
    once, as "Phase 1/2"), never PHASE1 AND PHASE2 separately. A study
    registered in neither (shouldn't happen given this project's own query
    filters to Phase 1 or Phase 2 only, but handled rather than assumed
    away) falls into "UNKNOWN".
    """
    present = set(phases or []) & {"PHASE1", "PHASE2"}
    if present == {"PHASE1", "PHASE2"}:
        return "PHASE1_PHASE2"
    if present == {"PHASE1"}:
        return "PHASE1"
    if present == {"PHASE2"}:
        return "PHASE2"
    return "UNKNOWN"

FIELDS = [
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "StartDate",
    "PrimaryCompletionDate",
    "LeadSponsorName",
    "Condition",
    "ConditionMeshTerm",
    "ConditionAncestorTerm",
]

PAGE_SIZE = 100
MAX_RECORDS_PER_SPONSOR = 2000  # safety cap; live counts are ~33-92 each as of 2026-11-17
MIN_SECONDS_BETWEEN_REQUESTS = 1.0

# Fixed, documented MeSH-ancestor -> therapeutic-area-style bucket mapping.
# The registry itself has no therapeutic-area field (PA direction
# 2026-11-17), so every study is bucketed by matching its
# derivedSection.conditionBrowseModule.ancestors (broad MeSH tree terms)
# against this ordered list, first match wins. A study whose ancestors
# match none of these falls into "Other (MeSH present)" -- never a guess
# at a category -- and a study with no MeSH terms *at all* falls into its
# own explicit "No MeSH category" bucket.
MESH_CATEGORY_PRIORITY: list[tuple[str, str]] = [
    ("Neoplasms", "Oncology"),
    ("Immune System Diseases", "Immunology"),
    ("Infections", "Infectious Disease"),
    ("Nervous System Diseases", "Neurology"),
    ("Mental Disorders", "Psychiatry"),
    ("Eye Diseases", "Ophthalmology"),
    ("Cardiovascular Diseases", "Cardiovascular"),
    ("Respiratory Tract Diseases", "Respiratory"),
    ("Skin Diseases", "Dermatology"),
    ("Digestive System Diseases", "Gastroenterology"),
    ("Endocrine System Diseases", "Metabolic / Endocrine"),
    ("Nutritional and Metabolic Diseases", "Metabolic / Endocrine"),
    ("Musculoskeletal Diseases", "Musculoskeletal"),
    ("Hemic and Lymphatic Diseases", "Hematology"),
    ("Urogenital Diseases", "Urogenital / Renal"),
    ("Genetic Diseases, Inborn", "Genetic / Rare Disease"),
    ("Congenital, Hereditary, and Neonatal Diseases and Abnormalities", "Genetic / Rare Disease"),
    ("Wounds and Injuries", "Injury / Wounds"),
]
NO_MESH_BUCKET = "No MeSH category"
OTHER_MESH_BUCKET = "Other (MeSH present)"


def build_query_params(lead_sponsor: str, page_token: str | None = None) -> dict:
    filter_expr = (
        "AREA[Phase](" + " OR ".join(PHASES) + ") AND "
        "AREA[OverallStatus](" + " OR ".join(ACTIVE_STATUSES) + ")"
    )
    params = {
        "query.lead": lead_sponsor,
        "filter.advanced": filter_expr,
        "fields": ",".join(FIELDS),
        "pageSize": str(PAGE_SIZE),
        "countTotal": "true",
    }
    if page_token:
        params["pageToken"] = page_token
    return params


def parse_study(study: dict) -> dict:
    """Pull the fields this project uses out of one v2 'study' object,
    tolerating any of them being absent (the registry does not guarantee
    every module is populated for every study).
    """
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {})
    conditions = proto.get("conditionsModule", {})
    design = proto.get("designModule", {})
    derived = study.get("derivedSection", {})
    condition_browse = derived.get("conditionBrowseModule", {})

    return {
        "nct_id": ident.get("nctId"),
        "brief_title": ident.get("briefTitle"),
        "overall_status": status.get("overallStatus"),
        "start_date": status.get("startDateStruct", {}).get("date"),
        "primary_completion_date": status.get("primaryCompletionDateStruct", {}).get("date"),
        "lead_sponsor": sponsor.get("leadSponsor", {}).get("name"),
        "phases": design.get("phases", []),
        "conditions": conditions.get("conditions", []),
        "mesh_terms": [m.get("term") for m in condition_browse.get("meshes", []) if m.get("term")],
        "ancestor_terms": [a.get("term") for a in condition_browse.get("ancestors", []) if a.get("term")],
    }


def categorize_study(study: dict) -> str:
    if not study.get("mesh_terms") and not study.get("ancestor_terms"):
        return NO_MESH_BUCKET
    ancestor_set = set(study.get("ancestor_terms", [])) | set(study.get("mesh_terms", []))
    for term, bucket in MESH_CATEGORY_PRIORITY:
        if term in ancestor_set:
            return bucket
    return OTHER_MESH_BUCKET


def aggregate(studies: list[dict]) -> dict:
    status_phase_counts: dict[str, dict[str, int]] = {}
    mesh_categories: dict[str, int] = {}
    timeline = []

    for s in studies:
        status = s.get("overall_status") or "UNKNOWN"
        phase_key = phase_bucket_key(s.get("phases"))
        bucket = status_phase_counts.setdefault(status, {})
        bucket[phase_key] = bucket.get(phase_key, 0) + 1

        category = categorize_study(s)
        mesh_categories[category] = mesh_categories.get(category, 0) + 1

        if status in ("RECRUITING", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"):
            if s.get("start_date") or s.get("primary_completion_date"):
                timeline.append(
                    {
                        "nct_id": s.get("nct_id"),
                        "brief_title": s.get("brief_title"),
                        "overall_status": status,
                        "phases": s.get("phases") or [],
                        "lead_sponsor": s.get("lead_sponsor"),
                        "start_date": s.get("start_date"),
                        "primary_completion_date": s.get("primary_completion_date"),
                    }
                )

    timeline.sort(key=lambda r: (r["start_date"] or "9999"))
    return {
        "total_studies": len(studies),
        "status_phase_counts": status_phase_counts,
        "mesh_categories": mesh_categories,
        "timeline_recruiting_or_active": timeline,
    }
