from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def test_whole_quoted_generic_add_has_no_target_name():
    query = '"LTA400HR01-001 P01 모델에 자재를 추가하고 싶어"'
    assert DEFAULT_DOMAIN_INTENT_ROUTER.extract_add_target_name(query) is None


def test_quoted_real_add_target_is_unwrapped():
    query = 'LTA400HR01-001 P01 모델에 "SEALANT" 자재를 추가하고 싶어'
    assert DEFAULT_DOMAIN_INTENT_ROUTER.extract_add_target_name(query) == "SEALANT"


def test_multi_hyphen_assy_code_remains_whole():
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("AS-FA-001") == ["AS-FA-001"]
