import pytest

from core.settings import Settings


def test_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AZURE_OPENAI_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://example.com/",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_API_VERSION",
        "2024-12-01-preview",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_DEPLOYMENT",
        "gpt-4.1-mini",
    )

    settings = Settings.from_env()

    assert settings.azure_openai_api_key == "test-key"
    assert (
        settings.azure_openai_endpoint
        == "https://example.com"
    )
    assert (
        settings.azure_openai_api_version
        == "2024-12-01-preview"
    )
    assert (
        settings.azure_openai_deployment
        == "gpt-4.1-mini"
    )


def test_settings_rejects_missing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AZURE_OPENAI_API_KEY",
        "",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT",
        "https://example.com",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_API_VERSION",
        "2024-12-01-preview",
    )
    monkeypatch.setenv(
        "AZURE_OPENAI_DEPLOYMENT",
        "gpt-4.1-mini",
    )

    with pytest.raises(
        ValueError,
        match="필수 환경설정이 누락되었습니다",
    ):
        Settings.from_env()