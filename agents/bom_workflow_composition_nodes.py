"""PLAN-04 workflow-aware runtime composition.

This path composes read-only analytics + Knowledge evidence and hands a verified
single source item into the existing Design Change Analysis Session.

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
    EvidenceToWorkflowHandoff,
    HandoffStatus,
    ResolvedWorkflowScope,
)
from core.performance_profiler import record_performance_event
from rag.query_router import (
    DEFAULT_KNOWLEDGE_QUERY_ROUTER,
    KnowledgeQueryRouter,
)
from text_to_sql.pipeline import TextToSqlPipelineResult
from text_to_sql.workflow_cost_evidence import ScopedBomCostEvidenceQuery


WORKFLOW_COMPOSITION_PLAN = "workflow_composition_plan"
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
    """Execute a guarded TEXT_TO_SQL + RAG -> Analysis composition.

    The node never creates a Design Change Request.  It can only dispatch the
    existing read-only ``analyze_design_change_candidates`` Tool after the
    PLAN-03 evidence contract returns READY.
    """

    SUPPORTED_RUNTIME_CAPABILITIES = frozenset({
        Capability.TEXT_TO_SQL,
        Capability.RAG,
        Capability.DESIGN_CHANGE_ANALYSIS,
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
        if cost_evidence_query is not None:
            self.cost_evidence_query = cost_evidence_query
        else:
            pipeline = getattr(self.text_to_sql_nodes, "pipeline", None)
            executor = getattr(pipeline, "executor", None)
            self.cost_evidence_query = (
                ScopedBomCostEvidenceQuery(executor)
                if executor is not None
                else None
            )

    def can_execute(self, state: BomAgentState) -> bool:
        """Admit only fresh, fully scoped workflow compositions.

        Missing MODEL/PLANT scope remains on the existing Agent path so the
        current PLANT/context clarification UX is preserved.
        """
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
        if not self._safe_scope_entry(
            workflow=workflow,
            step=step,
            scope=scope,
        ):
            return False

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        return bool(
            plan is not None
            and not plan.write_authority_granted
            and plan.capability_names
            == ("TEXT_TO_SQL", "RAG", "DESIGN_CHANGE_ANALYSIS")
        )

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
            # can_execute() prevents this route at Graph entry. Keep the node
            # defensive for direct invocation/tests.
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                "설계변경 분석을 시작하려면 MODEL과 PLANT 범위를 먼저 확정해 주세요.",
            )

        workflow = state.get("design_change") or {}
        step = str(workflow.get("current_step") or "NOT_STARTED").strip().upper()
        if not self._safe_scope_entry(
            workflow=workflow,
            step=step,
            scope=scope,
        ):
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                (
                    "진행 중인 설계변경 Workflow를 자동으로 다른 범위로 전환할 수 "
                    "없습니다. 새 분석은 Request 생성 전 Analysis 상태에서 현재 "
                    "MODEL/PLANT를 명시한 경우에만 시작할 수 있습니다."
                ),
            )

        preflight = self.handoff.build(
            user_goal=query,
            sql_result=None,
            knowledge_payload=None,
            scope=scope,
        )
        if preflight.status == HandoffStatus.USER_SELECTION_REQUIRED:
            return self._blocked(preflight.status, preflight.reason)
        if preflight.status == HandoffStatus.UNSUPPORTED_GOAL:
            return self._blocked(preflight.status, preflight.reason)
        if preflight.status != HandoffStatus.KNOWLEDGE_EVIDENCE_REQUIRED:
            return self._blocked(preflight.status, preflight.reason)

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        if plan is None or plan.write_authority_granted:
            raise ValueError("Workflow Composition requires a safe Planner plan.")

        analytics_query = self.handoff.build_scoped_analytics_question(
            query,
            scope=scope,
        )
        if not analytics_query:
            return self._blocked(
                HandoffStatus.USER_SELECTION_REQUIRED,
                (
                    "변경 대상을 자동 선정하려면 '가장 원가가 높은 자재 1개'처럼 "
                    "유일한 선택 기준을 명시해 주세요."
                ),
            )

        knowledge_query = self._knowledge_query(query)
        runtime = {
            "mode": "WORKFLOW_ANALYSIS_COMPOSITION",
            "status": "PLANNED",
            "original_query": query,
            "plan": plan.as_dict(),
            "scope": scope.as_dict(),
            "queries": {
                Capability.TEXT_TO_SQL.value: analytics_query,
                Capability.RAG.value: knowledge_query,
            },
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
            },
            metrics={"step_count": len(plan.steps)},
        )
        return {
            "composition_runtime": runtime,
            "error": None,
        }

    def text_to_sql(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        query = self._runtime_query(runtime, Capability.TEXT_TO_SQL)
        scope = self._deserialize_scope(runtime.get("scope"))
        if scope is None:
            return self._blocked(
                HandoffStatus.SCOPE_REQUIRED,
                "변경 대상 선정을 위한 MODEL/PLANT 범위가 없습니다.",
            )

        try:
            if self.cost_evidence_query is not None:
                # Workflow target promotion must not depend on free-form SQL
                # generation.  Use one deterministic recursive BOM query over
                # the same read-only executor.  General FAST_TEXT_TO_SQL and
                # PLAN-02 ad-hoc analytics continue to use LLM Text-to-SQL.
                result = self.cost_evidence_query.run(
                    version_code=scope.version_code,
                    plant_code=scope.plant_code,
                    question=query,
                )
                execution_mode = "DETERMINISTIC_SCOPED_BOM_SQL"
            else:
                # Test/backward-compatibility fallback only.  Production graph
                # supplies a real TextToSqlPipeline with ReadOnlySqlExecutor.
                result = self.text_to_sql_nodes.execute_result(query)
                execution_mode = "GENERATED_SQL_FALLBACK"
        except Exception:
            return self._blocked(
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                (
                    "변경 대상 선정을 위한 읽기 전용 분석 조회를 안전하게 실행하지 "
                    "못했습니다. MODEL/PLANT와 선택 기준을 확인해 주세요."
                ),
            )

        if result.status != "SQL":
            return self._blocked(
                HandoffStatus.SQL_RESULT_UNSUPPORTED,
                str(result.reason or "").strip()
                or "변경 대상 선정을 위한 분석 조회를 수행할 수 없습니다.",
            )

        # A reachable BOM material without comparable COST evidence must never
        # be promoted into a Design Change target.  Stop here before RAG so the
        # user gets the real data-quality reason and no unnecessary Knowledge
        # or Analysis tool is executed.
        if result.row_count == 0 or not result.rows:
            return self._blocked(
                HandoffStatus.SQL_RESULT_EMPTY,
                (
                    f"{scope.version_code} / {scope.plant_code} 활성 BOM에는 "
                    "현재 비교 가능한 원가/단가 근거가 등록된 자재가 없어 "
                    "'가장 원가가 높은 자재 1개'를 확정할 수 없습니다."
                ),
            )

        updated = self._copy_runtime(runtime)
        updated["status"] = "TEXT_TO_SQL_COMPLETED"
        updated["results"][Capability.TEXT_TO_SQL.value] = {
            "query": query,
            "answer": self.text_to_sql_nodes._format_result(result),
            "raw": self._serialize_sql_result(result),
            "authority": "READ_ONLY_SQL_EVIDENCE",
            "execution_mode": execution_mode,
        }
        return {
            "composition_runtime": updated,
            "error": None,
        }

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

        sql_evidence = (
            (runtime.get("results") or {})
            .get(Capability.TEXT_TO_SQL.value, {})
        )
        sql_result = self._deserialize_sql_result(sql_evidence.get("raw"))
        scope = self._deserialize_scope(runtime.get("scope"))

        decision = self.handoff.build(
            user_goal=str(runtime.get("original_query") or ""),
            sql_result=sql_result,
            knowledge_payload=knowledge_payload,
            scope=scope,
        )
        if not decision.ready:
            analytics_answer = str(sql_evidence.get("answer") or "").strip()
            prefix = (
                f"### 데이터 분석\n{analytics_answer}\n\n"
                if analytics_answer else ""
            )
            return {
                "messages": [AIMessage(content=f"{prefix}{decision.reason}".strip())],
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
        analytics = handoff.get("analytics_evidence") or {}
        knowledge = handoff.get("knowledge_evidence") or {}

        evidence_lines: list[str] = []
        item_code = str(analytics.get("item_code") or "").strip()
        metric_name = str(analytics.get("metric_name") or "").strip()
        metric_value = analytics.get("metric_value")
        if item_code:
            metric_text = (
                f" · {metric_name}={metric_value}"
                if metric_name and metric_value is not None else ""
            )
            evidence_lines.append(
                f"- 분석 대상 선정 근거: {item_code}{metric_text}"
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
            == self.SUPPORTED_RUNTIME_CAPABILITIES
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
    def _knowledge_query(user_goal: str) -> str:
        # PLAN-03 currently supports only COST-based REPLACE handoff.  Use a
        # dedicated evidence query instead of leaking the action directive into
        # the standalone Knowledge router.
        del user_goal
        return "원가 절감 설계변경 기준과 영향"

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
    "WORKFLOW_COMPOSITION_TEXT_TO_SQL",
    "is_workflow_composition_analysis_tool_result",
    "is_workflow_composition_knowledge_tool_result",
]
