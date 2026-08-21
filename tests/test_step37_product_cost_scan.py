from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip("langchain_core")
from langchain_core.messages import HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_mcp_tool_node import BomMcpToolNode
from agents.design_change_workflow_state import create_initial_design_change_state


def _active_analysis_state() -> dict:
    return {
        **create_initial_design_change_state(),
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "plant_code": "P01",
        "analysis_request": {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "CF 원가가 높아서 변경하고 싶어",
        },
        "analysis_context": {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "target_item": {"item_code": "ASSY-123456", "item_name": "CF"},
        },
        "actions": [{"action_id": "ANA-ACT-1", "old_item_code": "ASSY-123456"}],
        "candidates": [{"action_id": "ANA-ACT-1", "candidate_item_code": "ASSY-123457", "status": "FAIL"}],
    }


def _node() -> tuple[BomAgentNode, Mock]:
    client = Mock()
    client.create_agent_completion.return_value = SimpleNamespace(
        content="제품 BOM 전체 Scan 결과를 설명합니다.", tool_calls=None
    )
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": name}}
        for name in (
            "list_plants",
            "analyze_design_change_candidates",
            "compare_design_change_analysis_candidates",
            "scan_product_cost_reduction_candidates",
        )
    ]
    return BomAgentNode(client, mcp_client, "Phase3 skill"), client


def test_broad_model_cost_question_does_not_choose_last_bom_item_as_single_target():
    node, client = _node()
    query = "CF 자재 말고 대상모델의 BOM에 구성된 자재들의 원가를 낮출 수 있는 대체 자재가 있는지 찾아줘"
    result = node({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": _active_analysis_state(),
    })
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "scan_product_cost_reduction_candidates"
    assert call["args"]["version_code"] == "MODEL-1"
    assert call["args"]["plant_code"] == "P01"
    assert call["args"]["exclude_item_names"] == ["CF"]
    assert "old_item_code" not in call["args"]
    client.create_agent_completion.assert_not_called()


def test_cost_scan_observation_is_answered_without_repeating_tool():
    node, client = _node()
    query = "대상 모델 BOM 전체에서 원가를 줄일 수 있는 대체 자재를 찾아줘"
    messages = [
        HumanMessage(content=query),
        ToolMessage(
            content='{"scan_type":"PRODUCT_COST_REDUCTION","opportunities":[],"request_created":false}',
            tool_call_id="scan-1",
            name="scan_product_cost_reduction_candidates",
        ),
    ]
    result = node({
        "messages": messages,
        "user_query": query,
        "design_change": _active_analysis_state(),
    })
    assert result["messages"][0].content == "제품 BOM 전체 Scan 결과를 설명합니다."
    kwargs = client.create_agent_completion.call_args.kwargs
    assert kwargs["tools"] == []
    assert kwargs["tool_choice"] == "auto"


def test_read_only_cost_scan_does_not_replace_active_analysis_state():
    state = _active_analysis_state()
    updated = BomMcpToolNode._build_phase3_workflow_state(
        "scan_product_cost_reduction_candidates",
        state,
        {
            "scan_type": "PRODUCT_COST_REDUCTION",
            "version_code": "MODEL-1",
            "request_created": False,
            "production_bom_modified": False,
        },
    )
    assert updated["analysis_id"] == "ANA-1"
    assert updated["current_step"] == "ANALYSIS_READY"
    assert updated["analysis_context"]["target_item"]["item_code"] == "ASSY-123456"


def test_realistic_cost_scan_question_survives_bom_normalization_and_forces_scan_tool():
    from agents.bom_agent_graph import BomAgentGraph

    raw = (
        "LTA550HR01-001 모델의 CF 자재 말고 대상 모델의 BOM 정보를 확인해서 "
        "BOM에 구성된 자재들의 원가를 낮출 수 있는 대체 자재들이 있는지 찾아줘. "
        "PLANT는 P01이야."
    )
    normalized = BomAgentGraph._normalize_bom_query(raw)
    assert normalized == raw

    node, client = _node()
    # Fresh Analysis state: the LLM must be forced to the product-wide scan tool,
    # and get_bom must not be exposed as an alternative.
    state = create_initial_design_change_state()
    result = node({
        "messages": [HumanMessage(content=normalized)],
        "user_query": normalized,
        "design_change": state,
    })

    kwargs = client.create_agent_completion.call_args.kwargs
    names = {tool["function"]["name"] for tool in kwargs["tools"]}
    assert names == {"scan_product_cost_reduction_candidates"}
    assert kwargs["tool_choice"] == "scan_product_cost_reduction_candidates"
    assert not result["messages"][0].tool_calls
