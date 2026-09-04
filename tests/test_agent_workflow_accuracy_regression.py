from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch
from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.domain_intent_router import DomainIntentRouter


def _defs():
    return [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
        {"type": "function", "function": {"name": "list_plants"}},
    ]


def test_apply_without_final_approval_is_change_intent():
    decision = DomainIntentRouter().route("분석이나 최종 승인 없이 바로 설계변경 BOM 반영해줘")
    assert decision.intent == "DESIGN_CHANGE"
    assert decision.change is True


def test_fail_candidate_apply_attempt_is_change_not_recommendation():
    decision = DomainIntentRouter().route("FAIL 후보로 그냥 설계변경 BOM 반영해줘")
    assert decision.intent == "DESIGN_CHANGE"
    assert decision.change is True


def test_add_then_score_request_keeps_add_as_change_intent():
    decision = DomainIntentRouter().route(
        "LTA400HR01-001 P01 모델에 FILM 자재를 추가하고 후보 점수도 보여줘"
    )
    assert decision.intent == "DESIGN_CHANGE"
    assert decision.change is True


def test_explicit_code_recommendation_can_use_read_only_macro():
    spec = DeterministicAnalysisMacroDispatch().build_spec(
        user_query="LTA400HR01-001 P01 0001-200003 교체 후보 분석해줘",
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert spec is not None
    assert spec["actions"][0]["action_type"] == "REPLACE"
    assert spec["actions"][0]["old_item_code"] == "0001-200003"


def test_named_recommendation_stays_agent_path():
    gateway = BomGraphGateway(design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS)
    state = {
        "messages": [HumanMessage(content="LTA400HR01-001 P01 DRIVE-IC 대체 후보 추천해줘")],
        "design_change": {"current_step": "NOT_STARTED"},
    }
    assert gateway.route(state) == AGENT_PATH


def test_assy_add_without_parent_clarifies_before_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")
    result = node({
        "messages": [HumanMessage(content="LTA400HR01-001 P01 모델에 BIN ASSY를 추가하고 싶어")],
        "design_change": {"current_step": "NOT_STARTED"},
    })
    client.create_agent_completion.assert_not_called()
    assert "Parent ASSY 코드" in result["messages"][0].content
    assert result["design_change"]["pending_add_parent_request"]["target_name"] == "BIN"


def test_assy_add_parent_followup_resumes_original_request():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")
    result = node({
        "messages": [HumanMessage(content="AS-FA-001")],
        "design_change": {
            "current_step": "NOT_STARTED",
            "pending_add_parent_request": {
                "version_code": "LTA400HR01-001",
                "plant_code": "P01",
                "target_name": "BIN",
            },
        },
    })
    client.create_agent_completion.assert_not_called()
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["actions"][0]["target_item_name"] == "BIN"
    assert call["args"]["actions"][0]["parent_item_code"] == "AS-FA-001"


def test_vague_delete_target_clarifies_before_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")
    result = node({
        "messages": [HumanMessage(content="LTA400HR01-001 P02 모델에서 자재 하나 삭제해줘")],
        "design_change": {"current_step": "NOT_STARTED"},
    })
    client.create_agent_completion.assert_not_called()
    assert result["messages"][0].tool_calls == []
    assert "삭제할 자재/ASSY를 특정" in result["messages"][0].content
    pending = result["design_change"]["pending_delete_target_request"]
    assert pending["version_code"] == "LTA400HR01-001"
    assert pending["plant_code"] == "P02"


def test_delete_target_followup_resumes_scoped_analysis_without_llm():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")
    result = node({
        "messages": [HumanMessage(content="0001-200003")],
        "design_change": {
            "current_step": "NOT_STARTED",
            "pending_delete_target_request": {
                "original_request": "LTA400HR01-001 P02 모델에서 자재 하나 삭제해줘",
                "version_code": "LTA400HR01-001",
                "plant_code": "P02",
            },
        },
    })
    client.create_agent_completion.assert_not_called()
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert call["args"]["request"]["plant_code"] == "P02"
    assert call["args"]["actions"] == [{
        "action_type": "DELETE",
        "old_item_code": "0001-200003",
    }]
    assert result["design_change"]["pending_delete_target_request"] is None
