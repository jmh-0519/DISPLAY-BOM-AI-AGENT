"""Runtime factory and serialization helpers for RAG retrieval."""

from __future__ import annotations

from functools import lru_cache

from .config import RagSettings
from .embedding_client import AzureOpenAIEmbeddingClient
from .retrieval_service import RagRetrievalService
from .vector_store import ChromaVectorStore, KnowledgeSearchFilter


@lru_cache(maxsize=1)
def get_retrieval_service() -> RagRetrievalService:
    settings = RagSettings.from_env()
    store = ChromaVectorStore(
        settings.vector_store_path,
        settings.collection_name,
    )
    if store.count() < 1:
        raise RuntimeError(
            "RAG Knowledge index가 비어 있습니다. "
            "python -m scripts.build_rag_index를 먼저 실행하세요."
        )
    return RagRetrievalService(
        embedding_provider=AzureOpenAIEmbeddingClient(settings),
        vector_store=store,
    )


def search_knowledge(
    query: str,
    *,
    top_k: int = 5,
    document_type: str | None = None,
    language: str | None = None,
    product_family: str | None = None,
    material_type: str | None = None,
    tag: str | None = None,
    retrieval_service: RagRetrievalService | None = None,
) -> dict:
    service = retrieval_service or get_retrieval_service()
    filters = KnowledgeSearchFilter(
        document_type=document_type,
        language=language,
        product_family=product_family,
        material_type=material_type,
        tag=tag,
    )
    response = service.search(query, top_k=top_k, filters=filters)
    hits = []
    for hit in response.hits:
        hits.append({
            "rank": hit.rank,
            "distance": hit.distance,
            "document_id": hit.document_id,
            "document_title": hit.document_title,
            "document_type": hit.document_type,
            "section_title": hit.section_title,
            "section_path": hit.section_path,
            "source_file": hit.source_file,
            "source_page": hit.source_page,
            "content": hit.content,
        })
    return {
        "success": True,
        "query": response.query,
        "hit_count": len(hits),
        "hits": hits,
        "authority": {
            "knowledge_evidence_only": True,
            "business_status_authority": "RuleEngine/SQLite",
            "production_bom_modified": False,
        },
    }


def clear_retrieval_service_cache() -> None:
    get_retrieval_service.cache_clear()


__all__ = [
    "clear_retrieval_service_cache",
    "get_retrieval_service",
    "search_knowledge",
]
