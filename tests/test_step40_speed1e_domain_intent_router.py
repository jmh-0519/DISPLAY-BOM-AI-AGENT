from agents.domain_intent_router import DomainIntentRouter


ROUTER = DomainIntentRouter()


def test_where_used_routes_to_fast_path_without_llm():
    decision = ROUTER.route("P01에서 0001-310901 포함한 모델 알려줘")

    assert decision.intent == "WHERE_USED"
    assert decision.fast_path_candidate is True
    assert decision.where_used is True
    assert decision.plant_code == "P01"
    assert decision.where_used_item_code == "0001-310901"
    assert decision.phase3_mode is False


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

    assert decision.intent == "PHASE3_CHANGE"
    assert decision.fast_path_candidate is False
    assert decision.change is True
    assert decision.quantity_change is True
    assert decision.where_used is False
    assert decision.phase3_mode is True
    assert decision.new_quantity is None


def test_explicit_quantity_is_extracted_by_router():
    decision = ROUTER.route(
        "LTA400HR01-001 P01 모델에서 LJ94-100006 자재 수량을 3으로 변경해줘"
    )

    assert decision.intent == "PHASE3_CHANGE"
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
    assert ROUTER.route(current).intent == "PHASE3_CHANGE"


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
