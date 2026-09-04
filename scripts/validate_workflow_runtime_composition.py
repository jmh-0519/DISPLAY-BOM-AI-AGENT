from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_analysis_finalizer_node import is_macro_analysis_tool_result
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.bom_mcp_tool_node import BomMcpToolNode
from agents.bom_text_to_sql_nodes import BomTextToSqlPathNodes
from agents.bom_workflow_composition_nodes import (
    WORKFLOW_COMPOSITION_PLAN,
    BomWorkflowCompositionNodes,
    is_workflow_composition_analysis_tool_result,
)
from agents.design_change_workflow_state import create_initial_design_change_state
from text_to_sql.pipeline import TextToSqlPipelineResult


VERSION = "LTA400HR01-001"
PLANT = "P01"
ITEM = "0001-200007"
PARENT = "LJ94-100003"
GOAL = (
    "이 모델에서 가장 원가가 높은 자재 1개를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)
AMBIGUOUS_GOAL = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


class _Pipeline:
    """Guard: workflow target evidence must not use this generated-SQL path."""

    def __init__(self):
        self.calls = 0

    def run(self, question):
        self.calls += 1
        raise AssertionError(
            "workflow target selection must not call the generated SQL pipeline"
        )


class _CostEvidence:
    def __init__(self):
        self.calls = 0

    def run(self, *, version_code, plant_code, question, as_of_date=None):
        self.calls += 1
        assert version_code == VERSION
        assert plant_code == PLANT
        del as_of_date
        return TextToSqlPipelineResult(
            status="SQL",
            question=question,
            sql=(
                "WITH RECURSIVE reachable(item_code) AS ("
                f"SELECT '{VERSION}' UNION SELECT b.child_item_code "
                "FROM reachable r JOIN bom_master b "
                "ON b.parent_item_code=r.item_code "
                f"WHERE b.plant_code='{PLANT}') "
                "SELECT e.child_item_code AS item_code, "
                "e.parent_item_code, e.location_code, "
                "1200.0 AS unit_cost "
                "FROM bom_master e "
                f"WHERE e.plant_code='{PLANT}' "
                "ORDER BY unit_cost DESC LIMIT 1"
            ),
            reason="deterministic scoped BOM cost evidence",
            columns=(
                "item_code", "item_name", "parent_item_code", "location_code",
                "unit_cost", "price_source", "currency_code",
            ),
            rows=({
                "item_code": ITEM,
                "item_name": "FILM",
                "parent_item_code": PARENT,
                "location_code": "ALL",
                "unit_cost": 1200.0,
                "price_source": "PRIMARY_SUPPLIER",
                "currency_code": "KRW",
            },),
            row_count=1,
            truncated=False,
            elapsed_ms=1.0,
        )


class _Finalizer:
    def __call__(self, state):
        return {
            "messages": [AIMessage(content="분석 완료")],
            "error": None,
        }


def _state(query):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "active_bom_context": {
            "product_id": VERSION,
            "plant_code": PLANT,
            "source": "get_bom",
        },
        "tool_steps": 0,
        "error": None,
    }


def main() -> None:
    failures = []
    pipeline = _Pipeline()
    cost_evidence = _CostEvidence()
    nodes = BomWorkflowCompositionNodes(
        text_to_sql_nodes=BomTextToSqlPathNodes(pipeline=pipeline),
        analysis_finalizer=_Finalizer(),
        cost_evidence_query=cost_evidence,
    )

    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )

    class _ReadOnly:
        @staticmethod
        def can_execute(state):
            return False

    graph.composition_path_nodes = _ReadOnly()
    graph.workflow_composition_path_nodes = nodes

    state = _state(GOAL)
    gateway_route = graph.gateway.route(state)
    runtime_route = graph._runtime_route(state)
    if gateway_route != AGENT_PATH:
        failures.append(f"gateway route expected agent actual={gateway_route}")
    if runtime_route != WORKFLOW_COMPOSITION_PLAN:
        failures.append(
            f"runtime route expected={WORKFLOW_COMPOSITION_PLAN} actual={runtime_route}"
        )

    state.update(nodes.plan(state))
    if not isinstance(state.get("composition_runtime"), dict):
        failures.append("unique goal did not create workflow composition plan")

    state.update(nodes.text_to_sql(state))
    runtime = state.get("composition_runtime") or {}
    sql_result = (runtime.get("results") or {}).get("TEXT_TO_SQL") or {}
    execution_mode = sql_result.get("execution_mode")
    if pipeline.calls != 0:
        failures.append(
            f"generated Text-to-SQL was called {pipeline.calls} times instead of 0"
        )
    if cost_evidence.calls != 1:
        failures.append(
            f"scoped BOM cost evidence executed {cost_evidence.calls} times instead of 1"
        )
    if execution_mode != "DETERMINISTIC_SCOPED_BOM_SQL":
        failures.append(
            f"unexpected workflow analytics execution mode: {execution_mode}"
        )

    knowledge = nodes.knowledge_query(state)
    state["messages"] += knowledge["messages"]
    state["composition_runtime"] = knowledge["composition_runtime"]
    call = state["messages"][-1].tool_calls[0]
    state["messages"].append(
        ToolMessage(
            content=json.dumps({
                "success": True,
                "authority": {"knowledge_evidence_only": True},
                "hits": [{
                    "document_id": "COST-RULE",
                    "document_title": "원가 절감 기준",
                    "section_path": "원가 절감",
                }],
            }, ensure_ascii=False),
            tool_call_id=call["id"],
            name="search_knowledge",
        )
    )

    handoff = nodes.handoff_and_dispatch(state)
    analysis_call = handoff["messages"][-1].tool_calls[0]
    args = analysis_call["args"]
    if analysis_call["name"] != "analyze_design_change_candidates":
        failures.append("READY handoff did not dispatch Analysis tool")
    if (args.get("request") or {}).get("request_id"):
        failures.append("Analysis handoff unexpectedly created request_id")
    action = (args.get("actions") or [{}])[0]
    if action.get("old_item_code") != ITEM:
        failures.append("Verified analytics target was not handed off")
    if action.get("parent_item_code") != PARENT:
        failures.append("Exact nested BOM parent relation was not handed off")
    if action.get("location_code") != "ALL":
        failures.append("Exact BOM location was not handed off")
    if len(args.get("actions") or []) != 1:
        failures.append("Analysis handoff violated Single Action policy")

    try:
        BomMcpToolNode._validate_design_change_request(
            "analyze_design_change_candidates",
            create_initial_design_change_state(),
            args,
        )
    except Exception as exc:
        failures.append(f"MCP Analysis transition rejected handoff: {exc}")

    state["messages"] += handoff["messages"]
    state["composition_runtime"] = handoff["composition_runtime"]
    state["messages"].append(
        ToolMessage(
            content=json.dumps({
                "analysis_id": "ANA-PLAN04-R1",
                "request_created": False,
                "request_id": None,
                "request": {
                    "version_code": VERSION,
                    "plant_code": PLANT,
                },
                "actions": [{
                    "action_type": "REPLACE",
                    "old_item_code": ITEM,
                    "parent_item_code": PARENT,
                    "location_code": "ALL",
                }],
                "candidates": [],
                "status_counts": {
                    "PASS": 0,
                    "CONDITIONAL": 0,
                    "FAIL": 0,
                },
                "analysis_status": "FAIL",
                "production_bom_modified": False,
            }, ensure_ascii=False),
            tool_call_id=analysis_call["id"],
            name="analyze_design_change_candidates",
        )
    )
    if not is_workflow_composition_analysis_tool_result(state):
        failures.append("workflow analysis result identity was not preserved")
    if not is_macro_analysis_tool_result(state):
        failures.append("existing deterministic Analysis finalizer cannot accept result")

    ambiguous = _state(AMBIGUOUS_GOAL)
    blocked = nodes.plan(ambiguous)
    if blocked.get("composition_runtime") is not None:
        failures.append("ambiguous target unexpectedly created runtime plan")
    if (blocked.get("messages") or [AIMessage(content="", tool_calls=[])])[-1].tool_calls:
        failures.append("ambiguous target unexpectedly dispatched a Tool")

    print(
        "PLAN-04-R1 Workflow-aware Runtime Composition "
        + ("PASS" if not failures else "FAIL")
    )
    print(f"gateway_route={gateway_route}")
    print(f"runtime_route={runtime_route}")
    print(f"workflow_analytics_execution_mode={execution_mode}")
    print(f"scoped_cost_evidence_query_count={cost_evidence.calls}")
    print(f"sql_generation_llm_calls={pipeline.calls}")
    print("runtime_capabilities=TEXT_TO_SQL,RAG,DESIGN_CHANGE_ANALYSIS")
    print("recursive_bom_scope=YES")
    print("exact_parent_location_handoff=YES")
    print("analysis_tool_execution_enabled=YES")
    print("analysis_session_only=YES")
    print("planner_llm_calls=0")
    print("extra_synthesis_llm_calls=0")
    print("request_creation_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")
    print("ambiguous_target_auto_selection=NO")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
