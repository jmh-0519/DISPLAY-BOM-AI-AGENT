"""Deterministic dispatch for high-confidence Design Change Analysis requests.

This module removes the first LLM call only when all routing slots required to
start a read-only Analysis Session are already deterministic.

It never creates a Design Change Request and never applies Production E-BOM.
"""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage

from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)


MACRO_ANALYZE = "macro_analyze"
MACRO_ANALYZE_TOOL_CALL_PREFIX = "macro-analysis-"


class DeterministicAnalysisMacroDispatch:
    """Build one `analyze_design_change_candidates` Tool Call without LLM."""

    SAFE_START_STEPS = frozenset({
        "NOT_STARTED",
        "APPLIED",
        "REPORT_COMPLETED",
        "BLOCKED",
    })

    def __init__(self, router: DomainIntentRouter | None = None) -> None:
        self.router = router or DEFAULT_DOMAIN_INTENT_ROUTER

    def build_tool_message(
        self,
        *,
        user_query: str,
        active_bom_context: dict[str, Any] | None = None,
        workflow_state: dict[str, Any] | None = None,
    ) -> AIMessage | None:
        spec = self.build_spec(
            user_query=user_query,
            active_bom_context=active_bom_context,
            workflow_state=workflow_state,
        )
        if spec is None:
            return None

        return AIMessage(
            content="",
            tool_calls=[{
                "name": "analyze_design_change_candidates",
                "args": spec,
                "id": f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }],
        )

    def build_spec(
        self,
        *,
        user_query: str,
        active_bom_context: dict[str, Any] | None = None,
        workflow_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return Tool args when the request is safe for deterministic dispatch."""
        workflow_state = workflow_state or {}
        current_step = str(
            workflow_state.get("current_step") or "NOT_STARTED"
        ).strip().upper()

        if current_step not in self.SAFE_START_STEPS:
            return None
        if str(workflow_state.get("pending_quantity_request") or "").strip():
            return None

        decision = self.router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )
        # A reason-grounded recommendation such as EOL/supply-stop is still a
        # read-only design-change Analysis request.  It may safely use the
        # deterministic macro when MODEL/PLANT/target are explicit.  A generic
        # "candidate recommendation" without business reason remains on the
        # normal Agent path because its analysis objective may be ambiguous.
        reason_based_recommendation = (
            decision.recommendation
            and self.router.has_design_change_reason_language(user_query)
        )
        # A recommendation request with explicit MODEL + target item codes and
        # PLANT is also safe for the read-only Analysis macro.  The macro never
        # creates a Request or applies Production BOM.  Named/ambiguous targets
        # remain on the Agent path for resolution.
        explicit_code_recommendation = (
            decision.recommendation
            and bool(self.router.extract_plant_code(user_query))
            and len(list(dict.fromkeys(self.router.item_codes(user_query)))) >= 2
        )
        if (
            not decision.change
            and not reason_based_recommendation
            and not explicit_code_recommendation
        ):
            return None

        action_type = self._action_type(user_query)
        if action_type is None:
            return None

        version_code, plant_code = self._scope(
            user_query=user_query,
            active_bom_context=active_bom_context,
        )
        if not version_code or not plant_code:
            return None

        if action_type == "ADD":
            action = self._add_action(
                user_query=user_query,
                version_code=version_code,
            )
            if action is None:
                return None
        else:
            target = self._source_target(
                user_query=user_query,
                version_code=version_code,
            )
            if target is None:
                return None
            action = {
                "action_type": action_type,
                **target,
            }

        if action_type == "QUANTITY_CHANGE":
            new_quantity = self.router.extract_new_quantity(user_query)
            if new_quantity is None:
                return None
            action["new_quantity"] = new_quantity

        request = {
            "version_code": version_code,
            "plant_code": plant_code,
            "original_request": str(user_query).strip(),
        }

        return {
            "request": request,
            "actions": [action],
        }

    def _scope(
        self,
        *,
        user_query: str,
        active_bom_context: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        context = active_bom_context or {}
        active_version = str(context.get("product_id") or "").strip().upper() or None
        active_plant = str(context.get("plant_code") or "").strip().upper() or None

        explicit_version = self.router.explicit_model_scope_code(user_query)
        explicit_plant = self.router.extract_plant_code(user_query)

        if explicit_version is None and explicit_plant:
            explicit_version = self._positional_version_scope(user_query)

        if explicit_version:
            # Current-turn explicit MODEL always wins. Reuse the active PLANT only
            # when the explicit MODEL is the same currently viewed BOM.
            if explicit_plant:
                return explicit_version, explicit_plant
            if active_version == explicit_version and active_plant:
                return explicit_version, active_plant
            return None, None

        if explicit_plant:
            # Do not combine a new explicit PLANT with an inherited MODEL. The
            # user must provide the MODEL too so write scope cannot be guessed.
            if active_plant and explicit_plant == active_plant and active_version:
                return active_version, explicit_plant
            return None, None

        if active_version and active_plant:
            return active_version, active_plant

        return None, None


    def _positional_version_scope(self, user_query: str) -> str | None:
        """Resolve a high-confidence VERSION scope without a ``모델`` suffix.

        Natural requests often omit the word ``모델``::

            LTA... P02 0001-... 교체해줘
            LTA... P02 DRIVE-IC가 단종이라 교체하고 싶어

        When PLANT is explicit, the first code can safely serve as the scope if
        another item code or an explicit named ADD/change target is also present.
        A lone code is never promoted to VERSION because it may itself be the
        source MATERIAL/ASSY.  Service validation remains authoritative.
        """
        if not self.router.extract_plant_code(user_query):
            return None

        codes = list(dict.fromkeys(self.router.item_codes(user_query)))
        if len(codes) >= 2:
            return codes[0]
        if len(codes) != 1:
            return None

        if (
            self.router.extract_named_change_target(user_query)
            or self.router.extract_add_target_name(user_query)
        ):
            return codes[0]
        return None

    def _add_action(
        self,
        *,
        user_query: str,
        version_code: str,
    ) -> dict[str, Any] | None:
        """Build a safe ADD action only when the requested target is explicit.

        MATERIAL ADD:
            target type + item code/name/family must be explicit.
            Parent may be omitted because the Service uses VERSION as the visible
            provisional parent during Analysis.

        ASSY ADD:
            target type + item code/name + explicit parent are required.
            The parent is never guessed.

        Generic requests such as ``자재를 추가하고 싶어`` deliberately return
        ``None`` so the Agent node can ask which material/ASSY the user means
        before creating an Analysis Session.
        """
        target_type = self.router.extract_add_target_type(user_query)
        target_name = self.router.extract_add_target_name(user_query)
        if not target_type:
            return None

        non_version_codes = [
            code for code in self.router.item_codes(user_query)
            if code != version_code
        ]

        explicit_new_code: str | None = None
        if target_type == "MATERIAL":
            # With the product VERSION already removed from scope, one explicit
            # MATERIAL code is unambiguously the item the user wants to add.
            if len(non_version_codes) == 1:
                explicit_new_code = non_version_codes[0]
            elif len(non_version_codes) > 1:
                return None

            if not target_name and not explicit_new_code:
                return None

            action: dict[str, Any] = {
                "action_type": "ADD",
                "target_type": target_type,
            }
            if explicit_new_code:
                action["new_item_code"] = explicit_new_code
            if target_name:
                action["target_item_name"] = target_name

        else:
            # ASSY placement must never guess its parent. Keep unnamed or
            # parentless ASSY requests on the clarification/Agent path.
            if not target_name:
                return None
            parent_code = self.router.extract_add_parent_code(
                user_query,
                version_code=version_code,
            )
            if not parent_code:
                return None
            action = {
                "action_type": "ADD",
                "target_type": target_type,
                "target_item_name": target_name,
                "parent_item_code": parent_code,
            }

        new_quantity = self.router.extract_new_quantity(user_query)
        if new_quantity is not None:
            action["new_quantity"] = new_quantity

        return action

    def _source_target(
        self,
        *,
        user_query: str,
        version_code: str,
    ) -> dict[str, str] | None:
        codes = [
            code
            for code in self.router.item_codes(user_query)
            if code != version_code
        ]

        # More than one non-version code can mean an explicit old/new pair.
        # Keep such requests on the LLM Agent path instead of guessing roles.
        unique_codes = list(dict.fromkeys(codes))
        if len(unique_codes) > 1:
            return None
        if len(unique_codes) == 1:
            return {"old_item_code": unique_codes[0]}

        named_target = self.router.extract_named_change_target(user_query)
        if not named_target:
            return None
        return {"target_item_name": named_target}

    def _action_type(self, user_query: str) -> str | None:
        normalized = self.router.normalize(user_query)

        if self.router.is_quantity_change_instruction(user_query):
            return "QUANTITY_CHANGE"
        if self.router.is_delete_instruction(user_query):
            return "DELETE"

        if "추가" in normalized or "넣어" in normalized:
            return "ADD"

        if any(
            marker in normalized
            for marker in ("변경", "교체", "대체", "바꾸", "바꿔")
        ):
            return "REPLACE"

        return None


def is_macro_analysis_tool_call_id(tool_call_id: str | None) -> bool:
    return str(tool_call_id or "").startswith(MACRO_ANALYZE_TOOL_CALL_PREFIX)
