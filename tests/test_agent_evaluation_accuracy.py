from __future__ import annotations

import json
from pathlib import Path

from evaluation.dataset import load_evaluation_cases
from evaluation.evaluator import (
    AgentAccuracyEvaluator,
    load_fixture_manifest,
    load_observations_jsonl,
    write_accuracy_report,
)
from evaluation.fixtures import EvaluationFixtureResolver


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE = PROJECT_ROOT / "data" / "display_bom.db"


def _case(case_id: str):
    return next(case for case in load_evaluation_cases() if case.case_id == case_id)


def _observation(case_id, turn_index, *, intent, route, tool=None, args=None):
    calls = [] if tool is None else [{"name": tool, "arguments": args or {}, "tool_call_id": "test-1"}]
    return {
        "run_id": "run-test",
        "case_id": case_id,
        "turn_index": turn_index,
        "user_input": "test",
        "actual_intent": intent,
        "execution_path": route,
        "primary_tool": tool,
        "tool_calls": calls,
    }


def test_accuracy_evaluator_scores_perfect_fast_path_tool_call():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("BOM_READ-001")
    observation = _observation(
        "BOM_READ-001",
        1,
        intent="BOM_READ",
        route="FAST_PATH",
        tool="get_bom",
        args={"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
    )
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([observation])
    assert report.complete
    assert report.metrics["intent"]["accuracy"] == 100.0
    assert report.metrics["route"]["accuracy"] == 100.0
    assert report.metrics["tool_selection"]["accuracy"] == 100.0
    assert report.metrics["tool_arguments"]["accuracy"] == 100.0


def test_accuracy_evaluator_classifies_intent_route_and_tool_failures():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("BOM_READ-001")
    observation = _observation(
        "BOM_READ-001", 1,
        intent="LLM_FALLBACK", route="AGENT_PATH", tool=None,
    )
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([observation])
    result = report.turn_results[0]
    assert "INTENT_MISMATCH" in result.failures
    assert "ROUTE_MISMATCH" in result.failures
    assert "TOOL_SELECTION_MISMATCH" in result.failures
    assert "TOOL_ARGUMENT_MISMATCH" in result.failures


def test_macro_argument_accuracy_accepts_nested_grounded_arguments():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("REPLACE-001")
    observation = _observation(
        "REPLACE-001",
        1,
        intent="PHASE3_CHANGE",
        route="DETERMINISTIC_MACRO",
        tool="analyze_design_change_candidates",
        args={
            "request": {"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
            "actions": [{"action_type": "REPLACE", "target_name": fixtures["MATERIAL_NAME_A"]}],
        },
    )
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([observation])
    assert report.metrics["tool_arguments"]["accuracy"] == 100.0


def test_macro_argument_accuracy_requires_requested_quantity():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("QUANTITY_CHANGE-001")
    good = _observation(
        "QUANTITY_CHANGE-001",
        1,
        intent="PHASE3_CHANGE",
        route="DETERMINISTIC_MACRO",
        tool="analyze_design_change_candidates",
        args={
            "request": {"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
            "actions": [{"action_type": "QUANTITY_CHANGE", "target_name": fixtures["MATERIAL_A"], "new_quantity": 2.0}],
        },
    )
    bad = json.loads(json.dumps(good))
    bad["tool_calls"][0]["arguments"]["actions"][0]["new_quantity"] = 7
    assert AgentAccuracyEvaluator([case], fixtures).evaluate([good]).metrics["tool_arguments"]["accuracy"] == 100.0
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([bad])
    assert report.metrics["tool_arguments"]["accuracy"] == 0.0
    assert "TOOL_ARGUMENT_MISMATCH" in report.turn_results[0].failures


def test_context_quantity_get_bom_checks_inherited_model_and_plant():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("CONTEXT-001")
    observations = [
        _observation(
            "CONTEXT-001", 1, intent="BOM_READ", route="FAST_PATH", tool="get_bom",
            args={"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
        ),
        _observation(
            "CONTEXT-001", 2, intent="CURRENT_BOM_QUANTITY", route="FAST_PATH", tool="get_bom",
            args={"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
        ),
    ]
    report = AgentAccuracyEvaluator([case], fixtures).evaluate(observations)
    assert report.complete
    assert report.metrics["tool_arguments"]["accuracy"] == 100.0


def test_accuracy_report_marks_missing_observations_without_inventing_scores():
    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("CONTEXT-001")
    first = _observation(
        "CONTEXT-001", 1, intent="BOM_READ", route="FAST_PATH", tool="get_bom",
        args={"version_code": fixtures["MODEL_A"], "plant_code": fixtures["PLANT_A"]},
    )
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([first])
    assert not report.complete
    assert report.missing_observations == ["CONTEXT-001#2"]
    assert report.evaluated_turn_count == 1


def test_accuracy_jsonl_manifest_and_report_io(tmp_path):
    obs = tmp_path / "obs.jsonl"
    obs.write_text(json.dumps({"case_id": "CHAT-001", "turn_index": 1}) + "\n", encoding="utf-8")
    manifest = tmp_path / "obs.manifest.json"
    manifest.write_text(json.dumps({"fixtures": {"MODEL_A": "M1"}}), encoding="utf-8")
    assert load_observations_jsonl(obs)[0]["case_id"] == "CHAT-001"
    assert load_fixture_manifest(manifest)["MODEL_A"] == "M1"

    fixtures = EvaluationFixtureResolver(DATABASE).resolve().values
    case = _case("CHAT-001")
    row = _observation("CHAT-001", 1, intent="CHAT", route="FAST_PATH", tool=None)
    report = AgentAccuracyEvaluator([case], fixtures).evaluate([row])
    target = write_accuracy_report(report, tmp_path / "report.json")
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["metrics"]["intent"]["accuracy"] == 100.0
