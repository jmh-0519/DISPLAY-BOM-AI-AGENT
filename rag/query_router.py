"""High-confidence routing for read-only knowledge questions.

This router is intentionally conservative. It admits only questions that clearly
ask for policy/criteria/guide/specification evidence and rejects design-change
action directives so workflow authority remains in the existing Agent path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeRouteDecision:
    eligible: bool
    document_type: str | None = None
    reason: str = ""


class KnowledgeQueryRouter:
    KNOWLEDGE_MARKERS = (
        "기준", "정책", "절차", "가이드", "규정", "규칙", "원칙", "요건",
        "요구사항", "매뉴얼", "기술문서", "근거", "사양", "SPEC", "FAQ",
        "자주 묻는",
    )
    DOMAIN_MARKERS = (
        "설계변경", "설계 변경", "교체", "대체", "단종", "EOL", "공급 중단",
        "납품 중단", "납기", "원가", "재고", "품질", "규제", "고객 사양",
        "고객사양", "공용화", "DRIVE-IC", "DRIVER_IC", "OLB", "FPCB",
        "POLARIZER", "편광판", "SEALANT", "실란트", "EMI", "차폐", "접착제",
        "MATERIAL", "ASSY", "자재",
    )
    ACTION_DIRECTIVES = (
        "바꿔줘", "바꿔 줘", "교체해줘",
        "교체해 줘", "변경해줘", "변경해 줘", "추가해줘", "추가해 줘",
        "삭제해줘", "삭제해 줘", "제거해줘", "제거해 줘", "적용해줘",
        "적용해 줘", "진행해줘", "진행해 줘", "하고 싶", "하려고",
        "하자", "진행하자", "반영해", "APPLY 해", "APPLY해",
    )

    def route(self, query: str) -> KnowledgeRouteDecision:
        normalized = " ".join(str(query or "").strip().split())
        if not normalized:
            return KnowledgeRouteDecision(False, reason="EMPTY")
        upper = normalized.upper()

        if any(marker.upper() in upper for marker in self.ACTION_DIRECTIVES):
            return KnowledgeRouteDecision(False, reason="ACTION_DIRECTIVE")
        has_knowledge = any(
            marker.upper() in upper for marker in self.KNOWLEDGE_MARKERS
        )
        has_domain = any(marker.upper() in upper for marker in self.DOMAIN_MARKERS)
        if not has_knowledge or not has_domain:
            return KnowledgeRouteDecision(False, reason="LOW_CONFIDENCE")

        return KnowledgeRouteDecision(
            True,
            document_type=self._document_type(upper),
            reason="HIGH_CONFIDENCE_KNOWLEDGE",
        )

    @staticmethod
    def _document_type(upper_query: str) -> str | None:
        # Only explicit document-class wording creates a hard metadata filter.
        # Generic "기준" intentionally stays unfiltered so Reason + Rule evidence
        # can be retrieved together.
        explicit = (
            (("FAQ", "자주 묻는"), "FAQ"),
            (("자재 사양", "MATERIAL SPEC", "MATERIAL_SPEC"), "MATERIAL_SPEC"),
            (("설계 가이드", "DESIGN GUIDE", "DESIGN_GUIDE"), "DESIGN_GUIDE"),
            (("공정 가이드", "공정 절차", "PROCESS GUIDE", "PROCESS_GUIDE"), "PROCESS_GUIDE"),
            (("변경 정책", "설계변경 정책", "CHANGE POLICY", "CHANGE_POLICY"), "CHANGE_POLICY"),
            (("공급사 기술", "SUPPLIER TECHNICAL", "SUPPLIER_TECHNICAL"), "SUPPLIER_TECHNICAL"),
            (("변경 사유", "설계변경 사유", "CHANGE REASON", "CHANGE_REASON"), "CHANGE_REASON"),
            (("적합성 규칙", "CHANGE RULE", "CHANGE_RULE"), "CHANGE_RULE"),
        )
        for markers, document_type in explicit:
            if any(marker.upper() in upper_query for marker in markers):
                return document_type
        return None


DEFAULT_KNOWLEDGE_QUERY_ROUTER = KnowledgeQueryRouter()

__all__ = [
    "DEFAULT_KNOWLEDGE_QUERY_ROUTER",
    "KnowledgeQueryRouter",
    "KnowledgeRouteDecision",
]
