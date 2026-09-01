from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .config import RagSettings


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: Iterable[str]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...


@dataclass
class AzureOpenAIEmbeddingClient:
    """Thin Azure OpenAI embedding adapter used only by the RAG layer."""

    settings: RagSettings
    client: Any | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            from openai import AzureOpenAI

            self.client = AzureOpenAI(
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_key=self.settings.azure_openai_api_key,
                api_version=self.settings.azure_openai_api_version,
            )

    def embed_texts(self, texts: Iterable[str]) -> tuple[tuple[float, ...], ...]:
        normalized = [str(text or "").strip() for text in texts]
        if not normalized:
            return ()
        if any(not text for text in normalized):
            raise ValueError("embedding 대상 text는 비어 있을 수 없습니다.")

        embeddings: list[tuple[float, ...]] = []
        batch_size = self.settings.embedding_batch_size
        for start in range(0, len(normalized), batch_size):
            batch = normalized[start : start + batch_size]
            response = self.client.embeddings.create(
                model=self.settings.azure_openai_embedding_deployment,
                input=batch,
            )
            ordered = sorted(response.data, key=lambda value: int(value.index))
            if len(ordered) != len(batch):
                raise RuntimeError("Azure OpenAI embedding 응답 건수가 입력과 다릅니다.")
            embeddings.extend(
                tuple(float(component) for component in item.embedding)
                for item in ordered
            )

        if embeddings:
            dimension = len(embeddings[0])
            if dimension == 0 or any(len(value) != dimension for value in embeddings):
                raise RuntimeError("Azure OpenAI embedding 차원이 일관되지 않습니다.")
        return tuple(embeddings)

    def embed_query(self, text: str) -> tuple[float, ...]:
        normalized = str(text or "").strip()
        if not normalized:
            raise ValueError("query는 비어 있을 수 없습니다.")
        result = self.embed_texts((normalized,))
        return result[0]


__all__ = ["AzureOpenAIEmbeddingClient", "EmbeddingProvider"]
