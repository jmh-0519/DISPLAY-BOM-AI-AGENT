from agents.domain_intent_router import DomainIntentRouter


def test_plant_only_selection_is_explicit_slot_value():
    router = DomainIntentRouter()

    assert router.is_plant_only_selection("P01") is True
    assert router.is_plant_only_selection("P01에서 변경해줘") is False


def test_explicit_old_new_pair_is_current_design_change_analysis():
    router = DomainIntentRouter()

    decision = router.route(
        "MODEL-789의 1234-567890을 1234-567891로 교체 가능한지 분석해줘"
    )

    assert decision.design_change_mode is True
    assert decision.recommendation is True
    assert decision.change is False
    assert decision.intent == "DESIGN_CHANGE_RECOMMENDATION"

    direct_change = router.route(
        "MODEL-789의 1234-567890을 1234-567891로 교체해줘"
    )
    assert direct_change.design_change_mode is True
    assert direct_change.recommendation is False
    assert direct_change.change is True
    assert direct_change.intent == "DESIGN_CHANGE"
