from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode


def _assistant_message(content="", tool_calls=None):
    message = Mock()
    message.content = content
    message.tool_calls = tool_calls
    return message


def _analysis_state():
    return {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-OLD",
        "plant_code": "P01",
        "analysis_request": {
            "version_code": "LTA400HR01-001",
            "plant_code": "P01",
            "original_request": (
                "LTA400HR01-001 P01 모델에서 LJ94-100006 수량을 3으로 바꿔줘"
            ),
        },
        "analysis_memory": {
            "candidate_count": 0,
            "status_counts": {"FAIL": 1},
        },
    }


def test_new_explicit_model_change_does_not_reuse_old_analysis_plant():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {
            "type": "function",
            "function": {"name": "analyze_design_change_candidates"},
        },
    ]

    node = BomAgentNode(client, mcp_client, "Design Change workflow")
    result = node({
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 모델에서 SEALANT를 변경하고싶어"
            )
        ],
        "design_change": _analysis_state(),
        "active_bom_context": {
            "product_id": "LTA400HR01-001",
            "plant_code": "P01",
            "source": "get_bom",
        },
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "list_plants"
    assert tool_call["args"]["reference_code"] == "LTA400HR01-001"


def test_new_explicit_model_and_plant_can_start_fresh_analysis_directly():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {
            "type": "function",
            "function": {"name": "analyze_design_change_candidates"},
        },
    ]

    node = BomAgentNode(client, mcp_client, "Design Change workflow")
    result = node({
        "messages": [
            HumanMessage(
                content=(
                    "LTA400HR01-001 P01 모델에서 "
                    "SEALANT를 변경하고싶어"
                )
            )
        ],
        "design_change": _analysis_state(),
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    assert tool_call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert tool_call["args"]["request"]["plant_code"] == "P01"


def test_analysis_explanation_followup_keeps_existing_analysis_context():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {"name": "explain_design_change_analysis_candidate"},
        },
        {
            "type": "function",
            "function": {"name": "analyze_design_change_candidates"},
        },
    ]

    node = BomAgentNode(client, mcp_client, "Design Change workflow")
    # A true follow-up should not be interpreted as a fresh MODEL scope.
    result = node({
        "messages": [
            HumanMessage(content="왜 1번 후보가 FAIL이야?")
        ],
        "design_change": {
            **_analysis_state(),
            "actions": [{"action_id": "ACT-1"}],
            "analysis_memory": {
                "candidate_count": 1,
                "status_counts": {"FAIL": 1},
                "candidates": [
                    {
                        "candidate_index": 1,
                        "candidate_item_code": "0004-230010",
                    }
                ],
            },
        },
    })

    # The exact explain Tool contract is covered by existing follow-up tests;
    # this assertion protects the important boundary: no fresh list_plants.
    if result["messages"][0].tool_calls:
        assert result["messages"][0].tool_calls[0]["name"] != "list_plants"
