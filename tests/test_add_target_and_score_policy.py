from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from services.design_change_workflow_service import DesignChangeWorkflowService


def _tool_defs():
    return [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]


def test_generic_add_asks_for_target_before_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _tool_defs()
    node = BomAgentNode(client, mcp_client, "skill")

    result = node({
        "messages": [HumanMessage(content="LTA400HR01-001 P01 모델에 자재를 추가하고 싶어")],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    assert not result["messages"][0].tool_calls
    assert "자재코드, 자재명 또는 품목군" in result["messages"][0].content
    pending = result["design_change"]["pending_add_target_request"]
    assert pending["target_type"] == "MATERIAL"
    assert pending["version_code"] == "LTA400HR01-001"
    assert pending["plant_code"] == "P01"


def test_add_target_followup_resumes_original_scope_and_macro():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _tool_defs()
    node = BomAgentNode(client, mcp_client, "skill")

    result = node({
        "messages": [HumanMessage(content="SEALANT")],
        "design_change": {
            "current_step": "NOT_STARTED",
            "pending_add_target_request": {
                "original_request": "LTA400HR01-001 P01 모델에 자재를 추가하고 싶어",
                "target_type": "MATERIAL",
                "version_code": "LTA400HR01-001",
                "plant_code": "P01",
            },
        },
    })

    client.create_agent_completion.assert_not_called()
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert call["args"]["request"]["plant_code"] == "P01"
    assert call["args"]["actions"] == [{
        "action_type": "ADD",
        "target_type": "MATERIAL",
        "target_item_name": "SEALANT",
    }]


def test_ranking_score_is_not_exposed_until_technical_pass():
    service = object.__new__(DesignChangeWorkflowService)
    service.recommendation = Mock()
    service.recommendation.rule_engine.grade.return_value = "C"

    conditional = {
        "status": "CONDITIONAL",
        "technical_status": "CONDITIONAL",
        "rule_score": 0.0,
        "total_score": 0.0,
        "grade": "C",
    }
    service._apply_candidate_ranking_score(
        conditional,
        {"status": "PASS", "recommended": {"score": 90.0}},
        {"status": "PASS"},
    )
    assert conditional["ranking_score"] is None
    assert conditional["ranking_grade"] is None

    passed = {
        "status": "PASS",
        "technical_status": "PASS",
        "rule_score": 80.0,
        "total_score": 80.0,
        "grade": "B",
    }
    service._apply_candidate_ranking_score(
        passed,
        {"status": "PASS", "recommended": {"score": 90.0}},
        {"status": "PASS"},
    )
    assert passed["ranking_score"] == 85.0
    assert passed["ranking_grade"] == "C"
