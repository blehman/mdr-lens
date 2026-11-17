"""Pin mdrlens.studyconfig: the reusable StudyConfig template, PRIMARY_STUDY
(this project's existing five-domain replay) and SECOND_STUDY (the second
SDTM subset that proves the template plugs in). Pure unit tests against
the config objects in code -- no raw/derived data required, always runs.
"""

from __future__ import annotations

from mdrlens.studyconfig import PHARMAVERSESDTM_COMMIT, PRIMARY_STUDY, SECOND_STUDY, StudyConfig


def test_primary_and_second_study_share_the_same_pinned_commit():
    """Both configs -- and scripts/fetch_data.py -- must stay pinned
    together: a study config naming a different commit than the one this
    project's raw-data fetch script uses would silently drift."""
    assert PRIMARY_STUDY.source_commit == PHARMAVERSESDTM_COMMIT
    assert SECOND_STUDY.source_commit == PHARMAVERSESDTM_COMMIT
    assert PHARMAVERSESDTM_COMMIT == "7ec53ea88dfe1c168f9efbef59233c4426813b89"


def test_primary_study_uses_all_five_domains():
    assert set(PRIMARY_STUDY.domain_files.keys()) == {"dm", "ae", "lb", "sv", "ds"}
    assert PRIMARY_STUDY.domain_files["dm"] == "dm"  # no suffix on the primary study's own files


def test_second_study_plugs_in_demographics_and_labs_only():
    """SECOND_STUDY proves the template on labs + liver views only: DM and
    LB, nothing else -- no AE/SV/DS, matching mdrlens.second_study's scope."""
    assert set(SECOND_STUDY.domain_files.keys()) == {"dm", "lb"}
    assert SECOND_STUDY.domain_files["dm"] == "dm_metabolic"
    assert SECOND_STUDY.domain_files["lb"] == "lb_metabolic"


def test_second_study_liver_panel_tests_are_a_subset_of_the_primary_studys():
    assert set(SECOND_STUDY.liver_panel_tests) <= set(PRIMARY_STUDY.liver_panel_tests)
    assert set(SECOND_STUDY.liver_panel_tests) == {"AST", "ALP", "GGT"}


def test_crf_and_non_crf_domains_partition_each_configs_domains():
    for config in (PRIMARY_STUDY, SECOND_STUDY):
        declared = set(config.domain_files.keys())
        labeled = set(config.crf_domains) | set(config.non_crf_domains)
        assert labeled == declared, f"{config.study_key}: CRF/non-CRF labels don't cover every domain used"
        assert not (set(config.crf_domains) & set(config.non_crf_domains))


def test_lb_is_always_non_crf():
    for config in (PRIMARY_STUDY, SECOND_STUDY):
        if "lb" in config.domain_files:
            assert "lb" in config.non_crf_domains


def test_enables_text_is_positive_not_a_gap_statement():
    """Describes what the template enables, never what's missing -- see
    the project's own wording rule (no 'lack'/'missing'/'shortfall' framing
    about the data)."""
    for config in (PRIMARY_STUDY, SECOND_STUDY):
        lowered = config.enables.lower()
        for banned in ("lack", "shortfall", "gap", "missing"):
            assert banned not in lowered, f"{config.study_key}.enables uses banned word {banned!r}"
        assert len(config.enables) > 20


def test_domain_url_matches_fetch_data_py_pattern():
    url = SECOND_STUDY.domain_url("lb")
    assert url == (
        f"https://raw.githubusercontent.com/pharmaverse/pharmaversesdtm/"
        f"{PHARMAVERSESDTM_COMMIT}/data/lb_metabolic.rda"
    )


def test_study_config_is_frozen():
    cfg = StudyConfig(
        study_key="x", display_name="x", source_repo="x", source_commit="x",
        domain_files={"dm": "dm"}, liver_panel_tests=(), crf_domains=("dm",),
        non_crf_domains=(), enables="x",
    )
    import dataclasses
    assert dataclasses.is_dataclass(cfg)
    try:
        cfg.study_key = "y"  # type: ignore[misc]
        assert False, "StudyConfig should be frozen"
    except dataclasses.FrozenInstanceError:
        pass
