from ontology.context_semantics import (
    ContextSemanticResolver,
    RelativeReferenceType,
    ScopeRelation,
)


def _workflow(version="LTA400HR01-001", plant="P01"):
    return {
        "current_step": "ANALYSIS_READY",
        "analysis_request": {
            "version_code": version,
            "plant_code": plant,
        },
        "plant_code": plant,
    }


def test_relative_reference_classifier_covers_model_bom_item_assy_and_analysis():
    resolver = ContextSemanticResolver()

    assert resolver.classify_relative_references("이 모델에서 분석해줘").references == (
        RelativeReferenceType.MODEL_SCOPE,
    )
    assert resolver.classify_relative_references("해당 BOM에서 찾아줘").references == (
        RelativeReferenceType.BOM_SCOPE,
    )
    assert resolver.classify_relative_references("방금 본 자재를 변경 분석해줘").references == (
        RelativeReferenceType.TARGET_ITEM,
    )
    assert resolver.classify_relative_references("이 ASSY를 변경 분석해줘").references == (
        RelativeReferenceType.TARGET_ASSY,
    )
    analysis = resolver.classify_relative_references("기존 분석 결과를 설명해줘")
    assert analysis.references == (RelativeReferenceType.WORKFLOW_ANALYSIS,)
    assert analysis.workflow_only_reference is True
    assert analysis.requires_scope_alignment is False


def test_scope_comparison_is_deterministic_and_requires_complete_pair():
    resolver = ContextSemanticResolver()
    active = {"product_id": "LTA400HR01-001", "plant_code": "P01"}

    relation, active_scope, workflow_scope = resolver.compare_runtime_scopes(
        active_bom_context=active,
        workflow_state=_workflow(),
    )
    assert relation == ScopeRelation.SAME
    assert active_scope.key == "LTA400HR01-001/P01"
    assert workflow_scope.key == "LTA400HR01-001/P01"

    relation, _, workflow_scope = resolver.compare_runtime_scopes(
        active_bom_context=active,
        workflow_state=_workflow("LTA550HR11-001", "P01"),
    )
    assert relation == ScopeRelation.DIFFERENT
    assert workflow_scope.key == "LTA550HR11-001/P01"

    relation, _, _ = resolver.compare_runtime_scopes(
        active_bom_context={"product_id": "LTA400HR01-001"},
        workflow_state=_workflow(),
    )
    assert relation == ScopeRelation.INCOMPLETE
