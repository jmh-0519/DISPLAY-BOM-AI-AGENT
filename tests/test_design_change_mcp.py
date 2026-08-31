import asyncio
import json
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agents.bom_mcp_tool_node import BomMcpToolNode
from agents.design_change_workflow_state import create_initial_design_change_state
from mcp_server import server


DESIGN_CHANGE_TOOLS = {
    "analyze_design_change_candidates", "scan_product_cost_reduction_candidates", "revalidate_design_change_analysis",
    "preview_design_change_analysis_impact", "create_design_change_request_from_analysis",
    "explain_design_change_analysis_session", "explain_design_change_analysis_candidate",
    "compare_design_change_analysis_candidates",

    "create_design_change_preview", "record_final_apply_approval",
    "apply_approved_change_request", "get_change_request_result",
    "get_design_change_analysis", "get_candidate_evaluation_detail",
    "compare_design_change_candidates",
}


REMOVED_REQUEST_FIRST_TOOLS = {
    "create_design_change_request",
    "evaluate_replacement_candidates",
    "select_candidate_and_supplier",
    "confirm_candidate_selection",
    "approve_candidate_impact",
    "submit_candidate_additional_data",
    "record_exception_approval",
}


def test_design_change_mcp_tools_are_registered():
    for name in DESIGN_CHANGE_TOOLS:
        assert callable(getattr(server, name))


def test_removed_request_first_tools_are_not_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert not (REMOVED_REQUEST_FIRST_TOOLS & names)


def test_analysis_tool_schema_exposes_design_change_enums():
    tools = asyncio.run(server.mcp.list_tools())
    tool = next(value for value in tools if value.name == "analyze_design_change_candidates")
    schema = tool.input_schema
    definitions = schema["$defs"]
    request_schema = definitions["DesignChangeRequestInput"]
    action_schema = definitions["DesignChangeActionInput"]

    assert "demand_source" not in request_schema["properties"]
    assert "demand_quantity" not in request_schema["properties"]
    assert action_schema["properties"]["action_type"]["enum"] == [
        "REPLACE", "ADD", "DELETE", "QUANTITY_CHANGE",
    ]
    assert action_schema["properties"]["target_type"]["enum"] == ["MATERIAL", "ASSY"]
    assert set(action_schema["required"]) == {"action_type"}



def test_agent_analysis_state_does_not_have_request_until_explicit_commit():
    state = create_initial_design_change_state()
    state = BomMcpToolNode._build_design_change_workflow_state(
        "analyze_design_change_candidates", state,
        {
            "analysis_id": "ANA-1",
            "request_id": None,
            "request_created": False,
            "request": {"plant_code": "P01", "version_code": "MODEL"},
            "actions": [{"action_id": "ANA-ACT-1", "action_type": "REPLACE"}],
            "candidates": [{"action_id": "ANA-ACT-1", "candidate_item_code": "C1", "status": "PASS"}],
            "status_counts": {"PASS": 1, "CONDITIONAL": 0, "FAIL": 0},
        },
    )
    assert state["current_step"] == "ANALYSIS_READY"
    assert state["analysis_id"] == "ANA-1"
    assert state["request_id"] is None
    assert state["analysis_base_request"]["version_code"] == "MODEL"

    state = BomMcpToolNode._build_design_change_workflow_state(
        "preview_design_change_analysis_impact", state,
        {"requires_impact_approval": False, "production_bom_modified": False},
    )
    assert state["current_step"] == "ANALYSIS_CONFIRMED"
    assert state["request_id"] is None

    state = BomMcpToolNode._build_design_change_workflow_state(
        "create_design_change_request_from_analysis", state,
        {
            "request_id": "REQ-1",
            "request_created": True,
            "actions": [{"action_id": "ACT-1"}],
            "selections": [{"action_id": "ACT-1", "candidate_id": "CAND-1"}],
            "approval_id": "APR-1",
        },
    )
    assert state["request_id"] == "REQ-1"
    assert state["current_step"] == "CANDIDATE_APPROVED"


def test_agent_design_change_state_progression():
    state = create_initial_design_change_state()
    state = BomMcpToolNode._build_design_change_workflow_state(
        "analyze_design_change_candidates", state,
        {
            "analysis_id": "ANA-1",
            "request": {"plant_code": "P01", "version_code": "MODEL"},
            "actions": [{"action_id": "ANA-ACT-1", "action_type": "REPLACE"}],
            "candidates": [{"action_id": "ANA-ACT-1", "candidate_item_code": "C1", "status": "PASS"}],
            "status_counts": {"PASS": 1, "CONDITIONAL": 0, "FAIL": 0},
        },
    )
    state = BomMcpToolNode._build_design_change_workflow_state(
        "preview_design_change_analysis_impact", state,
        {"requires_impact_approval": False},
    )
    state = BomMcpToolNode._build_design_change_workflow_state(
        "create_design_change_request_from_analysis", state,
        {
            "request_id": "REQ",
            "actions": [{"action_id": "A1"}],
            "selections": [{"action_id": "A1", "candidate_id": "C1"}],
            "approval_id": "APR-C",
        },
    )
    assert state["current_step"] == "CANDIDATE_APPROVED"
    state = BomMcpToolNode._build_design_change_workflow_state(
        "create_design_change_preview", state,
        {"preview_id": "PRE", "validation_status": "PASS", "impacts": []},
    )
    assert state["current_step"] == "WAITING_FINAL_APPROVAL"
    state = BomMcpToolNode._build_design_change_workflow_state(
        "record_final_apply_approval", state, {"approval_id": "APR-F"},
    )
    state = BomMcpToolNode._build_design_change_workflow_state(
        "apply_approved_change_request", state, {"apply_id": "APPLY", "result": "APPLIED"},
    )
    assert state["current_step"] == "APPLIED"
    assert state["candidate_approval_id"] == "APR-C"
    assert state["final_approval_id"] == "APR-F"


def test_fail_preview_moves_agent_to_blocked():
    result = BomMcpToolNode._build_design_change_workflow_state(
        "create_design_change_preview", create_initial_design_change_state(),
        {"preview_id": "PRE", "validation_status": "FAIL", "impacts": []},
    )
    assert result["current_step"] == "BLOCKED"



def test_design_change_agent_rejects_invalid_transition_and_request_mismatch():
    with pytest.raises(ValueError, match="cannot run"):
        BomMcpToolNode._validate_design_change_request(
            "apply_approved_change_request", create_initial_design_change_state(),
            {"request_id": "REQ"},
        )
    state = create_initial_design_change_state()
    state.update({"current_step": "WAITING_FINAL_APPROVAL", "request_id": "REQ-A"})
    with pytest.raises(ValueError, match="does not match"):
        BomMcpToolNode._validate_design_change_request(
            "record_final_apply_approval", state, {"request_id": "REQ-B"},
        )


def test_invalid_design_change_transition_returns_recovery_message_without_tool_execution():
    mcp_client = Mock()
    node = BomMcpToolNode(mcp_client=mcp_client)
    state = create_initial_design_change_state()

    result = node(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "apply_approved_change_request",
                            "args": {"request_id": "REQ-UNKNOWN", "final_approval_id": "APR-X", "applied_by": "tester"},
                            "id": "call-invalid-transition",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "tool_steps": 0,
            "design_change": state,
        }
    )

    mcp_client.call_tool.assert_not_called()
    assert result["design_change"]["current_step"] == "NOT_STARTED"
    assert result["tool_steps"] == 1
    message = result["messages"][0]
    assert isinstance(message, ToolMessage)
    payload = json.loads(message.content)
    assert payload["error_code"] == "INVALID_DESIGN_CHANGE_TRANSITION"
    assert payload["current_step"] == "NOT_STARTED"
    assert payload["allowed_next_tools"] == ["analyze_design_change_candidates"]
    assert payload["production_bom_modified"] is False


def test_tool_execution_error_returns_matching_tool_message():
    mcp_client = Mock()
    mcp_client.call_tool.side_effect = RuntimeError("source relation missing")
    node = BomMcpToolNode(mcp_client=mcp_client)
    state = create_initial_design_change_state()
    state.update({"current_step": "CANDIDATE_APPROVED", "request_id": "REQ-1"})

    result = node({
        "messages": [AIMessage(
            content="",
            tool_calls=[{
                "name": "create_design_change_preview",
                "args": {"request_id": "REQ-1", "created_by": "tester"},
                "id": "call-tool-error",
                "type": "tool_call",
            }],
        )],
        "tool_steps": 0,
        "design_change": state,
    })

    message = result["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-tool-error"
    payload = json.loads(message.content)
    assert payload["error_code"] == "TOOL_EXECUTION_FAILED"
    assert payload["production_bom_modified"] is False
    assert result["error"] == "create_design_change_preview: source relation missing"
    assert result["design_change"]["current_step"] == "CANDIDATE_APPROVED"
