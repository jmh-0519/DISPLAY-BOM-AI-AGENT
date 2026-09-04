from agents.domain_intent_router import DomainIntentRouter


ROUTER = DomainIntentRouter()


def test_where_used_routes_to_fast_path_without_llm():
    decision = ROUTER.route("P01에서 0001-310901 포함한 모델 알려줘")

    assert decision.intent == "WHERE_USED"
    assert decision.fast_path_candidate is True
    assert decision.where_used is True
    assert decision.plant_code == "P01"
    assert decision.where_used_item_code == "0001-310901"
    assert decision.design_change_mode is False


def test_plain_bom_routes_to_fast_path_without_llm():
    decision = ROUTER.route("LTA400HR01-001 P01 BOM 보여줘")

    assert decision.intent == "BOM_READ"
    assert decision.fast_path_candidate is True
    assert decision.plain_bom is True
    assert decision.plant_code == "P01"
    assert decision.reference_code == "LTA400HR01-001"


def test_quantity_change_takes_precedence_over_read_intent():
    decision = ROUTER.route(
        "LTA400HR01-001 P01 모델에서 LJ94-100006 자재의 수량을 바꾸고싶어"
    )

    assert decision.intent == "DESIGN_CHANGE"
    assert decision.fast_path_candidate is False
    assert decision.change is True
    assert decision.quantity_change is True
    assert decision.where_used is False
    assert decision.design_change_mode is True
    assert decision.new_quantity is None


def test_explicit_quantity_is_extracted_by_router():
    decision = ROUTER.route(
        "LTA400HR01-001 P01 모델에서 LJ94-100006 자재 수량을 3으로 변경해줘"
    )

    assert decision.intent == "DESIGN_CHANGE"
    assert decision.quantity_change is True
    assert decision.new_quantity == 3.0


def test_ambiguous_request_falls_back_to_llm():
    decision = ROUTER.route("이 제품 좀 검토해줘")

    assert decision.intent == "LLM_FALLBACK"
    assert decision.fast_path_candidate is False


def test_current_turn_only_intent_is_not_inherited_from_previous_where_used():
    previous = "P01에서 0001-310901 포함한 모델 알려줘"
    current = "LTA400HR01-001 P01 모델에서 LJ94-100006 자재의 수량을 바꾸고싶어"

    assert ROUTER.route(previous).intent == "WHERE_USED"
    assert ROUTER.route(current).intent == "DESIGN_CHANGE"


def test_candidate_free_fail_followup_is_analysis_explain():
    workflow = {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "request_id": None,
        "candidates": [],
        "actions": [{"action_type": "QUANTITY_CHANGE", "evaluation_status": "FAIL"}],
    }

    intent = ROUTER.classify_analysis_follow_up(
        "왜 fail 이야?",
        workflow,
        active_steps={"ANALYSIS_READY"},
    )

    assert intent == "EXPLAIN_ANALYSIS"


def test_explicit_named_replace_analysis_is_read_only_recommendation():
    query = "LTA400HR01-001 P01에서 SEALANT를 다른 자재로 변경할 수 있는지 분석해줘"
    decision = ROUTER.route(query)

    assert decision.intent == "DESIGN_CHANGE_RECOMMENDATION"
    assert decision.recommendation is True
    assert decision.change is False
    assert decision.design_change_mode is True


def test_commonality_comparison_criterion_is_detected():
    query = "LTA400HR01-001 P01에서 공용성이 가장 높은 자재 1개를 찾아 변경 분석해줘"

    assert ROUTER.comparison_criterion(query) == "COMMONALITY"
    assert ROUTER.route(query).intent == "DESIGN_CHANGE_RECOMMENDATION"


def test_change_policy_question_is_not_a_write_intent():
    decision = ROUTER.route("단종 자재 교체 기준이 뭐야?")

    assert decision.intent == "LLM_FALLBACK"
    assert decision.change is False
    assert decision.recommendation is False
