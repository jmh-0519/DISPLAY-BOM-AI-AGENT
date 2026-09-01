"""Read-only MCP capability for external Knowledge Evidence retrieval."""

from __future__ import annotations

from rag.runtime import search_knowledge


def search_knowledge_data(
    query: str,
    top_k: int = 5,
    document_type: str | None = None,
    language: str | None = None,
    product_family: str | None = None,
    material_type: str | None = None,
    tag: str | None = None,
    *,
    retrieval_service=None,
) -> dict:
    """Search policy/technical knowledge; never determine BOM facts or status."""
    return search_knowledge(
        query,
        top_k=top_k,
        document_type=document_type,
        language=language,
        product_family=product_family,
        material_type=material_type,
        tag=tag,
        retrieval_service=retrieval_service,
    )


__all__ = ["search_knowledge_data"]
