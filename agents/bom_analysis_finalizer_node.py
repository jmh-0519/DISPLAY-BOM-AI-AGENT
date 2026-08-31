"""Dedicated final-answer node for deterministic Design Change Macro Analysis.

The expensive Agent routing prompt, Skills and Tool catalog are not needed
after a high-confidence Macro Analysis has already completed successfully.

This node keeps the original ToolMessage in LangGraph state, builds a compact
LLM-only Analysis Evidence copy, and asks Azure OpenAI only to explain that
evidence in Korean.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.analysis_macro_dispatch import is_macro_analysis_tool_call_id
from agents.bom_agent_state import BomAgentState
from agents.llm_context_compactor import LlmContextCompactor
from core.azure_openai_client import AzureOpenAIClient
from core.performance_profiler import record_performance_event


ANALYSIS_FINALIZE = "analysis_finalize"


def is_macro_analysis_tool_result(state: BomAgentState) -> bool:
    """Whether the latest Tool result came from deterministic Macro dispatch."""
    messages = state.get("messages", [])
    if not messages:
        return False

    last_message = messages[-1]
    return (
        isinstance(last_message, ToolMessage)
        and str(last_message.name or "") == "analyze_design_change_candidates"
        and is_macro_analysis_tool_call_id(last_message.tool_call_id)
    )


class BomAnalysisFinalizerNode:
    """Generate a concise natural-language Analysis summary with zero Tools."""

    def __init__(
        self,
        *,
        client: AzureOpenAIClient,
        compactor: LlmContextCompactor | None = None,
        deterministic: bool = False,
    ) -> None:
        self.client = client
        self.compactor = compactor or LlmContextCompactor()
        self.deterministic = bool(deterministic)

    def __call__(self, state: BomAgentState) -> BomAgentState:
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("Analysis Finalizer requires Agent messages.")

        last_message = messages[-1]
        if not isinstance(last_message, ToolMessage):
            raise TypeError("Analysis Finalizer requires a ToolMessage result.")
        if not is_macro_analysis_tool_result(state):
            raise ValueError(
                "Analysis Finalizer accepts only deterministic Macro Analysis results."
            )

        user_query = self._last_user_query(messages)

        # Macro Analysis already has deterministic, verified Tool evidence.
        # Render the common successful result locally so the high-confidence Macro
        # path does not spend 4-5 seconds on a prose-only LLM call.  If the payload
        # is malformed or outside the supported shape, fall back to the original
        # LLM finalizer for robustness.
        if self.deterministic:
            deterministic_answer = self._render_deterministic_analysis(
                str(last_message.content or "")
            )
            if deterministic_answer:
                record_performance_event(
                    category="finalizer",
                    name="analysis.finalizer.deterministic",
                    metadata={"mode": "DETERMINISTIC"},
                    metrics={"llm_calls_avoided": 1},
                )
                return {
                    "messages": [AIMessage(content=deterministic_answer)],
                    "error": None,
                }

        # Build an LLM-only compact copy. The original ToolMessage remains intact
        # in LangGraph state, Workflow state and Streamlit evidence.
        compacted, stats = self.compactor.compact(
            [
                HumanMessage(content=user_query),
                last_message,
            ],
            current_user_query=user_query,
        )
        compacted_tool = compacted[-1]
        if not isinstance(compacted_tool, ToolMessage):
            raise RuntimeError("Analysis Evidence compaction did not return ToolMessage.")

        record_performance_event(
            category="context",
            name="llm.context_diet",
            metadata={
                "message_count": 2,
                "compacted_message_count": 2,
                "finalizer": True,
            },
            metrics={
                "original_tool_chars": stats.original_tool_chars,
                "compacted_tool_chars": stats.compacted_tool_chars,
                "saved_tool_chars": stats.saved_tool_chars,
                "compacted_tool_messages": stats.compacted_tool_messages,
            },
        )

        answer = self.client.create_analysis_final_answer(
            user_message=user_query,
            analysis_evidence=str(compacted_tool.content or ""),
        )

        return {
            "messages": [AIMessage(content=answer)],
            "error": None,
        }


    @classmethod
    def _render_deterministic_analysis(cls, content: str) -> str | None:
        """Render verified Macro Analysis evidence without another LLM call.

        The renderer never derives new business facts.  It only formats fields
        already present in the Tool result.  Returning ``None`` deliberately
        activates the existing LLM fallback for unexpected payloads.
        """
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None

        candidates = payload.get("candidates")
        actions = payload.get("actions")
        if candidates is not None and not isinstance(candidates, list):
            return None
        if actions is not None and not isinstance(actions, list):
            return None

        candidates = [row for row in (candidates or []) if isinstance(row, dict)]
        actions = [row for row in (actions or []) if isinstance(row, dict)]
        request = payload.get("request") if isinstance(payload.get("request"), dict) else {}

        counts = payload.get("status_counts")
        if not isinstance(counts, dict):
            counts = {
                status: sum(str(row.get("status") or "").upper() == status for row in candidates)
                for status in ("PASS", "CONDITIONAL", "FAIL")
            }

        lines = ["설계변경 후보 분석을 완료했습니다."]

        version_code = request.get("version_code")
        plant_code = request.get("plant_code")
        scope = " / ".join(str(value) for value in (version_code, plant_code) if value)
        if scope:
            lines.append(f"- 대상: {scope}")

        if actions:
            action = actions[0]
            action_type = str(action.get("action_type") or "").upper()
            target = (
                action.get("old_item_code")
                or action.get("new_item_code")
                or action.get("target_item_name")
            )
            action_text = " · ".join(str(value) for value in (action_type, target) if value)
            if action_text:
                lines.append(f"- 변경: {action_text}")

        lines.append(
            "- 결과: "
            f"PASS {int(counts.get('PASS') or 0)}건, "
            f"평가 보류 {int(counts.get('CONDITIONAL') or 0)}건, "
            f"FAIL {int(counts.get('FAIL') or 0)}건"
        )

        # The Tool already returns candidates in business ranking order. Preserve
        # that order and expose only a compact preview; the full evidence remains
        # in Graph state / Streamlit tables.
        preview = candidates[:5]
        if preview:
            lines.append("- 후보:")
            for index, row in enumerate(preview, 1):
                code = str(row.get("candidate_item_code") or "-")
                name = row.get("candidate_item_name") or row.get("candidate_name")
                label = f"{code} ({name})" if name else code
                status = str(row.get("status") or "-").upper()
                detail = cls._candidate_status_detail(row, status)
                reason = cls._first_reason(row)
                suffix = f" · {reason}" if reason else ""
                lines.append(f"  {index}. {label} — {status}{detail}{suffix}")

        analysis_status = str(payload.get("analysis_status") or "").upper()
        if analysis_status == "FAIL" and not any(
            str(row.get("status") or "").upper() in {"PASS", "CONDITIONAL"}
            for row in candidates
        ):
            lines.append("선택 가능한 PASS/평가 보류 후보가 없습니다.")
        elif int(counts.get("CONDITIONAL") or 0) > 0:
            lines.append("평가 보류 후보는 추가 근거 재검증 또는 예외 검토가 필요합니다.")
        elif int(counts.get("PASS") or 0) > 0:
            lines.append("PASS 후보의 근거를 확인한 뒤 설계변경 진행 여부를 결정할 수 있습니다.")

        if payload.get("request_created") is False or payload.get("production_bom_modified") is False:
            lines.append("현재는 분석 단계이며 설계변경 Request 생성이나 Production E-BOM 변경은 수행되지 않았습니다.")

        return "\n".join(lines)

    @staticmethod
    def _candidate_status_detail(row: dict[str, Any], status: str) -> str:
        if status == "PASS" and row.get("total_score") is not None:
            return f" · 점수 {row.get('total_score')}"
        if status == "CONDITIONAL":
            return " · 추천 점수 평가 보류"
        return ""

    @staticmethod
    def _first_reason(row: dict[str, Any]) -> str | None:
        reasons = row.get("decision_reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                text = str(reason or "").strip()
                if text:
                    return text
        for key in ("decision_reason", "evaluation_reason"):
            text = str(row.get(key) or "").strip()
            if text:
                return text
        return None

    @staticmethod
    def _last_user_query(messages: list) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                value = str(message.content or "").strip()
                if value:
                    return value
        raise ValueError("Analysis Finalizer could not find the current user query.")
