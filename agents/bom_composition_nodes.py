"""Safe runtime composition for read-only multi-capability goals.

PLAN-02 intentionally enables only the composition that can be executed
without business-workflow authority:

    TEXT_TO_SQL + RAG

Workflow-managed compositions remain on the existing Agent/Design Change path.
No Request, approval, or Production E-BOM write is allowed here.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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
    ExecutionPlan,
    SelectivePlanner,
)
from core.performance_profiler import record_performance_event
from rag.query_router import (
    DEFAULT_KNOWLEDGE_QUERY_ROUTER,
    KnowledgeQueryRouter,
)
from text_to_sql.query_router import (
    DEFAULT_TEXT_TO_SQL_QUERY_ROUTER,
    TextToSqlQueryRouter,
)


COMPOSITION_PLAN = "composition_plan"
COMPOSITION_TEXT_TO_SQL = "composition_text_to_sql"
COMPOSITION_KNOWLEDGE_QUERY = "composition_knowledge_query"
COMPOSITION_KNOWLEDGE_FINALIZE = "composition_knowledge_finalize"
COMPOSITION_FINALIZE = "composition_finalize"
COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX = "composition-knowledge-"


class BomReadOnlyCompositionNodes:
    """Execute the bounded PLAN-01 read-only composition contract.

    Runtime scope is deliberately narrower than the planner contract.
    PLAN-02 admits only TEXT_TO_SQL + RAG because both are read-only and already
    have independent safety/grounding paths.

    Any composition containing DESIGN_CHANGE_ANALYSIS or PRODUCT_COST_SCAN stays
    on the existing Agent/Workflow path until a later step explicitly wires
    workflow-aware evidence hand-off.
    """

    SUPPORTED_RUNTIME_CAPABILITIES = frozenset({
        Capability.TEXT_TO_SQL,
        Capability.RAG,
    })
    TERMINAL_WORKFLOW_STEPS = frozenset({
        "APPLIED",
        "REPORT_COMPLETED",
        "BLOCKED",
    })

    def __init__(
        self,
        *,
        text_to_sql_nodes,
        knowledge_nodes,
        capability_resolver: CapabilityRequirementResolver | None = None,
        planner: SelectivePlanner | None = None,
        text_to_sql_router: TextToSqlQueryRouter | None = None,
        knowledge_router: KnowledgeQueryRouter | None = None,
    ) -> None:
        self.text_to_sql_nodes = text_to_sql_nodes
        self.knowledge_nodes = knowledge_nodes
        self.capability_resolver = (
            capability_resolver or DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
        )
        self.planner = planner or DEFAULT_SELECTIVE_PLANNER
        self.text_to_sql_router = (
            text_to_sql_router or DEFAULT_TEXT_TO_SQL_QUERY_ROUTER
        )
        self.knowledge_router = (
            knowledge_router or DEFAULT_KNOWLEDGE_QUERY_ROUTER
        )

    def can_execute(self, state: BomAgentState) -> bool:
        """Return True only for a fresh, read-only, fully supported composition."""
        workflow = state.get("design_change") or {}
        step = str(workflow.get("current_step") or "NOT_STARTED").strip().upper()

        # Do not intercept pending slot completion or an active business workflow.
        if str(workflow.get("pending_quantity_request") or "").strip():
            return False
        if workflow.get("pending_add_target_request"):
            return False
        if workflow.get("pending_add_parent_request"):
            return False
        if step != "NOT_STARTED":
            return False

        query = BomGraphGateway.last_user_query(state)
        requirement = self.capability_resolver.resolve(query)
        if not requirement.composition_required:
            return False
        if requirement.workflow_managed:
            return False
        if frozenset(requirement.capabilities) != self.SUPPORTED_RUNTIME_CAPABILITIES:
            return False

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        return bool(
            plan is not None
            and not plan.write_authority_granted
            and plan.capability_names == ("TEXT_TO_SQL", "RAG")
        )

    def plan(self, state: BomAgentState) -> BomAgentState:
        query = BomGraphGateway.last_user_query(state)
        requirement = self.capability_resolver.resolve(query)
        if not self._supported_requirement(requirement):
            raise ValueError(
                "Read-only Composition Path received an unsupported requirement."
            )

        plan = self.planner.plan_if_needed(query, requirement=requirement)
        if plan is None:
            raise ValueError("Read-only Composition Path requires a plan.")
        if plan.write_authority_granted:
            raise ValueError("Composition plan must not grant write authority.")

        analytics_query = self._analytics_subquery(query)
        knowledge_query = self._knowledge_subquery(query)

        runtime = {
            "status": "PLANNED",
            "original_query": query,
            "plan": plan.as_dict(),
            "queries": {
                Capability.TEXT_TO_SQL.value: analytics_query,
                Capability.RAG.value: knowledge_query,
            },
            "results": {},
            "write_authority_granted": False,
        }
        record_performance_event(
            category="planning",
            name="composition.plan",
            metadata={
                "capability_count": len(plan.steps),
                "workflow_managed": plan.workflow_managed,
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

        synthetic_state: BomAgentState = {
            "messages": [HumanMessage(content=query)],
            "user_query": query,
            "tool_steps": state.get("tool_steps", 0),
            "error": None,
        }
        update = self.text_to_sql_nodes.query(synthetic_state)
        messages = update.get("messages", [])
        if not messages or not isinstance(messages[-1], AIMessage):
            raise RuntimeError("Text-to-SQL composition step returned no AI result.")

        updated = self._copy_runtime(runtime)
        updated["status"] = "TEXT_TO_SQL_COMPLETED"
        updated["results"][Capability.TEXT_TO_SQL.value] = {
            "query": query,
            "answer": str(messages[-1].content or "").strip(),
            "authority": "READ_ONLY_SQL_EVIDENCE",
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
            raise ValueError(
                "Composition RAG subquery is not eligible for Knowledge Path."
            )

        args: dict[str, object] = {
            "query": query,
            "top_k": 8,
        }
        if decision.document_type:
            args["document_type"] = decision.document_type

        call_id = (
            f"{COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX}"
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

    def knowledge_finalize(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], ToolMessage):
            raise ValueError(
                "Composition Knowledge Finalizer requires a ToolMessage."
            )
        tool_message = messages[-1]
        if not is_composition_knowledge_tool_result(state):
            raise ValueError(
                "Composition Knowledge Finalizer received another Tool result."
            )

        query = self._runtime_query(runtime, Capability.RAG)
        synthetic_state: BomAgentState = {
            "messages": [
                HumanMessage(content=query),
                tool_message,
            ],
            "user_query": query,
            "error": None,
        }
        update = self.knowledge_nodes.finalize(synthetic_state)
        answer_messages = update.get("messages", [])
        if not answer_messages or not isinstance(answer_messages[-1], AIMessage):
            raise RuntimeError("Knowledge composition step returned no AI result.")

        updated = self._copy_runtime(runtime)
        updated["status"] = "KNOWLEDGE_COMPLETED"
        updated["results"][Capability.RAG.value] = {
            "query": query,
            "answer": str(answer_messages[-1].content or "").strip(),
            "authority": "RAG_EVIDENCE_ONLY",
        }
        return {
            "composition_runtime": updated,
            "error": None,
        }

    def finalize(self, state: BomAgentState) -> BomAgentState:
        runtime = self._runtime(state)
        results = runtime.get("results") or {}
        analytics = results.get(Capability.TEXT_TO_SQL.value) or {}
        knowledge = results.get(Capability.RAG.value) or {}
        analytics_answer = str(analytics.get("answer") or "").strip()
        knowledge_answer = str(knowledge.get("answer") or "").strip()

        if not analytics_answer or not knowledge_answer:
            raise RuntimeError(
                "Composition finalization requires both SQL and RAG evidence."
            )

        answer = (
            "복합 요청을 데이터 분석과 업무 기준으로 나누어 확인했습니다.\n\n"
            "### 데이터 분석\n"
            f"{analytics_answer}\n\n"
            "### 관련 업무 기준\n"
            f"{knowledge_answer}"
        )
        record_performance_event(
            category="planning",
            name="composition.complete",
            metadata={
                "capability_count": 2,
                "synthesis_mode": "DETERMINISTIC_SECTION_MERGE",
            },
            metrics={
                "analytics_chars": len(analytics_answer),
                "knowledge_chars": len(knowledge_answer),
                "answer_chars": len(answer),
            },
        )
        # Clear ephemeral runtime state before the checkpoint is reused by the
        # next user turn. The final answer/evidence remains in message history.
        return {
            "messages": [AIMessage(content=answer)],
            "composition_runtime": None,
            "error": None,
        }

    def _supported_requirement(
        self,
        requirement: CapabilityRequirementDecision,
    ) -> bool:
        return bool(
            requirement.composition_required
            and not requirement.workflow_managed
            and frozenset(requirement.capabilities)
            == self.SUPPORTED_RUNTIME_CAPABILITIES
        )

    def _analytics_subquery(self, query: str) -> str:
        """Derive a read-only SQL clause without asking another planner LLM."""
        compact = " ".join(str(query or "").strip().split())
        if self.text_to_sql_router.route(compact).eligible:
            return compact

        # Compound goals commonly join the analytics question to the knowledge
        # question with "관련 ... 기준". Split only on explicit conjunctions and
        # require the existing conservative Text-to-SQL router to re-approve
        # every candidate.
        candidates = re.split(
            r"\s+(?:그리고|또한|또|및)\s+|\s+관련(?:한|된)?\s*",
            compact,
            flags=re.IGNORECASE,
        )
        for candidate in candidates:
            candidate = self._clean_clause(candidate)
            if candidate and self.text_to_sql_router.route(candidate).eligible:
                return candidate

        # Fallback: cut before the earliest explicit Knowledge marker. This is
        # still gated by the existing Text-to-SQL router; no unapproved query is
        # ever sent to SQL generation.
        lower = compact.lower()
        positions = [
            lower.find(str(marker).lower())
            for marker in self.knowledge_router.KNOWLEDGE_MARKERS
            if lower.find(str(marker).lower()) > 0
        ]
        if positions:
            prefix = self._clean_clause(compact[:min(positions)])
            prefix = re.sub(
                r"\s*(?:관련|대한|관한)\s*$",
                "",
                prefix,
                flags=re.IGNORECASE,
            ).strip()
            if prefix and self.text_to_sql_router.route(prefix).eligible:
                return prefix

        raise ValueError(
            "복합 요청에서 안전한 Text-to-SQL 하위 질의를 분리하지 못했습니다."
        )

    def _knowledge_subquery(self, query: str) -> str:
        compact = " ".join(str(query or "").strip().split())
        if self.knowledge_router.route(compact).eligible:
            return compact

        candidates = re.split(
            r"\s+(?:그리고|또한|또|및)\s+|\s+관련(?:한|된)?\s*",
            compact,
            flags=re.IGNORECASE,
        )
        for candidate in reversed(candidates):
            candidate = self._clean_clause(candidate)
            if candidate and self.knowledge_router.route(candidate).eligible:
                return candidate

        raise ValueError(
            "복합 요청에서 안전한 Knowledge 하위 질의를 분리하지 못했습니다."
        )

    @staticmethod
    def _clean_clause(value: str) -> str:
        return " ".join(str(value or "").strip(" ,.;:").split())

    @staticmethod
    def _runtime(state: BomAgentState) -> dict[str, Any]:
        runtime = state.get("composition_runtime")
        if not isinstance(runtime, dict):
            raise ValueError("Composition runtime state is missing.")
        return runtime

    @staticmethod
    def _runtime_query(runtime: dict[str, Any], capability: Capability) -> str:
        queries = runtime.get("queries") or {}
        value = str(queries.get(capability.value) or "").strip()
        if not value:
            raise ValueError(
                f"Composition subquery is missing for {capability.value}."
            )
        return value

    @staticmethod
    def _copy_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
        copied = dict(runtime)
        copied["queries"] = dict(runtime.get("queries") or {})
        copied["results"] = dict(runtime.get("results") or {})
        return copied


def is_composition_knowledge_tool_result(state: BomAgentState) -> bool:
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False
    message = messages[-1]
    return bool(
        message.name == "search_knowledge"
        and str(message.tool_call_id or "").startswith(
            COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX
        )
    )


__all__ = [
    "BomReadOnlyCompositionNodes",
    "COMPOSITION_FINALIZE",
    "COMPOSITION_KNOWLEDGE_FINALIZE",
    "COMPOSITION_KNOWLEDGE_QUERY",
    "COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX",
    "COMPOSITION_PLAN",
    "COMPOSITION_TEXT_TO_SQL",
    "is_composition_knowledge_tool_result",
]
