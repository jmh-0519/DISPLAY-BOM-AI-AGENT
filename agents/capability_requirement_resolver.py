"""Deterministic capability requirement resolution for current-turn goals.

CTX-05 detects whether a request needs one existing capability or composition
of multiple capabilities. It does not plan execution order and does not execute
tools. Multi-capability requests are conservatively deferred to the existing
Agent path until PLAN-01 provides selective composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)
from rag.query_router import (
    DEFAULT_KNOWLEDGE_QUERY_ROUTER,
    KnowledgeQueryRouter,
)
from text_to_sql.query_router import (
    DEFAULT_TEXT_TO_SQL_QUERY_ROUTER,
    TextToSqlQueryRouter,
)


class Capability(str, Enum):
    CHAT = "CHAT"
    BOM_READ = "BOM_READ"
    WHERE_USED = "WHERE_USED"
    CURRENT_BOM_QUANTITY = "CURRENT_BOM_QUANTITY"
    RAG = "RAG"
    TEXT_TO_SQL = "TEXT_TO_SQL"
    DESIGN_CHANGE_ANALYSIS = "DESIGN_CHANGE_ANALYSIS"
    PRODUCT_COST_SCAN = "PRODUCT_COST_SCAN"
    AGENT_REASONING = "AGENT_REASONING"


@dataclass(frozen=True)
class CapabilityRequirementDecision:
    capabilities: tuple[Capability, ...]
    composition_required: bool
    workflow_managed: bool
    reasons: tuple[str, ...] = ()

    @property
    def capability_names(self) -> tuple[str, ...]:
        return tuple(value.value for value in self.capabilities)


class CapabilityRequirementResolver:
    """Resolve capability requirements without LLM inference.

    Important boundary:
    - this class answers "what capabilities are required?";
    - it does not answer "in what execution order?";
    - it never creates Request/approval/apply authority.
    """

    CHANGE_CONCEPT_MARKERS = (
        "설계변경",
        "설계 변경",
        "변경",
        "교체",
        "대체",
        "바꾸",
    )
    IMPACT_ANALYSIS_MARKERS = (
        "영향",
        "영향도",
        "impact",
        "영향 분석",
        "영향분석",
    )
    ANALYTICS_EXTRA_PATTERNS = (
        re.compile(
            r"(?:원가|단가|가격|cost|price).{0,12}"
            r"(?:높|낮|비싸|저렴|싼)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:높|낮|비싸|저렴|싼).{0,12}"
            r"(?:원가|단가|가격|cost|price)",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        *,
        domain_router: DomainIntentRouter | None = None,
        knowledge_router: KnowledgeQueryRouter | None = None,
        text_to_sql_router: TextToSqlQueryRouter | None = None,
    ) -> None:
        self.domain_router = domain_router or DEFAULT_DOMAIN_INTENT_ROUTER
        self.knowledge_router = knowledge_router or DEFAULT_KNOWLEDGE_QUERY_ROUTER
        self.text_to_sql_router = (
            text_to_sql_router or DEFAULT_TEXT_TO_SQL_QUERY_ROUTER
        )

    def resolve(self, query: str) -> CapabilityRequirementDecision:
        text = str(query or "").strip()
        if not text:
            return CapabilityRequirementDecision(
                capabilities=(Capability.AGENT_REASONING,),
                composition_required=False,
                workflow_managed=False,
                reasons=("EMPTY_OR_AMBIGUOUS",),
            )

        domain = self.domain_router.route(
            text,
            workflow_active=False,
            workflow_state={},
        )

        detected: list[Capability] = []
        reasons: list[str] = []

        if self._has_analytics_requirement(text):
            self._append(
                detected,
                Capability.TEXT_TO_SQL,
                reasons,
                "ANALYTICS_SIGNAL",
            )

        knowledge_required = self._has_knowledge_requirement(text)
        if knowledge_required:
            self._append(
                detected,
                Capability.RAG,
                reasons,
                "KNOWLEDGE_SIGNAL",
            )

        if domain.product_cost_scan:
            self._append(
                detected,
                Capability.PRODUCT_COST_SCAN,
                reasons,
                "PRODUCT_COST_SCAN_SIGNAL",
            )
        elif self._has_design_change_requirement(
            text,
            domain=domain,
            knowledge_required=knowledge_required,
        ):
            self._append(
                detected,
                Capability.DESIGN_CHANGE_ANALYSIS,
                reasons,
                "DESIGN_CHANGE_SIGNAL",
            )

        # When a cross-capability signal already exists, keep only those
        # business capabilities. Simple deterministic route labels are fallback
        # classifications, not additional requirements.
        if not detected:
            fallback = self._fallback_capability(domain.intent)
            detected.append(fallback)
            reasons.append(f"DOMAIN_INTENT_{domain.intent}")

        capabilities = tuple(detected)
        workflow_managed = any(
            value in {
                Capability.DESIGN_CHANGE_ANALYSIS,
                Capability.PRODUCT_COST_SCAN,
            }
            for value in capabilities
        )
        return CapabilityRequirementDecision(
            capabilities=capabilities,
            composition_required=len(capabilities) > 1,
            workflow_managed=workflow_managed,
            reasons=tuple(reasons),
        )

    def _has_analytics_requirement(self, query: str) -> bool:
        normalized = self.text_to_sql_router.normalize(query)
        if not any(
            marker in normalized
            for marker in self.text_to_sql_router.DOMAIN_MARKERS
        ):
            return False

        if any(
            marker in normalized
            for marker in self.text_to_sql_router.AGGREGATION_MARKERS
        ):
            return True
        if any(
            marker in normalized
            for marker in self.text_to_sql_router.RANKING_MARKERS
        ):
            return True
        if self.text_to_sql_router.GROUPED_COUNT_PATTERN.search(normalized):
            return True
        if self.text_to_sql_router.NUMERIC_LIMIT_PATTERN.search(normalized):
            return True
        return any(
            pattern.search(normalized)
            for pattern in self.ANALYTICS_EXTRA_PATTERNS
        )

    def _has_knowledge_requirement(self, query: str) -> bool:
        """Detect a knowledge need independently from FAST_KNOWLEDGE eligibility.

        KnowledgeQueryRouter deliberately rejects action directives so they do
        not enter the standalone RAG fast path. Capability resolution has a
        different job: a compound request may still require RAG together with
        Design Change or Analytics. Therefore this check uses the router's
        knowledge/domain vocabulary but does not apply its action-directive
        exclusion.
        """
        upper = " ".join(str(query or "").strip().split()).upper()
        has_knowledge = any(
            marker.upper() in upper
            for marker in self.knowledge_router.KNOWLEDGE_MARKERS
        )
        has_domain = any(
            marker.upper() in upper
            for marker in self.knowledge_router.DOMAIN_MARKERS
        )
        return has_knowledge and has_domain

    def _has_design_change_requirement(
        self,
        query: str,
        *,
        domain,
        knowledge_required: bool,
    ) -> bool:
        normalized = self.domain_router.normalize(query)
        has_change_concept = any(
            marker in normalized
            for marker in self.CHANGE_CONCEPT_MARKERS
        )
        has_impact_analysis = any(
            marker in normalized
            for marker in self.IMPACT_ANALYSIS_MARKERS
        )

        # "교체 기준이 뭐야?" contains a change noun but is a pure knowledge
        # question. Do not convert that wording into Design Change Analysis.
        #
        # A knowledge request may still genuinely need Design Change when the
        # same turn asks for impact analysis or contains an explicit action
        # directive ("변경하고싶어", "교체해줘", ...).
        if knowledge_required:
            if has_change_concept and has_impact_analysis:
                return True
            return self._has_explicit_change_directive(
                normalized,
                domain=domain,
            )

        if domain.change or domain.recommendation:
            return True
        return has_change_concept and has_impact_analysis

    def _has_explicit_change_directive(self, normalized: str, *, domain) -> bool:
        """Require execution language, not merely a change-related noun.

        `DomainIntentRouter` intentionally treats reason + terse replacement
        wording conservatively as a possible Design Change. That is useful for
        Agent routing, but capability composition needs a stricter distinction:

        - "단종 자재 교체 기준이 뭐야?" -> knowledge only
        - "... 기준을 참고해서 SEALANT를 변경하고싶어"
          -> knowledge + Design Change Analysis
        """
        if domain.delete or domain.quantity_change:
            return True

        if self.domain_router.is_design_change_apply_instruction(normalized):
            return True

        if (
            domain.change
            and self.domain_router._has_direct_replace_directive(normalized)
        ):
            return True

        if (
            domain.change
            and any(
                marker in normalized
                for marker in self.domain_router.DESIGN_CHANGE_EXPLICIT_ACTION_MARKERS
            )
        ):
            return True

        # ADD uses its own natural-language forms. Require an actual action
        # phrase so a knowledge sentence containing the noun "추가" alone does
        # not become workflow execution.
        if domain.change and any(
            marker in normalized
            for marker in ("추가하고 싶", "추가하고싶", "추가해줘", "추가해 줘",
                           "추가해주세요", "추가해 주세요", "추가하자",
                           "넣어줘", "넣어 줘", "넣고 싶", "넣고싶")
        ):
            return True

        return False

    @staticmethod
    def _append(
        values: list[Capability],
        capability: Capability,
        reasons: list[str],
        reason: str,
    ) -> None:
        if capability in values:
            return
        values.append(capability)
        reasons.append(reason)

    @staticmethod
    def _fallback_capability(intent: str) -> Capability:
        mapping = {
            "CHAT": Capability.CHAT,
            "BOM_READ": Capability.BOM_READ,
            "WHERE_USED": Capability.WHERE_USED,
            "CURRENT_BOM_QUANTITY": Capability.CURRENT_BOM_QUANTITY,
            "PRODUCT_COST_SCAN": Capability.PRODUCT_COST_SCAN,
            "DESIGN_CHANGE": Capability.DESIGN_CHANGE_ANALYSIS,
            "DESIGN_CHANGE_RECOMMENDATION": Capability.DESIGN_CHANGE_ANALYSIS,
        }
        return mapping.get(intent, Capability.AGENT_REASONING)


DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER = CapabilityRequirementResolver()


__all__ = [
    "Capability",
    "CapabilityRequirementDecision",
    "CapabilityRequirementResolver",
    "DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER",
]
