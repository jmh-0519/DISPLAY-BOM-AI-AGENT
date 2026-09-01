"""Deterministic evidence selection for user-facing RAG answers.

Vector retrieval optimizes recall. Runtime answers must additionally enforce
source isolation and trim the candidate set to evidence that is relevant to the
question type. Evaluation fixtures are never eligible for runtime answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .query_router import KnowledgeQueryRouter


_RUNTIME_BLOCKED_SEGMENT = "/documents/evaluation/"


def is_runtime_source_file(source_file: str) -> bool:
    normalized = "/" + str(source_file or "").replace("\\", "/").strip("/").lower() + "/"
    return _RUNTIME_BLOCKED_SEGMENT not in normalized


@dataclass(frozen=True)
class KnowledgeEvidenceSelector:
    router: KnowledgeQueryRouter = KnowledgeQueryRouter()

    def select(self, query: str, hits: Iterable[dict], *, max_hits: int = 3) -> list[dict]:
        """Return a small, deterministic user-facing evidence set.

        Retrieval rank remains the primary relevance signal.  The selector only
        removes document classes that do not fit the question intent; it does not
        globally promote every CHANGE_REASON ahead of a better-ranked CHANGE_RULE.
        That distinction is important for questions such as EOL replacement
        criteria where the expected evidence pair is Reason + Rule.
        """
        limit = max(1, min(int(max_hits or 3), 5))
        decision = self.router.route(query)
        intent = decision.intent or "GENERIC"
        upper = " ".join(str(query or "").upper().split())
        supplier_specific = any(
            marker in upper
            for marker in ("공급사", "SUPPLIER", "납품", "공급 중단", "공급중단")
        )
        reason_family = self._reason_family(upper)

        allowed = self._allowed_types(intent, supplier_specific=supplier_specific)
        candidates: list[tuple[int, dict]] = []
        seen_docs: set[str] = set()
        for fallback_rank, hit in enumerate(hits, 1):
            if not isinstance(hit, dict):
                continue
            if not is_runtime_source_file(str(hit.get("source_file") or "")):
                continue
            document_id = str(hit.get("document_id") or "").strip()
            if document_id and document_id in seen_docs:
                continue
            document_type = str(hit.get("document_type") or "").strip().upper()
            if decision.document_type and document_type != decision.document_type:
                continue
            if document_type not in allowed:
                continue
            if (
                reason_family
                and document_type in {"CHANGE_REASON", "CHANGE_RULE"}
                and not self._matches_reason_family(hit, reason_family)
            ):
                continue
            seen_docs.add(document_id)
            rank = int(hit.get("rank") or fallback_rank)
            candidates.append((rank, hit))

        # Preserve semantic retrieval order after deterministic filtering.
        candidates.sort(key=lambda value: value[0])
        selected = [dict(value[1]) for value in candidates[:limit]]
        for index, hit in enumerate(selected, 1):
            hit["rank"] = index
        return selected

    @staticmethod
    def _reason_family(upper_query: str) -> str | None:
        families = (
            (("단종", "EOL", "OBSOLETE", "DISCONTINUED", "생산 종료"), "EOL"),
            (("공급 중단", "공급중단", "납품 중단", "SUPPLIER STOP"), "SUPPLIER_STOP"),
            (("납기", "LEAD TIME", "LEAD_TIME"), "LEAD_TIME"),
            (("원가", "비용", "COST"), "COST"),
            (("재고", "INVENTORY"), "INVENTORY"),
            (("품질", "불량", "QUALITY"), "QUALITY"),
            (("고객 사양", "고객사양", "CUSTOMER SPEC", "CUSTOMER_SPEC"), "CUSTOMER_SPEC"),
            (("규제", "인증", "REGULATION"), "REGULATION"),
            (("공용화", "공통화", "COMMONIZATION"), "COMMONIZATION"),
            (("사용자 요청", "USER REQUEST", "USER_REQUEST"), "USER_REQUEST"),
        )
        for markers, reason_code in families:
            if any(marker in upper_query for marker in markers):
                return reason_code
        return None

    @staticmethod
    def _matches_reason_family(hit: dict, reason_family: str) -> bool:
        haystack = " | ".join(
            str(hit.get(key) or "")
            for key in (
                "document_id",
                "document_title",
                "section_path",
                "source_file",
                "content",
            )
        ).upper().replace("-", "_").replace(" ", "_")
        expected = str(reason_family or "").upper().replace("-", "_").replace(" ", "_")
        return bool(expected and expected in haystack)

    @staticmethod
    def _allowed_types(intent: str, *, supplier_specific: bool) -> frozenset[str]:
        if intent == "PROCESS":
            return frozenset({
                "PROCESS_GUIDE", "CHANGE_POLICY", "CHANGE_REASON", "FAQ", "CHANGE_RULE",
            })
        if intent == "POLICY":
            return frozenset({
                "CHANGE_POLICY", "PROCESS_GUIDE", "CHANGE_REASON", "FAQ", "CHANGE_RULE",
            })
        if intent == "TECHNICAL":
            values = {
                "MATERIAL_SPEC", "DESIGN_GUIDE", "CHANGE_RULE", "CHANGE_REASON",
            }
            if supplier_specific:
                values.add("SUPPLIER_TECHNICAL")
            return frozenset(values)
        if intent == "CRITERIA":
            values = {
                "CHANGE_REASON", "CHANGE_RULE", "DESIGN_GUIDE", "MATERIAL_SPEC",
                "CHANGE_POLICY", "FAQ",
            }
            if supplier_specific:
                values.add("SUPPLIER_TECHNICAL")
            return frozenset(values)
        return frozenset({
            "CHANGE_REASON", "CHANGE_RULE", "PROCESS_GUIDE", "CHANGE_POLICY",
            "DESIGN_GUIDE", "MATERIAL_SPEC", "SUPPLIER_TECHNICAL", "FAQ",
        })


DEFAULT_KNOWLEDGE_EVIDENCE_SELECTOR = KnowledgeEvidenceSelector()

__all__ = [
    "DEFAULT_KNOWLEDGE_EVIDENCE_SELECTOR",
    "KnowledgeEvidenceSelector",
    "is_runtime_source_file",
]
