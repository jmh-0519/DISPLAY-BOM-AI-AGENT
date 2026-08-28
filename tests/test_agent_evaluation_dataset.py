from __future__ import annotations

from collections import Counter

import pytest

from evaluation.dataset import dataset_summary, load_evaluation_cases, render_case


def test_agent_evaluation_dataset_is_valid_and_has_50_cases():
    cases = load_evaluation_cases()
    assert len(cases) == 50
    assert len({case.case_id for case in cases}) == 50


def test_agent_evaluation_dataset_covers_all_core_categories():
    cases = load_evaluation_cases()
    categories = {case.category for case in cases}
    assert categories == {
        "CHAT",
        "BOM_READ",
        "WHERE_USED",
        "CONTEXT",
        "REPLACE",
        "ADD",
        "DELETE",
        "QUANTITY_CHANGE",
        "SAFETY",
    }


def test_agent_evaluation_dataset_covers_hybrid_execution_paths():
    summary = dataset_summary(load_evaluation_cases())
    paths = summary["by_execution_path"]
    assert paths["FAST_PATH"] >= 10
    assert paths["DETERMINISTIC_MACRO"] >= 10
    assert paths["AGENT_PATH"] >= 10


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
        turn
        for case in add_cases
        for turn in case.turns
        if turn.expected.interaction == "CLARIFY"
    ]
    assert ambiguous
    assert all(
        "NO_TARGET_GUESS" in turn.expected.safety_assertions
        for turn in ambiguous
    )


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
