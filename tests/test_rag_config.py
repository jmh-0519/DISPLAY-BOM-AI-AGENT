from __future__ import annotations

import pytest

from rag.config import RagSettings


def _set_required(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "embedding-small")


def test_rag_settings_reads_embedding_and_vector_config(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("RAG_VECTOR_STORE_PATH", "tmp/vector")
    monkeypatch.setenv("RAG_COLLECTION_NAME", "knowledge_test")
    monkeypatch.setenv("RAG_EMBEDDING_BATCH_SIZE", "32")

    settings = RagSettings.from_env()

    assert settings.azure_openai_endpoint == "https://example.openai.azure.com"
    assert settings.azure_openai_embedding_deployment == "embedding-small"
    assert settings.vector_store_path.as_posix() == "tmp/vector"
    assert settings.collection_name == "knowledge_test"
    assert settings.embedding_batch_size == 32


def test_rag_settings_requires_embedding_deployment(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    with pytest.raises(ValueError, match="azure_openai_embedding_deployment"):
        RagSettings.from_env()
