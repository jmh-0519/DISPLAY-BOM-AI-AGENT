import json
from unittest.mock import Mock

from langchain_core.messages import HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode
from agents.design_change_workflow_state import (
    create_initial_design_change_state,
)
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def _active_bom():
    return {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }


def test_agent_projection_marks_implicit_scope_as_inherited():
    node = BomAgentNode(Mock(), Mock(), "skill")
    query = "SEALANT를 변경하고싶어"
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        query,
        workflow_active=False,
        workflow_state={},
    )

    result = node._build_llm_context_projection(
        messages=[HumanMessage(content=query)],
        raw_user_query=query,
        state={"active_bom_context": _active_bom()},
        workflow_state=create_initial_design_change_state(),
        routing_decision=decision,
        routing_step="NOT_STARTED",
        follow_up_intent=None,
        design_change_mode=True,
        product_cost_scan_intent=False,
    )

    assert '"value":"LTA400HR01-001"' in result.text
    assert '"source":"ACTIVE_BOM"' in result.text
    assert '"authority":"GRAPH_STATE"' in result.text
    assert '"inherited":true' in result.text
    assert '"value":"SEALANT"' in result.text
    assert '"source":"CURRENT_TURN"' in result.text
    assert '"value":"REPLACE"' in result.text
    assert '"authority":"DERIVED"' in result.text


def test_explicit_model_is_fresh_and_old_plant_is_not_projected():
    query = (
        "LTA400HR01-001 모델에서 "
        "SEALANT를 변경하고싶어"
    )
    node = BomAgentNode(Mock(), Mock(), "skill")
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        query,
        workflow_active=False,
        workflow_state={},
    )

    result = node._build_llm_context_projection(
        messages=[HumanMessage(content=query)],
        raw_user_query=query,
        state={"active_bom_context": _active_bom()},
        workflow_state=create_initial_design_change_state(),
        routing_decision=decision,
        routing_step="NOT_STARTED",
        follow_up_intent=None,
        design_change_mode=True,
        product_cost_scan_intent=False,
    )

    assert (
        '"value":"LTA400HR01-001",'
        '"source":"CURRENT_TURN"'
    ) in result.text
    assert "plant_code=" not in result.text


def test_terminal_workflow_is_not_projected_into_unrelated_fresh_turn():
    node = BomAgentNode(Mock(), Mock(), "skill")
    query = "도와줄 수 있어?"
    workflow = create_initial_design_change_state()
    workflow.update({
        "current_step": "APPLIED",
        "analysis_id": "OLD-ANA",
        "request_id": "OLD-REQ",
        "plant_code": "P01",
        "analysis_request": {
            "version_code": "LTA400HR01-001",
            "plant_code": "P01",
        },
    })
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        query,
        workflow_active=False,
        workflow_state={},
    )

    result = node._build_llm_context_projection(
        messages=[HumanMessage(content=query)],
        raw_user_query=query,
        state={},
        workflow_state=workflow,
        routing_decision=decision,
        routing_step="APPLIED",
        follow_up_intent=None,
        design_change_mode=False,
        product_cost_scan_intent=False,
    )

    assert result.text == ""
    assert "OLD-ANA" not in result.text
    assert "OLD-REQ" not in result.text


def test_projection_references_tool_evidence_without_copying_payload():
    node = BomAgentNode(Mock(), Mock(), "skill")
    query = "왜 후보가 FAIL이야?"
    workflow = create_initial_design_change_state()
    workflow.update({
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "plant_code": "P01",
        "analysis_request": {
            "version_code": "LTA400HR01-001",
            "plant_code": "P01",
        },
    })
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        query,
        workflow_active=True,
        workflow_state=workflow,
    )
    messages = [
        HumanMessage(content=query),
        ToolMessage(
            content=json.dumps({
                "success": True,
                "analysis_id": "ANA-1",
                "candidate_count": 5,
                "huge_payload": (
                    "SECRET-ROW-" + ("x" * 5000)
                ),
            }),
            tool_call_id="detail-1",
            name="get_design_change_analysis",
        ),
    ]

    result = node._build_llm_context_projection(
        messages=messages,
        raw_user_query=query,
        state={},
        workflow_state=workflow,
        routing_decision=decision,
        routing_step="ANALYSIS_READY",
        follow_up_intent="EXPLAIN_ANALYSIS",
        design_change_mode=True,
        product_cost_scan_intent=False,
    )

    assert '"value":"LTA400HR01-001"' in result.text
    assert '"source":"DESIGN_CHANGE_WORKFLOW"' in result.text
    assert "get_design_change_analysis:detail-1" in result.text
    assert "candidate_count=5" in result.text
    assert "SECRET-ROW" not in result.text
