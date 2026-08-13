from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agents.design_change_workflow_state import (
    DesignChangeWorkflowState,
)


class BomAgentState(TypedDict, total=False):
    """Display BOM AI Agent의 LangGraph 실행 상태."""

    messages: Annotated[list[BaseMessage], add_messages]
    user_query: str
    tool_steps: int
    error: str | None
    design_change: DesignChangeWorkflowState
    
