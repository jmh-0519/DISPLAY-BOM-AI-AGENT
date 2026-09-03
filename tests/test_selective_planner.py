import pytest

from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementDecision,
    CapabilityRequirementResolver,
)
from agents.selective_planner import PlanStepMode, SelectivePlanner


def test_single_capability_bypasses_planner():
    planner = SelectivePlanner()
    resolver = CapabilityRequirementResolver()
    for query in (
        "단종 자재 교체 기준이 뭐야?",
        "공급사별 평균 단가를 알려줘",
        "SEALANT를 변경하고싶어",
    ):
        req = resolver.resolve(query)
        assert req.composition_required is False
        assert planner.plan_if_needed(query, requirement=req) is None


def test_analytics_plus_rag_plan_is_read_only_and_not_executable():
    query = "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
    req = CapabilityRequirementResolver().resolve(query)
    plan = SelectivePlanner().plan_if_needed(query, requirement=req)

    assert plan is not None
    assert plan.capability_names == ("TEXT_TO_SQL", "RAG")
    assert [s.mode for s in plan.steps] == [
        PlanStepMode.READ_ONLY_ANALYTICS,
        PlanStepMode.READ_ONLY_KNOWLEDGE,
    ]
    assert plan.execution_enabled is False
    assert plan.write_authority_granted is False


def test_design_change_analysis_is_last_and_depends_on_prior_evidence():
    query = (
        "이 모델의 원가가 높은 자재를 찾고 "
        "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
    )
    req = CapabilityRequirementResolver().resolve(query)
    plan = SelectivePlanner().plan_if_needed(query, requirement=req)

    assert plan is not None
    assert plan.capability_names == (
        "TEXT_TO_SQL", "RAG", "DESIGN_CHANGE_ANALYSIS"
    )
    assert plan.steps[-1].mode == PlanStepMode.WORKFLOW_ANALYSIS_ONLY
    assert plan.steps[-1].depends_on == tuple(
        s.step_id for s in plan.steps[:-1]
    )
    assert plan.write_authority_granted is False


def test_knowledge_plus_explicit_change_has_analysis_only_authority():
    query = "단종 자재 교체 기준을 참고해서 SEALANT를 변경하고싶어"
    req = CapabilityRequirementResolver().resolve(query)
    plan = SelectivePlanner().plan_if_needed(query, requirement=req)

    assert plan is not None
    assert plan.capability_names == ("RAG", "DESIGN_CHANGE_ANALYSIS")
    assert plan.steps[-1].depends_on == (plan.steps[0].step_id,)
    assert all(
        not s.request_creation_allowed
        and not s.approval_allowed
        and not s.production_write_allowed
        for s in plan.steps
    )


def test_build_plan_rejects_single_capability_requirement():
    req = CapabilityRequirementDecision(
        capabilities=(Capability.RAG,),
        composition_required=False,
        workflow_managed=False,
    )
    with pytest.raises(ValueError):
        SelectivePlanner().build_plan("기준 알려줘", req)


def test_build_plan_rejects_agent_reasoning_composition():
    req = CapabilityRequirementDecision(
        capabilities=(Capability.RAG, Capability.AGENT_REASONING),
        composition_required=True,
        workflow_managed=False,
    )
    with pytest.raises(ValueError):
        SelectivePlanner().build_plan("복합 요청", req)
