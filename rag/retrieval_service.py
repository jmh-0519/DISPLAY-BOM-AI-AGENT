from __future__ import annotations

from dataclasses import dataclass

from .embedding_client import EmbeddingProvider
from .vector_store import KnowledgeSearchFilter, KnowledgeSearchHit, VectorStore


@dataclass(frozen=True)
class RagSearchResponse:
    query: str
    hits: tuple[KnowledgeSearchHit, ...]


class RagRetrievalService:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: KnowledgeSearchFilter | None = None,
    ) -> RagSearchResponse:
        normalized = str(query or "").strip()
        if not normalized:
            raise ValueError("query는 비어 있을 수 없습니다.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k는 1~50 범위여야 합니다.")
        embedding = self.embedding_provider.embed_query(normalized)
        hits = self.vector_store.search(
            embedding,
            top_k=top_k,
            filters=filters,
        )
        return RagSearchResponse(query=normalized, hits=hits)


__all__ = ["RagRetrievalService", "RagSearchResponse"]
