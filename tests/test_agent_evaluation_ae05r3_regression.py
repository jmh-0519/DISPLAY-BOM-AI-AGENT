from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage

from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch
from agents.bom_agent_node import BomAgentNode


def _defs():
    return [
        {"type": "function", "function": {"name": "list_plants"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]


def test_reason_based_recommendation_with_explicit_scope_uses_macro():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query="P01에서 MODEL-123의 1234-567890이 단종됐어. 변경 가능한 자재를 찾아줘",
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert spec is not None
    assert spec["request"]["version_code"] == "MODEL-123"
    assert spec["request"]["plant_code"] == "P01"
    assert spec["actions"] == [{"action_type": "REPLACE", "old_item_code": "1234-567890"}]


def test_generic_candidate_recommendation_without_reason_stays_off_macro():
    dispatch = DeterministicAnalysisMacroDispatch()
    spec = dispatch.build_spec(
        user_query="MODEL-123 P01 DRIVE-IC 대체 후보 추천해줘",
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert spec is None


def test_selected_plant_continuation_restores_reason_based_macro():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")

    result = node({
        "messages": [
            HumanMessage(content="MODEL-123의 1234-567890이 단종됐어. 변경 가능한 자재를 찾아줘"),
            AIMessage(content="PLANT를 선택해 주세요. P01, P02"),
            HumanMessage(content="P01"),
        ],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "analyze_design_change_candidates"
    assert call["args"]["request"]["version_code"] == "MODEL-123"
    assert call["args"]["request"]["plant_code"] == "P01"
    assert call["args"]["actions"][0]["old_item_code"] == "1234-567890"


def test_add_target_followup_uses_add_target_parser_and_macro():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
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


def test_generic_material_add_still_clarifies_before_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = _defs()
    node = BomAgentNode(client, mcp_client, "skill")

    result = node({
        "messages": [HumanMessage(content="LTA400HR01-001 P01 모델에 자재를 추가하고 싶어")],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    assert "특정해 주세요" in result["messages"][0].content
    pending = result["design_change"]["pending_add_target_request"]
    assert pending["target_type"] == "MATERIAL"
