from agents.bom_agent_node import BomAgentNode


def test_where_used_accepts_included_model_expression():
    query = "P01에서 0001-310901 포함한 모델 알려줘"

    assert BomAgentNode._is_where_used_request(query) is True
    assert BomAgentNode._where_used_item_code(query) == "0001-310901"

    message = BomAgentNode._build_where_used_tool_message(
        user_query=query,
        plant_code="P01",
    )

    assert len(message.tool_calls) == 1
    tool_call = message.tool_calls[0]
    assert tool_call["name"] == "get_bom_where_used"
    assert tool_call["args"] == {
        "item_code": "0001-310901",
        "plant_code": "P01",
    }


def test_other_natural_where_used_examples_are_supported():
    assert BomAgentNode._is_where_used_request(
        "P01에서 0001-310901 포함된 모델 알려줘"
    )
    assert BomAgentNode._is_where_used_request(
        "P01에서 0001-310901 들어간 모델 알려줘"
    )
    assert BomAgentNode._is_where_used_request(
        "P01에서 0001-310901 사용한 모델 알려줘"
    )


def test_forward_bom_request_is_not_where_used():
    assert not BomAgentNode._is_where_used_request(
        "LTA400HR01-001 P01 BOM 보여줘"
    )
