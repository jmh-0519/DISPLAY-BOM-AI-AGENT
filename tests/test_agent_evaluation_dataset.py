from __future__ import annotations

from collections import Counter

import pytest

from evaluation.dataset import CURRENT_DATASET_PATH, dataset_summary, load_evaluation_cases, render_case


def test_agent_evaluation_dataset_is_current_release_dataset():
    cases = load_evaluation_cases()
    summary = dataset_summary(cases)
    assert CURRENT_DATASET_PATH.name == "agent_eval_v2.jsonl"
    assert summary["case_count"] == 56
    assert summary["turn_count"] == 69
    assert len({case.case_id for case in cases}) == 56


def test_agent_evaluation_dataset_covers_all_current_categories():
    cases = load_evaluation_cases()
    categories = {case.category for case in cases}
    assert categories == {
        "CHAT", "BOM_READ", "WHERE_USED", "CONTEXT", "REPLACE", "ADD", "DELETE",
        "QUANTITY_CHANGE", "SAFETY", "KNOWLEDGE", "ANALYTICS", "COMPOSITION",
    }


def test_agent_evaluation_dataset_covers_all_current_execution_paths():
    summary = dataset_summary(load_evaluation_cases())
    paths = summary["by_execution_path"]
    for name in (
        "FAST_PATH", "DETERMINISTIC_MACRO", "AGENT_PATH", "KNOWLEDGE_PATH",
        "TEXT_TO_SQL_PATH", "READ_ONLY_COMPOSITION", "WORKFLOW_COMPOSITION", "SCOPE_CONFLICT",
    ):
        assert paths[name] >= 1


def test_agent_evaluation_dataset_contains_clarification_and_plant_selection():
    summary = dataset_summary(load_evaluation_cases())
    interactions = summary["by_interaction"]
    assert interactions["CLARIFY"] >= 3
    assert interactions["PLANT_SELECT"] >= 3
    assert interactions["BLOCK"] >= 2


def test_add_unspecified_cases_require_no_target_guess():
    cases = load_evaluation_cases()
    add_cases = [case for case in cases if case.category == "ADD"]
    ambiguous = [
        turn for case in add_cases for turn in case.turns
        if turn.expected.interaction == "CLARIFY"
    ]
    assert ambiguous
    assert all("NO_TARGET_GUESS" in turn.expected.safety_assertions for turn in ambiguous)


def test_candidate_ranking_policy_is_explicit():
    cases = load_evaluation_cases()
    policies = Counter(
        turn.expected.status_policy
        for case in cases
        for turn in case.turns
        if turn.expected.status_policy
    )
    assert policies["PASS_RANK_ONLY"] >= 8
    assert policies["NO_RANKING"] >= 2


def test_render_case_requires_all_dynamic_fixtures():
    case = next(case for case in load_evaluation_cases() if case.fixture_requirements)
    with pytest.raises(KeyError):
        render_case(case, {})

    fixtures = {name: f"VALUE_{name}" for name in case.fixture_requirements}
    rendered = render_case(case, fixtures)
    assert rendered
    assert not any("{{" in query for query in rendered)


def test_current_dataset_contains_v4_runtime_coverage_cases():
    cases = load_evaluation_cases()
    assert {case.case_id for case in cases}.issuperset({
        "KNOWLEDGE-001", "ANALYTICS-001", "COMPOSITION-001",
        "COMPOSITION-002", "COMPOSITION-003", "CONTEXT-007",
    })


def test_context_case_covers_scope_conflict_workflow_reference_and_read_precedence():
    case = next(case for case in load_evaluation_cases() if case.case_id == "CONTEXT-007")
    paths = [turn.expected.execution_path for turn in case.turns]
    assert paths == [
        "FAST_PATH", "WORKFLOW_COMPOSITION", "FAST_PATH",
        "SCOPE_CONFLICT", "AGENT_PATH", "FAST_PATH",
    ]
    assert "CONTEXT_MUST_NOT_MUTATE_WORKFLOW" in case.turns[3].expected.safety_assertions


def test_expected_semantics_match_current_read_only_analysis_contract():
    cases = {case.case_id: case for case in load_evaluation_cases()}
    assert cases["COMPOSITION-002"].turns[0].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert cases["COMPOSITION-003"].turns[0].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    context = cases["CONTEXT-007"]
    assert context.turns[1].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert context.turns[3].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert context.turns[4].expected.primary_tool == "explain_design_change_analysis_session"


def test_current_dataset_summary_matches_release_evidence():
    summary = dataset_summary(load_evaluation_cases())
    assert summary["case_count"] == 56
    assert summary["turn_count"] == 69
