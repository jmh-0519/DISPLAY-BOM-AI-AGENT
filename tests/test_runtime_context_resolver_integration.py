from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import BomGraphGateway
from agents.design_change_workflow_state import create_initial_design_change_state
from ontology.context_contract import ContextSource


def _active_bom():
    return {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }


def _workflow():
    state = create_initial_design_change_state()
    state.update({
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "plant_code": "P02",
        "analysis_request": {
            "version_code": "LTA750HR11-001",
            "plant_code": "P02",
        },
    })
    return state


def test_gateway_resolved_read_context_prefers_active_bom_with_provenance():
    context = BomGraphGateway.resolve_read_context({
        "messages": [HumanMessage(content="실런트 자재수량은 몇이야?")],
        "active_bom_context": _active_bom(),
        "design_change": _workflow(),
    })

    assert context.version_code.value == "LTA400HR01-001"
    assert context.plant_code.value == "P01"
    assert context.version_code.source == ContextSource.ACTIVE_BOM
    assert context.plant_code.source == ContextSource.ACTIVE_BOM


def test_gateway_resolved_read_context_falls_back_to_workflow_scope():
    context = BomGraphGateway.resolve_read_context({
        "messages": [HumanMessage(content="실런트 자재수량은 몇이야?")],
        "active_bom_context": None,
        "design_change": _workflow(),
    })

    assert context.version_code.value == "LTA750HR11-001"
    assert context.plant_code.value == "P02"
    assert context.version_code.source == ContextSource.DESIGN_CHANGE_WORKFLOW


def test_read_scope_context_keeps_existing_public_dictionary_contract():
    scope = BomGraphGateway.read_scope_context({
        "active_bom_context": _active_bom(),
        "design_change": _workflow(),
    })

    assert scope == {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
    }


def test_gateway_allows_only_implicit_active_bom_continuation():
    gateway = BomGraphGateway()

    assert gateway.can_inherit_active_bom_context(
        "SEALANT를 변경하고싶어",
        _active_bom(),
    ) is True

    assert gateway.can_inherit_active_bom_context(
        "LTA400HR01-001 모델에서 SEALANT를 변경하고싶어",
        _active_bom(),
    ) is False

    assert gateway.can_inherit_active_bom_context(
        "P02에서 SEALANT를 변경하고싶어",
        _active_bom(),
    ) is False


def test_agent_change_scope_uses_resolver_without_changing_existing_behavior():
    node = BomAgentNode(Mock(), Mock(), "skill")

    enriched = node._inherit_active_bom_context_for_change(
        user_query="SEALANT를 변경하고싶어",
        workflow_state=create_initial_design_change_state(),
        active_bom_context=_active_bom(),
    )

    assert enriched == "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"


def test_agent_same_plant_followup_inherits_model_only_once():
    node = BomAgentNode(Mock(), Mock(), "skill")

    enriched = node._inherit_active_bom_context_for_change(
        user_query="P01에서 SEALANT를 변경하고싶어",
        workflow_state=create_initial_design_change_state(),
        active_bom_context=_active_bom(),
    )

    assert enriched.startswith("LTA400HR01-001 모델에서")
    assert enriched.count("P01") == 1


def test_agent_explicit_model_or_different_plant_never_inherits_stale_scope():
    node = BomAgentNode(Mock(), Mock(), "skill")

    explicit_model = "LTA400HR01-001 모델에서 SEALANT를 변경하고싶어"
    assert node._inherit_active_bom_context_for_change(
        user_query=explicit_model,
        workflow_state=create_initial_design_change_state(),
        active_bom_context=_active_bom(),
    ) == explicit_model

    different_plant = "P02에서 SEALANT를 변경하고싶어"
    assert node._inherit_active_bom_context_for_change(
        user_query=different_plant,
        workflow_state=create_initial_design_change_state(),
        active_bom_context=_active_bom(),
    ) == different_plant


def test_active_design_change_workflow_still_blocks_active_bom_reinheritance():
    node = BomAgentNode(Mock(), Mock(), "skill")
    workflow = _workflow()

    query = "SEALANT를 변경하고싶어"
    assert node._inherit_active_bom_context_for_change(
        user_query=query,
        workflow_state=workflow,
        active_bom_context=_active_bom(),
    ) == query


def test_agent_followup_projection_includes_workflow_target_edge_only_when_opted_in():
    node = BomAgentNode(Mock(), Mock(), "skill")
    workflow = _workflow()
    workflow.update({
        "plant_code": "P02",
        "analysis_request": {
            "version_code": "LTA750HR11-001",
            "plant_code": "P02",
        },
        "actions": [{
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "old_item_code": "0001-200008",
            "parent_item_code": "LJ94-100003",
            "location_code": "ALL",
        }],
        "analysis_context": {
            "version_code": "LTA750HR11-001",
            "plant_code": "P02",
            "target_item": {
                "item_code": "0001-200008",
                "item_name": "SPACER",
            },
        },
    })
    query = "왜 후보가 FAIL이야?"
    decision = node.domain_intent_router.route(
        query,
        workflow_active=True,
        workflow_state=workflow,
    )

    result = node._build_llm_context_projection(
        messages=[HumanMessage(content=query)],
        raw_user_query=query,
        state={
            "active_bom_context": None,
            "design_change": workflow,
        },
        workflow_state=workflow,
        routing_decision=decision,
        routing_step="ANALYSIS_READY",
        follow_up_intent="EXPLAIN_ANALYSIS",
        design_change_mode=True,
        product_cost_scan_intent=False,
    )

    assert '"value":"0001-200008"' in result.text
    assert '"value":"LJ94-100003"' in result.text
    assert '"value":"ALL"' in result.text
    assert '"source":"DESIGN_CHANGE_WORKFLOW"' in result.text
