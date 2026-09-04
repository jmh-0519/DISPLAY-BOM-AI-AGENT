"""Evidence-driven workflow analysis composition.

This path resolves either an explicit source target or a deterministic analytics
target, attaches Knowledge evidence, and hands one verified BOM edge into the
existing Design Change Analysis Session.

Runtime authority remains intentionally narrow:
- Text-to-SQL: read-only evidence only.
- RAG: knowledge evidence only.
- Evidence handoff: may prepare one Analysis tool call.
- DesignChangeWorkflowService: remains authoritative for BOM/source validation.
- Request creation, approval and Production E-BOM write are never performed here.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from langchain_core.messages import AIMessage, ToolMessage

from agents.analysis_macro_dispatch import MACRO_ANALYZE_TOOL_CALL_PREFIX
from agents.bom_agent_state import BomAgentState
from agents.bom_graph_gateway import BomGraphGateway
from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementDecision,
    CapabilityRequirementResolver,
    DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER,
)
from agents.selective_planner import (
    DEFAULT_SELECTIVE_PLANNER,
    SelectivePlanner,
)
from agents.workflow_evidence_handoff import (
    DEFAULT_EVIDENCE_TO_WORKFLOW_HANDOFF,
    DesignChangeTargetEvidence,
    EvidenceToWorkflowHandoff,
    HandoffStatus,
    ResolvedWorkflowScope,
)
from agents.workflow_target_resolution import (
    DEFAULT_WORKFLOW_TARGET_RESOLUTION_PLANNER,
    TargetCriterion,
    TargetResolutionMode,
    WorkflowTargetResolutionPlanner,
)
from core.performance_profiler import record_performance_event
from rag.query_router import (
    DEFAULT_KNOWLEDGE_QUERY_ROUTER,
    KnowledgeQueryRouter,
)
from text_to_sql.pipeline import TextToSqlPipelineResult
from text_to_sql.workflow_cost_evidence import ScopedBomCostEvidenceQuery
from text_to_sql.workflow_target_evidence import (
    ScopedBomTargetEvidenceQuery,
    TargetEvidenceQueryResult,
    TargetQueryStatus,
)


WORKFLOW_COMPOSITION_PLAN = "workflow_composition_plan"
WORKFLOW_COMPOSITION_TARGET_RESOLVE = "workflow_composition_target_resolve"
WORKFLOW_COMPOSITION_TEXT_TO_SQL = "workflow_composition_text_to_sql"
WORKFLOW_COMPOSITION_KNOWLEDGE_QUERY = "workflow_composition_knowledge_query"
WORKFLOW_COMPOSITION_HANDOFF = "workflow_composition_handoff"
WORKFLOW_COMPOSITION_ANALYSIS_FINALIZE = "workflow_composition_analysis_finalize"

WORKFLOW_COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX = (
    "workflow-composition-knowledge-"
)
# Keep the existing deterministic Analysis Finalizer contract while preserving
# a distinguishable suffix for observability/tests.
WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX = (
    f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}composition-"
)


class BomWorkflowCompositionNodes:
    """Execute a guarded target evidence + RAG -> Analysis composition.

    Explicit targets bypass analytics.  Deterministic ranked targets use the
    read-only BOM evidence executor.  The node never creates a Design Change
    Request and can dispatch only ``analyze_design_change_candidates``.
    """

    SUPPORTED_RUNTIME_CAPABILITY_SETS = frozenset({
        frozenset({Capability.RAG, Capability.DESIGN_CHANGE_ANALYSIS}),
        frozenset({
            Capability.TEXT_TO_SQL,
            Capability.RAG,
            Capability.DESIGN_CHANGE_ANALYSIS,
        }),
    })
    SAFE_START_STEPS = frozenset({"NOT_STARTED"})
    REPLACEABLE_PRE_REQUEST_ANALYSIS_STEPS = frozenset({
        "ANALYSIS_READY",
        "ANALYSIS_REVALIDATED",
        "ANALYSIS_IMPACT_REVIEW",
        "ANALYSIS_CONFIRMED",
    })

    def __init__(
        self,
        *,
        text_to_sql_nodes,
        analysis_finalizer: Callable[[BomAgentState], BomAgentState],
        capability_resolver: CapabilityRequirementResolver | None = None,
        planner: SelectivePlanner | None = None,
        handoff: EvidenceToWorkflowHandoff | None = None,
        knowledge_router: KnowledgeQueryRouter | None = None,
        cost_evidence_query: ScopedBomCostEvidenceQuery | None = None,
        target_resolution_planner: WorkflowTargetResolutionPlanner | None = None,
        target_evidence_query: ScopedBomTargetEvidenceQuery | None = None,
    ) -> None:
        self.text_to_sql_nodes = text_to_sql_nodes
        self.analysis_finalizer = analysis_finalizer
        self.capability_resolver = (
            capability_resolver or DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
        )
        self.planner = planner or DEFAULT_SELECTIVE_PLANNER
        self.handoff = handoff or DEFAULT_EVIDENCE_TO_WORKFLOW_HANDOFF
        self.knowledge_router = (
            knowledge_router or DEFAULT_KNOWLEDGE_QUERY_ROUTER
        )
        self.target_resolution_planner = (
            target_resolution_planner
            or DEFAULT_WORKFLOW_TARGET_RESOLUTION_PLANNER
        )
        pipeline = getattr(self.text_to_sql_nodes, "pipeline", None)
        executor = getattr(pipeline, "executor", None)
        self.target_evidence_query = (
            target_evidence_query
            if target_evidence_query is not None
            else (ScopedBomTargetEvidenceQuery(executor) if executor is not None else None)
        )
        if cost_evidence_query is not None:
            self.cost_evidence_query = cost_evidence_query
        else:
            self.cost_evidence_query = (
                ScopedBomCostEvidenceQuery(executor)
                if executor is not None
                else None
            )

    def can_execute(self, state: BomAgentState) -> bool:
        """Admit only safe, fully-scoped Evidence -> Analysis compositions."""
        workflow = state.get("design_change") or {}
        step = str(workflow.get("current_step") or "NOT_STARTED").strip().upper()
        if str(workflow.get("pending_quantity_request") or "").strip():
            return False
        if workflow.get("pending_add_target_request"):
            return False
        if workflow.get("pending_add_parent_request"):
            return False
        if workflow.get("pending_version_request"):
            return False

        query = BomGraphGateway.last_user_query(state)
        requirement = self.capability_resolver.resolve(query)
        if not self._supported_requirement(requirement):
            return False

        scope = self.handoff.resolve_scope(
            query,
            active_bom_context=state.get("active_bom_context"),
        )
        if scope is None:
            return False
        if not self._safe_scope_entry(workflow=workflow, step=step, scope=scope):
            return False

        target_decision = self.target_resolution_planner.resolve(
            query,
            scope_version_code=scope.version_code,
        )
        if not target_decision.ready:
            # Analytics requests with a non-unique ranking are intentionally
            # admitted so the plan node can return a deterministic clarification
            # instead of falling back to LLM target selection.  Other unsupported
            # shapes (for example an explicit old/new pair) stay on the existing
            # Agent/Macro path.
            if Capability.TEXT_TO_SQL not in requirement.capabilities:
                return False

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        if plan is None or plan.write_authority_granted:
            return False
        return frozenset(requirement.capabilities) in self.SUPPORTED_RUNTIME_CAPABILITY_SETS

    def plan(self, state: BomAgentState) -> BomAgentState:
        query = BomGraphGateway.last_user_query(state)
        requirement = self.capability_resolver.resolve(query)
        if not self._supported_requirement(requirement):
            raise ValueError(
                "Workflow Composition Path received an unsupported requirement."
            )

        scope = self.handoff.resolve_scope(
            query,
            active_bom_context=state.get("active_bom_context"),
        )
        if scope is None:
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                "설계변경 분석을 시작하려면 MODEL과 PLANT 범위를 먼저 확정해 주세요.",
            )

        workflow = state.get("design_change") or {}
        step = str(workflow.get("current_step") or "NOT_STARTED").strip().upper()
        if not self._safe_scope_entry(workflow=workflow, step=step, scope=scope):
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                (
                    "진행 중인 설계변경 Workflow를 자동으로 다른 범위로 전환할 수 "
                    "없습니다. 새 분석은 Request 생성 전 Analysis 상태에서 현재 "
                    "MODEL/PLANT를 명시한 경우에만 시작할 수 있습니다."
                ),
            )

        target_decision = self.target_resolution_planner.resolve(
            query,
            scope_version_code=scope.version_code,
        )
        if not target_decision.ready or target_decision.request is None:
            return self._blocked(
                HandoffStatus.USER_SELECTION_REQUIRED,
                target_decision.blocked_reason
                or "변경 대상을 하나로 확정할 수 없습니다.",
            )
        target_request = target_decision.request

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        if plan is None or plan.write_authority_granted:
            raise ValueError("Workflow Composition requires a safe Planner plan.")

        queries: dict[str, str] = {
            Capability.RAG.value: self._knowledge_query(
                query,
                target_request=target_request.as_dict(),
            )
        }
        if target_request.analytics_required:
            queries[Capability.TEXT_TO_SQL.value] = self._analytics_question(
                scope=scope,
                target_request=target_request.as_dict(),
            )

        runtime = {
            "mode": "WORKFLOW_ANALYSIS_COMPOSITION",
            "status": "PLANNED",
            "original_query": query,
            "plan": plan.as_dict(),
            "scope": scope.as_dict(),
            "target_request": target_request.as_dict(),
            "target_evidence": None,
            "queries": queries,
            "results": {},
            "handoff": None,
            "write_authority_granted": False,
        }
        record_performance_event(
            category="planning",
            name="workflow_composition.plan",
            metadata={
                "capability_count": len(plan.steps),
                "workflow_managed": True,
                "target_resolution_mode": target_request.mode.value,
                "target_criterion": target_request.criterion.value,
            },
            metrics={"step_count": len(plan.steps)},
        )
        return {"composition_runtime": runtime, "error": None}

    def resolve_explicit_target(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        scope = self._deserialize_scope(runtime.get("scope"))
        target_request = runtime.get("target_request") or {}
        if scope is None:
            return self._blocked(HandoffStatus.SCOPE_REQUIRED, "변경 대상 범위가 없습니다.")
        if self.target_evidence_query is None:
            return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, "명시 Target을 검증할 read-only resolver가 없습니다.")
        try:
            result = self.target_evidence_query.resolve_explicit(
                version_code=scope.version_code,
                plant_code=scope.plant_code,
                item_code=target_request.get("explicit_item_code"),
                target_name=target_request.get("explicit_target_name"),
            )
        except Exception:
            return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, "명시 Target BOM 근거를 안전하게 확인하지 못했습니다.")
        return self._apply_target_result(runtime, scope, target_request, result, execution_mode="DETERMINISTIC_EXPLICIT_BOM_TARGET")

    def text_to_sql(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        query = self._runtime_query(runtime, Capability.TEXT_TO_SQL)
        scope = self._deserialize_scope(runtime.get("scope"))
        target_request = runtime.get("target_request") or {}
        if scope is None:
            return self._blocked(HandoffStatus.SCOPE_REQUIRED, "변경 대상 선정을 위한 MODEL/PLANT 범위가 없습니다.")

        criterion = str(target_request.get("criterion") or "").upper()
        selection_mode = str(target_request.get("selection_mode") or "").upper()
        try:
            if self.target_evidence_query is not None:
                if criterion == TargetCriterion.COST.value:
                    result = self.target_evidence_query.resolve_cost_rank(
                        version_code=scope.version_code,
                        plant_code=scope.plant_code,
                        direction="LOW" if selection_mode == "TOP_1_LOW" else "HIGH",
                    )
                elif criterion == TargetCriterion.COMMONALITY.value:
                    result = self.target_evidence_query.resolve_commonality_rank(
                        version_code=scope.version_code,
                        plant_code=scope.plant_code,
                    )
                else:
                    return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, "지원하지 않는 deterministic 분석 기준입니다.")
                return self._apply_target_result(runtime, scope, target_request, result, execution_mode="DETERMINISTIC_SCOPED_BOM_SQL")

            # Compatibility path for existing isolated tests/validators.
            if criterion != TargetCriterion.COST.value or self.cost_evidence_query is None:
                return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, "deterministic target evidence resolver가 없습니다.")
            legacy = self.cost_evidence_query.run(
                version_code=scope.version_code,
                plant_code=scope.plant_code,
                question=query,
            )
            if legacy.status != "SQL" or not legacy.rows:
                fallback_reason = str(legacy.reason or "").strip()
                if not fallback_reason and criterion == TargetCriterion.COST.value:
                    fallback_reason = (
                        f"{scope.version_code} / {scope.plant_code} 활성 BOM에는 "
                        "현재 비교 가능한 원가/단가 근거가 등록된 자재가 없습니다."
                    )
                return self._blocked(
                    HandoffStatus.SQL_RESULT_EMPTY,
                    fallback_reason or "비교 가능한 Target Evidence가 없습니다.",
                )
            if legacy.row_count != 1:
                return self._blocked(HandoffStatus.USER_SELECTION_REQUIRED, "동일 ranking 조건의 Target이 복수입니다. 품목을 직접 선택해 주세요.")
            row = dict(legacy.rows[0])
            evidence = self._target_evidence_from_row(scope, target_request, row)
            updated = self._copy_runtime(runtime)
            updated["status"] = "TARGET_RESOLVED"
            updated["target_evidence"] = evidence.as_dict()
            updated["results"][Capability.TEXT_TO_SQL.value] = {
                "query": query,
                "answer": self.text_to_sql_nodes._format_result(legacy),
                "raw": self._serialize_sql_result(legacy),
                "authority": "READ_ONLY_SQL_EVIDENCE",
                "execution_mode": "DETERMINISTIC_SCOPED_BOM_SQL",
            }
            return {"composition_runtime": updated, "error": None}
        except Exception:
            return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, "변경 대상 선정을 위한 읽기 전용 분석 조회를 안전하게 실행하지 못했습니다.")

    def knowledge_query(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        query = self._runtime_query(runtime, Capability.RAG)
        decision = self.knowledge_router.route(query)
        if not decision.eligible:
            return self._blocked(
                HandoffStatus.KNOWLEDGE_EVIDENCE_INVALID,
                "설계변경 기준을 조회할 안전한 Knowledge 질의를 구성하지 못했습니다.",
            )

        args: dict[str, object] = {"query": query, "top_k": 8}
        if decision.document_type:
            args["document_type"] = decision.document_type

        call_id = (
            f"{WORKFLOW_COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX}"
            f"{uuid.uuid4().hex[:12]}"
        )
        updated = self._copy_runtime(runtime)
        updated["status"] = "KNOWLEDGE_QUERY_DISPATCHED"
        updated["knowledge_tool_call_id"] = call_id
        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_knowledge",
                    "args": args,
                    "id": call_id,
                    "type": "tool_call",
                }],
            )],
            "composition_runtime": updated,
            "error": None,
        }

    def handoff_and_dispatch(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], ToolMessage):
            raise ValueError("Workflow Handoff requires a Knowledge ToolMessage.")
        if not is_workflow_composition_knowledge_tool_result(state):
            raise ValueError("Workflow Handoff received another Tool result.")

        try:
            knowledge_payload = json.loads(str(messages[-1].content or "{}"))
        except (TypeError, json.JSONDecodeError):
            knowledge_payload = {}
        if not isinstance(knowledge_payload, dict):
            knowledge_payload = {}

        scope = self._deserialize_scope(runtime.get("scope"))
        target_evidence = self._deserialize_target_evidence(
            runtime.get("target_evidence")
        )
        decision = self.handoff.build_from_target(
            user_goal=str(runtime.get("original_query") or ""),
            target_evidence=target_evidence,
            knowledge_payload=knowledge_payload,
            scope=scope,
        )
        if not decision.ready:
            return {
                "messages": [AIMessage(content=decision.reason)],
                "composition_runtime": None,
                "error": None,
            }

        if (
            decision.tool_name != "analyze_design_change_candidates"
            or not isinstance(decision.tool_arguments, dict)
            or decision.write_authority_granted
        ):
            raise RuntimeError(
                "READY handoff violated the Design Change Analysis authority contract."
            )

        updated = self._copy_runtime(runtime)
        updated["status"] = "HANDOFF_READY"
        updated["handoff"] = decision.as_dict()
        updated["results"][Capability.RAG.value] = {
            "query": self._runtime_query(runtime, Capability.RAG),
            "authority": "RAG_EVIDENCE_ONLY",
            "knowledge_evidence": (
                decision.knowledge_evidence.as_dict()
                if decision.knowledge_evidence else None
            ),
        }

        record_performance_event(
            category="planning",
            name="workflow_composition.handoff_ready",
            metadata={
                "tool_name": decision.tool_name,
                "write_authority_granted": False,
            },
            metrics={"candidate_target_count": 1},
        )
        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": decision.tool_name,
                    "args": decision.tool_arguments,
                    "id": (
                        f"{WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX}"
                        f"{uuid.uuid4().hex[:12]}"
                    ),
                    "type": "tool_call",
                }],
            )],
            "composition_runtime": updated,
            "error": None,
        }

    def analysis_finalize(self, state: BomAgentState) -> BomAgentState:
        """Reuse the existing deterministic Analysis finalizer and clear runtime."""
        if not is_workflow_composition_analysis_tool_result(state):
            raise ValueError(
                "Workflow Analysis Finalizer requires a composed Analysis result."
            )

        update = self.analysis_finalizer(state)
        messages = update.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            raise RuntimeError("Design Change Analysis finalizer returned no answer.")

        runtime = self._runtime(state)
        handoff = runtime.get("handoff") or {}
        target = handoff.get("target_evidence") or handoff.get("analytics_evidence") or {}
        knowledge = handoff.get("knowledge_evidence") or {}

        evidence_lines: list[str] = []
        item_code = str(target.get("item_code") or "").strip()
        metric_name = str(target.get("metric_name") or "").strip()
        metric_value = target.get("metric_value")
        resolution_mode = str(target.get("resolution_mode") or "").strip()
        if item_code:
            metric_text = (
                f" · {metric_name}={metric_value}"
                if metric_name and metric_value is not None else ""
            )
            mode_text = "사용자 지정" if resolution_mode == "EXPLICIT" else "deterministic evidence"
            evidence_lines.append(
                f"- 분석 대상 선정 근거: {item_code} · {mode_text}{metric_text}"
            )

        references = [
            str(value).strip()
            for value in (knowledge.get("references") or [])
            if str(value).strip()
        ]
        for reference in references[:3]:
            evidence_lines.append(f"- Knowledge 근거: {reference}")

        answer = str(messages[-1].content or "").strip()
        if evidence_lines:
            answer = (
                f"{answer}\n\n복합 분석 근거\n"
                + "\n".join(evidence_lines)
            )

        record_performance_event(
            category="planning",
            name="workflow_composition.complete",
            metadata={
                "analysis_only": True,
                "request_creation_allowed": False,
                "production_bom_write_allowed": False,
            },
            metrics={"reference_count": len(references[:3])},
        )
        return {
            "messages": [AIMessage(content=answer)],
            "composition_runtime": None,
            "error": update.get("error"),
        }

    def _supported_requirement(
        self,
        requirement: CapabilityRequirementDecision,
    ) -> bool:
        return bool(
            requirement.composition_required
            and requirement.workflow_managed
            and frozenset(requirement.capabilities)
            in self.SUPPORTED_RUNTIME_CAPABILITY_SETS
        )

    @classmethod
    def _safe_scope_entry(
        cls,
        *,
        workflow: dict[str, Any],
        step: str,
        scope: ResolvedWorkflowScope,
    ) -> bool:
        """Allow fresh composition only across the pre-Request boundary.

        Relative requests on an existing Analysis must remain with that
        Analysis.  Replacing a temporary Analysis scope is allowed only when
        the current turn explicitly resolves MODEL/PLANT.  Once a Request
        exists, the normal HITL workflow owns the transaction and composition
        can never switch scope.
        """
        if step in cls.SAFE_START_STEPS:
            return True
        if step not in cls.REPLACEABLE_PRE_REQUEST_ANALYSIS_STEPS:
            return False
        if str(workflow.get("request_id") or "").strip():
            return False
        return scope.source == "CURRENT_TURN_EXPLICIT"

    @staticmethod
    def _knowledge_query(
        user_goal: str,
        *,
        target_request: dict[str, Any],
    ) -> str:
        criterion = str(target_request.get("criterion") or "").strip().upper()
        if criterion == TargetCriterion.COST.value:
            return "원가 절감 설계변경 기준과 영향"
        if criterion == TargetCriterion.COMMONALITY.value:
            return "공용화 설계변경 기준과 영향"

        normalized = " ".join(str(user_goal or "").strip().split()).lower()
        reason_queries = (
            (("단종", "eol"), "단종 설계변경 기준과 영향"),
            (("공급 중단", "공급중단", "supplier stop"), "공급 중단 설계변경 기준과 영향"),
            (("납기",), "납기 설계변경 기준과 영향"),
            (("원가", "비용"), "원가 절감 설계변경 기준과 영향"),
            (("재고",), "재고 설계변경 기준과 영향"),
            (("품질", "불량"), "품질 설계변경 기준과 영향"),
            (("규제", "인증"), "규제 설계변경 기준과 영향"),
            (("공용화", "공통화"), "공용화 설계변경 기준과 영향"),
        )
        for markers, query in reason_queries:
            if any(marker in normalized for marker in markers):
                return query
        return "설계변경 기준과 영향"

    @staticmethod
    def _analytics_question(
        *,
        scope: ResolvedWorkflowScope,
        target_request: dict[str, Any],
    ) -> str:
        criterion = str(target_request.get("criterion") or "").upper()
        selection_mode = str(target_request.get("selection_mode") or "").upper()
        if criterion == TargetCriterion.COST.value:
            direction = "낮은" if selection_mode == "TOP_1_LOW" else "높은"
            return (
                f"{scope.version_code} {scope.plant_code} 모델의 활성 BOM에서 "
                f"현재 비교 가능한 원가 또는 단가가 가장 {direction} 자재 1개"
            )
        if criterion == TargetCriterion.COMMONALITY.value:
            return (
                f"{scope.version_code} {scope.plant_code} 모델의 활성 BOM에서 "
                "동일 PLANT의 활성 VERSION 사용 모델 수가 가장 많은 자재 1개"
            )
        raise ValueError("Unsupported workflow analytics criterion")

    def _apply_target_result(
        self,
        runtime: dict[str, Any],
        scope: ResolvedWorkflowScope,
        target_request: dict[str, Any],
        result: TargetEvidenceQueryResult,
        *,
        execution_mode: str,
    ) -> BomAgentState:
        if result.status == TargetQueryStatus.EMPTY:
            return self._blocked(HandoffStatus.SQL_RESULT_EMPTY, result.reason)
        if result.status == TargetQueryStatus.AMBIGUOUS:
            return self._blocked(HandoffStatus.USER_SELECTION_REQUIRED, result.reason)
        if not result.ready or result.row is None:
            return self._blocked(HandoffStatus.SQL_RESULT_UNSUPPORTED, result.reason)

        evidence = self._target_evidence_from_row(
            scope,
            target_request,
            result.row,
        )
        updated = self._copy_runtime(runtime)
        updated["status"] = "TARGET_RESOLVED"
        updated["target_evidence"] = evidence.as_dict()
        if str(target_request.get("mode") or "") == TargetResolutionMode.DETERMINISTIC_ANALYTICS.value:
            updated["results"][Capability.TEXT_TO_SQL.value] = {
                "query": (runtime.get("queries") or {}).get(Capability.TEXT_TO_SQL.value),
                "authority": result.authority,
                "execution_mode": execution_mode,
                "criterion": result.criterion,
                "selection_mode": result.selection_mode,
                "sql": result.sql,
                "rows": [dict(row) for row in result.rows],
            }
        else:
            updated["results"]["TARGET_RESOLUTION"] = {
                "authority": result.authority,
                "execution_mode": execution_mode,
                "rows": [dict(row) for row in result.rows],
            }
        return {"composition_runtime": updated, "error": None}

    @staticmethod
    def _target_evidence_from_row(
        scope: ResolvedWorkflowScope,
        target_request: dict[str, Any],
        row: dict[str, Any],
    ) -> DesignChangeTargetEvidence:
        item_type = str(row.get("target_item_type") or "").strip().upper()
        target_type = "ASSY" if item_type == "ASSEMBLY" else "MATERIAL"
        metric_name: str | None = None
        metric_value: float | None = None
        criterion = str(target_request.get("criterion") or "EXPLICIT").strip().upper()
        if criterion == TargetCriterion.COST.value and row.get("unit_cost") is not None:
            metric_name = "unit_cost"
            metric_value = float(row.get("unit_cost"))
        elif criterion == TargetCriterion.COMMONALITY.value and row.get("active_version_usage_count") is not None:
            metric_name = "active_version_usage_count"
            metric_value = float(row.get("active_version_usage_count"))

        return DesignChangeTargetEvidence(
            version_code=scope.version_code,
            plant_code=scope.plant_code,
            item_code=str(row.get("item_code") or "").strip().upper(),
            target_type=target_type,
            parent_item_code=str(row.get("parent_item_code") or "").strip().upper(),
            location_code=str(row.get("location_code") or "").strip().upper(),
            resolution_mode=str(target_request.get("mode") or "").strip().upper(),
            criterion=criterion,
            selection_mode=str(target_request.get("selection_mode") or "USER_SPECIFIED").strip().upper(),
            metric_name=metric_name,
            metric_value=metric_value,
            item_name=str(row.get("item_name") or "").strip() or None,
            price_source=str(row.get("price_source") or "").strip() or None,
            currency_code=str(row.get("currency_code") or "").strip().upper() or None,
        )

    @staticmethod
    def _serialize_sql_result(
        result: TextToSqlPipelineResult,
    ) -> dict[str, Any]:
        return {
            "status": result.status,
            "question": result.question,
            "sql": result.sql,
            "reason": result.reason,
            "columns": list(result.columns),
            "rows": [dict(row) for row in result.rows],
            "row_count": result.row_count,
            "truncated": result.truncated,
            "elapsed_ms": result.elapsed_ms,
        }

    @staticmethod
    def _deserialize_sql_result(
        payload: Any,
    ) -> TextToSqlPipelineResult | None:
        if not isinstance(payload, dict):
            return None
        rows = payload.get("rows")
        columns = payload.get("columns")
        if not isinstance(rows, list) or not isinstance(columns, list):
            return None
        return TextToSqlPipelineResult(
            status=str(payload.get("status") or ""),
            question=str(payload.get("question") or ""),
            sql=payload.get("sql"),
            reason=str(payload.get("reason") or ""),
            columns=tuple(str(value) for value in columns),
            rows=tuple(dict(row) for row in rows if isinstance(row, dict)),
            row_count=int(payload.get("row_count") or 0),
            truncated=bool(payload.get("truncated")),
            elapsed_ms=float(payload.get("elapsed_ms") or 0.0),
        )

    @staticmethod
    def _deserialize_target_evidence(payload: Any) -> DesignChangeTargetEvidence | None:
        if not isinstance(payload, dict):
            return None
        required = (
            "version_code", "plant_code", "item_code", "target_type",
            "parent_item_code", "location_code", "resolution_mode",
            "criterion", "selection_mode",
        )
        if any(not str(payload.get(key) or "").strip() for key in required):
            return None
        metric_value = payload.get("metric_value")
        return DesignChangeTargetEvidence(
            version_code=str(payload["version_code"]).strip().upper(),
            plant_code=str(payload["plant_code"]).strip().upper(),
            item_code=str(payload["item_code"]).strip().upper(),
            target_type=str(payload["target_type"]).strip().upper(),
            parent_item_code=str(payload["parent_item_code"]).strip().upper(),
            location_code=str(payload["location_code"]).strip().upper(),
            resolution_mode=str(payload["resolution_mode"]).strip().upper(),
            criterion=str(payload["criterion"]).strip().upper(),
            selection_mode=str(payload["selection_mode"]).strip().upper(),
            metric_name=str(payload.get("metric_name") or "").strip() or None,
            metric_value=(float(metric_value) if metric_value is not None else None),
            item_name=str(payload.get("item_name") or "").strip() or None,
            price_source=str(payload.get("price_source") or "").strip() or None,
            currency_code=str(payload.get("currency_code") or "").strip().upper() or None,
        )

    @staticmethod
    def _deserialize_scope(payload: Any) -> ResolvedWorkflowScope | None:
        if not isinstance(payload, dict):
            return None
        version = str(payload.get("version_code") or "").strip().upper()
        plant = str(payload.get("plant_code") or "").strip().upper()
        if not version or not plant:
            return None
        return ResolvedWorkflowScope(
            version_code=version,
            plant_code=plant,
            source=str(payload.get("source") or "COMPOSITION_RUNTIME"),
        )

    @staticmethod
    def _runtime(state: BomAgentState) -> dict[str, Any]:
        runtime = state.get("composition_runtime")
        if not isinstance(runtime, dict):
            raise ValueError("Workflow Composition runtime state is missing.")
        if runtime.get("mode") != "WORKFLOW_ANALYSIS_COMPOSITION":
            raise ValueError("Another composition runtime is active.")
        return runtime

    @staticmethod
    def _runtime_query(runtime: dict[str, Any], capability: Capability) -> str:
        queries = runtime.get("queries") or {}
        value = str(queries.get(capability.value) or "").strip()
        if not value:
            raise ValueError(
                f"Workflow Composition subquery is missing for {capability.value}."
            )
        return value

    @staticmethod
    def _copy_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
        copied = dict(runtime)
        copied["queries"] = dict(runtime.get("queries") or {})
        copied["results"] = dict(runtime.get("results") or {})
        return copied

    @staticmethod
    def _blocked(status: HandoffStatus, reason: str) -> BomAgentState:
        record_performance_event(
            category="planning",
            name="workflow_composition.blocked",
            metadata={"status": status.value},
        )
        return {
            "messages": [AIMessage(content=str(reason).strip())],
            "composition_runtime": None,
            "error": None,
        }


def is_workflow_composition_knowledge_tool_result(
    state: BomAgentState,
) -> bool:
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False
    message = messages[-1]
    return bool(
        message.name == "search_knowledge"
        and str(message.tool_call_id or "").startswith(
            WORKFLOW_COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX
        )
    )


def is_workflow_composition_analysis_tool_result(
    state: BomAgentState,
) -> bool:
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False
    message = messages[-1]
    return bool(
        message.name == "analyze_design_change_candidates"
        and str(message.tool_call_id or "").startswith(
            WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX
        )
    )


__all__ = [
    "BomWorkflowCompositionNodes",
    "WORKFLOW_COMPOSITION_ANALYSIS_FINALIZE",
    "WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX",
    "WORKFLOW_COMPOSITION_HANDOFF",
    "WORKFLOW_COMPOSITION_KNOWLEDGE_QUERY",
    "WORKFLOW_COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX",
    "WORKFLOW_COMPOSITION_PLAN",
    "WORKFLOW_COMPOSITION_TARGET_RESOLVE",
    "WORKFLOW_COMPOSITION_TEXT_TO_SQL",
    "is_workflow_composition_analysis_tool_result",
    "is_workflow_composition_knowledge_tool_result",
]
