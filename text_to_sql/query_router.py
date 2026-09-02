"""Conservative deterministic routing for ad-hoc read-only SQL analytics."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextToSqlRouteDecision:
    eligible: bool
    reason: str


class TextToSqlQueryRouter:
    """High-confidence current-turn router for ad-hoc read-only analytics."""

    DOMAIN_MARKERS = (
        "자재", "material", "assy", "assembly", "공급사", "supplier",
        "재고", "inventory", "생산계획", "생산 계획", "production plan",
        "plant", "플랜트", "bom", "제품 버전", "버전별", "version",
    )
    AGGREGATION_MARKERS = (
        "평균", "avg", "average", "합계", "총합", "sum",
        "개수", "건수", "count", "몇 개씩", "몇개씩", "몇 개인",
        "몇개인", "전체 몇 개", "전체 몇개", "비율", "ratio",
    )
    RANKING_MARKERS = (
        "상위", "하위", "top ", "bottom ", "가장 높은", "가장 낮은",
        "가장 많은", "가장 적은", "많은 순서", "적은 순서",
        "높은 순서", "낮은 순서", "짧은 순서", "긴 순서",
    )
    BLOCKING_ACTION_MARKERS = (
        "설계변경", "설계 변경", "교체", "대체", "바꿔", "바꾸",
        "변경해", "추가해", "삭제해", "제거해", "적용해", "반영해",
        "추천", "후보", "승인", "apply",
    )
    WORKFLOW_MARKERS = (
        "change_request", "change requests", "change_requests", "request_id",
        "analysis_id", "설계변경 요청", "변경 요청", "승인 이력",
        "apply 이력", "최종 승인", "후보 승인",
    )
    KNOWLEDGE_MARKERS = (
        "정책", "기준", "절차", "가이드", "규정", "규칙", "원칙",
        "요건", "요구사항", "매뉴얼", "기술문서", "faq",
    )
    GROUPED_COUNT_PATTERN = re.compile(
        r"(?:별|기준)\s*[^?.!]{0,40}?\s(?:수|개수|건수)"
        r"(?:을|를|은|는|이|가|의)?(?:\s|$|[?.!,])",
        re.IGNORECASE,
    )
    NUMERIC_LIMIT_PATTERN = re.compile(
        r"(?:가장\s+(?:높은|낮은|많은|적은)|상위|하위)\s*\d*\s*(?:개|건)?",
        re.IGNORECASE,
    )

    @staticmethod
    def normalize(query: str) -> str:
        return " ".join(str(query or "").strip().lower().split())

    def route(self, query: str) -> TextToSqlRouteDecision:
        normalized = self.normalize(query)
        if not normalized:
            return TextToSqlRouteDecision(False, "EMPTY")
        if any(marker in normalized for marker in self.WORKFLOW_MARKERS):
            return TextToSqlRouteDecision(False, "WORKFLOW_MANAGED")
        if any(marker in normalized for marker in self.BLOCKING_ACTION_MARKERS):
            return TextToSqlRouteDecision(False, "ACTION_OR_RECOMMENDATION")
        if any(marker in normalized for marker in self.KNOWLEDGE_MARKERS):
            return TextToSqlRouteDecision(False, "KNOWLEDGE_QUERY")
        if not any(marker in normalized for marker in self.DOMAIN_MARKERS):
            return TextToSqlRouteDecision(False, "NON_DOMAIN")

        has_aggregation = any(
            marker in normalized for marker in self.AGGREGATION_MARKERS
        )
        has_grouped_count = bool(self.GROUPED_COUNT_PATTERN.search(normalized))
        has_ranking = (
            any(marker in normalized for marker in self.RANKING_MARKERS)
            or bool(self.NUMERIC_LIMIT_PATTERN.search(normalized))
        )
        if has_aggregation or has_grouped_count or has_ranking:
            return TextToSqlRouteDecision(True, "HIGH_CONFIDENCE_ANALYTICS")
        return TextToSqlRouteDecision(False, "NO_ANALYTICS_SIGNAL")


DEFAULT_TEXT_TO_SQL_QUERY_ROUTER = TextToSqlQueryRouter()


__all__ = [
    "DEFAULT_TEXT_TO_SQL_QUERY_ROUTER",
    "TextToSqlQueryRouter",
    "TextToSqlRouteDecision",
]
