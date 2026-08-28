from types import SimpleNamespace
from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode

def _workflow_state() -> dict:
    return {
        "current_step": "WAITING_CANDIDATE_APPROVAL",
        "request_id": "REQ-1",
        "actions": [{"action_id": "ACT-1"}],
        "analysis_memory": {
            "candidate_count": 2,
            "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 2},
        },
        "candidates": [
            {"action_id": "ACT-1", "candidate_item_code": "LJ94-310311", "status": "FAIL"},
            {"action_id": "ACT-1", "candidate_item_code": "LJ94-310312", "status": "FAIL"},
        ],
    }


def _node() -> tuple[BomAgentNode, Mock]:
    client = Mock()
    client.create_agent_completion.return_value = SimpleNamespace(
        content="근거를 설명합니다.", tool_calls=None
    )
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": name}}
        for name in (
            "evaluate_replacement_candidates",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        )
    ]
    return BomAgentNode(client, mcp_client, "Design Change skill"), client


def test_followup_why_routes_to_read_only_analysis_tool_without_llm_selection():
    node, client = _node()
    result = node({
        "messages": [HumanMessage(content="왜 대상후보가 없는거야?")],
        "user_query": "왜 대상후보가 없는거야?",
        "design_change": _workflow_state(),
    })
    message = result["messages"][0]
    assert isinstance(message, AIMessage)
    assert message.tool_calls[0]["name"] == "get_design_change_analysis"
    assert message.tool_calls[0]["args"] == {"request_id": "REQ-1"}
    client.create_agent_completion.assert_not_called()


def test_specific_candidate_why_routes_to_candidate_detail():
    node, client = _node()
    result = node({
        "messages": [HumanMessage(content="LJ94-310311은 왜 FAIL이야?")],
        "user_query": "LJ94-310311은 왜 FAIL이야?",
        "design_change": _workflow_state(),
    })
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "get_candidate_evaluation_detail"
    assert call["args"]["candidate_item_code"] == "LJ94-310311"
    assert call["args"]["action_id"] == "ACT-1"
    client.create_agent_completion.assert_not_called()


def test_candidate_rank_question_routes_to_compare_tool_with_spec_criterion():
    node, _ = _node()
    result = node({
        "messages": [HumanMessage(content="그럼 가장 비슷한 후보는 뭐야?")],
        "user_query": "그럼 가장 비슷한 후보는 뭐야?",
        "design_change": _workflow_state(),
    })
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "compare_design_change_candidates"
    assert call["args"]["criterion"] == "SPEC_SIMILARITY"
    assert call["args"]["action_id"] == "ACT-1"


def test_after_explain_tool_observation_agent_answers_without_recalling_tools():
    node, client = _node()
    messages = [
        HumanMessage(content="왜 전부 FAIL이야?"),
        AIMessage(content="", tool_calls=[{
            "name": "get_design_change_analysis",
            "args": {"request_id": "REQ-1"},
            "id": "call-1",
            "type": "tool_call",
        }]),
        ToolMessage(
            content='{"summary":"후보는 2개 검색되었지만 모두 FAIL입니다."}',
            tool_call_id="call-1",
            name="get_design_change_analysis",
        ),
    ]
    result = node({
        "messages": messages,
        "user_query": "왜 전부 FAIL이야?",
        "design_change": _workflow_state(),
    })
    assert result["messages"][0].content == "근거를 설명합니다."
    kwargs = client.create_agent_completion.call_args.kwargs
    assert kwargs["tools"] == []
    assert kwargs["tool_choice"] == "auto"


def _analysis_workflow_state() -> dict:
    return {
        "current_step": "ANALYSIS_REVALIDATED",
        "analysis_id": "ANA-1",
        "request_id": None,
        "analysis_request": {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "단종 때문에 변경 가능한 후보를 찾아줘",
            "demand_source": "USER",
            "demand_quantity": 2,
        },
        "analysis_base_request": {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "단종 때문에 변경 가능한 후보를 찾아줘",
        },
        "actions": [{
            "action_id": "ANA-ACT-1",
            "action_type": "REPLACE",
            "old_item_code": "1234-567890",
        }],
        "candidates": [{
            "action_id": "ANA-ACT-1",
            "candidate_item_code": "1234-567891",
            "status": "FAIL",
        }],
        "analysis_memory": {
            "candidate_count": 1,
            "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 1},
        },
    }


def test_analysis_followup_why_uses_read_only_analysis_tool():
    client = Mock()
    client.create_agent_completion.return_value = SimpleNamespace(content="설명", tool_calls=None)
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": name}}
        for name in (
            "analyze_design_change_candidates",
            "revalidate_design_change_analysis",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        )
    ]
    node = BomAgentNode(client, mcp_client, "Design Change skill")
    result = node({
        "messages": [HumanMessage(content="왜 전부 FAIL이야?")],
        "user_query": "왜 전부 FAIL이야?",
        "design_change": _analysis_workflow_state(),
    })
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "explain_design_change_analysis_session"
    assert call["args"]["analysis"]["analysis_id"] == "ANA-1"
    client.create_agent_completion.assert_not_called()


def test_restart_analysis_reuses_original_analysis_input_without_request_creation():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
        {"type": "function", "function": {"name": "revalidate_design_change_analysis"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change skill")
    state = _analysis_workflow_state()
    result = node({
        "messages": [HumanMessage(content="다시 처음부터 확인하자")],
        "user_query": "다시 처음부터 확인하자",
        "design_change": state,
    })
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "MODEL-1"
    assert "demand_quantity" not in call["args"]["request"]
    assert call["args"]["actions"][0]["old_item_code"] == "1234-567890"
    client.create_agent_completion.assert_not_called()
