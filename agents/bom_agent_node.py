import json
import re
import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch
from agents.bom_agent_state import BomAgentState
from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)
from agents.llm_context_compactor import LlmContextCompactor
from core.azure_openai_client import AzureOpenAIClient
from mcp_client.client import DisplayBomMcpClient
from core.performance_profiler import record_performance_event


class BomAgentNode:
    """
    LangGraph에서 Azure OpenAI의
    다음 행동을 한 번 판단하는 Agent Node입니다.

    Tool을 직접 실행하지 않습니다.
    """

    PHASE3_TOOLS = {
        # Analysis Session (Request 미생성)
        "analyze_design_change_candidates",
        "scan_product_cost_reduction_candidates",
        "revalidate_design_change_analysis",
        "preview_design_change_analysis_impact",
        "create_design_change_request_from_analysis",
        "explain_design_change_analysis_session",
        "explain_design_change_analysis_candidate",
        "compare_design_change_analysis_candidates",
        # 기존 Request-first Phase3 Tool은 호환성/이력 조회를 위해 보존
        "create_design_change_request",
        "evaluate_replacement_candidates",
        "submit_candidate_additional_data",
        "select_candidate_and_supplier",
        "confirm_candidate_selection",
        "approve_candidate_impact",
        "record_exception_approval",
        "create_multi_action_preview",
        "record_final_apply_approval",
        "apply_approved_change_request",
        "get_change_request_result",
        "get_design_change_analysis",
        "get_candidate_evaluation_detail",
        "compare_design_change_candidates",
    }

    UI_ONLY_PHASE3_TOOLS = {
        "preview_design_change_analysis_impact",
        "create_design_change_request_from_analysis",
        "select_candidate_and_supplier",
        "confirm_candidate_selection",
        "approve_candidate_impact",
        "record_exception_approval",
        "create_multi_action_preview",
        "record_final_apply_approval",
        "apply_approved_change_request",
    }

    PHASE3_EXPLAIN_TOOLS = {
        "explain_design_change_analysis_session",
        "explain_design_change_analysis_candidate",
        "compare_design_change_analysis_candidates",
        "get_design_change_analysis",
        "get_candidate_evaluation_detail",
        "compare_design_change_candidates",
    }

    # Domain language rules are owned by DomainIntentRouter.
    # Aliases are kept for backward compatibility with existing tests/helpers.
    FOLLOW_UP_EXPLAIN_MARKERS = DomainIntentRouter.FOLLOW_UP_EXPLAIN_MARKERS
    FOLLOW_UP_COMPARE_MARKERS = DomainIntentRouter.FOLLOW_UP_COMPARE_MARKERS
    ANALYSIS_RESTART_MARKERS = DomainIntentRouter.ANALYSIS_RESTART_MARKERS

    LEGACY_DESIGN_CHANGE_TOOLS = {
        "analyze_design_change",
        "create_design_change_preview",
        "record_design_change_decision",
        "apply_approved_design_change",
        "create_ai_change_request",
        "create_review_bom",
        "run_ai_bom_review",
        "generate_design_change_report",
        "apply_reviewed_bom",
    }

    PHASE3_RECOMMENDATION_MARKERS = DomainIntentRouter.PHASE3_RECOMMENDATION_MARKERS
    PRODUCT_COST_SCAN_SCOPE_MARKERS = DomainIntentRouter.PRODUCT_COST_SCAN_SCOPE_MARKERS
    PRODUCT_COST_SCAN_COST_MARKERS = DomainIntentRouter.PRODUCT_COST_SCAN_COST_MARKERS
    PRODUCT_COST_SCAN_ACTION_MARKERS = DomainIntentRouter.PRODUCT_COST_SCAN_ACTION_MARKERS
    ASSY_PROCESS_NAMES = DomainIntentRouter.ASSY_PROCESS_NAMES
    PHASE3_CHANGE_INTENT_MARKERS = DomainIntentRouter.PHASE3_CHANGE_INTENT_MARKERS
    PHASE3_EXPLICIT_ACTION_MARKERS = DomainIntentRouter.PHASE3_EXPLICIT_ACTION_MARKERS
    PHASE3_REASON_LANGUAGE_MARKERS = DomainIntentRouter.PHASE3_REASON_LANGUAGE_MARKERS
    ITEM_CODE_PATTERN = DomainIntentRouter.ITEM_CODE_PATTERN
    PLANT_CODE_PATTERN = DomainIntentRouter.PLANT_CODE_PATTERN
    PLANT_REQUIRED_QUERY_MARKERS = DomainIntentRouter.PLANT_REQUIRED_QUERY_MARKERS
    WHERE_USED_MARKERS = DomainIntentRouter.WHERE_USED_MARKERS
    PLAIN_BOM_QUERY_MARKERS = DomainIntentRouter.PLAIN_BOM_QUERY_MARKERS
    SIMPLE_CHAT_EXACT = DomainIntentRouter.SIMPLE_CHAT_EXACT

    PHASE3_ACTIVE_STEPS = {
        "ANALYSIS_READY",
        "ANALYSIS_REVALIDATED",
        "ANALYSIS_IMPACT_REVIEW",
        "ANALYSIS_CONFIRMED",
        "REQUESTED",
        "CANDIDATES_EVALUATED",
        "WAITING_CANDIDATE_APPROVAL",
        "CONDITIONAL_REVIEW_REQUIRED",
        "IMPACT_REVIEW_REQUIRED",
        "CANDIDATE_APPROVED",
        "WAITING_FINAL_APPROVAL",
        "FINAL_APPROVED",
        "APPLIED",
        "BLOCKED",
    }

    # Analysis Session exists, but no Design Change Request has been created yet.
    # A clearly scoped new change request may replace this temporary Analysis
    # context without touching persisted Request/Production BOM state.
    PHASE3_PRE_REQUEST_ANALYSIS_STEPS = {
        "ANALYSIS_READY",
        "ANALYSIS_REVALIDATED",
        "ANALYSIS_IMPACT_REVIEW",
        "ANALYSIS_CONFIRMED",
    }

    PHASE3_ALLOWED_TOOLS = {
        "NOT_STARTED": {"analyze_design_change_candidates"},
        "ANALYSIS_READY": {
            "analyze_design_change_candidates",
            "revalidate_design_change_analysis",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        },
        "ANALYSIS_REVALIDATED": {
            "analyze_design_change_candidates",
            "revalidate_design_change_analysis",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        },
        "ANALYSIS_IMPACT_REVIEW": {
            "analyze_design_change_candidates",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        },
        "ANALYSIS_CONFIRMED": {
            "analyze_design_change_candidates",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        },
        "REQUESTED": {
            "evaluate_replacement_candidates",
            "get_change_request_result",
        },
        "CANDIDATES_EVALUATED": {
            "evaluate_replacement_candidates",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "WAITING_CANDIDATE_APPROVAL": {
            "evaluate_replacement_candidates",
            "submit_candidate_additional_data",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "CONDITIONAL_REVIEW_REQUIRED": {
            "submit_candidate_additional_data",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "IMPACT_REVIEW_REQUIRED": {
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "CANDIDATE_APPROVED": {
            "record_exception_approval",
            "create_multi_action_preview",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "WAITING_FINAL_APPROVAL": {
            "record_final_apply_approval",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "FINAL_APPROVED": {
            "apply_approved_change_request",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "APPLIED": {
            "analyze_design_change_candidates",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
        "BLOCKED": {
            "analyze_design_change_candidates",
            "get_change_request_result",
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
        },
    }

    def __init__(
        self,
        client: AzureOpenAIClient,
        mcp_client: DisplayBomMcpClient,
        skill_context: str,
    ) -> None:
        self.client = client
        self.mcp_client = mcp_client
        self.skill_context = skill_context
        self.domain_intent_router = DEFAULT_DOMAIN_INTENT_ROUTER
        self.analysis_macro_dispatch = DeterministicAnalysisMacroDispatch(
            self.domain_intent_router
        )
        self.llm_context_compactor = LlmContextCompactor()

    def __call__(
        self,
        state: BomAgentState,
    ) -> BomAgentState:
        messages = state.get(
            "messages",
            [],
        )

        if not messages:
            raise ValueError(
                "Agent Node 실행에는 "
                "하나 이상의 메시지가 필요합니다."
            )

        workflow_state = state.get("design_change") or {}
        current_step = workflow_state.get("current_step", "NOT_STARTED")
        user_query = self._current_user_query(
            messages,
            state.get("user_query"),
        )

        user_query = self._inherit_active_bom_context_for_change(
            user_query=user_query,
            workflow_state=workflow_state,
            active_bom_context=state.get("active_bom_context"),
        )

        pending_add_parent_request = workflow_state.get("pending_add_parent_request") or None
        pending_add_parent_consumed = False
        if pending_add_parent_request:
            pending = dict(pending_add_parent_request)
            version_code = str(pending.get("version_code") or "").strip().upper()
            plant_code = str(pending.get("plant_code") or "").strip().upper()
            target_name = str(pending.get("target_name") or "").strip()
            parent_codes = list(dict.fromkeys(
                self.domain_intent_router.item_codes(user_query)
            ))
            if len(parent_codes) != 1:
                return {
                    "messages": [AIMessage(content="추가할 ASSY의 Parent ASSY 코드를 입력해 주세요.")],
                    "design_change": dict(workflow_state),
                    "error": None,
                }
            parent_code = parent_codes[0]
            user_query = (
                f"{version_code} {plant_code} 모델에서 "
                f"{parent_code} 하위에 {target_name} ASSY를 추가해줘"
            ).strip()
            workflow_state = dict(workflow_state)
            workflow_state["pending_add_parent_request"] = None
            pending_add_parent_consumed = True

        pending_add_target_request = workflow_state.get("pending_add_target_request") or None
        pending_add_target_consumed = False
        if pending_add_target_request:
            pending = dict(pending_add_target_request)
            target_type = str(pending.get("target_type") or "MATERIAL").upper()
            version_code = str(pending.get("version_code") or "").strip().upper()
            plant_code = str(pending.get("plant_code") or "").strip().upper()
            reply = " ".join(str(user_query or "").strip().split())
            reply = re.sub(
                r"\s*(?:자재|MATERIAL|ASSY|어셈블리|어셈블리)\s*$",
                "",
                reply,
                flags=re.IGNORECASE,
            ).strip().strip('\"\'`“”‘’')
            if not reply:
                role = "자재" if target_type == "MATERIAL" else "ASSY"
                return {
                    "messages": [AIMessage(content=f"추가하려는 {role}의 자재코드, 자재명 또는 품목군을 입력해 주세요.")],
                    "design_change": dict(workflow_state),
                    "error": None,
                }
            role = "자재" if target_type == "MATERIAL" else "ASSY"
            scope = " ".join(value for value in (version_code, plant_code) if value)
            user_query = f"{scope} 모델에 {reply} {role}를 추가해줘".strip()
            workflow_state = dict(workflow_state)
            workflow_state["pending_add_target_request"] = None
            pending_add_target_consumed = True

        pending_quantity_request = str(
            workflow_state.get("pending_quantity_request") or ""
        ).strip()
        pending_quantity_consumed = False

        if pending_quantity_request:
            quantity_value = self.domain_intent_router.extract_quantity_only_input(user_query)
            if quantity_value is None:
                return {
                    "messages": [AIMessage(
                        content="변경할 수량을 입력해 주세요."
                    )],
                    "design_change": dict(workflow_state),
                    "error": None,
                }

            user_query = (
                f"{pending_quantity_request} "
                f"수량을 {self._format_quantity(quantity_value)}로 변경해줘"
            )
            workflow_state = dict(workflow_state)
            workflow_state["pending_quantity_request"] = None
            pending_quantity_consumed = True

        elif (
            self.domain_intent_router.is_quantity_change_instruction(user_query)
            and self.domain_intent_router.extract_new_quantity(user_query) is None
        ):
            updated_workflow_state = dict(workflow_state)
            updated_workflow_state["pending_quantity_request"] = user_query
            return {
                "messages": [AIMessage(
                    content="변경할 수량을 입력해 주세요."
                )],
                "design_change": updated_workflow_state,
                "error": None,
            }

        # ADD Target Resolution Gate:
        # A request that only says "자재/ASSY를 추가하고 싶어" does not identify
        # a meaningful business target.  Do not create Analysis or rank unrelated
        # master items.  Ask for the item code/name/family first and keep a narrow
        # pending slot so the next short reply can resume the original scope.
        normalized_add = self.domain_intent_router.normalize(user_query)
        is_add_instruction = any(marker in normalized_add for marker in ("추가", "넣어", " add "))
        if is_add_instruction:
            add_target_type = self.domain_intent_router.extract_add_target_type(user_query)
            add_target_name = self.domain_intent_router.extract_add_target_name(user_query)
            explicit_version = self.domain_intent_router.explicit_model_scope_code(user_query)
            non_version_codes = [
                code for code in self.domain_intent_router.item_codes(user_query)
                if code != explicit_version
            ]
            explicit_new_code = (
                non_version_codes[0]
                if add_target_type == "MATERIAL" and len(non_version_codes) == 1
                else None
            )
            if add_target_type and not add_target_name and not explicit_new_code:
                updated_workflow_state = dict(workflow_state)
                updated_workflow_state["pending_add_target_request"] = {
                    "original_request": user_query,
                    "target_type": add_target_type,
                    "version_code": explicit_version,
                    "plant_code": self.domain_intent_router.extract_plant_code(user_query),
                }
                role = "자재" if add_target_type == "MATERIAL" else "ASSY"
                return {
                    "messages": [AIMessage(
                        content=(
                            f"추가하려는 {role}를 특정해 주세요. "
                            "자재코드, 자재명 또는 품목군으로 입력할 수 있습니다. "
                            "예: FILM, SEALANT, 0001-200007"
                        )
                    )],
                    "design_change": updated_workflow_state,
                    "error": None,
                }

            if add_target_type == "ASSY" and add_target_name:
                parent_code = self.domain_intent_router.extract_add_parent_code(
                    user_query,
                    version_code=explicit_version,
                )
                if not parent_code:
                    updated_workflow_state = dict(workflow_state)
                    updated_workflow_state["pending_add_parent_request"] = {
                        "original_request": user_query,
                        "version_code": explicit_version,
                        "plant_code": self.domain_intent_router.extract_plant_code(user_query),
                        "target_name": add_target_name,
                    }
                    return {
                        "messages": [AIMessage(
                            content="추가할 ASSY의 Parent ASSY 코드를 입력해 주세요."
                        )],
                        "design_change": updated_workflow_state,
                        "error": None,
                    }

        # Azure message conversion is intentionally deferred until an actual
        # LLM call is required. Deterministic Tool routing must not pay the
        # cost of serializing/compacting the entire message history.
        fast_chat = self.domain_intent_router.fast_chat_response(user_query)
        if fast_chat is not None:
            return {"messages": [AIMessage(content=fast_chat)], "error": None}

        # A completed/blocked request is historical context, not the routing context
        # for a brand-new change instruction.  Without this separation a new DELETE
        # after REPORT_COMPLETED can inherit the previous request/PLANT and never
        # expose the Analysis tool.  Keep the persisted state intact for history, but
        # route the new instruction exactly like a fresh Analysis Session.
        initial_routing = self.domain_intent_router.route(
            user_query,
            workflow_active=current_step in self.PHASE3_ACTIVE_STEPS,
            workflow_state=workflow_state,
        )
        fresh_change_intent = (
            initial_routing.product_cost_scan
            or initial_routing.recommendation
            or initial_routing.change
        )
        start_fresh_after_terminal = (
            current_step in {"APPLIED", "REPORT_COMPLETED", "BLOCKED"}
            and fresh_change_intent
        )

        # A pre-Request Analysis is temporary working context. If the user starts
        # another explicitly scoped change request, do not reuse the old
        # Analysis MODEL/PLANT merely because it is still present in LangGraph
        # state. This is especially important for:
        #
        #   old Analysis: LTA400HR01-001 / P01
        #   new request : "LTA400HR01-001 모델에서 SEALANT를 변경하고싶어"
        #
        # The MODEL is explicitly restated while PLANT is omitted, so the new
        # request must resolve valid Plants again instead of inheriting P01.
        #
        # Genuine Analysis follow-ups ("왜 1번 후보가 FAIL이야?") remain on the
        # existing Analysis Session.
        current_analysis_follow_up = (
            self.domain_intent_router.classify_analysis_follow_up(
                user_query,
                workflow_state,
                active_steps=self.PHASE3_ACTIVE_STEPS,
            )
            if current_step in self.PHASE3_PRE_REQUEST_ANALYSIS_STEPS
            else None
        )
        explicit_current_model = (
            self.domain_intent_router.explicit_model_scope_code(user_query)
        )
        start_fresh_analysis_scope = (
            current_step in self.PHASE3_PRE_REQUEST_ANALYSIS_STEPS
            and fresh_change_intent
            and current_analysis_follow_up is None
            and bool(explicit_current_model)
        )

        start_fresh_scope = (
            start_fresh_after_terminal
            or start_fresh_analysis_scope
        )
        routing_step = "NOT_STARTED" if start_fresh_scope else current_step
        routing_workflow_state = {} if start_fresh_scope else workflow_state

        # SPEED1B contract:
        # - history must not silently redefine a normal current-turn intent;
        # - history may supply missing entity/slot context.
        #
        # A PLANT-only reply is an explicit slot-completion turn, not a new
        # arbitrary intent, so the immediately preceding Phase3 request may be
        # restored only for this narrow case.
        previous_user_query = self._previous_user_query(messages, user_query)
        plant_slot_continuation = (
            routing_step == "NOT_STARTED"
            and self.domain_intent_router.is_plant_only_selection(user_query)
            and bool(previous_user_query)
            and self.domain_intent_router.route(
                previous_user_query,
                workflow_active=False,
                workflow_state={},
            ).phase3_mode
        )

        current_routing_query = (
            f"{previous_user_query} {user_query}".strip()
            if plant_slot_continuation
            else user_query
        )

        # Current-turn intent remains authoritative except for the explicit
        # PLANT-slot continuation above.
        routing_decision = self.domain_intent_router.route(
            current_routing_query,
            workflow_active=routing_step in self.PHASE3_ACTIVE_STEPS,
            workflow_state=routing_workflow_state,
        )

        current_has_entity_scope = bool(
            self.domain_intent_router.item_codes(user_query)
            or self.domain_intent_router.extract_plant_code(user_query)
            or self.domain_intent_router.extract_named_change_target(user_query)
        )
        short_entity_followup = (
            routing_step == "NOT_STARTED"
            and routing_decision.phase3_mode
            and not current_has_entity_scope
            and bool(previous_user_query)
        )

        if start_fresh_scope:
            design_change_context = str(user_query)
        elif plant_slot_continuation or short_entity_followup:
            design_change_context = self._recent_user_context(messages, user_query)
        elif routing_step == "NOT_STARTED" and fresh_change_intent:
            # A complete new request must not inherit stale scope.
            design_change_context = str(user_query)
        else:
            design_change_context = self._recent_user_context(messages, user_query)

        current_turn_tools = self._current_turn_tool_names(messages)
        product_cost_scan_intent = routing_decision.product_cost_scan
        current_recommendation_intent = routing_decision.recommendation
        current_change_intent = routing_decision.change
        explicit_pair_analysis = (
            self.domain_intent_router.is_explicit_replacement_pair_analysis(
                user_query
            )
        )
        phase3_mode = (
            False if explicit_pair_analysis else routing_decision.phase3_mode
        )
        plant_required = (
            False if explicit_pair_analysis else routing_decision.requires_plant
        )
        active_plant_code = str(routing_workflow_state.get("plant_code") or "").strip().upper()
        plant_code_in_context = self.domain_intent_router.extract_plant_code(design_change_context)
        plant_context_ready = bool(active_plant_code or plant_code_in_context)
        plant_reference_code = self.domain_intent_router.reference_code_for_plant_lookup(
            design_change_context, routing_workflow_state
        )
        product_cost_scan_observed = "scan_product_cost_reduction_candidates" in current_turn_tools
        follow_up_complete = bool(current_turn_tools & self.PHASE3_EXPLAIN_TOOLS)
        follow_up_intent = (
            None if (follow_up_complete or product_cost_scan_intent)
            else self.domain_intent_router.classify_analysis_follow_up(
                user_query,
                routing_workflow_state,
                active_steps=self.PHASE3_ACTIVE_STEPS,
            )
        )
        bom_context_ready = "get_bom" in current_turn_tools

        # Router already applies write/recommendation precedence over WHERE_USED.
        where_used_intent = routing_decision.where_used
        where_used_observed = "get_bom_where_used" in current_turn_tools
        plant_options_observed = "list_plants" in current_turn_tools

        # Structured Streamlit panels already render these read-only Tool results.
        # Avoid a second Azure call whose prose would be suppressed by the UI.
        if where_used_observed:
            return {
                "messages": [AIMessage(content="역방향 BOM 조회 결과를 확인해 주세요.")],
                "error": None,
            }
        if plant_options_observed:
            return {
                "messages": [AIMessage(content="조회할 PLANT를 선택해 주세요.")],
                "error": None,
            }
        if "get_bom" in current_turn_tools and not phase3_mode:
            return {
                "messages": [AIMessage(content="BOM 조회 결과를 확인해 주세요.")],
                "error": None,
            }

        tool_definitions = self._filter_tool_definitions(
            self.mcp_client.get_tool_definitions(),
            routing_step,
            phase3_mode=phase3_mode,
            bom_context_ready=bom_context_ready,
            follow_up_intent=follow_up_intent,
            follow_up_complete=follow_up_complete,
            product_cost_scan_intent=product_cost_scan_intent,
        )
        if plant_context_ready:
            # PLANT가 사용자 요청 또는 활성 Analysis/Workflow에서 이미 확정된 경우
            # list_plants는 더 이상 선택지로 노출하지 않는다.
            # 같은 턴에 업무 Tool과 list_plants가 함께 노출되면 LLM이 이미 확정된
            # PLANT를 다시 묻거나 불필요한 PLANT 조회를 선택할 수 있다.
            tool_definitions = [
                definition
                for definition in tool_definitions
                if str(definition.get("function", {}).get("name") or "") != "list_plants"
            ]
        elif plant_required and not plant_reference_code:
            # 대상 코드가 아직 식별되지 않은 상태에서 모든 활성 PLANT를 보여주면
            # 실제 대상과 무관한 선택지가 섞일 수 있다. 먼저 모델/ASSY/자재를
            # 식별하도록 하고, reference_code가 생긴 뒤에만 list_plants를 호출한다.
            tool_definitions = [
                definition
                for definition in tool_definitions
                if str(definition.get("function", {}).get("name") or "") != "list_plants"
            ]
        if product_cost_scan_observed:
            # Opportunity Scan Observation을 받은 같은 턴에는 추가 Tool을 반복 호출하지
            # 않고 실제 scan evidence로 최종 답변만 작성한다.
            tool_definitions = []
        if where_used_observed:
            # 역방향 BOM Observation을 받은 뒤에는 추가 Tool을 반복 호출하지 않고
            # 실제 where-used evidence로 답변만 작성한다.
            tool_definitions = []
        if plant_required and not plant_context_ready and plant_options_observed:
            # list_plants Observation을 받은 같은 턴에서는 다른 업무 Tool을 호출하지 않고
            # LLM이 사용자에게 PLANT 선택지만 설명하도록 한다.
            tool_definitions = []
        allowed_phase3_tools = sorted({
            str(tool.get("function", {}).get("name") or "")
            for tool in tool_definitions
            if str(tool.get("function", {}).get("name") or "")
            in self.PHASE3_TOOLS
        })
        active_request_id = routing_workflow_state.get("request_id")
        active_action_ids = [
            str(value.get("action_id"))
            for value in routing_workflow_state.get("actions", [])
            if value.get("action_id")
        ]
        mentioned_candidate_codes = self.domain_intent_router.mentioned_candidate_codes(
            user_query, routing_workflow_state
        )
        analysis_memory = routing_workflow_state.get("analysis_memory") or {}

        phase3_instruction = (
            "현재 요청은 Phase3 설계변경 후보 추천 Workflow입니다. "
            "analyze_design_change는 호출하지 마세요. "
            "제품과 변경 대상 기존 품목이 현재 또는 직전 대화에 명확하면 "
            "analyze_design_change_candidates를 호출해 Request 생성 없이 Analysis Session을 시작하세요. "
            "REPLACE 후보 추천에서는 신규 자재 ID를 사용자에게 요구하지 마세요. "
            "new_item_code를 비운 채 요청을 등록하고 Service가 후보를 동적으로 탐색합니다. "
            "ADD도 사용자가 신규 자재 코드를 모르면 new_item_code를 요구하지 말고, "
            "요청에서 명확한 target_type(MATERIAL/ASSY)과 추가하려는 품목명/품목군이 있으면 target_item_name에 반드시 보존하세요. "
            "예: '차폐 테이프를 추가' 요청은 target_item_name에 그 의미를 보존하여 Service가 관련 Rule과 동일 품목군 후보만 탐색하게 하세요. "
            "일반 MATERIAL ADD에서 parent가 명시되지 않은 후보 탐색은 VERSION을 임시 Parent로 분석할 수 있으며, "
            "ASSY ADD는 Parent를 추측하지 마세요. '삭제/제거/없애기/빼기'는 DELETE로 해석합니다. "
            "DELETE는 별도 EOL/원가 사유가 없어도 명시적 설계변경 Action이며 후보 선택 없이 영향분석으로 진행합니다. "
            "REPLACE/DELETE/QUANTITY_CHANGE 대상이 품목명으로만 표현되어 old_item_code가 불명확하면 "
            "get_bom을 먼저 호출하지 말고 target_item_name에 사용자의 품목명을 보존한 채 "
            "analyze_design_change_candidates를 바로 호출하세요. Service가 지정된 VERSION/PLANT의 실제 활성 BOM에서 "
            "정확한 source item을 resolve한 뒤 같은 Tool 호출에서 후보/Rule/재고/공급사 평가까지 수행합니다. "
            "QUANTITY_CHANGE는 변경 전/후 BOM QUANTITY를 기준으로 검증합니다. "
            "target_type, parent_item_code, location_code, as_of_date, effective_date는 명확하지 않으면 추측하지 말고 생략하세요. "
            "수량 평가는 생산계획을 사용하지 않고 BOM의 QUANTITY만 사용합니다. Service가 실제 Item/BOM/Metadata를 조회해 보완합니다. "
            "get_bom은 사용자가 BOM 자체를 보고 싶어 하거나 대상 식별이 불명확할 때만 "
            "사용하고, get_bom 결과만 보여주고 설계변경 Workflow를 종료하지 마세요. "
            "후보 탐색과 평가는 analyze_design_change_candidates 한 번으로 수행합니다. "
            "분석/재검증/후보 임시선택/공용 영향 확인 단계에서는 change request를 생성하지 마세요. "
            "사용자가 분석 결과를 확인하고 설계변경 진행을 명시적으로 승인한 뒤에만 실제 Request를 생성합니다. "
            "후보 선택·공용 영향 확인·Preview·최종 Apply 승인은 반드시 "
            "사용자 UI 조작으로만 진행하며 Agent가 자동 호출하지 마세요."
            if phase3_mode
            else (
                "기존 자재와 사용자가 지정한 신규 자재가 모두 명확한 "
                "교체 적합성 분석에만 analyze_design_change를 사용하세요."
            )
        )
        runtime_skill_context = (
            f"{self.skill_context}\n\n"
            "[Phase3 Runtime Workflow Gate]\n"
            f"현재 단계: {routing_step}\n"
            f"후보 추천 Workflow 여부: {phase3_mode}\n"
            f"현재 턴 BOM 확인 여부: {bom_context_ready}\n"
            f"현재 Analysis ID: {routing_workflow_state.get('analysis_id') or '없음'}\n"
            f"현재 Request ID: {active_request_id or '없음'}\n"
            f"현재 Action ID: {', '.join(active_action_ids) if active_action_ids else '없음'}\n"
            f"현재 분석 후보수: {analysis_memory.get('candidate_count', 0)}\n"
            f"현재 분석 상태건수: {analysis_memory.get('status_counts', {})}\n"
            f"현재 후속질문 Intent: {follow_up_intent or ('EVIDENCE_OBSERVED' if follow_up_complete else '없음')}\n"
            f"제품 BOM 전체 원가절감 Scan 여부: {product_cost_scan_intent}\n"
            f"질문에 명시된 후보코드: {', '.join(mentioned_candidate_codes) if mentioned_candidate_codes else '없음'}\n"
            f"PLANT 필요 여부: {plant_required}\n"
            f"현재 확정 PLANT: {active_plant_code or plant_code_in_context or '없음'}\n"
            f"현재 턴 PLANT 목록 조회 여부: {plant_options_observed}\n"
            "BOM 조회와 설계변경은 plant_code가 반드시 필요합니다. 사용자가 PLANT를 명시하지 않았고 "
            "현재 Analysis/Workflow에도 PLANT가 없으면 다른 업무 Tool을 실행하지 말고 list_plants로 대상 VERSION/ASSY/MATERIAL이 "
            "실제 존재하는 PLANT만 조회하세요. 대상 코드가 아직 식별되지 않았다면 모든 PLANT를 나열하지 말고 먼저 대상 모델/ASSY/자재를 확인하세요. "
            "기본 PLANT를 추측하지 마세요. PLANT 선택은 Streamlit 버튼 UI가 처리하므로 "
            "list_plants 결과를 받은 턴에는 다른 업무 Tool을 이어서 호출하지 마세요. "
            "사용자가 버튼으로 PLANT를 선택하면 직전 요청 Context와 결합해 원래 업무를 계속하세요.\n"
            "자재/ASSY가 어떤 상위 ASSY 또는 최상위 MODEL에 사용되는지 묻는 역방향 BOM 질문은 "
            "get_bom_where_used를 사용하세요. MATERIAL을 get_bom의 Root로 사용하지 마세요. "
            "where-used 결과가 없으면 현재 선택한 PLANT의 BOM에 구성되어 있지 않다고 명확히 답하세요.\n"
            "설계변경 사유는 사용자의 원문을 request.original_request로 전달하고, "
            "사용자가 표준 reason_code를 직접 명시하지 않았다면 reason_code를 추측해 "
            "만들지 마세요. Service의 Reason Metadata Resolver가 Primary/Secondary Reason을 확정합니다. "
            "사용자가 별도 업무 사유를 말하지 않았더라도 REPLACE/ADD/DELETE/QUANTITY_CHANGE 분석을 중단하거나 "
            "사유를 추가 질문하지 마세요. 이 경우 Service가 등록된 중립 사유 USER_REQUEST를 사용합니다. "
            "복수 사유가 감지되어도 하나만 다시 선택하라고 요구하지 말고 모든 사유를 보존해 평가하세요. "
            "COMMON_ASSY를 변경 사유로 사용하지 마세요.\n"
            "설계변경 분석 후 사용자의 왜/사유/근거/비교 질문은 새로운 설계변경 요청으로 초기화하지 마세요. "
            "다만 사용자가 '다시 처음부터', '새로 분석', '다시 조회'처럼 명시적으로 재시작을 요청하면 "
            "현재 Analysis Memory만 새 Analysis Session으로 교체하고 실제 Design Change Request는 생성/취소하지 마세요. "
            "후속질문에서는 기존 후보평가를 다시 실행하지 말고 Explain Tool의 저장된 Evidence를 사용하세요. "
            "후보가 0건인지, 후보는 있지만 PASS/CONDITIONAL이 0건인지 반드시 구분하세요. "
            "기술 FAIL은 공급사 PASS로 뒤집지 말고, 근거 데이터가 없으면 추측하지 마세요. "
            "사용자가 특정 한 품목이 아니라 대상 모델/BOM 전체에서 원가를 낮출 대체 자재를 찾는 경우에는 "
            "임의의 BOM 마지막 품목을 설계변경 target으로 선택하지 마세요. "
            "scan_product_cost_reduction_candidates를 사용해 BOM 전체를 탐색하세요. "
            "Scan 결과의 cost_reduction_status=CONFIRMED인 경우에만 실제 원가 절감 후보라고 표현하고, "
            "UNAVAILABLE은 기술적으로 대체 가능하지만 현재품/후보 단가 근거 부족으로 원가절감 여부를 확정할 수 없다고 설명하세요. "
            "이 Scan은 탐색용 read-only 작업이며 현재 Analysis Session을 다른 단일 target으로 덮어쓰지 않습니다. "
            "Explain Tool Observation을 이미 받은 턴에는 추가 Tool을 반복 호출하지 말고 그 근거로 최종 답변하세요.\n"
            "현재 허용된 Phase3 Tool: "
            f"{', '.join(allowed_phase3_tools) if allowed_phase3_tools else '없음'}\n"
            f"{phase3_instruction} "
            "Tool 결과에서 반환된 request_id와 action_id만 다음 단계에 사용하세요."
        )

        # A concrete design-change Action does not require a separate reason
        # confirmation turn. When the user does not state a registered business
        # reason, the Service records the neutral USER_REQUEST reason. Explicit
        # reason language (EOL/COST/COMMONIZATION/...) still takes precedence.

        plain_bom_intent = routing_decision.plain_bom
        analysis_routing_query = (
            design_change_context
            if (plant_slot_continuation or short_entity_followup)
            else user_query
        )
        named_change_target = self.domain_intent_router.extract_named_change_target(
            analysis_routing_query
        )
        # ADD uses a dedicated target parser.  After a clarification reply such
        # as "SEALANT", extract_named_change_target intentionally returns None,
        # so the ADD target must also participate in deterministic Analysis
        # routing or the turn unnecessarily falls back to the LLM.
        add_target_name = self.domain_intent_router.extract_add_target_name(
            analysis_routing_query
        )

        required_tool_name = None
        available_tool_names = {
            str(tool.get("function", {}).get("name") or "")
            for tool in tool_definitions
        }
        if (
            plant_required and not plant_context_ready and plant_reference_code
            and not plant_options_observed and "list_plants" in available_tool_names
        ):
            required_tool_name = "list_plants"
        elif (
            plain_bom_intent
            and plant_context_ready
            and not bom_context_ready
            and "get_bom" in available_tool_names
        ):
            required_tool_name = "get_bom"
        elif (
            product_cost_scan_intent
            and plant_context_ready
            and not product_cost_scan_observed
            and "scan_product_cost_reduction_candidates" in available_tool_names
        ):
            required_tool_name = "scan_product_cost_reduction_candidates"
        elif (
            where_used_intent
            and plant_context_ready
            and not where_used_observed
            and routing_decision.where_used_item_code
            and "get_bom_where_used" in available_tool_names
        ):
            required_tool_name = "get_bom_where_used"
        elif follow_up_intent == "EXPLAIN_ANALYSIS" and "get_design_change_analysis" in allowed_phase3_tools:
            required_tool_name = "get_design_change_analysis"
        elif follow_up_intent == "EXPLAIN_CANDIDATE" and "get_candidate_evaluation_detail" in allowed_phase3_tools:
            required_tool_name = "get_candidate_evaluation_detail"
        elif follow_up_intent in {"COMPARE_CANDIDATES", "RANK_CANDIDATES"} and "compare_design_change_candidates" in allowed_phase3_tools:
            required_tool_name = "compare_design_change_candidates"
        elif (
            phase3_mode
            and routing_step == "NOT_STARTED"
            and plant_context_ready
            and (
                self.domain_intent_router.has_explicit_design_change_target(
                    analysis_routing_query
                )
                or named_change_target
                or add_target_name
                or bom_context_ready
            )
            and "analyze_design_change_candidates" in allowed_phase3_tools
        ):
            required_tool_name = "analyze_design_change_candidates"

        if required_tool_name == "list_plants":
            ai_message = self._build_plant_list_tool_message(
                user_query=design_change_context,
                workflow_state=routing_workflow_state,
            )
        elif required_tool_name == "get_bom" and plain_bom_intent:
            ai_message = self._build_bom_tool_message(
                user_query=design_change_context,
                plant_code=active_plant_code or plant_code_in_context,
            )
        elif required_tool_name == "get_bom_where_used":
            ai_message = self._build_where_used_tool_message(
                user_query=user_query,
                plant_code=active_plant_code or plant_code_in_context,
            )
        elif (
            product_cost_scan_intent
            and plant_context_ready
            and not product_cost_scan_observed
            and "scan_product_cost_reduction_candidates" in available_tool_names
            and self._active_version_code(routing_workflow_state)
        ):
            ai_message = self._build_product_cost_scan_tool_message(
                user_query=user_query,
                workflow_state=routing_workflow_state,
                plant_code=active_plant_code or plant_code_in_context,
            )
        elif follow_up_intent == "RESTART_ANALYSIS" and not follow_up_complete:
            ai_message = self._build_restart_analysis_tool_message(workflow_state)
        elif follow_up_intent and not follow_up_complete:
            ai_message = self._build_follow_up_tool_message(
                follow_up_intent=follow_up_intent,
                user_query=user_query,
                workflow_state=workflow_state,
            )
        elif required_tool_name == "analyze_design_change_candidates":
            macro_message = self.analysis_macro_dispatch.build_tool_message(
                user_query=analysis_routing_query,
                active_bom_context=state.get("active_bom_context"),
                workflow_state={
                    **routing_workflow_state,
                    "current_step": routing_step,
                    # pending slot has already been consumed and normalized above.
                    "pending_quantity_request": None,
                },
            )
            if macro_message is not None:
                ai_message = macro_message
            else:
                effective_messages = self._messages_with_effective_user_query(
                    messages,
                    user_query,
                )
                compacted_messages, _context_diet_stats = (
                    self.llm_context_compactor.compact(
                        effective_messages,
                        current_user_query=user_query,
                    )
                )
                record_performance_event(
                    category="context",
                    name="llm.context_diet",
                    metadata={
                        "message_count": len(effective_messages),
                        "compacted_message_count": len(compacted_messages),
                    },
                    metrics={
                        "original_tool_chars": _context_diet_stats.original_tool_chars,
                        "compacted_tool_chars": _context_diet_stats.compacted_tool_chars,
                        "saved_tool_chars": _context_diet_stats.saved_tool_chars,
                        "compacted_tool_messages": _context_diet_stats.compacted_tool_messages,
                    },
                )
                openai_messages = self._convert_messages(compacted_messages)
                self._record_prompt_budget(
                    compacted_messages=compacted_messages,
                    openai_messages=openai_messages,
                    tool_definitions=tool_definitions,
                    runtime_skill_context=runtime_skill_context,
                )
                assistant_message = self.client.create_agent_completion(
                    messages=openai_messages,
                    tools=tool_definitions,
                    skill_context=runtime_skill_context,
                    tool_choice=required_tool_name,
                )
                ai_message = self._convert_assistant_message(assistant_message)
        else:
            effective_messages = self._messages_with_effective_user_query(
                messages,
                user_query,
            )
            compacted_messages, _context_diet_stats = (
                self.llm_context_compactor.compact(
                    effective_messages,
                    current_user_query=user_query,
                )
            )
            record_performance_event(
                category="context",
                name="llm.context_diet",
                metadata={
                    "message_count": len(effective_messages),
                    "compacted_message_count": len(compacted_messages),
                },
                metrics={
                    "original_tool_chars": _context_diet_stats.original_tool_chars,
                    "compacted_tool_chars": _context_diet_stats.compacted_tool_chars,
                    "saved_tool_chars": _context_diet_stats.saved_tool_chars,
                    "compacted_tool_messages": _context_diet_stats.compacted_tool_messages,
                },
            )
            openai_messages = self._convert_messages(compacted_messages)
            self._record_prompt_budget(
                compacted_messages=compacted_messages,
                openai_messages=openai_messages,
                tool_definitions=tool_definitions,
                runtime_skill_context=runtime_skill_context,
            )

            assistant_message = (
                self.client
                .create_agent_completion(
                    messages=openai_messages,
                    tools=tool_definitions,
                    skill_context=runtime_skill_context,
                    tool_choice=required_tool_name or "auto",
                )
            )

            ai_message = (
                self._convert_assistant_message(
                    assistant_message
                )
            )

        result = {
            "messages": [ai_message],
            "error": None,
        }
        if (
            pending_quantity_consumed
            or pending_add_target_consumed
            or pending_add_parent_consumed
        ):
            result["design_change"] = dict(workflow_state)
        return result

    def _record_prompt_budget(
        self,
        *,
        compacted_messages: list[BaseMessage],
        openai_messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        runtime_skill_context: str,
    ) -> None:
        """Record prompt-size components without storing prompt contents."""
        base_skill_chars = len(str(self.skill_context or ""))
        runtime_skill_chars = len(str(runtime_skill_context or ""))
        runtime_gate_chars = max(
            0,
            runtime_skill_chars - base_skill_chars - 2,  # separating newlines
        )

        # Profiling must never depend on a mocked/injected client implementation.
        # Use the real static prompt builder so unit tests with Mock clients keep
        # exercising Agent behavior instead of failing inside instrumentation.
        core_system_prompt = AzureOpenAIClient._build_agent_system_prompt(None)
        full_system_prompt = AzureOpenAIClient._build_agent_system_prompt(
            runtime_skill_context
        )
        skill_wrapper_chars = max(
            0,
            len(full_system_prompt)
            - len(core_system_prompt)
            - runtime_skill_chars,
        )

        message_payload_chars = len(
            json.dumps(
                openai_messages,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        )
        tool_definition_chars = len(
            json.dumps(
                tool_definitions,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        )

        human_content_chars = 0
        assistant_content_chars = 0
        tool_content_chars = 0
        for message in compacted_messages:
            content_chars = len(str(getattr(message, "content", "") or ""))
            if isinstance(message, HumanMessage):
                human_content_chars += content_chars
            elif isinstance(message, ToolMessage):
                tool_content_chars += content_chars
            elif isinstance(message, AIMessage):
                assistant_content_chars += content_chars

        approx_total_chars = (
            len(core_system_prompt)
            + skill_wrapper_chars
            + base_skill_chars
            + runtime_gate_chars
            + message_payload_chars
            + tool_definition_chars
        )

        record_performance_event(
            category="prompt",
            name="llm.prompt_budget",
            metadata={
                "message_count": len(compacted_messages),
                "tool_definition_count": len(tool_definitions),
            },
            metrics={
                "core_system_chars": len(core_system_prompt),
                "skill_wrapper_chars": skill_wrapper_chars,
                "base_skill_chars": base_skill_chars,
                "runtime_gate_chars": runtime_gate_chars,
                "message_payload_chars": message_payload_chars,
                "human_content_chars": human_content_chars,
                "assistant_content_chars": assistant_content_chars,
                "tool_content_chars": tool_content_chars,
                "tool_definition_chars": tool_definition_chars,
                "tool_definition_count": len(tool_definitions),
                "approx_total_chars": approx_total_chars,
            },
        )

        for definition in tool_definitions:
            function = definition.get("function") or {}
            tool_name = str(function.get("name") or "unknown")
            schema_chars = len(
                json.dumps(
                    definition,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                )
            )
            record_performance_event(
                category="prompt",
                name="llm.tool_schema_budget",
                metadata={"tool_name": tool_name},
                metrics={"schema_chars": schema_chars},
            )

    @classmethod
    def _comparison_criterion(cls, user_query: str) -> str:
        return DEFAULT_DOMAIN_INTENT_ROUTER.comparison_criterion(user_query)

    @classmethod
    def _build_restart_analysis_tool_message(cls, workflow_state: dict) -> AIMessage:
        """Restart only the read-only Analysis Session using the original analysis input.

        No persisted Design Change Request is created, superseded, or deleted here.
        """
        base_request = dict(
            workflow_state.get("analysis_base_request")
            or workflow_state.get("analysis_request")
            or {}
        )
        actions = [
            {
                key: value.get(key)
                for key in (
                    "action_type", "target_type", "parent_item_code", "reason_code",
                    "old_item_code", "new_item_code", "location_code",
                    "old_quantity", "new_quantity",
                )
                if value.get(key) is not None
            }
            for value in workflow_state.get("actions", [])
        ]
        if not base_request or not actions:
            raise ValueError("다시 분석할 원래 Analysis Context가 없습니다.")
        base_request.pop("request_id", None)
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "analyze_design_change_candidates",
                "args": {"request": base_request, "actions": actions},
                "id": f"restart-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _build_follow_up_tool_message(
        cls,
        *,
        follow_up_intent: str,
        user_query: str,
        workflow_state: dict,
    ) -> AIMessage:
        request_id = workflow_state.get("request_id")
        analysis_id = workflow_state.get("analysis_id")
        analysis_payload = {
            "analysis_id": analysis_id,
            "request": workflow_state.get("analysis_request") or {},
            "actions": workflow_state.get("actions") or [],
            "candidates": workflow_state.get("candidates") or [],
            "analysis_context": workflow_state.get("analysis_context"),
        }
        if not request_id and not analysis_id:
            raise ValueError("후속질문을 처리할 활성 Analysis/Request Context가 없습니다.")
        mentioned = cls._mentioned_candidate_codes(user_query, workflow_state)
        action_ids = list(dict.fromkeys(
            str(value.get("action_id"))
            for value in workflow_state.get("actions", [])
            if value.get("action_id")
        ))
        if follow_up_intent == "EXPLAIN_ANALYSIS":
            if request_id:
                name = "get_design_change_analysis"
                args = {"request_id": request_id}
            else:
                name = "explain_design_change_analysis_session"
                args = {"analysis": analysis_payload}
        elif follow_up_intent == "EXPLAIN_CANDIDATE":
            if not mentioned:
                if request_id:
                    name = "get_design_change_analysis"
                    args = {"request_id": request_id}
                else:
                    name = "explain_design_change_analysis_session"
                    args = {"analysis": analysis_payload}
            else:
                name = "get_candidate_evaluation_detail" if request_id else "explain_design_change_analysis_candidate"
                matching_actions = list(dict.fromkeys(
                    str(value.get("action_id"))
                    for value in workflow_state.get("candidates", [])
                    if str(value.get("candidate_item_code") or "").upper() == mentioned[0]
                    and value.get("action_id")
                ))
                args = {"candidate_item_code": mentioned[0]}
                if request_id:
                    args["request_id"] = request_id
                else:
                    args["analysis"] = analysis_payload
                if len(matching_actions) == 1:
                    args["action_id"] = matching_actions[0]
        else:
            name = "compare_design_change_candidates" if request_id else "compare_design_change_analysis_candidates"
            args = {
                "candidate_item_codes": mentioned or None,
                "criterion": DEFAULT_DOMAIN_INTENT_ROUTER.comparison_criterion(user_query),
            }
            if request_id:
                args["request_id"] = request_id
            else:
                args["analysis"] = analysis_payload
            if len(action_ids) == 1:
                args["action_id"] = action_ids[0]
        return AIMessage(
            content="",
            tool_calls=[{
                "name": name,
                "args": args,
                "id": f"followup-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _filter_tool_definitions(
        cls,
        definitions: list[dict[str, Any]],
        current_step: str,
        *,
        phase3_mode: bool,
        bom_context_ready: bool,
        follow_up_intent: str | None = None,
        follow_up_complete: bool = False,
        product_cost_scan_intent: bool = False,
    ) -> list[dict[str, Any]]:
        """현재 Phase3 단계와 후속질문 Intent에 맞는 Tool만 LLM에 노출합니다."""
        if follow_up_complete:
            return []
        allowed_phase3 = cls.PHASE3_ALLOWED_TOOLS.get(
            current_step,
            {"get_change_request_result"},
        )
        filtered = []
        for definition in definitions:
            name = str(definition.get("function", {}).get("name") or "")
            if product_cost_scan_intent:
                if name not in {"list_plants", "scan_product_cost_reduction_candidates"}:
                    continue
                filtered.append(definition)
                continue
            if follow_up_intent:
                if follow_up_intent == "RESTART_ANALYSIS":
                    if name != "analyze_design_change_candidates":
                        continue
                elif name not in cls.PHASE3_EXPLAIN_TOOLS:
                    continue
            if phase3_mode:
                if name in cls.LEGACY_DESIGN_CHANGE_TOOLS:
                    continue
                if name in cls.PHASE3_TOOLS:
                    if name in cls.UI_ONLY_PHASE3_TOOLS:
                        continue
                    if name not in allowed_phase3:
                        continue
            elif name in cls.PHASE3_TOOLS:
                continue
            filtered.append(definition)
        return filtered

    @classmethod
    def _fast_chat_response(cls, user_query: str) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.fast_chat_response(user_query)

    @classmethod
    def _is_plain_bom_query(cls, user_query: str, *, phase3_mode: bool) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_plain_bom_query(
            user_query, phase3_mode=phase3_mode
        )

    @classmethod
    def _build_bom_tool_message(
        cls, *, user_query: str, plant_code: str | None
    ) -> AIMessage:
        product_id = cls._reference_code_for_plant_lookup(user_query, {})
        if not product_id or not plant_code:
            raise ValueError("BOM 조회에는 product_id와 plant_code가 필요합니다.")
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "get_bom",
                "args": {
                    "plant_code": str(plant_code).strip().upper(),
                    "product_id": product_id,
                },
                "id": f"bom-fast-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _is_product_cost_scan_request(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_product_cost_scan_request(user_query)

    @staticmethod
    def _active_version_code(workflow_state: dict) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.active_version_code(workflow_state)

    @classmethod
    def _excluded_items_for_product_scan(cls, user_query: str) -> tuple[list[str], list[str]]:
        text = str(user_query or "")
        upper = text.upper()
        excluded_codes: list[str] = []
        for match in cls.ITEM_CODE_PATTERN.finditer(upper):
            code = match.group(0).upper()
            tail = upper[match.end():match.end() + 16]
            if "말고" in tail or "제외" in tail:
                excluded_codes.append(code)
        excluded_names = []
        for name in cls.ASSY_PROCESS_NAMES:
            if re.search(rf"(?<![A-Z]){name}(?:\s*자재|\s*ASSY|\s*어셈블리)?\s*(?:말고|제외)", upper):
                excluded_names.append(name)
        return list(dict.fromkeys(excluded_codes)), list(dict.fromkeys(excluded_names))

    @classmethod
    def _is_where_used_request(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_where_used_request(user_query)

    @classmethod
    def _where_used_item_code(cls, user_query: str) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.where_used_item_code(user_query)

    @classmethod
    def _build_where_used_tool_message(
        cls, *, user_query: str, plant_code: str | None
    ) -> AIMessage:
        item_code = cls._where_used_item_code(user_query)
        if not item_code or not plant_code:
            raise ValueError("역방향 BOM 조회에는 item_code와 plant_code가 필요합니다.")
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "get_bom_where_used",
                "args": {
                    "item_code": item_code,
                    "plant_code": str(plant_code).strip().upper(),
                },
                "id": f"where-used-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _reference_code_for_plant_lookup(
        cls, user_query: str, workflow_state: dict
    ) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.reference_code_for_plant_lookup(
            user_query, workflow_state
        )

    @classmethod
    def _build_plant_list_tool_message(
        cls,
        *,
        user_query: str,
        workflow_state: dict,
    ) -> AIMessage:
        reference_code = cls._reference_code_for_plant_lookup(user_query, workflow_state)
        args = {"reference_code": reference_code} if reference_code else {}
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "list_plants",
                "args": args,
                "id": f"plant-list-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _build_product_cost_scan_tool_message(
        cls,
        *,
        user_query: str,
        workflow_state: dict,
        plant_code: str | None,
    ) -> AIMessage:
        version_code = cls._active_version_code(workflow_state)
        if not version_code or not plant_code:
            raise ValueError("제품 BOM 전체 원가 Scan에는 version_code와 plant_code가 필요합니다.")
        excluded_codes, excluded_names = cls._excluded_items_for_product_scan(user_query)
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "scan_product_cost_reduction_candidates",
                "args": {
                    "version_code": version_code,
                    "plant_code": str(plant_code).strip().upper(),
                    "exclude_item_codes": excluded_codes or None,
                    "exclude_item_names": excluded_names or None,
                    "include_target_types": ["MATERIAL", "ASSY"],
                    "candidates_per_item": 5,
                },
                "id": f"cost-scan-{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    @classmethod
    def _is_phase3_recommendation_request(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_phase3_recommendation_request(user_query)

    @classmethod
    def _has_phase3_reason_language(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.has_phase3_reason_language(user_query)

    @classmethod
    def _is_delete_instruction(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_delete_instruction(user_query)

    @staticmethod
    def _extract_quantity_only_input(user_query: str) -> float | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.extract_quantity_only_input(user_query)

    @staticmethod
    def _format_quantity(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    def _inherit_active_bom_context_for_change(
        self,
        *,
        user_query: str,
        workflow_state: dict,
        active_bom_context: dict | None,
    ) -> str:
        """Scope a fresh design-change follow-up to the currently active BOM.

        Example:
            active BOM = LTA400HR01-001 / P01
            current turn = "LJ94-100006 수량 바꾸고싶어"

        becomes internally:
            "LTA400HR01-001 P01 모델에서 LJ94-100006 수량 바꾸고싶어"

        This uses explicit Graph State from the latest successful get_bom,
        not an arbitrary model string found somewhere in conversation history.
        """
        context = active_bom_context or {}
        product_id = str(context.get("product_id") or "").strip().upper()
        plant_code = str(context.get("plant_code") or "").strip().upper()
        if not product_id or not plant_code:
            return user_query

        current_step = str(
            workflow_state.get("current_step") or "NOT_STARTED"
        ).strip().upper()
        if (
            current_step in self.PHASE3_ACTIVE_STEPS
            and current_step not in {"APPLIED", "BLOCKED"}
        ):
            return user_query

        decision = self.domain_intent_router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )
        if not decision.change:
            return user_query

        explicit_plant = self.domain_intent_router.extract_plant_code(user_query)
        if explicit_plant and explicit_plant != plant_code:
            # The user deliberately changed PLANT scope. Do not reuse the old BOM.
            return user_query

        explicit_model = self.domain_intent_router.explicit_model_scope_code(
            user_query
        )
        if explicit_model:
            # The user explicitly restated MODEL/PRODUCT scope. Treat it as a
            # fresh scoped request and do not silently carry PLANT from the
            # previously viewed BOM, even when the model code happens to match.
            #
            # Only queries that omit MODEL/PRODUCT may inherit active BOM scope.
            return user_query

        normalized_upper = str(user_query or "").upper()
        parts: list[str] = []

        if product_id not in normalized_upper:
            parts.append(product_id)
        if not explicit_plant:
            parts.append(plant_code)

        if not parts:
            return user_query

        # "모델에서" makes the inherited role explicit to both deterministic
        # extraction and the LLM fallback without changing the user's chat text.
        prefix = " ".join(parts)
        if product_id in parts:
            prefix += " 모델에서"

        return f"{prefix} {user_query}".strip()

    @staticmethod
    def _messages_with_effective_user_query(
        messages: list[BaseMessage],
        effective_user_query: str,
    ) -> list[BaseMessage]:
        """Use the restored full request only for current Agent reasoning.

        The actual chat history still keeps the user's compact input ("2").
        """
        updated = list(messages)
        for index in range(len(updated) - 1, -1, -1):
            if isinstance(updated[index], HumanMessage):
                updated[index] = HumanMessage(content=effective_user_query)
                break
        return updated

    @classmethod
    def _extract_new_quantity(cls, user_query: str) -> float | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.extract_new_quantity(user_query)

    @classmethod
    def _is_quantity_change_instruction(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_quantity_change_instruction(user_query)

    @classmethod
    def _is_phase3_change_request(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.is_phase3_change_request(user_query)

    @staticmethod
    def _previous_user_query(
        messages: list[BaseMessage],
        current_query: str,
    ) -> str | None:
        """Return the immediately preceding distinct HumanMessage."""
        current = str(current_query or "").strip()
        skipped_current = False
        for message in reversed(messages):
            if not isinstance(message, HumanMessage):
                continue
            value = str(message.content or "").strip()
            if not value:
                continue
            if not skipped_current and value == current:
                skipped_current = True
                continue
            if value != current:
                return value
        return None

    @staticmethod
    def _recent_user_context(messages: list[BaseMessage], current_query: str) -> str:
        """Keep the recent user target available across short follow-up turns."""
        values: list[str] = []
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                text = str(message.content or "").strip()
                if text and text not in values:
                    values.append(text)
                if len(values) >= 3:
                    break
        if current_query and current_query not in values:
            values.insert(0, str(current_query))
        return " ".join(reversed(values))

    @classmethod
    def _classify_analysis_follow_up(
        cls, user_query: str, workflow_state: dict
    ) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.classify_analysis_follow_up(
            user_query,
            workflow_state,
            active_steps=cls.PHASE3_ACTIVE_STEPS,
        )

    @classmethod
    def _mentioned_candidate_codes(
        cls, user_query: str, workflow_state: dict
    ) -> list[str]:
        return DEFAULT_DOMAIN_INTENT_ROUTER.mentioned_candidate_codes(
            user_query, workflow_state
        )

    @classmethod
    def _extract_plant_code(cls, user_query: str) -> str | None:
        return DEFAULT_DOMAIN_INTENT_ROUTER.extract_plant_code(user_query)

    @classmethod
    def _requires_plant_context(cls, user_query: str, phase3_mode: bool) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.requires_plant_context(
            user_query, phase3_mode=phase3_mode
        )

    @classmethod
    def _has_explicit_design_change_target(cls, user_query: str) -> bool:
        return DEFAULT_DOMAIN_INTENT_ROUTER.has_explicit_design_change_target(user_query)

    @staticmethod
    def _current_user_query(
        messages: list[BaseMessage],
        state_user_query: str | None,
    ) -> str:
        if state_user_query:
            return str(state_user_query)
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""

    @staticmethod
    def _current_turn_tool_names(messages: list[BaseMessage]) -> set[str]:
        names: set[str] = set()
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                break
            if isinstance(message, ToolMessage) and message.name:
                names.add(str(message.name))
        return names

    @staticmethod
    def _convert_messages(
        messages: list[BaseMessage],
    ) -> list[dict[str, Any]]:
        """
        LangChain 메시지를 Azure OpenAI가 받는
        dictionary 메시지로 변환합니다.
        """

        converted_messages: list[
            dict[str, Any]
        ] = []

        for message in messages:
            if isinstance(
                message,
                HumanMessage,
            ):
                converted_messages.append(
                    {
                        "role": "user",
                        "content": message.content,
                    }
                )
                continue

            if isinstance(
                message,
                AIMessage,
            ):
                assistant_data: dict[
                    str,
                    Any,
                ] = {
                    "role": "assistant",
                    "content": (
                        message.content or None
                    ),
                }

                if message.tool_calls:
                    assistant_data["tool_calls"] = [
                        {
                            "id": tool_call["id"],
                            "type": "function",
                            "function": {
                                "name": (
                                    tool_call["name"]
                                ),
                                "arguments": json.dumps(
                                    tool_call["args"],
                                    ensure_ascii=False,
                                ),
                            },
                        }
                        for tool_call
                        in message.tool_calls
                    ]

                converted_messages.append(
                    assistant_data
                )
                continue

            if isinstance(
                message,
                ToolMessage,
            ):
                tool_data: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": (
                        message.tool_call_id
                    ),
                    "content": message.content,
                }

                if message.name:
                    tool_data["name"] = (
                        message.name
                    )

                converted_messages.append(
                    tool_data
                )
                continue

            raise TypeError(
                "지원하지 않는 메시지 타입입니다: "
                f"{type(message).__name__}"
            )

        return converted_messages

    @staticmethod
    def _convert_assistant_message(
        assistant_message: Any,
    ) -> AIMessage:
        """
        Azure OpenAI의 ChatCompletionMessage를
        LangChain AIMessage로 변환합니다.
        """

        tool_calls = []

        for tool_call in (
            assistant_message.tool_calls or []
        ):
            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except json.JSONDecodeError as error:
                raise ValueError(
                    "Azure OpenAI가 올바르지 않은 "
                    "Tool arguments를 반환했습니다."
                ) from error

            if not isinstance(
                arguments,
                dict,
            ):
                raise ValueError(
                    "Tool arguments는 "
                    "JSON 객체여야 합니다."
                )

            tool_calls.append(
                {
                    "name": (
                        tool_call.function.name
                    ),
                    "args": arguments,
                    "id": tool_call.id,
                    "type": "tool_call",
                }
            )

        return AIMessage(
            content=(
                assistant_message.content or ""
            ),
            tool_calls=tool_calls,
        )
