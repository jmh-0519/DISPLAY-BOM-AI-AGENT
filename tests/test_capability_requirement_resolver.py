from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_KNOWLEDGE,
    FAST_TEXT_TO_SQL,
    BomGraphGateway,
)
from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementResolver,
)
from agents.design_change_workflow_state import create_initial_design_change_state


def _gateway():
    return BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )


def _state(query, *, active_bom=None):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "active_bom_context": active_bom,
    }


def test_single_knowledge_request_remains_single_capability():
    decision = CapabilityRequirementResolver().resolve(
        "단종 자재 교체 기준이 뭐야?"
    )

    assert decision.capabilities == (Capability.RAG,)
    assert decision.composition_required is False
    assert _gateway().route(
        _state("단종 자재 교체 기준이 뭐야?")
    ) == FAST_KNOWLEDGE


def test_knowledge_wording_plus_explicit_change_requires_composition():
    query = "단종 자재 교체 기준을 참고해서 SEALANT를 변경하고싶어"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is True
    assert _gateway().route(_state(query)) == AGENT_PATH


def test_knowledge_wording_with_change_noun_but_no_directive_stays_rag_only():
    query = "단종 자재 교체 기준과 변경 원칙이 뭐야?"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (Capability.RAG,)
    assert decision.composition_required is False
    assert decision.workflow_managed is False
    assert _gateway().route(_state(query)) == FAST_KNOWLEDGE


def test_single_analytics_request_remains_text_to_sql_fast_path():
    query = "공급사별 평균 단가를 알려줘"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (Capability.TEXT_TO_SQL,)
    assert decision.composition_required is False
    assert _gateway().route(_state(query)) == FAST_TEXT_TO_SQL


def test_analytics_plus_knowledge_requires_composition():
    query = "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.TEXT_TO_SQL,
        Capability.RAG,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is False
    assert _gateway().route(_state(query)) == AGENT_PATH


def test_analytics_knowledge_and_design_change_impact_require_composition():
    query = (
        "이 모델의 원가가 높은 자재를 찾고 "
        "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
    )
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.TEXT_TO_SQL,
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is True

    active = {
        "product_id": "LTA400HR01-001",
        "plant_code": "P01",
        "source": "get_bom",
    }
    assert _gateway().route(
        _state(query, active_bom=active)
    ) == AGENT_PATH


def test_analytics_design_change_infers_mandatory_rag_evidence_dependency():
    query = (
        "LTA550HR11-001 P01 대상으로 가장 원가가 높은 자재 1개를 찾아 "
        "변경 분석해줘"
    )
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.TEXT_TO_SQL,
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is True
    assert "WORKFLOW_KNOWLEDGE_EVIDENCE_REQUIRED" in decision.reasons


def test_direct_design_change_is_not_misclassified_as_composition():
    query = "SEALANT를 변경하고싶어"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is False
    assert decision.workflow_managed is True


def test_product_cost_scan_is_a_single_workflow_capability():
    query = "모델 전체 BOM에서 원가 절감 가능한 대체 후보를 찾아줘"
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.PRODUCT_COST_SCAN,
    )
    assert decision.composition_required is False
    assert decision.workflow_managed is True


def test_capability_resolution_is_current_turn_only():
    resolver = CapabilityRequirementResolver()

    first = resolver.resolve(
        "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
    )
    second = resolver.resolve("안녕하세요")

    assert first.composition_required is True
    assert second.capabilities == (Capability.CHAT,)
    assert second.composition_required is False


def test_explicit_target_analysis_infers_rag_evidence_dependency_without_analytics():
    query = (
        "LTA400HR01-001 P01에서 0001-200008을 변경할 때 "
        "적용되는 기준과 영향을 분석해줘"
    )
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is True
    assert "WORKFLOW_KNOWLEDGE_EVIDENCE_REQUIRED" in decision.reasons


def test_named_target_read_only_analysis_infers_rag_evidence_dependency():
    query = (
        "LTA400HR01-001 P01에서 SEALANT를 다른 자재로 "
        "변경할 수 있는지 분석해줘"
    )
    decision = CapabilityRequirementResolver().resolve(query)

    assert decision.capabilities == (
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    )
    assert decision.composition_required is True
    assert decision.workflow_managed is True


def test_direct_write_like_change_remains_existing_single_capability_path():
    decision = CapabilityRequirementResolver().resolve("SEALANT를 변경하고싶어")

    assert decision.capabilities == (Capability.DESIGN_CHANGE_ANALYSIS,)
    assert decision.composition_required is False
