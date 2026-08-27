from agents.bom_graph_gateway import BomGraphGateway
from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode


ACTIVE_CONTEXT = {
    "product_id": "LTA400HR01-001",
    "plant_code": "P01",
    "source": "get_bom",
}


def test_implicit_change_followup_can_still_inherit_active_bom():
    gateway = BomGraphGateway()

    assert gateway.can_inherit_active_bom_context(
        "SEALANT를 변경하고싶어",
        ACTIVE_CONTEXT,
    ) is True


def test_explicit_same_model_does_not_silently_inherit_plant():
    gateway = BomGraphGateway()

    assert gateway.can_inherit_active_bom_context(
        "LTA400HR01-001 모델에서 SEALANT를 변경하고싶어",
        ACTIVE_CONTEXT,
    ) is False


def test_agent_context_policy_matches_gateway_for_explicit_same_model():
    node = object.__new__(BomAgentNode)
    from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER
    node.domain_intent_router = DEFAULT_DOMAIN_INTENT_ROUTER

    original = "LTA400HR01-001 모델에서 SEALANT를 변경하고싶어"
    result = node._inherit_active_bom_context_for_change(
        user_query=original,
        workflow_state={"current_step": "NOT_STARTED"},
        active_bom_context=ACTIVE_CONTEXT,
    )

    assert result == original
    assert "P01" not in result


def test_agent_still_inherits_active_context_for_implicit_followup():
    node = object.__new__(BomAgentNode)
    from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER
    node.domain_intent_router = DEFAULT_DOMAIN_INTENT_ROUTER

    result = node._inherit_active_bom_context_for_change(
        user_query="SEALANT를 변경하고싶어",
        workflow_state={"current_step": "NOT_STARTED"},
        active_bom_context=ACTIVE_CONTEXT,
    )

    assert "LTA400HR01-001" in result
    assert "P01" in result
    assert "SEALANT를 변경하고싶어" in result


def test_invalid_old_item_error_is_business_friendly():
    raw = (
        "analyze_design_change_candidates: "
        "old_item_code must reference an active item"
    )

    assert BomAgentGraph._user_facing_tool_error(raw) == (
        "요청한 자재를 활성 자재 기준정보에서 찾을 수 없습니다. "
        "자재 코드를 확인해 주세요."
    )


def test_invalid_new_item_error_is_business_friendly():
    raw = (
        "analyze_design_change_candidates: "
        "new_item_code must reference an active item"
    )

    assert BomAgentGraph._user_facing_tool_error(raw) == (
        "변경 후보 자재를 활성 자재 기준정보에서 찾을 수 없습니다. "
        "자재 코드를 확인해 주세요."
    )
