"""LangGraph Node for deterministic Phase3 Analysis Macro dispatch."""

from __future__ import annotations

from agents.analysis_macro_dispatch import DeterministicAnalysisMacroDispatch
from agents.bom_agent_state import BomAgentState
from agents.bom_graph_gateway import BomGraphGateway


class BomMacroDispatchNode:
    """Create the Analysis Macro Tool Call without Azure OpenAI."""

    def __init__(
        self,
        dispatch: DeterministicAnalysisMacroDispatch | None = None,
    ) -> None:
        self.dispatch = dispatch or DeterministicAnalysisMacroDispatch()

    def __call__(self, state: BomAgentState) -> BomAgentState:
        user_query = BomGraphGateway.last_user_query(state)
        message = self.dispatch.build_tool_message(
            user_query=user_query,
            active_bom_context=state.get("active_bom_context"),
            workflow_state=state.get("design_change") or {},
        )
        if message is None:
            raise ValueError(
                "Macro Analysis Node requires a complete deterministic change request."
            )
        return {
            "messages": [message],
            "error": None,
        }
