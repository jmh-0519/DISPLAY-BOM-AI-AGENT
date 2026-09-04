from evaluation.dataset import FINAL02_DATASET_PATH, dataset_summary, load_evaluation_cases


def test_final02_dataset_extends_clean_core_without_replacing_v1():
    cases = load_evaluation_cases(FINAL02_DATASET_PATH)
    summary = dataset_summary(cases)
    assert summary["case_count"] == 56
    assert summary["turn_count"] == 69
    assert {case.case_id for case in cases}.issuperset({
        "KNOWLEDGE-001",
        "ANALYTICS-001",
        "COMPOSITION-001",
        "COMPOSITION-002",
        "COMPOSITION-003",
        "CONTEXT-007",
    })


def test_final02_dataset_covers_every_current_runtime_execution_path():
    summary = dataset_summary(load_evaluation_cases(FINAL02_DATASET_PATH))
    paths = summary["by_execution_path"]
    for name in (
        "FAST_PATH",
        "DETERMINISTIC_MACRO",
        "AGENT_PATH",
        "KNOWLEDGE_PATH",
        "TEXT_TO_SQL_PATH",
        "READ_ONLY_COMPOSITION",
        "WORKFLOW_COMPOSITION",
        "SCOPE_CONFLICT",
    ):
        assert paths[name] >= 1


def test_final02_context_case_covers_scope_conflict_workflow_reference_and_read_precedence():
    case = next(
        case for case in load_evaluation_cases(FINAL02_DATASET_PATH)
        if case.case_id == "CONTEXT-007"
    )
    paths = [turn.expected.execution_path for turn in case.turns]
    assert paths == [
        "FAST_PATH",
        "WORKFLOW_COMPOSITION",
        "FAST_PATH",
        "SCOPE_CONFLICT",
        "AGENT_PATH",
        "FAST_PATH",
    ]
    assert "CONTEXT_MUST_NOT_MUTATE_WORKFLOW" in case.turns[3].expected.safety_assertions


def test_final02_expected_semantics_match_current_read_only_analysis_contract():
    cases = {case.case_id: case for case in load_evaluation_cases(FINAL02_DATASET_PATH)}

    assert cases["COMPOSITION-002"].turns[0].expected.intent == (
        "DESIGN_CHANGE_RECOMMENDATION"
    )
    assert cases["COMPOSITION-003"].turns[0].expected.intent == (
        "DESIGN_CHANGE_RECOMMENDATION"
    )
    context = cases["CONTEXT-007"]
    assert context.turns[1].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert context.turns[3].expected.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert context.turns[4].expected.primary_tool == (
        "explain_design_change_analysis_session"
    )
