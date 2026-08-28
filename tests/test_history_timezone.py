from core.datetime_display import format_utc_timestamp


def test_sqlite_current_timestamp_is_displayed_as_kst():
    assert (
        format_utc_timestamp("2026-08-25 08:56:10")
        == "2026-08-25 17:56:10"
    )


def test_explicit_utc_iso_timestamp_is_displayed_as_kst():
    assert (
        format_utc_timestamp("2026-08-25T08:56:10+00:00")
        == "2026-08-25 17:56:10"
    )


def test_timestamp_with_existing_offset_is_converted_to_kst():
    assert (
        format_utc_timestamp("2026-08-25T10:56:10+02:00")
        == "2026-08-25 17:56:10"
    )


def test_empty_timestamp_is_safe():
    assert format_utc_timestamp(None) == "-"
    assert format_utc_timestamp("") == "-"


def test_unexpected_legacy_timestamp_is_preserved():
    assert format_utc_timestamp("legacy-value") == "legacy-value"
