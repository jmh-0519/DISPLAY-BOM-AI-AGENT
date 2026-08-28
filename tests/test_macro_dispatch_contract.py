from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch


def test_delete_and_quantity_requests_are_macro_dispatch_candidates():
    dispatch = DeterministicAnalysisMacroDispatch()

    delete_spec = dispatch.build_spec(
        user_query=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 "
            "0001-310701 자재를 제거하자."
        ),
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert delete_spec is not None
    assert delete_spec["actions"][0]["action_type"] == "DELETE"

    quantity_spec = dispatch.build_spec(
        user_query=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 "
            "0001-310701 자재 수량을 2로 바꾸자."
        ),
        workflow_state={"current_step": "NOT_STARTED"},
    )
    assert quantity_spec is not None
    assert quantity_spec["actions"][0]["action_type"] == "QUANTITY_CHANGE"
    assert quantity_spec["actions"][0]["new_quantity"] == 2


def test_name_based_quantity_uses_service_side_target_resolution():
    dispatch = DeterministicAnalysisMacroDispatch()

    spec = dispatch.build_spec(
        user_query=(
            "LTA650HR11-001 모델 P03 PLANT BOM에서 "
            "브라켓 자재 수량을 2로 변경하자."
        ),
        workflow_state={"current_step": "NOT_STARTED"},
    )

    assert spec is not None
    action = spec["actions"][0]
    assert action["action_type"] == "QUANTITY_CHANGE"
    assert action["new_quantity"] == 2
    assert action.get("target_item_name")
