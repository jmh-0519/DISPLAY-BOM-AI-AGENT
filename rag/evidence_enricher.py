"""Optional, fail-open RAG enrichment for persisted Design Change evidence."""

from __future__ import annotations

import os
from typing import Any

from .runtime import get_retrieval_service, search_knowledge


_EVIDENCE_KEYS = frozenset({
    "reason_code", "reason_name", "rule_id", "rule_name", "evaluation_item",
    "action_type", "target_type", "target_item_name", "item_name", "description",
    "decision_reason", "evaluation_reason", "reason_summary", "original_request",
})


def enrich_design_change_evidence(
    payload: dict,
    *,
    retrieval_service=None,
    enabled: bool | None = None,
    top_k: int = 3,
) -> dict:
    """Append informational knowledge evidence without changing business fields.

    The feature is opt-in for Design Change follow-up paths so deterministic test
    suites never make external embedding calls by accident. Retrieval failures are
    fail-open: the original authoritative payload is returned unchanged.
    """
    if not isinstance(payload, dict):
        return payload
    if enabled is None:
        enabled = str(
            os.getenv("RAG_DESIGN_CHANGE_EVIDENCE_ENABLED", "0") or "0"
        ).strip().lower() in {"1", "true", "on", "yes"}
    if not enabled:
        return payload

    query = _evidence_query(payload)
    if not query:
        return payload
    try:
        service = retrieval_service or get_retrieval_service()
        response = search_knowledge(
            query,
            top_k=max(1, min(int(top_k), 5)),
            retrieval_service=service,
        )
    except Exception:
        return payload
    hits = response.get("hits") if isinstance(response, dict) else []
    if not hits:
        return payload

    enriched = dict(payload)
    enriched["knowledge_evidence"] = [
        {
            "rank": hit.get("rank"),
            "distance": hit.get("distance"),
            "document_id": hit.get("document_id"),
            "document_title": hit.get("document_title"),
            "document_type": hit.get("document_type"),
            "section_path": hit.get("section_path"),
            "source_file": hit.get("source_file"),
            "content": str(hit.get("content") or "")[:1000],
        }
        for hit in hits
        if isinstance(hit, dict)
    ]
    enriched["knowledge_authority"] = {
        "informational_only": True,
        "may_change_business_status": False,
        "business_status_authority": "persisted RuleEngine/SQLite evidence",
    }
    return enriched


def _evidence_query(payload: dict) -> str:
    values: list[str] = []

    def visit(value: Any, key: str | None = None) -> None:
        if len(values) >= 14:
            return
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value[:8]:
                visit(child, key)
        elif key in _EVIDENCE_KEYS and value is not None:
            text = " ".join(str(value).strip().split())
            if text and text not in values:
                values.append(text[:280])

    visit(payload)
    return " | ".join(values)


__all__ = ["enrich_design_change_evidence"]
