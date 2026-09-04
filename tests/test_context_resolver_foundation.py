from ontology.context_contract import (
    ContextAuthority,
    ContextPurpose,
    ContextSource,
)
from ontology.context_resolver import (
    ContextResolutionInput,
    DomainContextResolverFoundation,
)


def _resolver():
    return DomainContextResolverFoundation()


def _active_bom():
    return {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }


def _workflow():
    return {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "request_id": None,
        "plant_code": "P02",
        "analysis_request": {
            "version_code": "LTA750HR11-001",
            "plant_code": "P02",
        },
    }


def test_inheritance_is_opt_in_by_default():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            active_bom_context=_active_bom(),
            workflow_state=_workflow(),
        )
    )

    assert context.version_code is None
    assert context.plant_code is None


def test_active_bom_scope_can_be_inherited_with_provenance():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            active_bom_context=_active_bom(),
            allow_active_bom_scope=True,
        )
    )

    assert context.version_code.value == "LTA400HR01-001"
    assert context.plant_code.value == "P01"
    assert context.version_code.source == ContextSource.ACTIVE_BOM
    assert context.version_code.authority == ContextAuthority.GRAPH_STATE
    assert context.version_code.inherited is True


def test_explicit_model_declares_fresh_scope_and_blocks_old_plant_inheritance():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            explicit_version_code="LTA400HR01-001",
            active_bom_context=_active_bom(),
            allow_active_bom_scope=True,
        )
    )

    assert context.version_code.value == "LTA400HR01-001"
    assert context.version_code.source == ContextSource.CURRENT_TURN
    assert context.plant_code is None


def test_explicit_different_plant_does_not_mix_with_old_model_scope():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            explicit_plant_code="P02",
            active_bom_context=_active_bom(),
            allow_active_bom_scope=True,
        )
    )

    assert context.version_code is None
    assert context.plant_code.value == "P02"
    assert context.plant_code.source == ContextSource.CURRENT_TURN


def test_explicit_same_plant_may_reuse_active_model_when_caller_allows_it():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            explicit_plant_code="P01",
            active_bom_context=_active_bom(),
            allow_active_bom_scope=True,
        )
    )

    assert context.version_code.value == "LTA400HR01-001"
    assert context.version_code.source == ContextSource.ACTIVE_BOM
    assert context.plant_code.value == "P01"
    assert context.plant_code.source == ContextSource.CURRENT_TURN


def test_design_change_prefers_workflow_scope_over_active_bom_when_both_allowed():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            active_bom_context=_active_bom(),
            workflow_state=_workflow(),
            allow_active_bom_scope=True,
            allow_workflow_scope=True,
        )
    )

    assert context.version_code.value == "LTA750HR11-001"
    assert context.plant_code.value == "P02"
    assert context.version_code.source == ContextSource.DESIGN_CHANGE_WORKFLOW


def test_read_only_prefers_current_active_bom_over_workflow_scope():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.READ_ONLY,
            active_bom_context=_active_bom(),
            workflow_state=_workflow(),
            allow_active_bom_scope=True,
            allow_workflow_scope=True,
        )
    )

    assert context.version_code.value == "LTA400HR01-001"
    assert context.plant_code.value == "P01"
    assert context.version_code.source == ContextSource.ACTIVE_BOM


def test_target_and_action_are_never_guessed_from_active_or_workflow_context():
    workflow = _workflow()
    workflow["old_material_id"] = "0001-200010"
    workflow["actions"] = [{
        "action_type": "REPLACE",
        "old_item_code": "0001-200010",
    }]

    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            active_bom_context=_active_bom(),
            workflow_state=workflow,
            allow_active_bom_scope=True,
            allow_workflow_scope=True,
        )
    )

    assert context.target_item_code is None
    assert context.action_type is None


def test_current_turn_target_and_action_are_recorded_with_user_provenance():
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            explicit_target_item_code="0001-200010",
            explicit_target_item_type="material",
            action_type="replace",
            business_intent="design_change",
        )
    )

    assert context.target_item_code.value == "0001-200010"
    assert context.target_item_type.value == "MATERIAL"
    assert context.action_type.value == "REPLACE"
    assert context.business_intent.value == "DESIGN_CHANGE"
    assert context.target_item_code.source == ContextSource.CURRENT_TURN


def test_workflow_ids_are_observational_and_workflow_authoritative():
    context = _resolver().resolve(
        ContextResolutionInput(
            workflow_state=_workflow(),
        )
    )

    assert context.analysis_id.value == "ANA-1"
    assert context.analysis_id.source == ContextSource.DESIGN_CHANGE_WORKFLOW
    assert context.analysis_id.authority == ContextAuthority.WORKFLOW_STATE
    assert context.request_id is None
    assert context.workflow_step.value == "ANALYSIS_READY"


def test_workflow_target_edge_is_opt_in_and_preserves_exact_parent_location():
    workflow = _workflow()
    workflow["actions"] = [{
        "action_type": "REPLACE",
        "target_type": "MATERIAL",
        "old_item_code": "0001-200008",
        "parent_item_code": "LJ94-100003",
        "location_code": "ALL",
    }]
    workflow["analysis_context"] = {
        "version_code": "LTA750HR11-001",
        "plant_code": "P02",
        "target_item": {
            "item_code": "0001-200008",
            "item_name": "SPACER",
        },
    }

    default_context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            workflow_state=workflow,
            allow_workflow_scope=True,
        )
    )
    assert default_context.target_item_code is None
    assert default_context.target_parent_item_code is None

    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            workflow_state=workflow,
            allow_workflow_scope=True,
            allow_workflow_target_context=True,
        )
    )

    assert context.target_item_code.value == "0001-200008"
    assert context.target_item_name.value == "SPACER"
    assert context.target_item_type.value == "MATERIAL"
    assert context.target_parent_item_code.value == "LJ94-100003"
    assert context.target_location_code.value == "ALL"
    assert context.action_type.value == "REPLACE"
    assert context.target_item_code.source == ContextSource.DESIGN_CHANGE_WORKFLOW
    assert context.target_parent_item_code.source == ContextSource.DESIGN_CHANGE_WORKFLOW


def test_multi_action_workflow_never_collapses_to_one_target_edge():
    workflow = _workflow()
    workflow["actions"] = [
        {"action_type": "REPLACE", "old_item_code": "0001-200008"},
        {"action_type": "REPLACE", "old_item_code": "0001-200009"},
    ]
    context = _resolver().resolve(
        ContextResolutionInput(
            purpose=ContextPurpose.DESIGN_CHANGE,
            workflow_state=workflow,
            allow_workflow_scope=True,
            allow_workflow_target_context=True,
        )
    )
    assert context.target_item_code is None
    assert context.target_parent_item_code is None
    assert context.target_location_code is None
    assert context.action_type is None
