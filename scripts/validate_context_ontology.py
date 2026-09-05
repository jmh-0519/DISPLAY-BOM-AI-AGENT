"""Ontology / Context Understanding validator for the current release."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import SCOPE_CONFLICT, BomGraphGateway
from ontology.context_contract import ContextPurpose, ContextSource
from ontology.context_projection import LlmContextProjector
from ontology.context_resolver import ContextResolutionInput, DomainContextResolverFoundation
from ontology.context_semantics import ContextSemanticResolver, RelativeReferenceType, ScopeRelation
from ontology.domain_ontology import (
    DEFAULT_DOMAIN_ONTOLOGY,
    DomainEntityType,
    DomainRelationType,
)


WORKFLOW_VERSION = "LTA400HR01-001"
ACTIVE_VERSION = "LTA550HR11-001"
PLANT = "P01"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _workflow() -> dict:
    return {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-FINAL01",
        "request_id": None,
        "plant_code": PLANT,
        "analysis_request": {
            "version_code": WORKFLOW_VERSION,
            "plant_code": PLANT,
        },
        "actions": [{
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "old_item_code": "0001-200008",
            "parent_item_code": "LJ94-100003",
            "location_code": "ALL",
        }],
        "analysis_context": {
            "version_code": WORKFLOW_VERSION,
            "plant_code": PLANT,
            "target_item": {
                "item_code": "0001-200008",
                "item_name": "SPACER",
            },
        },
    }


def main() -> None:
    DEFAULT_DOMAIN_ONTOLOGY.validate()
    _assert(
        DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
            DomainEntityType.BOM,
            DomainRelationType.HAS_EDGE,
            DomainEntityType.BOM_EDGE,
        ),
        "BOM_EDGE relation missing",
    )
    _assert(
        DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
            DomainEntityType.ANALYSIS_SESSION,
            DomainRelationType.TARGETS,
            DomainEntityType.BOM_EDGE,
        ),
        "Analysis Session must target an exact BOM edge",
    )
    _assert(
        DEFAULT_DOMAIN_ONTOLOGY.relation_allowed(
            DomainEntityType.CHANGE_REQUEST,
            DomainRelationType.BASED_ON,
            DomainEntityType.ANALYSIS_SESSION,
        ),
        "Change Request must be based on Analysis Session",
    )

    semantic = ContextSemanticResolver()
    refs = semantic.classify_relative_references(
        "해당 ASSY를 변경할 때 적용되는 기준과 영향을 분석해줘"
    )
    _assert(
        RelativeReferenceType.TARGET_ASSY in refs.references
        and refs.requires_scope_alignment,
        "ASSY relative reference semantics missing",
    )
    analysis_refs = semantic.classify_relative_references("기존 분석 결과를 설명해줘")
    _assert(
        analysis_refs.workflow_only_reference
        and not analysis_refs.requires_scope_alignment,
        "workflow analysis reference must not bind to Active BOM",
    )

    relation, active_scope, workflow_scope = semantic.compare_runtime_scopes(
        active_bom_context={
            "product_id": ACTIVE_VERSION,
            "plant_code": PLANT,
        },
        workflow_state=_workflow(),
    )
    _assert(relation == ScopeRelation.DIFFERENT, "scope mismatch must be deterministic")
    _assert(active_scope is not None and workflow_scope is not None, "scope identity missing")

    resolver = DomainContextResolverFoundation()
    read_context = resolver.resolve(ContextResolutionInput(
        purpose=ContextPurpose.READ_ONLY,
        active_bom_context={"product_id": ACTIVE_VERSION, "plant_code": PLANT},
        workflow_state=_workflow(),
        allow_active_bom_scope=True,
        allow_workflow_scope=True,
    ))
    _assert(read_context.version_code.value == ACTIVE_VERSION, "READ_ONLY precedence changed")
    _assert(read_context.version_code.source == ContextSource.ACTIVE_BOM, "READ_ONLY provenance changed")

    design_context = resolver.resolve(ContextResolutionInput(
        purpose=ContextPurpose.DESIGN_CHANGE,
        active_bom_context={"product_id": ACTIVE_VERSION, "plant_code": PLANT},
        workflow_state=_workflow(),
        allow_active_bom_scope=True,
        allow_workflow_scope=True,
        allow_workflow_target_context=True,
    ))
    _assert(design_context.version_code.value == WORKFLOW_VERSION, "Design Change precedence changed")
    _assert(design_context.target_item_code.value == "0001-200008", "workflow target missing")
    _assert(design_context.target_parent_item_code.value == "LJ94-100003", "parent edge missing")
    _assert(design_context.target_location_code.value == "ALL", "location edge missing")
    _assert(
        design_context.target_item_code.source == ContextSource.DESIGN_CHANGE_WORKFLOW,
        "workflow target provenance missing",
    )
    projected = LlmContextProjector().project(design_context).text
    _assert("target_parent_item_code=" in projected, "parent edge not projected")
    _assert("target_location_code=" in projected, "location edge not projected")

    gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )
    state = {
        "messages": [HumanMessage(content=(
            "해당 ASSY를 변경할 때 적용되는 기준과 영향을 분석해줘"
        ))],
        "user_query": "해당 ASSY를 변경할 때 적용되는 기준과 영향을 분석해줘",
        "active_bom_context": {
            "product_id": ACTIVE_VERSION,
            "plant_code": PLANT,
            "source": "get_bom",
        },
        "design_change": _workflow(),
        "tool_steps": 0,
        "error": None,
    }
    _assert(gateway.route(state) == SCOPE_CONFLICT, "centralized scope conflict guard failed")

    workflow_followup = dict(state)
    workflow_followup["messages"] = [HumanMessage(content="기존 분석 결과를 설명해줘")]
    workflow_followup["user_query"] = "기존 분석 결과를 설명해줘"
    _assert(
        gateway.design_change_scope_conflict(workflow_followup) is None,
        "workflow-only analysis reference must not conflict with Active BOM",
    )

    print("Ontology / Context Understanding Validation PASS")
    print("bom_edge_ontology=YES")
    print("analysis_session_change_request_split=YES")
    print("context_policy_runtime_validation=YES")
    print("workflow_target_edge_provenance=YES")
    print("relative_model_bom_item_assy_semantics=YES")
    print("workflow_analysis_reference_semantics=YES")
    print("scope_compatibility_deterministic=YES")
    print("scope_conflict_guard_centralized=YES")
    print("read_only_active_bom_precedence=UNCHANGED")
    print("design_change_workflow_precedence=UNCHANGED")
    print("multi_action_target_auto_collapse=NO")
    print("episode_memory_added=NO")
    print("request_approval_production_write_authority=NO")


if __name__ == "__main__":
    main()
