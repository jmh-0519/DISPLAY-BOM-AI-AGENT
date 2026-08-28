from agents.bom_agent_node import BomAgentNode


def test_quantity_change_is_current_write_intent_not_where_used():
    current = (
        "LTA400HR01-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )

    assert BomAgentNode._is_quantity_change_instruction(current) is True
    assert BomAgentNode._is_design_change_request(current) is True
    assert BomAgentNode._is_where_used_request(current) is False


def test_previous_where_used_text_must_not_define_current_intent():
    previous = "P01에서 0001-310901 포함한 모델 알려줘"
    current = (
        "LTA400HR01-001 P01 모델에서 "
        "LJ94-100006 자재의 수량을 바꾸고싶어"
    )
    combined_history = f"{previous} {current}"

    # This reproduces the old failure mechanism: combined history contains
    # a WHERE_USED marker even though the current turn does not.
    assert BomAgentNode._is_where_used_request(combined_history) is True
    assert BomAgentNode._is_where_used_request(current) is False
    assert BomAgentNode._is_design_change_request(current) is True


def test_current_where_used_request_still_routes_as_where_used():
    current = "P01에서 0001-310901 포함한 모델 알려줘"

    assert BomAgentNode._is_where_used_request(current) is True
    assert BomAgentNode._is_design_change_request(current) is False


def test_plain_bom_request_stays_read_only():
    current = "LTA400HR01-001 P01 BOM 보여줘"

    assert BomAgentNode._is_where_used_request(current) is False
    assert BomAgentNode._is_design_change_request(current) is False
    assert BomAgentNode._is_plain_bom_query(current, design_change_mode=False) is True
