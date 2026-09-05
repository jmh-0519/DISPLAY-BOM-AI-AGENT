from __future__ import annotations

from pathlib import Path


QUICK_TEST_FILES: tuple[str, ...] = (
    "tests/test_domain_intent_router.py",
    "tests/test_current_turn_intent.py",
    "tests/test_entity_parser_regression.py",
    "tests/test_graph_gateway.py",
    "tests/test_fast_path_nodes.py",
    "tests/test_deterministic_macro_dispatch.py",
    "tests/test_add_macro_dispatch.py",
    "tests/test_macro_target_resolution.py",
    "tests/test_bom_agent_router.py",
    "tests/test_bom_agent_node.py",
    "tests/test_bom_agent_graph.py",
    "tests/test_candidate_public_projection.py",
    "tests/test_candidate_ranking_policy.py",
    "tests/test_analysis_finalizer.py",
    "tests/test_deterministic_finalizer.py",
    "tests/test_rule_engine.py",
    "tests/test_query_normalizer.py",
    "tests/test_design_change_contract.py",
)

EVALUATION_TEST_FILES: tuple[str, ...] = (
    "tests/test_agent_evaluation_dataset.py",
    "tests/test_agent_evaluation_accuracy.py",
    "tests/test_agent_evaluation_runtime_observation.py",
    "tests/test_agent_evaluation_safety.py",
    "tests/test_agent_evaluation_performance.py",
    "tests/test_agent_evaluation_triage.py",
    "tests/test_evaluation_quality_gate.py",
    "tests/test_evaluation_quality_gate_contract.py",
    "tests/test_agent_intent_accuracy_regression.py",
    "tests/test_agent_workflow_accuracy_regression.py",
    "tests/test_macro_routing_accuracy_regression.py",
)

CORE_EXCLUDED_FILES = frozenset(
    EVALUATION_TEST_FILES
    + (
        "tests/test_observability.py",
        "tests/test_performance_profiler.py",
        "tests/test_prompt_budget_profiler.py",
        "tests/test_prompt_profiling_mock_safety.py",
    )
)


def _all_test_files(project_root: Path) -> tuple[str, ...]:
    return tuple(
        path.relative_to(project_root).as_posix()
        for path in sorted((project_root / "tests").glob("test_*.py"))
    )


def get_suite_files(project_root: Path, suite: str) -> tuple[str, ...]:
    normalized = suite.strip().lower()
    if normalized == "quick":
        return QUICK_TEST_FILES
    if normalized == "evaluation":
        return EVALUATION_TEST_FILES
    if normalized == "core":
        return tuple(path for path in _all_test_files(project_root) if path not in CORE_EXCLUDED_FILES)
    if normalized == "full":
        return ()
    raise ValueError(
        f"Unknown test suite: {suite}. Use one of: quick, core, evaluation, full"
    )
