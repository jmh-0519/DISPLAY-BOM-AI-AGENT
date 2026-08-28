from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def test_whole_quoted_generic_add_has_no_target_name():
    query = '"LTA400HR01-001 P01 모델에 자재를 추가하고 싶어"'
    assert DEFAULT_DOMAIN_INTENT_ROUTER.extract_add_target_name(query) is None


def test_quoted_real_add_target_is_unwrapped():
    query = 'LTA400HR01-001 P01 모델에 "SEALANT" 자재를 추가하고 싶어'
    assert DEFAULT_DOMAIN_INTENT_ROUTER.extract_add_target_name(query) == "SEALANT"


def test_multi_hyphen_assy_code_remains_whole():
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("AS-FA-001") == ["AS-FA-001"]


def test_existing_item_code_formats_remain_supported():
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("LTA400HR01-001") == ["LTA400HR01-001"]
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("LJ94-100006") == ["LJ94-100006"]
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("0001-310901") == ["0001-310901"]


def test_hyphenated_plain_word_is_not_item_code():
    assert DEFAULT_DOMAIN_INTENT_ROUTER.item_codes("WHERE-USED") == []


def test_parent_extraction_preserves_full_multi_segment_assy_code():
    query = "LTA400HR01-001 P01 모델에서 AS-FA-001 하위에 BIN ASSY를 추가해줘"
    assert (
        DEFAULT_DOMAIN_INTENT_ROUTER.extract_add_parent_code(
            query,
            version_code="LTA400HR01-001",
        )
        == "AS-FA-001"
    )
