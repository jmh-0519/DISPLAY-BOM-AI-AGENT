from agents.domain_intent_router import DomainIntentRouter


def test_plant_only_selection_is_explicit_slot_value():
    router = DomainIntentRouter()

    assert router.is_plant_only_selection("P01") is True
    assert router.is_plant_only_selection("P01에서 변경해줘") is False


def test_explicit_old_new_pair_analysis_is_not_candidate_discovery():
    router = DomainIntentRouter()

    assert router.is_explicit_replacement_pair_analysis(
        "MODEL-789의 1234-567890을 1234-567891로 교체 가능한지 분석해줘"
    ) is True

    assert router.is_explicit_replacement_pair_analysis(
        "MODEL-789의 1234-567890을 1234-567891로 교체해줘"
    ) is False
