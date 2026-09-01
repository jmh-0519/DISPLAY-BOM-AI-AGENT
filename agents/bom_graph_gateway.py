"""LangGraph entry gateway for Display BOM hybrid routing.

The gateway decides whether the current turn can safely bypass BomAgentNode.
Only high-confidence, read-only/simple requests are admitted to Fast Path.
Workflow-sensitive, write, follow-up, or ambiguous requests stay on Agent Path.
"""

from __future__ import annotations

from typing import Iterable

from langchain_core.messages import HumanMessage

from agents.analysis_macro_dispatch import (
    MACRO_ANALYZE,
    DeterministicAnalysisMacroDispatch,
)
from agents.bom_agent_state import BomAgentState
from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)
from rag.query_router import (
    DEFAULT_KNOWLEDGE_QUERY_ROUTER,
    KnowledgeQueryRouter,
)


FAST_CHAT = "fast_chat"
FAST_BOM_READ = "fast_bom_read"
FAST_WHERE_USED = "fast_where_used"
FAST_CURRENT_BOM_QUANTITY = "fast_current_bom_quantity"
FAST_KNOWLEDGE = "fast_knowledge"
AGENT_PATH = "agent"


class BomGraphGateway:
    """Workflow-aware LangGraph entry router.

    Routing priority:
    1. pending slot / active non-terminal Design Change workflow -> Agent
    2. Analysis follow-up -> Agent
    3. write/recommendation/product-cost-scan -> Agent
    4. high-confidence CHAT/BOM_READ/WHERE_USED with complete slots -> Fast Path
    5. incomplete/ambiguous request -> Agent
    """

    TERMINAL_WORKFLOW_STEPS = frozenset({
        "APPLIED",
        "REPORT_COMPLETED",
        "BLOCKED",
    })

    def __init__(
        self,
        *,
        router: DomainIntentRouter | None = None,
        knowledge_router: KnowledgeQueryRouter | None = None,
        design_change_active_steps: Iterable[str] = (),
    ) -> None:
        self.router = router or DEFAULT_DOMAIN_INTENT_ROUTER
        self.knowledge_router = knowledge_router or DEFAULT_KNOWLEDGE_QUERY_ROUTER
        self.design_change_active_steps = frozenset(design_change_active_steps)
        self.analysis_macro_dispatch = DeterministicAnalysisMacroDispatch(
            self.router
        )

    def can_inherit_active_bom_context(
        self,
        user_query: str,
        active_bom_context: dict | None,
    ) -> bool:
        """Whether a fresh change request may inherit the currently viewed BOM.

        This is intentionally a Gateway policy so Streamlit and LangGraph use
        the same decision rule.

        Allowed:
            active BOM = LTA400HR01-001 / P01
            "LJ94-100006 수량 바꾸고싶어"

        Not inherited:
            - read-only request
            - no active BOM context
            - user explicitly selects a different PLANT
            - user explicitly selects a different MODEL/PRODUCT
        """
        context = active_bom_context or {}
        product_id = str(context.get("product_id") or "").strip().upper()
        plant_code = str(context.get("plant_code") or "").strip().upper()
        if not product_id or not plant_code:
            return False

        decision = self.router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )
        if (
            not decision.change
            and decision.intent != "CURRENT_BOM_QUANTITY"
        ):
            return False

        explicit_plant = self.router.extract_plant_code(user_query)
        if explicit_plant and explicit_plant != plant_code:
            return False

        explicit_model = self.router.explicit_model_scope_code(user_query)
        if explicit_model:
            # Explicit MODEL/PRODUCT in the current turn declares a fresh scope.
            # Even when it equals the currently viewed BOM model, do not silently
            # inherit the old PLANT. Resolve valid Plant options again.
            #
            # Active-BOM inheritance remains available for genuine implicit
            # follow-ups such as:
            #   "SEALANT를 변경하고싶어"
            #   "LJ94-100006 수량 바꾸고싶어"
            return False

        return True

    def route(self, state: BomAgentState) -> str:
        user_query = self.last_user_query(state)
        workflow_state = state.get("design_change") or {}
        current_step = str(
            workflow_state.get("current_step") or "NOT_STARTED"
        ).strip().upper()

        # A pending slot is part of an existing business transaction. A numeric
        # follow-up such as "3" must never be mistaken for a new simple request.
        if str(workflow_state.get("pending_quantity_request") or "").strip():
            return AGENT_PATH
        if workflow_state.get("pending_add_target_request"):
            # The previous turn intentionally asked which material/ASSY should be
            # added.  The short slot-completion reply (for example "FILM") must
            # return to the Agent node so it can reconstruct the original ADD
            # request before any normal intent routing is applied.
            return AGENT_PATH
        if workflow_state.get("pending_add_parent_request"):
            # ASSY ADD requires an explicit Parent.  The next short Parent-code
            # reply belongs to the pending ADD transaction, not a fresh query.
            return AGENT_PATH

        # A fresh, high-confidence policy/guide/spec question is read-only and
        # should beat Design Change macro parsing. Action directives are rejected
        # by KnowledgeQueryRouter and therefore remain in the workflow path.
        if current_step == "NOT_STARTED":
            knowledge = self.knowledge_router.route(user_query)
            if knowledge.eligible:
                return FAST_KNOWLEDGE

        # High-confidence fresh design-change analysis can bypass the first LLM
        # entirely. This creates only an Analysis Session Tool Call; Request/HITL/
        # Apply authority remains in the existing Design Change workflow.
        if self.analysis_macro_dispatch.build_spec(
            user_query=user_query,
            active_bom_context=state.get("active_bom_context"),
            workflow_state=workflow_state,
        ) is not None:
            return MACRO_ANALYZE

        # A read-only fact question about the currently viewed BOM is safe to
        # answer without entering the LLM, even while a Design Change analysis remains
        # active. It must not mutate the design-change workflow.
        current_turn_decision = self.router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )
        if current_turn_decision.intent == "CURRENT_BOM_QUANTITY":
            read_scope = self.read_scope_context(state)
            if read_scope.get("product_id") and read_scope.get("plant_code"):
                return FAST_CURRENT_BOM_QUANTITY

        # During a live Design Change workflow, the Agent owns context, HITL and state
        # transitions. Terminal historical states may accept a new simple read.
        if (
            current_step in self.design_change_active_steps
            and current_step not in self.TERMINAL_WORKFLOW_STEPS
        ):
            return AGENT_PATH

        # Terminal states can still receive evidence/explanation follow-ups.
        follow_up_intent = self.router.classify_analysis_follow_up(
            user_query,
            workflow_state,
            active_steps=self.design_change_active_steps,
        )
        if follow_up_intent:
            return AGENT_PATH

        # Terminal historical workflows may start a fresh read-only knowledge
        # question after the workflow-specific follow-up guard has declined it.
        knowledge = self.knowledge_router.route(user_query)
        if knowledge.eligible:
            return FAST_KNOWLEDGE

        # Gateway Fast Path is intentionally current-turn only. Do not inherit a
        # product/item from a completed historical workflow when routing a fresh
        # read request.
        decision = self.router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )

        if decision.intent in {
            "PRODUCT_COST_SCAN",
            "DESIGN_CHANGE",
            "DESIGN_CHANGE_RECOMMENDATION",
        }:
            return AGENT_PATH

        if decision.intent == "CHAT" and decision.chat_response:
            return FAST_CHAT

        if (
            decision.intent == "BOM_READ"
            and decision.plant_code
            and decision.reference_code
        ):
            return FAST_BOM_READ

        if (
            decision.intent == "WHERE_USED"
            and decision.plant_code
            and decision.where_used_item_code
        ):
            return FAST_WHERE_USED

        # Missing PLANT/entity, ambiguous language, and unsupported simple
        # patterns intentionally fall back to the normal LLM Agent path.
        return AGENT_PATH

    @staticmethod
    def read_scope_context(state: BomAgentState) -> dict[str, str]:
        """Return read-only MODEL/PLANT scope from active BOM or Analysis.

        A read-only follow-up during an Analysis Session may safely reuse the
        Analysis request scope without mutating the design-change workflow.
        Explicit current-turn MODEL/PLANT handling remains in the normal router.
        """
        active = state.get("active_bom_context") or {}
        product_id = str(active.get("product_id") or "").strip().upper()
        plant_code = str(active.get("plant_code") or "").strip().upper()
        if product_id and plant_code:
            return {"product_id": product_id, "plant_code": plant_code}

        workflow = state.get("design_change") or {}
        request = workflow.get("analysis_request") or workflow.get("analysis_context") or {}
        product_id = str(
            request.get("version_code")
            or request.get("product_id")
            or ""
        ).strip().upper()
        plant_code = str(
            workflow.get("plant_code")
            or request.get("plant_code")
            or ""
        ).strip().upper()
        if product_id and plant_code:
            return {"product_id": product_id, "plant_code": plant_code}
        return {}

    @staticmethod
    def last_user_query(state: BomAgentState) -> str:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content or "").strip()
        return str(state.get("user_query") or "").strip()
