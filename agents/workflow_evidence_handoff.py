"""PLAN-03 typed Evidence -> Design Change Analysis handoff foundation.

This module deliberately does NOT modify LangGraph runtime yet.

It converts already-executed, read-only Text-to-SQL and RAG observations into
a typed handoff decision.  Only deterministic, uniquely-selected evidence may
become the source target of ``analyze_design_change_candidates``.

Authority boundary:
- Text-to-SQL may provide read-only analytics evidence.
- RAG may provide policy/knowledge evidence only.
- This handoff may prepare a read-only Design Change Analysis tool call.
- It never creates a Design Change Request.
- It never approves a candidate or final apply.
- It never writes Production E-BOM.
- DesignChangeWorkflowService remains authoritative and revalidates the
  VERSION / PLANT / source BOM relation when Analysis actually executes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementResolver,
    DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER,
)
from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)
from text_to_sql.pipeline import TextToSqlPipelineResult


class HandoffStatus(str, Enum):
    READY = "READY"
    UNSUPPORTED_GOAL = "UNSUPPORTED_GOAL"
    USER_SELECTION_REQUIRED = "USER_SELECTION_REQUIRED"
    SCOPE_REQUIRED = "SCOPE_REQUIRED"
    SQL_RESULT_UNSUPPORTED = "SQL_RESULT_UNSUPPORTED"
    SQL_RESULT_EMPTY = "SQL_RESULT_EMPTY"
    SQL_RESULT_AMBIGUOUS = "SQL_RESULT_AMBIGUOUS"
    SQL_RESULT_TRUNCATED = "SQL_RESULT_TRUNCATED"
    SQL_SELECTION_NOT_PROVEN = "SQL_SELECTION_NOT_PROVEN"
    SQL_SCOPE_MISMATCH = "SQL_SCOPE_MISMATCH"
    ITEM_CODE_REQUIRED = "ITEM_CODE_REQUIRED"
    ITEM_CODE_AMBIGUOUS = "ITEM_CODE_AMBIGUOUS"
    COST_METRIC_REQUIRED = "COST_METRIC_REQUIRED"
    COST_METRIC_AMBIGUOUS = "COST_METRIC_AMBIGUOUS"
    KNOWLEDGE_EVIDENCE_REQUIRED = "KNOWLEDGE_EVIDENCE_REQUIRED"
    KNOWLEDGE_EVIDENCE_INVALID = "KNOWLEDGE_EVIDENCE_INVALID"
    KNOWLEDGE_EVIDENCE_EMPTY = "KNOWLEDGE_EVIDENCE_EMPTY"


@dataclass(frozen=True)
class ResolvedWorkflowScope:
    version_code: str
    plant_code: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "version_code": self.version_code,
            "plant_code": self.plant_code,
            "source": self.source,
        }


@dataclass(frozen=True)
class AnalyticsTargetEvidence:
    version_code: str
    plant_code: str
    item_code: str
    criterion: str
    selection_mode: str
    metric_name: str
    metric_value: float
    question: str
    row_count: int
    parent_item_code: str | None = None
    location_code: str | None = None
    price_source: str | None = None
    currency_code: str | None = None
    authority: str = "READ_ONLY_SQL_EVIDENCE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_code": self.version_code,
            "plant_code": self.plant_code,
            "item_code": self.item_code,
            "criterion": self.criterion,
            "selection_mode": self.selection_mode,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "question": self.question,
            "row_count": self.row_count,
            "parent_item_code": self.parent_item_code,
            "location_code": self.location_code,
            "price_source": self.price_source,
            "currency_code": self.currency_code,
            "authority": self.authority,
        }




@dataclass(frozen=True)
class DesignChangeTargetEvidence:
    """Verified source target that may enter read-only Design Change Analysis."""

    version_code: str
    plant_code: str
    item_code: str
    target_type: str
    parent_item_code: str
    location_code: str
    resolution_mode: str
    criterion: str
    selection_mode: str
    metric_name: str | None = None
    metric_value: float | None = None
    item_name: str | None = None
    price_source: str | None = None
    currency_code: str | None = None
    evidence_source: str = "READ_ONLY_SCOPED_BOM_EVIDENCE"
    authority: str = "READ_ONLY_TARGET_EVIDENCE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_code": self.version_code,
            "plant_code": self.plant_code,
            "item_code": self.item_code,
            "target_type": self.target_type,
            "parent_item_code": self.parent_item_code,
            "location_code": self.location_code,
            "resolution_mode": self.resolution_mode,
            "criterion": self.criterion,
            "selection_mode": self.selection_mode,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "item_name": self.item_name,
            "price_source": self.price_source,
            "currency_code": self.currency_code,
            "evidence_source": self.evidence_source,
            "authority": self.authority,
        }


@dataclass(frozen=True)
class KnowledgeEvidenceSummary:
    observed: bool
    hit_count: int
    references: tuple[str, ...]
    authority: str = "RAG_EVIDENCE_ONLY"

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed": self.observed,
            "hit_count": self.hit_count,
            "references": list(self.references),
            "authority": self.authority,
        }


@dataclass(frozen=True)
class WorkflowHandoffDecision:
    status: HandoffStatus
    reason: str
    scope: ResolvedWorkflowScope | None = None
    analytics_evidence: AnalyticsTargetEvidence | None = None
    target_evidence: DesignChangeTargetEvidence | None = None
    knowledge_evidence: KnowledgeEvidenceSummary | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    request_creation_allowed: bool = False
    approval_allowed: bool = False
    production_write_allowed: bool = False

    @property
    def ready(self) -> bool:
        return self.status == HandoffStatus.READY

    @property
    def write_authority_granted(self) -> bool:
        return bool(
            self.request_creation_allowed
            or self.approval_allowed
            or self.production_write_allowed
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "ready": self.ready,
            "scope": self.scope.as_dict() if self.scope else None,
            "analytics_evidence": (
                self.analytics_evidence.as_dict()
                if self.analytics_evidence else None
            ),
            "target_evidence": (
                self.target_evidence.as_dict()
                if self.target_evidence else None
            ),
            "knowledge_evidence": (
                self.knowledge_evidence.as_dict()
                if self.knowledge_evidence else None
            ),
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "request_creation_allowed": self.request_creation_allowed,
            "approval_allowed": self.approval_allowed,
            "production_write_allowed": self.production_write_allowed,
            "write_authority_granted": self.write_authority_granted,
        }


class EvidenceToWorkflowHandoff:
    """Strict deterministic handoff for analytics-discovered REPLACE targets.

    PLAN-03 supports one narrow future runtime use case:

      TEXT_TO_SQL + RAG + DESIGN_CHANGE_ANALYSIS
      -> uniquely proven COST target
      -> analyze_design_change_candidates (Analysis only)

    The currently-used diagnostic wording
    "원가가 높은 자재를 찾고 그 자재를 변경..."
    is intentionally NOT enough to auto-select one target.  Unless the user
    explicitly requests a unique winner (e.g. "가장 높은", "상위 1개"),
    the handoff returns USER_SELECTION_REQUIRED.
    """

    REQUIRED_CAPABILITIES = frozenset({
        Capability.TEXT_TO_SQL,
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
    })

    ITEM_CODE_COLUMNS = (
        "source_item_code",
        "item_code",
        "child_item_code",
        "material_code",
    )
    COST_EXACT_COLUMNS = (
        "unit_cost",
        "unit_price",
        "cost",
        "price",
        "current_unit_price",
        "average_unit_price",
        "avg_unit_price",
        "average_cost",
        "avg_cost",
    )
    COST_COLUMN_MARKERS = (
        "cost",
        "price",
        "unit_cost",
        "unit_price",
        "원가",
        "단가",
        "가격",
        "금액",
    )
    UNIQUE_SELECTION_PATTERNS = (
        re.compile(r"(?:가장|제일)\s*(?:원가|단가|가격).{0,12}(?:높|비싸)", re.IGNORECASE),
        re.compile(r"(?:원가|단가|가격).{0,12}(?:가장|제일).{0,8}(?:높|비싸)", re.IGNORECASE),
        re.compile(r"(?:상위|TOP)\s*1\s*(?:개|건)?", re.IGNORECASE),
        re.compile(r"(?:최고|최대)\s*(?:원가|단가|가격)", re.IGNORECASE),
    )

    def __init__(
        self,
        *,
        capability_resolver: CapabilityRequirementResolver | None = None,
        domain_router: DomainIntentRouter | None = None,
    ) -> None:
        self.capability_resolver = (
            capability_resolver or DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
        )
        self.domain_router = domain_router or DEFAULT_DOMAIN_INTENT_ROUTER

    def resolve_scope(
        self,
        user_goal: str,
        *,
        active_bom_context: dict[str, Any] | None = None,
    ) -> ResolvedWorkflowScope | None:
        """Resolve scope without mixing explicit fresh scope with stale context."""
        text = " ".join(str(user_goal or "").strip().split())
        explicit_version = self.domain_router.explicit_model_scope_code(text)
        explicit_plant = self.domain_router.extract_plant_code(text)

        active = active_bom_context or {}
        active_version = str(active.get("product_id") or "").strip().upper()
        active_plant = str(active.get("plant_code") or "").strip().upper()

        # A user may disambiguate the scope by repeating the exact currently
        # viewed VERSION code and PLANT without the literal word "모델":
        #
        #   LTA550HR11-001 P01 대상으로 ...
        #
        # This is not scope guessing because the code is required to equal the
        # verified Active BOM VERSION already stored in Graph state.  An
        # arbitrary material/ASSY code is never promoted to VERSION here.
        if (
            explicit_version is None
            and explicit_plant
            and active_version
            and active_version in self.domain_router.item_codes(text)
        ):
            explicit_version = active_version

        # An explicit MODEL declares a fresh scope under the project's current
        # context policy.  Never silently reuse the old active PLANT.
        if explicit_version:
            if explicit_plant:
                return ResolvedWorkflowScope(
                    version_code=explicit_version,
                    plant_code=explicit_plant,
                    source="CURRENT_TURN_EXPLICIT",
                )
            return None

        # Likewise, do not combine a newly explicit PLANT with an inherited MODEL.
        if explicit_plant:
            return None

        if active_version and active_plant:
            return ResolvedWorkflowScope(
                version_code=active_version,
                plant_code=active_plant,
                source="ACTIVE_BOM_CONTEXT",
            )
        return None

    def build_scoped_analytics_question(
        self,
        user_goal: str,
        *,
        scope: ResolvedWorkflowScope,
    ) -> str | None:
        """Build a strict read-only top-1 COST question for later runtime use.

        This helper is intentionally available only when the user's wording
        explicitly authorizes a unique selection.  It does not execute SQL.
        """
        if not self._is_supported_goal(user_goal):
            return None
        if not self._has_explicit_unique_selection(user_goal):
            return None
        return (
            f"{scope.version_code} {scope.plant_code} 모델의 활성 BOM에서 "
            "현재 확인 가능한 원가 또는 단가가 가장 높은 자재 1개의 "
            "자재코드, 자재명, 원가 또는 단가를 알려줘"
        )

    def build(
        self,
        *,
        user_goal: str,
        sql_result: TextToSqlPipelineResult | None,
        knowledge_payload: dict[str, Any] | None,
        scope: ResolvedWorkflowScope | None,
    ) -> WorkflowHandoffDecision:
        goal = " ".join(str(user_goal or "").strip().split())

        if not self._is_supported_goal(goal):
            return self._blocked(
                HandoffStatus.UNSUPPORTED_GOAL,
                "현재 PLAN-03 handoff는 COST 기반 REPLACE 분석 조합만 지원합니다.",
                scope=scope,
            )

        if not self._has_explicit_unique_selection(goal):
            return self._blocked(
                HandoffStatus.USER_SELECTION_REQUIRED,
                (
                    "사용자가 단일 변경 대상을 명시적으로 선택하지 않았습니다. "
                    "'가장 원가가 높은 자재 1개'처럼 유일한 선택 기준을 "
                    "명시하거나 분석 결과에서 자재를 선택해야 합니다."
                ),
                scope=scope,
            )

        if scope is None:
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                "Design Change Analysis에는 확정된 VERSION과 PLANT가 필요합니다.",
            )

        knowledge, knowledge_error = self._knowledge_evidence(knowledge_payload)
        if knowledge_error is not None:
            return self._blocked(
                knowledge_error[0],
                knowledge_error[1],
                scope=scope,
            )

        if sql_result is None:
            return self._blocked(
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                "Text-to-SQL 실행 결과가 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )
        if str(sql_result.status or "").strip().upper() != "SQL":
            return self._blocked(
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                "Text-to-SQL 결과가 실행 가능한 SQL 증거가 아닙니다.",
                scope=scope,
                knowledge=knowledge,
            )
        if sql_result.truncated:
            return self._blocked(
                HandoffStatus.SQL_RESULT_TRUNCATED,
                "행 제한이 적용된 SQL 결과는 Design Change 대상을 확정하는 근거로 사용하지 않습니다.",
                scope=scope,
                knowledge=knowledge,
            )

        rows = list(sql_result.rows or ())
        if not rows or sql_result.row_count == 0:
            return self._blocked(
                HandoffStatus.SQL_RESULT_EMPTY,
                (
                    "확정된 MODEL/PLANT BOM에서 비교 가능한 원가/단가 근거가 "
                    "등록된 변경 대상 자재를 찾지 못했습니다. "
                    "원가 근거가 없는 자재를 임의로 선택하지 않습니다."
                ),
                scope=scope,
                knowledge=knowledge,
            )
        if len(rows) != 1 or sql_result.row_count != 1:
            return self._blocked(
                HandoffStatus.SQL_RESULT_AMBIGUOUS,
                "분석 결과가 복수 행이어서 Design Change 대상을 하나로 확정할 수 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )

        sql = str(sql_result.sql or "")
        if not self._selection_is_proven(sql):
            return self._blocked(
                HandoffStatus.SQL_SELECTION_NOT_PROVEN,
                "SQL에 고원가 정렬과 단일 행 선택 근거가 모두 확인되지 않습니다.",
                scope=scope,
                knowledge=knowledge,
            )
        if not self._sql_contains_scope(sql, scope):
            return self._blocked(
                HandoffStatus.SQL_SCOPE_MISMATCH,
                "SQL 결과가 확정된 VERSION/PLANT 범위에서 조회되었다는 근거가 부족합니다.",
                scope=scope,
                knowledge=knowledge,
            )

        row = dict(rows[0])
        item_codes = self._item_codes(row)
        if not item_codes:
            return self._blocked(
                HandoffStatus.ITEM_CODE_REQUIRED,
                "SQL 결과에 신뢰할 수 있는 자재코드 열이 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )
        if len(item_codes) != 1:
            return self._blocked(
                HandoffStatus.ITEM_CODE_AMBIGUOUS,
                "SQL 결과의 자재코드 열들이 서로 다른 품목을 가리킵니다.",
                scope=scope,
                knowledge=knowledge,
            )

        item_code = item_codes[0]
        if item_code == scope.version_code:
            return self._blocked(
                HandoffStatus.ITEM_CODE_REQUIRED,
                "VERSION 코드는 변경 대상 자재코드로 사용할 수 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )

        metric_values = self._cost_metrics(row)
        if not metric_values:
            return self._blocked(
                HandoffStatus.COST_METRIC_REQUIRED,
                "선택된 자재의 원가/단가 수치 근거가 SQL 결과에 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )
        distinct_metric_values = {round(value, 12) for _, value in metric_values}
        if len(distinct_metric_values) != 1:
            return self._blocked(
                HandoffStatus.COST_METRIC_AMBIGUOUS,
                "SQL 결과에 서로 다른 원가/단가 수치가 있어 어떤 값을 선택 근거로 사용했는지 확정할 수 없습니다.",
                scope=scope,
                knowledge=knowledge,
            )

        metric_name, metric_value = metric_values[0]
        parent_item_code = (
            str(row.get("parent_item_code") or "").strip().upper() or None
        )
        location_code = (
            str(row.get("location_code") or "").strip().upper() or None
        )
        price_source = str(row.get("price_source") or "").strip() or None
        currency_code = str(row.get("currency_code") or "").strip().upper() or None

        analytics = AnalyticsTargetEvidence(
            version_code=scope.version_code,
            plant_code=scope.plant_code,
            item_code=item_code,
            criterion="COST",
            selection_mode="TOP_1_HIGH",
            metric_name=metric_name,
            metric_value=metric_value,
            question=str(sql_result.question or "").strip(),
            row_count=sql_result.row_count,
            parent_item_code=parent_item_code,
            location_code=location_code,
            price_source=price_source,
            currency_code=currency_code,
        )

        # Only prepare the existing Analysis Session tool contract. The Service
        # remains authoritative and revalidates VERSION/PLANT/source relation.
        # When deterministic analytics already identifies the exact BOM edge,
        # preserve parent/location so a nested or repeated material is never
        # silently rebound to another relation.
        action = {
            "action_type": "REPLACE",
            "old_item_code": item_code,
        }
        if parent_item_code:
            action["parent_item_code"] = parent_item_code
        if location_code:
            action["location_code"] = location_code

        tool_arguments = {
            "request": {
                "version_code": scope.version_code,
                "plant_code": scope.plant_code,
                "original_request": goal,
            },
            "actions": [action],
        }

        target_evidence = None
        if parent_item_code and location_code:
            target_evidence = DesignChangeTargetEvidence(
                version_code=scope.version_code,
                plant_code=scope.plant_code,
                item_code=item_code,
                target_type="MATERIAL",
                parent_item_code=parent_item_code,
                location_code=location_code,
                resolution_mode="DETERMINISTIC_ANALYTICS",
                criterion="COST",
                selection_mode="TOP_1_HIGH",
                metric_name=metric_name,
                metric_value=metric_value,
                item_name=str(row.get("item_name") or "").strip() or None,
                price_source=price_source,
                currency_code=currency_code,
            )

        decision = WorkflowHandoffDecision(
            status=HandoffStatus.READY,
            reason=(
                "유일한 read-only analytics target과 knowledge observation이 "
                "검증되어 Design Change Analysis 입력을 준비했습니다."
            ),
            scope=scope,
            analytics_evidence=analytics,
            target_evidence=target_evidence,
            knowledge_evidence=knowledge,
            tool_name="analyze_design_change_candidates",
            tool_arguments=tool_arguments,
        )
        if decision.write_authority_granted:
            raise RuntimeError("Evidence handoff must never grant write authority.")
        return decision

    def build_from_target(
        self,
        *,
        user_goal: str,
        target_evidence: DesignChangeTargetEvidence | None,
        knowledge_payload: dict[str, Any] | None,
        scope: ResolvedWorkflowScope | None,
    ) -> WorkflowHandoffDecision:
        """Build Analysis-only handoff from already verified target evidence.

        This generalized contract accepts either a user-explicit BOM edge or a
        deterministic analytics-selected edge.  It never selects among ambiguous
        rows and never grants Request/approval/Production write authority.
        """
        goal = " ".join(str(user_goal or "").strip().split())
        if not self._is_supported_generalized_goal(goal):
            return self._blocked(
                HandoffStatus.UNSUPPORTED_GOAL,
                "현재 Evidence handoff는 read-only REPLACE Analysis만 지원합니다.",
                scope=scope,
            )
        if scope is None:
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                "Design Change Analysis에는 확정된 VERSION과 PLANT가 필요합니다.",
            )
        if target_evidence is None:
            return self._blocked(
                HandoffStatus.ITEM_CODE_REQUIRED,
                "검증된 Design Change Target Evidence가 없습니다.",
                scope=scope,
            )

        validation_error = self._validate_target_evidence(
            target_evidence=target_evidence,
            scope=scope,
        )
        if validation_error is not None:
            return self._blocked(
                validation_error[0],
                validation_error[1],
                scope=scope,
            )

        knowledge, knowledge_error = self._knowledge_evidence(knowledge_payload)
        if knowledge_error is not None:
            return self._blocked(
                knowledge_error[0],
                knowledge_error[1],
                scope=scope,
            )

        action = {
            "action_type": "REPLACE",
            "old_item_code": target_evidence.item_code,
            "parent_item_code": target_evidence.parent_item_code,
            "location_code": target_evidence.location_code,
        }
        tool_arguments = {
            "request": {
                "version_code": scope.version_code,
                "plant_code": scope.plant_code,
                "original_request": goal,
            },
            "actions": [action],
        }

        analytics: AnalyticsTargetEvidence | None = None
        if (
            target_evidence.resolution_mode == "DETERMINISTIC_ANALYTICS"
            and target_evidence.metric_name
            and target_evidence.metric_value is not None
        ):
            analytics = AnalyticsTargetEvidence(
                version_code=target_evidence.version_code,
                plant_code=target_evidence.plant_code,
                item_code=target_evidence.item_code,
                criterion=target_evidence.criterion,
                selection_mode=target_evidence.selection_mode,
                metric_name=target_evidence.metric_name,
                metric_value=float(target_evidence.metric_value),
                question=goal,
                row_count=1,
                parent_item_code=target_evidence.parent_item_code,
                location_code=target_evidence.location_code,
                price_source=target_evidence.price_source,
                currency_code=target_evidence.currency_code,
            )

        decision = WorkflowHandoffDecision(
            status=HandoffStatus.READY,
            reason=(
                "검증된 source target과 Knowledge Evidence를 기존 "
                "Design Change Analysis Session 입력으로 준비했습니다."
            ),
            scope=scope,
            analytics_evidence=analytics,
            target_evidence=target_evidence,
            knowledge_evidence=knowledge,
            tool_name="analyze_design_change_candidates",
            tool_arguments=tool_arguments,
        )
        if decision.write_authority_granted:
            raise RuntimeError("Evidence handoff must never grant write authority.")
        return decision

    def _is_supported_generalized_goal(self, user_goal: str) -> bool:
        requirement = self.capability_resolver.resolve(user_goal)
        allowed = (
            frozenset({Capability.RAG, Capability.DESIGN_CHANGE_ANALYSIS}),
            frozenset({
                Capability.TEXT_TO_SQL,
                Capability.RAG,
                Capability.DESIGN_CHANGE_ANALYSIS,
            }),
        )
        if not (
            requirement.composition_required
            and requirement.workflow_managed
            and frozenset(requirement.capabilities) in allowed
        ):
            return False

        normalized = self.domain_router.normalize(user_goal)
        if self.domain_router.is_delete_instruction(user_goal):
            return False
        if self.domain_router.is_quantity_change_instruction(user_goal):
            return False
        if any(marker in normalized for marker in ("추가", "넣어")):
            return False
        return True

    @staticmethod
    def _validate_target_evidence(
        *,
        target_evidence: DesignChangeTargetEvidence,
        scope: ResolvedWorkflowScope,
    ) -> tuple[HandoffStatus, str] | None:
        if target_evidence.authority != "READ_ONLY_TARGET_EVIDENCE":
            return (
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                "Target Evidence가 read-only authority로 표시되지 않았습니다.",
            )
        if target_evidence.evidence_source != "READ_ONLY_SCOPED_BOM_EVIDENCE":
            return (
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                "Target Evidence provenance가 scoped read-only BOM 근거가 아닙니다.",
            )
        if target_evidence.resolution_mode not in {
            "EXPLICIT", "DETERMINISTIC_ANALYTICS",
        }:
            return (
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                "지원하지 않는 Target resolution mode입니다.",
            )
        if target_evidence.resolution_mode == "EXPLICIT":
            if (
                target_evidence.criterion != "EXPLICIT"
                or target_evidence.selection_mode != "USER_SPECIFIED"
            ):
                return (
                    HandoffStatus.SQL_RESULT_UNSUPPORTED,
                    "명시 Target Evidence의 criterion/selection mode가 일치하지 않습니다.",
                )
        else:
            if target_evidence.criterion not in {"COST", "COMMONALITY"}:
                return (
                    HandoffStatus.SQL_RESULT_UNSUPPORTED,
                    "지원하지 않는 deterministic Target criterion입니다.",
                )
            if target_evidence.selection_mode not in {"TOP_1_HIGH", "TOP_1_LOW"}:
                return (
                    HandoffStatus.SQL_RESULT_UNSUPPORTED,
                    "deterministic Target은 유일한 TOP-1 selection mode가 필요합니다.",
                )
            if (
                not str(target_evidence.metric_name or "").strip()
                or target_evidence.metric_value is None
            ):
                return (
                    HandoffStatus.SQL_RESULT_UNSUPPORTED,
                    "deterministic Target Evidence에 비교 metric이 없습니다.",
                )
        if (
            target_evidence.version_code.upper() != scope.version_code.upper()
            or target_evidence.plant_code.upper() != scope.plant_code.upper()
        ):
            return (
                HandoffStatus.SQL_SCOPE_MISMATCH,
                "Target Evidence의 VERSION/PLANT가 확정된 Workflow scope와 다릅니다.",
            )
        if not str(target_evidence.item_code or "").strip():
            return (HandoffStatus.ITEM_CODE_REQUIRED, "Target Evidence에 품목코드가 없습니다.")
        if target_evidence.item_code.upper() == scope.version_code.upper():
            return (
                HandoffStatus.ITEM_CODE_REQUIRED,
                "VERSION 코드는 변경 대상 품목코드로 사용할 수 없습니다.",
            )
        if target_evidence.target_type not in {"MATERIAL", "ASSY"}:
            return (
                HandoffStatus.ITEM_CODE_REQUIRED,
                "Design Change source target은 MATERIAL 또는 ASSY여야 합니다.",
            )
        if not str(target_evidence.parent_item_code or "").strip():
            return (
                HandoffStatus.ITEM_CODE_AMBIGUOUS,
                "정확한 BOM edge를 확인할 parent_item_code가 없습니다.",
            )
        if not str(target_evidence.location_code or "").strip():
            return (
                HandoffStatus.ITEM_CODE_AMBIGUOUS,
                "정확한 BOM edge를 확인할 location_code가 없습니다.",
            )
        return None

    def _is_supported_goal(self, user_goal: str) -> bool:
        requirement = self.capability_resolver.resolve(user_goal)
        if not (
            requirement.composition_required
            and requirement.workflow_managed
            and frozenset(requirement.capabilities) == self.REQUIRED_CAPABILITIES
        ):
            return False

        normalized = self.domain_router.normalize(user_goal)
        if self.domain_router.is_delete_instruction(user_goal):
            return False
        if self.domain_router.is_quantity_change_instruction(user_goal):
            return False
        if any(marker in normalized for marker in ("추가", "넣어")):
            return False

        # PLAN-03 foundation is intentionally limited to COST-discovered source
        # material replacement.  Other criteria get their own explicit evidence
        # contracts later.
        return self.domain_router.comparison_criterion(user_goal) == "COST"

    def _has_explicit_unique_selection(self, user_goal: str) -> bool:
        normalized = " ".join(str(user_goal or "").strip().split())
        return any(
            pattern.search(normalized)
            for pattern in self.UNIQUE_SELECTION_PATTERNS
        )

    def _item_codes(self, row: dict[str, Any]) -> list[str]:
        found: list[str] = []
        for key in self.ITEM_CODE_COLUMNS:
            value = str(row.get(key) or "").strip().upper()
            if not value:
                continue
            if self.domain_router.ITEM_CODE_PATTERN.fullmatch(value) is None:
                continue
            if value not in found:
                found.append(value)
        return found

    def _cost_metrics(self, row: dict[str, Any]) -> list[tuple[str, float]]:
        candidates: list[tuple[str, float]] = []

        # Prefer exact business aliases first for deterministic behavior.
        ordered_keys: list[str] = []
        lower_to_original = {
            str(key).strip().lower(): str(key)
            for key in row.keys()
        }
        for key in self.COST_EXACT_COLUMNS:
            original = lower_to_original.get(key.lower())
            if original and original not in ordered_keys:
                ordered_keys.append(original)
        for original in row.keys():
            name = str(original).strip().lower()
            if original in ordered_keys:
                continue
            if any(marker in name for marker in self.COST_COLUMN_MARKERS):
                ordered_keys.append(str(original))

        for key in ordered_keys:
            value = row.get(key)
            if isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            candidates.append((str(key), number))
        return candidates

    @staticmethod
    def _selection_is_proven(sql: str) -> bool:
        normalized = " ".join(str(sql or "").strip().split())
        if not normalized:
            return False
        has_order = re.search(r"\bORDER\s+BY\b", normalized, re.IGNORECASE)
        has_desc = re.search(
            r"\bORDER\s+BY\b.+?\bDESC\b",
            normalized,
            re.IGNORECASE,
        )
        has_limit_one = re.search(
            r"\bLIMIT\s+1(?:\s|;|$)",
            normalized,
            re.IGNORECASE,
        )
        return bool(has_order and has_desc and has_limit_one)

    @staticmethod
    def _sql_contains_scope(
        sql: str,
        scope: ResolvedWorkflowScope,
    ) -> bool:
        upper = str(sql or "").upper()
        return (
            scope.version_code.upper() in upper
            and scope.plant_code.upper() in upper
        )

    @staticmethod
    def _knowledge_evidence(
        payload: dict[str, Any] | None,
    ) -> tuple[
        KnowledgeEvidenceSummary | None,
        tuple[HandoffStatus, str] | None,
    ]:
        if payload is None:
            return None, (
                HandoffStatus.KNOWLEDGE_EVIDENCE_REQUIRED,
                "RAG Knowledge 단계가 아직 실행되지 않았습니다.",
            )
        if not isinstance(payload, dict):
            return None, (
                HandoffStatus.KNOWLEDGE_EVIDENCE_INVALID,
                "RAG Knowledge 결과 형식이 올바르지 않습니다.",
            )
        if payload.get("success") is False:
            return None, (
                HandoffStatus.KNOWLEDGE_EVIDENCE_INVALID,
                "RAG Knowledge 조회가 실패했습니다.",
            )

        authority = payload.get("authority") or {}
        if not (
            isinstance(authority, dict)
            and authority.get("knowledge_evidence_only") is True
        ):
            return None, (
                HandoffStatus.KNOWLEDGE_EVIDENCE_INVALID,
                "RAG 결과가 knowledge_evidence_only 권한으로 표시되지 않았습니다.",
            )

        hits = [
            row for row in (payload.get("hits") or [])
            if isinstance(row, dict)
        ]
        if not hits:
            return None, (
                HandoffStatus.KNOWLEDGE_EVIDENCE_EMPTY,
                "설계변경 기준을 뒷받침할 RAG Knowledge 근거를 찾지 못했습니다.",
            )

        references: list[str] = []
        for row in hits:
            document_id = str(row.get("document_id") or "").strip()
            section = str(row.get("section_path") or "").strip()
            title = str(row.get("document_title") or "").strip()
            label = " / ".join(
                value for value in (document_id, title, section)
                if value
            )
            if label and label not in references:
                references.append(label)

        return KnowledgeEvidenceSummary(
            observed=True,
            hit_count=len(hits),
            references=tuple(references[:8]),
        ), None

    @staticmethod
    def _blocked(
        status: HandoffStatus,
        reason: str,
        *,
        scope: ResolvedWorkflowScope | None = None,
        knowledge: KnowledgeEvidenceSummary | None = None,
    ) -> WorkflowHandoffDecision:
        return WorkflowHandoffDecision(
            status=status,
            reason=reason,
            scope=scope,
            knowledge_evidence=knowledge,
        )


DEFAULT_EVIDENCE_TO_WORKFLOW_HANDOFF = EvidenceToWorkflowHandoff()


__all__ = [
    "AnalyticsTargetEvidence",
    "DesignChangeTargetEvidence",
    "DEFAULT_EVIDENCE_TO_WORKFLOW_HANDOFF",
    "EvidenceToWorkflowHandoff",
    "HandoffStatus",
    "KnowledgeEvidenceSummary",
    "ResolvedWorkflowScope",
    "WorkflowHandoffDecision",
]
