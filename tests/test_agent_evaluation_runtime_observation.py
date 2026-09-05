from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from evaluation.dataset import load_evaluation_cases, render_case
from evaluation.fixtures import EvaluationFixtureResolver, REQUIRED_FIXTURES
from evaluation.observation import (
    AgentTurnObservation,
    ObservedToolCall,
    RuntimeObservationCollector,
    write_observations_jsonl,
)
from evaluation.runtime import evaluation_database_sandbox


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE = PROJECT_ROOT / "data" / "display_bom.db"


def _active_descendants(con: sqlite3.Connection, plant: str, model: str) -> set[str]:
    rows = con.execute(
        """
        WITH RECURSIVE tree(child_item_code) AS (
          SELECT child_item_code
          FROM bom_master
          WHERE plant_code=? AND parent_item_code=? AND status='ACTIVE'
            AND valid_from<=date('now')
            AND (valid_to IS NULL OR valid_to>=date('now'))
          UNION
          SELECT b.child_item_code
          FROM tree t
          JOIN bom_master b ON b.parent_item_code=t.child_item_code
          WHERE b.plant_code=? AND b.status='ACTIVE'
            AND b.valid_from<=date('now')
            AND (b.valid_to IS NULL OR b.valid_to>=date('now'))
        )
        SELECT child_item_code FROM tree
        """,
        (plant, model, plant),
    ).fetchall()
    return {str(row[0]).upper() for row in rows}


def test_dynamic_fixture_resolver_satisfies_every_dataset_requirement():
    resolved = EvaluationFixtureResolver(DATABASE).resolve()
    assert REQUIRED_FIXTURES <= set(resolved.values)

    required_by_dataset = {
        name for case in load_evaluation_cases() for name in case.fixture_requirements
    }
    assert required_by_dataset <= set(resolved.values)

    for case in load_evaluation_cases():
        rendered = render_case(case, resolved.values)
        assert len(rendered) == len(case.turns)
        assert not any("{{" in value for value in rendered)


def test_dynamic_fixture_model_a_scope_contains_required_materials_and_assy():
    values = EvaluationFixtureResolver(DATABASE).resolve().values
    with sqlite3.connect(DATABASE) as con:
        descendants = _active_descendants(con, values["PLANT_A"], values["MODEL_A"])
    assert values["MATERIAL_A"] in descendants
    assert values["MATERIAL_B"] in descendants
    assert values["ASSY_A"] in descendants
    assert values["MATERIAL_C"] not in descendants


def test_dynamic_fixture_names_are_unambiguous_inside_model_a():
    values = EvaluationFixtureResolver(DATABASE).resolve().values
    with sqlite3.connect(DATABASE) as con:
        descendants = _active_descendants(con, values["PLANT_A"], values["MODEL_A"])
        placeholders = ",".join("?" for _ in descendants)
        rows = con.execute(
            f"SELECT item_code,UPPER(item_name) FROM item_master WHERE item_code IN ({placeholders})",
            tuple(descendants),
        ).fetchall()
    names = [str(row[1] or "").upper() for row in rows]
    assert names.count(values["MATERIAL_NAME_A"].upper()) == 1
    assert names.count(values["MATERIAL_NAME_B"].upper()) == 1


def test_dynamic_fixture_invalid_codes_do_not_exist():
    values = EvaluationFixtureResolver(DATABASE).resolve().values
    with sqlite3.connect(DATABASE) as con:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT item_code FROM item_master WHERE item_code IN (?,?)",
                (values["INVALID_MODEL"], values["INVALID_ITEM"]),
            )
        }
    assert not existing


def test_evaluation_database_sandbox_is_disposable_and_restores_environment(tmp_path):
    source = tmp_path / "source.db"
    source.write_bytes(b"original")
    old_value = os.environ.get("BOM_SQLITE_PATH")
    os.environ["BOM_SQLITE_PATH"] = "before-eval.db"
    try:
        with evaluation_database_sandbox(source, work_dir=tmp_path) as sandbox:
            assert sandbox.runtime_path != source
            assert sandbox.runtime_path.read_bytes() == b"original"
            assert os.environ["BOM_SQLITE_PATH"] == str(sandbox.runtime_path)
            sandbox.runtime_path.write_bytes(b"changed")
        assert source.read_bytes() == b"original"
        assert os.environ["BOM_SQLITE_PATH"] == "before-eval.db"
        assert not sandbox.runtime_path.exists()
    finally:
        if old_value is None:
            os.environ.pop("BOM_SQLITE_PATH", None)
        else:
            os.environ["BOM_SQLITE_PATH"] = old_value


def test_observation_extracts_structured_tool_calls_without_framework_dependency():
    class Message:
        tool_calls = [{
            "name": "get_bom",
            "args": {"plant_code": "P01", "product_id": "MODEL"},
            "id": "graph-fast-bom-1",
        }]

    calls = RuntimeObservationCollector.extract_tool_calls([Message()])
    assert calls == [
        ObservedToolCall(
            name="get_bom",
            arguments={"plant_code": "P01", "product_id": "MODEL"},
            tool_call_id="graph-fast-bom-1",
        )
    ]


def test_observation_route_event_maps_to_hybrid_execution_path():
    events = [{
        "name": "graph.gateway.route",
        "metadata": {"route": "macro_analyze"},
    }]
    route = RuntimeObservationCollector._gateway_route(events)
    assert route == "macro_analyze"

    fallback = RuntimeObservationCollector._fallback_execution_path(
        [ObservedToolCall("get_bom", {}, "graph-fast-bom-1")],
        {"timings": [], "llm_usage": {"total": 0}},
    )
    assert fallback == "FAST_PATH"


def test_observation_jsonl_contains_metric_fields(tmp_path):
    observation = AgentTurnObservation(
        run_id="run-1",
        case_id="CHAT-001",
        turn_index=1,
        thread_id="thread-1",
        user_input="안녕하세요",
        normalized_user_input="안녕하세요",
        actual_intent="CHAT",
        gateway_route="fast_chat",
        execution_path="FAST_PATH",
        interaction_hint="ANSWER",
        latency_ms=12.34,
        llm_call_count=0,
        tool_calls=[],
    )
    target = write_observations_jsonl([observation], tmp_path / "observations.jsonl")
    text = target.read_text(encoding="utf-8")
    assert '"case_id": "CHAT-001"' in text
    assert '"execution_path": "FAST_PATH"' in text
    assert '"tool_call_count": 0' in text


def test_observation_maps_current_runtime_routes_for_evaluation():
    from evaluation.observation import ROUTE_TO_EXECUTION_PATH

    assert ROUTE_TO_EXECUTION_PATH["fast_knowledge"] == "KNOWLEDGE_PATH"
    assert ROUTE_TO_EXECUTION_PATH["fast_text_to_sql"] == "TEXT_TO_SQL_PATH"
    assert ROUTE_TO_EXECUTION_PATH["composition_plan"] == "READ_ONLY_COMPOSITION"
    assert ROUTE_TO_EXECUTION_PATH["workflow_composition_plan"] == "WORKFLOW_COMPOSITION"
    assert ROUTE_TO_EXECUTION_PATH["scope_conflict"] == "SCOPE_CONFLICT"


def test_scope_conflict_interaction_hint_is_block_without_tool_or_llm_guessing():
    hint = RuntimeObservationCollector._interaction_hint(
        execution_path="SCOPE_CONFLICT",
        tool_calls=[],
        plant_options=[],
        workflow_before={"current_step": "ANALYSIS_READY", "analysis_id": "ANA-1"},
        workflow_after={"current_step": "ANALYSIS_READY", "analysis_id": "ANA-1"},
        error=None,
    )
    assert hint == "BLOCK"


def test_observation_intent_ignores_active_workflow_for_explicit_bom_read(tmp_path):
    from agents.domain_intent_router import DomainIntentRouter

    class Gateway:
        router = DomainIntentRouter()

    class Agent:
        gateway = Gateway()

    collector = RuntimeObservationCollector(
        Agent(), profile_path=tmp_path / "profile.jsonl"
    )
    workflow = {"current_step": "ANALYSIS_READY", "analysis_id": "ANA-1"}
    assert (
        collector._resolve_intent(
            "LTA550HR01-001 P01 BOM 조회해줘", workflow
        )
        == "BOM_READ"
    )


def test_delete_pending_slot_is_classified_as_clarify():
    hint = RuntimeObservationCollector._interaction_hint(
        execution_path="AGENT_PATH",
        tool_calls=[],
        plant_options=[],
        workflow_before={"pending_delete_target_request": None},
        workflow_after={
            "pending_delete_target_request": {
                "version_code": "LTA400HR01-001",
                "plant_code": "P02",
            }
        },
        error=None,
    )
    assert hint == "CLARIFY"
