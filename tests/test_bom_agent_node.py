from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from agents.bom_agent_node import BomAgentNode


def make_assistant_message(
    content=None,
    tool_calls=None,
):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )


def make_tool_call(
    tool_call_id,
    name,
    arguments,
):
    return SimpleNamespace(
        id=tool_call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def test_agent_node_returns_final_ai_message():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
            },
        }
    ]

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content="조회 결과입니다.",
            tool_calls=None,
        )
    )

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = node(
        {
            "messages": [
                HumanMessage(
                    content="PRD-001의 BOM을 조회해줘"
                )
            ]
        }
    )

    assert len(result["messages"]) == 1
    assert isinstance(
        result["messages"][0],
        AIMessage,
    )
    assert (
        result["messages"][0].content
        == "조회 결과입니다."
    )
    assert result["messages"][0].tool_calls == []
    assert result["error"] is None

    client.create_agent_completion.assert_called_once()


def test_agent_node_converts_tool_call():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
            },
        }
    ]

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content=None,
            tool_calls=[
                make_tool_call(
                    tool_call_id="call-001",
                    name="get_bom",
                    arguments='{"product_code": "PRD-001"}',
                )
            ],
        )
    )

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = node(
        {
            "messages": [
                HumanMessage(
                    content="PRD-001의 BOM을 조회해줘"
                )
            ]
        }
    )

    ai_message = result["messages"][0]

    assert ai_message.content == ""
    assert len(ai_message.tool_calls) == 1
    assert (
        ai_message.tool_calls[0]["name"]
        == "get_bom"
    )
    assert ai_message.tool_calls[0]["args"] == {
        "product_code": "PRD-001"
    }
    assert (
        ai_message.tool_calls[0]["id"]
        == "call-001"
    )


def test_agent_node_finalizes_plain_bom_observation_without_second_llm():
    client = Mock()
    mcp_client = Mock()

    node = BomAgentNode(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = node(
        {
            "messages": [
                HumanMessage(content="BOM을 조회해줘"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_bom",
                            "args": {"product_code": "PRD-001"},
                            "id": "call-001",
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(
                    content='{"product_code":"PRD-001"}',
                    tool_call_id="call-001",
                    name="get_bom",
                ),
            ]
        }
    )

    client.create_agent_completion.assert_not_called()
    assert result["messages"][0].content == "BOM 조회 결과를 확인해 주세요."

def test_agent_node_rejects_empty_messages():
    node = BomAgentNode(
        client=Mock(),
        mcp_client=Mock(),
        skill_context="BOM 조회 규칙",
    )

    with pytest.raises(
        ValueError,
        match="하나 이상의 메시지",
    ):
        node({})


def test_design_change_recommendation_exposes_analysis_without_request_creation():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "search_product"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    client.create_agent_completion.return_value = make_assistant_message(
        content="요청을 확인했습니다.",
        tool_calls=None,
    )
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    node(
        {
            "messages": [HumanMessage(content="단종 자재의 대체 후보를 추천해줘")],
            "design_change": {"current_step": "NOT_STARTED"},
        }
    )

    tools = client.create_agent_completion.call_args.kwargs["tools"]
    names = {tool["function"]["name"] for tool in tools}
    assert "get_bom" in names
    assert "search_product" in names
    assert "analyze_design_change_candidates" in names
    context = client.create_agent_completion.call_args.kwargs["skill_context"]
    assert "현재 단계: NOT_STARTED" in context
    assert "analyze_design_change_candidates를 호출" in context
    assert client.create_agent_completion.call_args.kwargs["tool_choice"] == "auto"


def test_design_change_recommendation_exposes_analysis_after_bom_result():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    client.create_agent_completion.return_value = make_assistant_message(
        content="요청을 생성합니다.",
        tool_calls=None,
    )
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    node(
        {
            "messages": [
                HumanMessage(content="단종 자재의 대체 후보를 추천해줘"),
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "get_bom",
                        "args": {"product_id": "MODEL-456"},
                        "id": "call-bom",
                        "type": "tool_call",
                    }],
                ),
                ToolMessage(
                    content='[{"bom_parent":"ASSY-456789"}]',
                    tool_call_id="call-bom",
                    name="get_bom",
                ),
            ],
            "user_query": "단종 자재의 대체 후보를 추천해줘",
            "design_change": {"current_step": "NOT_STARTED"},
        }
    )

    tools = client.create_agent_completion.call_args.kwargs["tools"]
    names = {tool["function"]["name"] for tool in tools}
    assert "analyze_design_change_candidates" in names


def test_design_change_explicit_product_and_item_uses_deterministic_analysis_macro():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "P01에서 MODEL-123의 1234-567890이 단종됐어. 변경 가능한 자재를 찾아줘"
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    assert tool_call["args"]["request"]["version_code"] == "MODEL-123"
    assert tool_call["args"]["request"]["plant_code"] == "P01"
    action = tool_call["args"]["actions"][0]
    assert action["action_type"] == "REPLACE"
    assert action["old_item_code"] == "1234-567890"

def test_explicit_old_to_new_analysis_uses_current_analysis_tool():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    client.create_agent_completion.return_value = make_assistant_message(
        content="교체 적합성을 분석합니다.",
        tool_calls=None,
    )
    node = BomAgentNode(client, mcp_client, "BOM change analysis")

    node({
        "messages": [HumanMessage(content=(
            "P01에서 MODEL-789의 1234-567890을 "
            "1234-567891로 교체 가능한지 분석해줘"
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    kwargs = client.create_agent_completion.call_args.kwargs
    names = {tool["function"]["name"] for tool in kwargs["tools"]}
    assert names == {"analyze_design_change_candidates"}
    assert kwargs["tool_choice"] == "analyze_design_change_candidates"


def test_design_change_multi_reason_change_request_uses_macro_without_new_item():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "[선택 PLANT: P01] LTA400HR01-001 모델의 0001-200010이 "
            "단종됐고 원가도 너무 높아서 변경하고 싶어"
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert request["version_code"] == "LTA400HR01-001"
    assert request["plant_code"] == "P01"
    assert "단종" in request["original_request"]
    assert "원가" in request["original_request"]
    assert action["action_type"] == "REPLACE"
    assert action["old_item_code"] == "0001-200010"
    assert "new_item_code" not in action

def test_design_change_short_followup_reuses_recent_product_item_context_for_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [
            HumanMessage(content=(
                "[선택 PLANT: P01] LTA400HR01-001 모델의 0001-200010이 "
                "단종됐고 원가가 높아서 변경하고 싶어"
            )),
            AIMessage(content="변경 대상과 사유를 확인했습니다."),
            HumanMessage(content="변경 가능한 자재를 알려줘"),
        ],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    message = result["messages"][0]
    assert len(message.tool_calls) == 1
    tool_call = message.tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    assert tool_call["args"]["request"]["version_code"] == "LTA400HR01-001"
    assert tool_call["args"]["request"]["plant_code"] == "P01"
    assert tool_call["args"]["actions"][0]["old_item_code"] == "0001-200010"

def test_design_change_missing_plant_forces_target_scoped_plant_discovery_before_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    client.create_agent_completion.return_value = make_assistant_message(content="", tool_calls=None)
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "MODEL-123의 1234-567890이 단종됐어. 변경 가능한 자재를 찾아줘"
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    # STEP40-C: PLANT 누락 시 LLM에게 list_plants 선택을 맡기지 않는다.
    # Agent가 질문의 대상 코드로 scope를 고정한 list_plants Tool Call을 직접 생성하고,
    # Streamlit이 실제 존재하는 PLANT 결과를 버튼으로 보여준다.
    client.create_agent_completion.assert_not_called()
    message = result["messages"][0]
    assert len(message.tool_calls) == 1
    tool_call = message.tool_calls[0]
    assert tool_call["name"] == "list_plants"
    assert tool_call["args"] == {"reference_code": "MODEL-123"}


def test_design_change_selected_plant_in_followup_reuses_original_request_and_forces_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [
            HumanMessage(content=(
                "MODEL-123의 1234-567890이 단종됐어. 변경 가능한 자재를 찾아줘"
            )),
            AIMessage(content="PLANT를 선택해 주세요. P01, P02"),
            HumanMessage(content="P01"),
        ],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    message = result["messages"][0]
    assert len(message.tool_calls) == 1
    tool_call = message.tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    assert tool_call["args"]["request"]["version_code"] == "MODEL-123"
    assert tool_call["args"]["request"]["plant_code"] == "P01"
    assert tool_call["args"]["actions"][0]["old_item_code"] == "1234-567890"

def test_exact_delete_without_reason_uses_macro_default_reason_policy():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 제거하자."
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert request["version_code"] == "LTA650HR11-001"
    assert request["plant_code"] == "P03"
    assert action["action_type"] == "DELETE"
    assert action["old_item_code"] == "0001-310701"

def test_exact_delete_with_reason_uses_macro_without_bom_lookup():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 공용화를 위해 제거하자."
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert "공용화" in request["original_request"]
    assert action["action_type"] == "DELETE"
    assert action["old_item_code"] == "0001-310701"

def test_delete_without_business_reason_is_phase3_change_intent():
    assert BomAgentNode._is_design_change_request(
        "LTA650HR11-001 P03에서 0001-310701 자재를 제거하자"
    )
    assert BomAgentNode._is_design_change_request(
        "LTA650HR11-001 P03에서 자재를 삭제하자"
    )
    assert BomAgentNode._is_design_change_request(
        "LTA650HR11-001 P03에서 GATE-IC 수량을 2로 바꾸자"
    )


def test_bom_observation_name_delete_continues_with_macro_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")
    query = (
        "LTA650HR11-001 모델 P03 PLANT BOM에서 공용화를 위해 "
        "브라켓 자재를 제거하자."
    )

    result = node({
        "messages": [
            HumanMessage(content=query),
            AIMessage(content="", tool_calls=[{
                "name": "get_bom",
                "args": {"product_id": "LTA650HR11-001", "plant_code": "P03"},
                "id": "call-bom-delete",
                "type": "tool_call",
            }]),
            ToolMessage(
                content='[{"PARENT_CODE":"LJ94-310701","CHILD_CODE":"0001-310701","CHILD_NAME":"BASE BRACKET","LOCATION":"N/A"}]',
                tool_call_id="call-bom-delete",
                name="get_bom",
            ),
        ],
        "user_query": query,
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    action = tool_call["args"]["actions"][0]
    assert action["action_type"] == "DELETE"
    assert action.get("target_item_name")

def test_completed_request_does_not_block_new_delete_macro_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
        {"type": "function", "function": {"name": "get_change_request_result"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 공용화를 위해 제거하자."
        ))],
        "design_change": {
            "current_step": "REPORT_COMPLETED",
            "request_id": "REQ-OLD",
            "plant_code": "P01",
            "analysis_request": {"version_code": "OLD-MODEL"},
        },
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert request["version_code"] == "LTA650HR11-001"
    assert request["plant_code"] == "P03"
    assert "REQ-OLD" not in str(tool_call["args"])
    assert "OLD-MODEL" not in str(tool_call["args"])
    assert action["action_type"] == "DELETE"

def test_where_used_without_plant_forces_scoped_plant_lookup():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {"type": "function", "function": {"name": "get_bom_where_used"}},
        {"type": "function", "function": {"name": "get_bom"}},
    ]
    node = BomAgentNode(client, mcp_client, "BOM query")

    result = node({
        "messages": [HumanMessage(content="0001-310501 자재를 가지고 있는 모델은?")],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "list_plants"
    assert tool_call["args"]["reference_code"] == "0001-310501"


def test_where_used_with_plant_forces_reverse_bom_tool():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "list_plants"}},
        {"type": "function", "function": {"name": "get_bom_where_used"}},
        {"type": "function", "function": {"name": "get_bom"}},
    ]
    node = BomAgentNode(client, mcp_client, "BOM query")

    result = node({
        "messages": [HumanMessage(content="0001-310501 자재를 가지고 있는 모델은? P01")],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "get_bom_where_used"
    assert tool_call["args"] == {"item_code": "0001-310501", "plant_code": "P01"}


def test_quantity_change_without_business_reason_uses_macro_analysis():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재 수량을 2로 바꾸자."
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    action = tool_call["args"]["actions"][0]
    assert action["action_type"] == "QUANTITY_CHANGE"
    assert action["old_item_code"] == "0001-310701"
    assert action["new_quantity"] == 2

def test_exact_quantity_change_with_reason_uses_macro_without_bom_lookup():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")

    result = node({
        "messages": [HumanMessage(content=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 "
            "공용화를 위해 수량 1에서 2로 변경하자."
        ))],
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert "공용화" in request["original_request"]
    assert action["action_type"] == "QUANTITY_CHANGE"
    assert action["old_item_code"] == "0001-310701"
    assert action["new_quantity"] == 2

def test_name_based_quantity_change_uses_macro_target_resolution():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "get_bom"}},
        {"type": "function", "function": {"name": "analyze_design_change_candidates"}},
    ]
    node = BomAgentNode(client, mcp_client, "Design Change workflow")
    query = (
        "LTA650HR11-001 모델 P03 PLANT BOM에서 공용화를 위해 "
        "브라켓 자재 수량을 2로 변경하자."
    )

    result = node({
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": {"current_step": "NOT_STARTED"},
    })

    client.create_agent_completion.assert_not_called()
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "analyze_design_change_candidates"
    request = tool_call["args"]["request"]
    action = tool_call["args"]["actions"][0]
    assert request["version_code"] == "LTA650HR11-001"
    assert request["plant_code"] == "P03"
    assert action["action_type"] == "QUANTITY_CHANGE"
    assert action["new_quantity"] == 2
    assert action.get("target_item_name")

def test_read_only_quantity_question_is_not_explicit_quantity_change():
    assert not BomAgentNode._is_quantity_change_instruction("이 자재의 현재 수량이 얼마야?")
    assert BomAgentNode._is_quantity_change_instruction("이 자재 수량을 2로 바꿔줘")
