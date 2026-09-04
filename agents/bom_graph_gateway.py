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
from agents.capability_requirement_resolver import (
    DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER,
    Capability,
    CapabilityRequirementResolver,
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
from text_to_sql.query_router import (
    DEFAULT_TEXT_TO_SQL_QUERY_ROUTER,
    TextToSqlQueryRouter,
)
from ontology.context_contract import ContextPurpose, DomainContextSnapshot
from ontology.context_resolver import (
    ContextResolutionInput,
    DEFAULT_DOMAIN_CONTEXT_RESOLVER,
    DomainContextResolverFoundation,
)


FAST_CHAT = "fast_chat"
FAST_BOM_READ = "fast_bom_read"
FAST_WHERE_USED = "fast_where_used"
FAST_CURRENT_BOM_QUANTITY = "fast_current_bom_quantity"
FAST_KNOWLEDGE = "fast_knowledge"
FAST_TEXT_TO_SQL = "fast_text_to_sql"
SCOPE_CONFLICT = "scope_conflict"
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

    # Relative expressions are safe only when Active BOM and active Design
    # Change Workflow refer to the same MODEL/PLANT scope.  They deliberately
    # stay narrow: ordinary read-only questions continue to prefer Active BOM,
    # while explicit MODEL requests remain authoritative current-turn scope.
    RELATIVE_SCOPE_MARKERS = (
        "이 모델",
        "이모델",
        "현재 모델",
        "현재모델",
        "이 BOM",
        "이BOM",
        "현재 BOM",
        "현재BOM",
        "이 자재",
        "이자재",
    )

    def __init__(
        self,
        *,
        router: DomainIntentRouter | None = None,
        knowledge_router: KnowledgeQueryRouter | None = None,
        text_to_sql_router: TextToSqlQueryRouter | None = None,
        context_resolver: DomainContextResolverFoundation | None = None,
        capability_resolver: CapabilityRequirementResolver | None = None,
        design_change_active_steps: Iterable[str] = (),
    ) -> None:
        self.router = router or DEFAULT_DOMAIN_INTENT_ROUTER
        self.knowledge_router = knowledge_router or DEFAULT_KNOWLEDGE_QUERY_ROUTER
        self.text_to_sql_router = (
            text_to_sql_router or DEFAULT_TEXT_TO_SQL_QUERY_ROUTER
        )
        self.context_resolver = (
            context_resolver or DEFAULT_DOMAIN_CONTEXT_RESOLVER
        )
        self.capability_resolver = (
            capability_resolver or DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
        )
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
        explicit_model = self.router.explicit_model_scope_code(user_query)
        if explicit_model:
            # Explicit MODEL/PRODUCT in the current turn declares a fresh scope.
            # Even when it equals the currently viewed BOM model, do not silently
            # inherit the old PLANT. Resolve valid Plant options again.
            return False

        resolved = self.context_resolver.resolve(
            ContextResolutionInput(
                purpose=(
                    ContextPurpose.DESIGN_CHANGE
                    if decision.change
                    else ContextPurpose.READ_ONLY
                ),
                explicit_plant_code=explicit_plant,
                active_bom_context=context,
                allow_active_bom_scope=True,
            )
        )
        return bool(
            resolved.version_code
            and resolved.plant_code
            and str(resolved.version_code.value).upper() == product_id
            and str(resolved.plant_code.value).upper()
            == (explicit_plant or plant_code)
        )

    def route(self, state: BomAgentState) -> str:
        user_query = self.last_user_query(state)
        workflow_state = state.get("design_change") or {}
        current_step = str(
            workflow_state.get("current_step") or "NOT_STARTED"
        ).strip().upper()

        # R3 scope-conflict guard:
        # A user may inspect another BOM while an Analysis remains active. That
        # is a valid read operation, but a later relative Design Change request
        # such as "이 모델에서..." must not silently bind to the old Workflow
        # merely because DESIGN_CHANGE context prefers workflow scope.
        if self.design_change_scope_conflict(state) is not None:
            return SCOPE_CONFLICT

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

        # CTX-05 capability preflight:
        # A request that explicitly requires more than one business capability
        # must never be consumed by the first matching single fast path. Until
        # PLAN-01 owns execution composition, defer it to the existing Agent
        # path instead of returning a partial RAG/Analytics answer.
        capability_requirement = self.capability_resolver.resolve(user_query)
        if capability_requirement.composition_required:
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
            previous_user_query=self.previous_user_query(state),
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

        # Text-to-SQL may only claim a request that the existing deterministic
        # domain router has already left as LLM_FALLBACK.
        if decision.intent == "LLM_FALLBACK":
            analytics = self.text_to_sql_router.route(user_query)
            if analytics.eligible:
                return FAST_TEXT_TO_SQL

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

    def design_change_scope_conflict(
        self,
        state: BomAgentState,
    ) -> dict[str, str] | None:
        """Return incompatible Active-BOM/Workflow scope for relative changes.

        Read-only requests are intentionally excluded: READ_ONLY context is
        allowed to prefer the currently viewed BOM even while another Analysis
        remains active.  The guard applies only when the current turn requires
        Design Change Analysis authority and the user did not explicitly name a
        MODEL/VERSION.
        """
        user_query = self.last_user_query(state)
        workflow_state = state.get("design_change") or {}
        current_step = str(
            workflow_state.get("current_step") or "NOT_STARTED"
        ).strip().upper()

        if (
            current_step not in self.design_change_active_steps
            or current_step in self.TERMINAL_WORKFLOW_STEPS
        ):
            return None

        if self.router.explicit_model_scope_code(user_query):
            # Explicit current-turn MODEL resolves the ambiguity. Existing
            # fresh-analysis policy decides whether that means old or new scope.
            return None

        compact = " ".join(str(user_query or "").strip().split())
        if not any(
            marker.lower() in compact.lower()
            for marker in self.RELATIVE_SCOPE_MARKERS
        ):
            return None

        requirement = self.capability_resolver.resolve(user_query)
        if Capability.DESIGN_CHANGE_ANALYSIS not in requirement.capabilities:
            return None

        active = state.get("active_bom_context") or {}
        active_version = str(
            active.get("version_code")
            or active.get("product_id")
            or ""
        ).strip().upper()
        active_plant = str(
            active.get("plant_code") or ""
        ).strip().upper()
        if not active_version or not active_plant:
            return None

        workflow_scope = self.context_resolver.resolve(
            ContextResolutionInput(
                purpose=ContextPurpose.DESIGN_CHANGE,
                workflow_state=workflow_state,
                allow_workflow_scope=True,
            )
        )
        if not workflow_scope.version_code or not workflow_scope.plant_code:
            return None

        workflow_version = str(
            workflow_scope.version_code.value
        ).strip().upper()
        workflow_plant = str(
            workflow_scope.plant_code.value
        ).strip().upper()

        if (
            active_version == workflow_version
            and active_plant == workflow_plant
        ):
            return None

        return {
            "active_version_code": active_version,
            "active_plant_code": active_plant,
            "workflow_version_code": workflow_version,
            "workflow_plant_code": workflow_plant,
            "workflow_step": current_step,
        }

    @staticmethod
    def scope_conflict_message(conflict: dict[str, str]) -> str:
        active_version = str(
            conflict.get("active_version_code") or ""
        ).strip()
        active_plant = str(
            conflict.get("active_plant_code") or ""
        ).strip()
        workflow_version = str(
            conflict.get("workflow_version_code") or ""
        ).strip()
        workflow_plant = str(
            conflict.get("workflow_plant_code") or ""
        ).strip()

        return (
            f"현재 조회 중인 BOM은 {active_version} / {active_plant}이고, "
            f"진행 중인 설계변경 분석 대상은 "
            f"{workflow_version} / {workflow_plant}입니다. "
            "'이 모델', '이 BOM', '이 자재' 같은 상대 표현만으로는 "
            "어느 범위를 의미하는지 안전하게 결정할 수 없습니다. "
            f"기존 분석을 이어가려면 {workflow_version} 모델을, "
            f"현재 조회 BOM을 새 대상으로 분석하려면 "
            f"{active_version} {active_plant}를 요청에 명시해 주세요."
        )

    @staticmethod
    def resolve_read_context(state: BomAgentState) -> DomainContextSnapshot:
        """Resolve read-only MODEL/PLANT scope with ontology provenance."""
        return DEFAULT_DOMAIN_CONTEXT_RESOLVER.resolve(
            ContextResolutionInput(
                purpose=ContextPurpose.READ_ONLY,
                active_bom_context=state.get("active_bom_context"),
                workflow_state=state.get("design_change") or {},
                allow_active_bom_scope=True,
                allow_workflow_scope=True,
            )
        )

    @staticmethod
    def read_scope_context(state: BomAgentState) -> dict[str, str]:
        """Keep the existing dictionary contract over unified context resolution."""
        resolved = BomGraphGateway.resolve_read_context(state)
        if not resolved.version_code or not resolved.plant_code:
            return {}
        return {
            "product_id": str(resolved.version_code.value).strip().upper(),
            "plant_code": str(resolved.plant_code.value).strip().upper(),
        }

    @staticmethod
    def previous_user_query(state: BomAgentState) -> str | None:
        seen_latest = False
        for message in reversed(state.get("messages", [])):
            if not isinstance(message, HumanMessage):
                continue
            if not seen_latest:
                seen_latest = True
                continue
            value = str(message.content or "").strip()
            return value or None
        return None

    @staticmethod
    def last_user_query(state: BomAgentState) -> str:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content or "").strip()
        return str(state.get("user_query") or "").strip()
