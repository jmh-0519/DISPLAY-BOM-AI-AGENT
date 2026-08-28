from __future__ import annotations

from evaluation.triage import triage_accuracy_report


def _result(case_id, failures, *, intent=("CHAT", "CHAT"), route=("FAST_PATH", "FAST_PATH"), tool=(None, None), args=(None, None, None)):
    arg_expected, arg_actual, arg_detail = args
    return {
        "case_id": case_id,
        "turn_index": 1,
        "user_input": "test",
        "failures": failures,
        "checks": {
            "intent": {"eligible": True, "passed": intent[0] == intent[1], "expected": intent[0], "actual": intent[1]},
            "route": {"eligible": True, "passed": route[0] == route[1], "expected": route[0], "actual": route[1]},
            "tool_selection": {"eligible": True, "passed": tool[0] == tool[1], "expected": tool[0], "actual": tool[1]},
            "tool_arguments": {"eligible": arg_expected is not None, "passed": (arg_expected == arg_actual) if arg_expected is not None else None, "expected": arg_expected, "actual": arg_actual, "detail": arg_detail},
        },
    }


def test_intent_mismatch_is_root_even_with_downstream_failures():
    report = {"evaluated_turn_count": 1, "turn_results": [_result(
        "REPLACE-001",
        ["INTENT_MISMATCH", "ROUTE_MISMATCH", "TOOL_SELECTION_MISMATCH"],
        intent=("DESIGN_CHANGE", "LLM_FALLBACK"),
        route=("DETERMINISTIC_MACRO", "AGENT_PATH"),
        tool=("analyze_design_change_candidates", "search_material"),
    )]}
    triage = triage_accuracy_report(report)
    assert triage["rows"][0]["primary_cause"] == "INTENT_ROOT"


def test_route_and_tool_mismatch_are_collapsed_as_cascade():
    report = {"evaluated_turn_count": 1, "turn_results": [_result(
        "DELETE-001",
        ["ROUTE_MISMATCH", "TOOL_SELECTION_MISMATCH", "TOOL_ARGUMENT_MISMATCH"],
        route=("DETERMINISTIC_MACRO", "AGENT_PATH"),
        tool=("analyze_design_change_candidates", "get_bom"),
        args=("grounded business arguments", {"x": 1}, "Expected primary tool was not observed"),
    )]}
    triage = triage_accuracy_report(report)
    row = triage["rows"][0]
    assert row["primary_cause"] == "ROUTE_TOOL_CASCADE"
    assert any("cascade-only" in note for note in row["notes"])


def test_argument_mismatch_is_root_when_expected_tool_was_used():
    report = {"evaluated_turn_count": 1, "turn_results": [_result(
        "ADD-001",
        ["TOOL_ARGUMENT_MISMATCH"],
        route=("DETERMINISTIC_MACRO", "DETERMINISTIC_MACRO"),
        tool=("analyze_design_change_candidates", "analyze_design_change_candidates"),
        args=([{"label": "MODEL"}], {"plant": "P01"}, "Missing argument evidence: MODEL"),
    )]}
    triage = triage_accuracy_report(report)
    assert triage["rows"][0]["primary_cause"] == "TOOL_ARGUMENT_ROOT"


def test_tool_selection_is_root_when_route_matches():
    report = {"evaluated_turn_count": 1, "turn_results": [_result(
        "BOM_READ-001",
        ["TOOL_SELECTION_MISMATCH"],
        tool=("get_bom", "search_product"),
    )]}
    triage = triage_accuracy_report(report)
    assert triage["rows"][0]["primary_cause"] == "TOOL_SELECTION_ROOT"


def test_summary_separates_semantic_and_architecture_roots():
    report = {
        "evaluated_turn_count": 3,
        "turn_results": [
            _result("REPLACE-001", ["INTENT_MISMATCH"], intent=("DESIGN_CHANGE", "LLM_FALLBACK")),
            _result("DELETE-001", ["ROUTE_MISMATCH"], route=("DETERMINISTIC_MACRO", "AGENT_PATH")),
            _result("ADD-001", ["TOOL_ARGUMENT_MISMATCH"], tool=("analyze_design_change_candidates", "analyze_design_change_candidates"), args=([{"label": "MODEL"}], {}, "Missing argument evidence: MODEL")),
        ],
    }
    triage = triage_accuracy_report(report)
    assert triage["failed_turn_count"] == 3
    assert triage["semantic_root_failed_turns"] == 2
    assert triage["architecture_root_failed_turns"] == 1
    assert triage["by_category"] == {"ADD": 1, "DELETE": 1, "REPLACE": 1}
