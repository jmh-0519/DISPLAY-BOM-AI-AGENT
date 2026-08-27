from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def test_replace_desire_language_is_explicit_change_intent():
    router = DEFAULT_DOMAIN_INTENT_ROUTER
    query = "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"

    decision = router.route(query)

    assert decision.change is True
    assert decision.intent == "PHASE3_CHANGE"
    assert router.extract_named_change_target(query) == "SEALANT"


def test_replace_request_language_variants_are_change_intent():
    router = DEFAULT_DOMAIN_INTENT_ROUTER

    assert router.is_phase3_change_request(
        "SEALANT를 변경해줘"
    ) is True
    assert router.is_phase3_change_request(
        "SEALANT를 교체하자"
    ) is True
    assert router.is_phase3_change_request(
        "SEALANT를 대체해 주세요"
    ) is True


def test_read_only_bom_query_remains_not_change_intent():
    router = DEFAULT_DOMAIN_INTENT_ROUTER

    assert router.is_phase3_change_request(
        "LTA400HR01-001 P01 BOM 보여줘"
    ) is False
    assert router.is_phase3_change_request(
        "실런트 수량은 몇이야?"
    ) is False
