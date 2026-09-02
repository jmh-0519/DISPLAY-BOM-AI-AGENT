from ontology.context_contract import (
    CONTEXT_FIELD_POLICIES,
    ContextInheritanceMode,
    ContextSource,
)


def test_context_contract_covers_core_fields():
    assert {
        "version_code",
        "plant_code",
        "target_item_code",
        "target_item_type",
        "target_item_name",
        "business_intent",
        "action_type",
        "user_goal",
        "optimization_criterion",
        "analysis_id",
        "request_id",
        "workflow_step",
        "evidence",
    } <= set(CONTEXT_FIELD_POLICIES)


def test_intent_and_goal_are_current_turn_only():
    assert (
        CONTEXT_FIELD_POLICIES["business_intent"].inheritance_mode
        == ContextInheritanceMode.CURRENT_TURN_ONLY
    )
    assert (
        CONTEXT_FIELD_POLICIES["user_goal"].allowed_sources
        == (ContextSource.CURRENT_TURN,)
    )


def test_workflow_identity_never_comes_from_conversation_history():
    for field_name in ("analysis_id", "request_id", "workflow_step"):
        policy = CONTEXT_FIELD_POLICIES[field_name]
        assert policy.inheritance_mode == ContextInheritanceMode.WORKFLOW_ONLY
        assert policy.allowed_sources == (
            ContextSource.DESIGN_CHANGE_WORKFLOW,
        )


def test_target_cannot_be_inherited_from_active_bom_alone():
    for field_name in (
        "target_item_code",
        "target_item_type",
        "target_item_name",
    ):
        assert (
            ContextSource.ACTIVE_BOM
            not in CONTEXT_FIELD_POLICIES[field_name].allowed_sources
        )


def test_evidence_requires_actual_retrieval_or_tool_result():
    policy = CONTEXT_FIELD_POLICIES["evidence"]
    assert policy.inheritance_mode == ContextInheritanceMode.TOOL_EVIDENCE_ONLY
    assert ContextSource.CURRENT_TURN not in policy.allowed_sources
    assert ContextSource.ACTIVE_BOM not in policy.allowed_sources
