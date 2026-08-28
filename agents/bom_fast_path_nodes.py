"""LLM-free LangGraph nodes for high-confidence Display BOM Fast Path."""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, ToolMessage

from agents.bom_agent_state import BomAgentState
from agents.bom_graph_gateway import BomGraphGateway
from services.query_normalizer import QueryNormalizer
from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)


FAST_READ_FINALIZE = "fast_read_finalize"
FAST_TOOL_CALL_ID_PREFIX = "graph-fast-"
FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX = (
    f"{FAST_TOOL_CALL_ID_PREFIX}current-bom-quantity-"
)


class BomFastPathNodes:
    """Deterministic Fast Path nodes.

    These nodes never call Azure OpenAI. They only convert a validated gateway
    decision into a deterministic Tool Call or a final lightweight message.
    """

    def __init__(
        self,
        router: DomainIntentRouter | None = None,
        query_normalizer: QueryNormalizer | None = None,
    ) -> None:
        self.router = router or DEFAULT_DOMAIN_INTENT_ROUTER
        self.query_normalizer = query_normalizer or QueryNormalizer()

    def chat(self, state: BomAgentState) -> BomAgentState:
        decision = self._decision(state)
        if decision.intent != "CHAT" or not decision.chat_response:
            raise ValueError("Fast Chat Node received a non-CHAT request.")
        return {
            "messages": [AIMessage(content=decision.chat_response)],
            "error": None,
        }

    def bom_read(self, state: BomAgentState) -> BomAgentState:
        decision = self._decision(state)
        if (
            decision.intent != "BOM_READ"
            or not decision.plant_code
            or not decision.reference_code
        ):
            raise ValueError(
                "Fast BOM Read Node requires BOM_READ, plant_code and reference_code."
            )

        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_bom",
                    "args": {
                        "plant_code": decision.plant_code,
                        "product_id": decision.reference_code,
                    },
                    "id": self._tool_call_id("bom"),
                    "type": "tool_call",
                }],
            )],
            "error": None,
        }

    def current_bom_quantity(self, state: BomAgentState) -> BomAgentState:
        decision = self._decision(state)
        context = BomGraphGateway.read_scope_context(state)
        product_id = str(context.get("product_id") or "").strip().upper()
        plant_code = str(context.get("plant_code") or "").strip().upper()

        if (
            decision.intent != "CURRENT_BOM_QUANTITY"
            or not decision.current_bom_subject
            or not product_id
            or not plant_code
        ):
            raise ValueError(
                "Current BOM Quantity Node requires an active BOM and quantity subject."
            )

        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_bom",
                    "args": {
                        "plant_code": plant_code,
                        "product_id": product_id,
                    },
                    "id": (
                        f"{FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX}"
                        f"{uuid.uuid4().hex[:12]}"
                    ),
                    "type": "tool_call",
                }],
            )],
            "error": None,
        }

    def where_used(self, state: BomAgentState) -> BomAgentState:
        decision = self._decision(state)
        if (
            decision.intent != "WHERE_USED"
            or not decision.plant_code
            or not decision.where_used_item_code
        ):
            raise ValueError(
                "Fast Where-used Node requires WHERE_USED, plant_code and item_code."
            )

        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": "get_bom_where_used",
                    "args": {
                        "plant_code": decision.plant_code,
                        "item_code": decision.where_used_item_code,
                    },
                    "id": self._tool_call_id("where-used"),
                    "type": "tool_call",
                }],
            )],
            "error": None,
        }

    def finalize_read(self, state: BomAgentState) -> BomAgentState:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], ToolMessage):
            raise ValueError("Fast Read Finalize Node requires a ToolMessage result.")

        tool_message = messages[-1]
        if is_current_bom_quantity_tool_message(tool_message):
            content = self._current_bom_quantity_answer(state, tool_message)
        elif tool_message.name == "get_bom":
            content = "BOM 조회 결과를 확인해 주세요."
        elif tool_message.name == "get_bom_where_used":
            content = "역방향 BOM 조회 결과를 확인해 주세요."
        else:
            raise ValueError(
                f"Unsupported Fast Read Tool result: {tool_message.name or '-'}"
            )

        return {
            "messages": [AIMessage(content=content)],
            "error": None,
        }

    def _current_bom_quantity_answer(
        self,
        state: BomAgentState,
        tool_message: ToolMessage,
    ) -> str:
        user_query = BomGraphGateway.last_user_query(state)
        subject = self.router.extract_current_bom_quantity_subject(user_query)
        context = BomGraphGateway.read_scope_context(state)
        product_id = str(context.get("product_id") or "-").strip().upper()
        plant_code = str(context.get("plant_code") or "-").strip().upper()

        if not subject:
            return "현재 BOM에서 조회할 자재 또는 품목을 확인할 수 없습니다."

        try:
            rows = json.loads(str(tool_message.content))
        except (TypeError, json.JSONDecodeError):
            rows = []

        if not isinstance(rows, list):
            rows = []

        explicit_codes = self.router.item_codes(subject)
        scored: list[tuple[int, dict]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            child_code = str(
                row.get("bom_child")
                or row.get("CHILD_CODE")
                or ""
            ).strip().upper()
            child_name = str(
                row.get("bom_child_name")
                or row.get("CHILD_NAME")
                or ""
            ).strip()

            if explicit_codes:
                score = 10000 if child_code in explicit_codes else 0
            else:
                score = self.query_normalizer.match_score(
                    subject,
                    child_code,
                    child_name,
                )

            if score > 0:
                scored.append((score, row))

        if not scored:
            return (
                f"현재 {product_id} / {plant_code} BOM에서 "
                f"'{subject}'에 해당하는 품목을 찾지 못했습니다."
            )

        best_score = max(score for score, _ in scored)
        best_rows = [row for score, row in scored if score == best_score]

        # Collapse exact duplicate relations while preserving different
        # parent/location occurrences.
        unique: list[dict] = []
        seen: set[tuple] = set()
        for row in best_rows:
            key = (
                row.get("bom_child") or row.get("CHILD_CODE"),
                row.get("bom_parent") or row.get("PARENT_CODE"),
                row.get("location") or row.get("LOCATION"),
                row.get("quantity") if "quantity" in row else row.get("수량"),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        if len(unique) == 1:
            row = unique[0]
            child_code = str(
                row.get("bom_child")
                or row.get("CHILD_CODE")
                or "-"
            ).strip().upper()
            child_name = str(
                row.get("bom_child_name")
                or row.get("CHILD_NAME")
                or "-"
            ).strip()
            quantity = (
                row.get("quantity")
                if "quantity" in row
                else row.get("수량")
            )
            return (
                f"현재 {product_id} / {plant_code} BOM에서 "
                f"{child_name}({child_code})의 BOM 수량은 {quantity}입니다."
            )

        lines = [
            (
                f"현재 {product_id} / {plant_code} BOM에서 "
                f"'{subject}'에 해당하는 항목이 {len(unique)}건 있습니다."
            )
        ]
        for row in unique:
            child_code = str(
                row.get("bom_child") or row.get("CHILD_CODE") or "-"
            ).strip().upper()
            child_name = str(
                row.get("bom_child_name") or row.get("CHILD_NAME") or "-"
            ).strip()
            parent = str(
                row.get("bom_parent") or row.get("PARENT_CODE") or "-"
            ).strip().upper()
            location = str(
                row.get("location") or row.get("LOCATION") or "-"
            ).strip()
            quantity = (
                row.get("quantity")
                if "quantity" in row
                else row.get("수량")
            )
            lines.append(
                f"- {child_name}({child_code}) / Parent {parent} / "
                f"LOCATION {location} / BOM 수량 {quantity}"
            )
        return "\n".join(lines)

    def _decision(self, state: BomAgentState):
        user_query = BomGraphGateway.last_user_query(state)
        return self.router.route(
            user_query,
            workflow_active=False,
            workflow_state={},
        )

    @staticmethod
    def _tool_call_id(kind: str) -> str:
        return f"{FAST_TOOL_CALL_ID_PREFIX}{kind}-{uuid.uuid4().hex[:12]}"


def is_current_bom_quantity_tool_message(
    message: ToolMessage,
) -> bool:
    return str(message.tool_call_id or "").startswith(
        FAST_CURRENT_BOM_QUANTITY_CALL_PREFIX
    )


def is_graph_fast_tool_result(state: BomAgentState) -> bool:
    """Return True only for a ToolMessage created by a Graph Fast Path node."""
    messages = state.get("messages", [])
    if not messages:
        return False
    last_message = messages[-1]
    if not isinstance(last_message, ToolMessage):
        return False
    return str(last_message.tool_call_id or "").startswith(
        FAST_TOOL_CALL_ID_PREFIX
    )
