"""Dedicated final-answer node for deterministic Phase3 Macro Analysis.

The expensive Agent routing prompt, Skills and Tool catalog are not needed
after a high-confidence Macro Analysis has already completed successfully.

This node keeps the original ToolMessage in LangGraph state, builds a compact
LLM-only Analysis Evidence copy, and asks Azure OpenAI only to explain that
evidence in Korean.
"""

from __future__ import annotations

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
    ) -> None:
        self.client = client
        self.compactor = compactor or LlmContextCompactor()

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

    @staticmethod
    def _last_user_query(messages: list) -> str:
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                value = str(message.content or "").strip()
                if value:
                    return value
        raise ValueError("Analysis Finalizer could not find the current user query.")
