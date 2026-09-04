from agents.workflow_target_resolution import (
    TargetCriterion,
    TargetResolutionMode,
    WorkflowTargetResolutionPlanner,
)


PLANNER = WorkflowTargetResolutionPlanner()
VERSION = "LTA400HR01-001"


def _resolve(query: str):
    return PLANNER.resolve(query, scope_version_code=VERSION)


def test_explicit_item_code_uses_user_specified_resolution():
    decision = _resolve(
        "LTA400HR01-001 P01에서 0001-200008을 변경할 때 기준과 영향을 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.mode == TargetResolutionMode.EXPLICIT
    assert decision.request.criterion == TargetCriterion.EXPLICIT
    assert decision.request.explicit_item_code == "0001-200008"
    assert decision.request.selection_mode == "USER_SPECIFIED"


def test_explicit_item_name_strips_scope_particle():
    decision = _resolve(
        "LTA400HR01-001 P01에서 SEALANT를 다른 자재로 변경할 수 있는지 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.mode == TargetResolutionMode.EXPLICIT
    assert decision.request.explicit_target_name == "SEALANT"


def test_explicit_item_name_strips_model_scope_particle():
    decision = _resolve(
        "LTA400HR01-001 P01 모델에서 SPACER를 다른 자재로 변경할 수 있는지 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.mode == TargetResolutionMode.EXPLICIT
    assert decision.request.explicit_target_name == "SPACER"


def test_highest_cost_uses_deterministic_top_one():
    decision = _resolve(
        "LTA400HR01-001 P01에서 가장 원가가 높은 자재 1개를 변경 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.mode == TargetResolutionMode.DETERMINISTIC_ANALYTICS
    assert decision.request.criterion == TargetCriterion.COST
    assert decision.request.selection_mode == "TOP_1_HIGH"


def test_lowest_cost_uses_deterministic_bottom_one():
    decision = _resolve(
        "LTA400HR01-001 P01에서 원가가 가장 낮은 자재 1개를 변경 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.criterion == TargetCriterion.COST
    assert decision.request.selection_mode == "TOP_1_LOW"


def test_commonality_uses_deterministic_top_one():
    decision = _resolve(
        "LTA400HR01-001 P01에서 공용성이 가장 높은 자재 1개를 찾아 변경 분석해줘"
    )

    assert decision.ready is True
    assert decision.request is not None
    assert decision.request.criterion == TargetCriterion.COMMONALITY
    assert decision.request.selection_mode == "TOP_1_HIGH"


def test_non_unique_rank_request_never_becomes_literal_item_name():
    decision = _resolve(
        "LTA400HR01-001 P01에서 원가가 높은 자재들을 보고 적당한 걸 변경해줘"
    )

    assert decision.ready is False
    assert decision.request is None
    assert "임의 선택하지 않습니다" in str(decision.blocked_reason)


def test_old_new_pair_is_not_auto_reduced_to_one_source_target():
    decision = _resolve(
        "LTA400HR01-001 모델 P01에서 0001-200008을 0001-200009로 교체 가능한지 분석해줘"
    )

    assert decision.ready is False
    assert decision.request is None
    assert "둘 이상" in str(decision.blocked_reason)


def test_multi_clause_knowledge_plus_change_does_not_guess_named_target():
    decision = _resolve(
        "단종 자재 교체 기준을 참고해서 SEALANT를 변경하고싶어"
    )

    assert decision.ready is False
    assert decision.request is None
