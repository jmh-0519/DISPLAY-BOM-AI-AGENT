from __future__ import annotations

from types import SimpleNamespace

from rag.config import RagSettings
from rag.embedding_client import AzureOpenAIEmbeddingClient


class FakeEmbeddingsApi:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input):
        self.calls.append((model, list(input)))
        data = [
            SimpleNamespace(index=index, embedding=[float(index + 1), 0.5])
            for index, _ in enumerate(input)
        ]
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self):
        self.embeddings = FakeEmbeddingsApi()


def _settings(batch_size=2):
    return RagSettings(
        azure_openai_api_key="key",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_version="2025-01-01-preview",
        azure_openai_embedding_deployment="embedding-small",
        embedding_batch_size=batch_size,
    )


def test_embedding_client_batches_and_preserves_order():
    client = FakeClient()
    provider = AzureOpenAIEmbeddingClient(_settings(batch_size=2), client=client)

    result = provider.embed_texts(["a", "b", "c"])

    assert len(result) == 3
    assert client.embeddings.calls == [
        ("embedding-small", ["a", "b"]),
        ("embedding-small", ["c"]),
    ]
    assert result[0] == (1.0, 0.5)


def test_embedding_client_rejects_blank_input():
    provider = AzureOpenAIEmbeddingClient(_settings(), client=FakeClient())
    try:
        provider.embed_query("   ")
    except ValueError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("blank query must fail")
