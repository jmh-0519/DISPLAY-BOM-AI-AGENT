"""Live smoke test for the deterministic Knowledge RAG graph path components."""

from __future__ import annotations

import argparse

from langchain_core.messages import HumanMessage

from agents.bom_graph_gateway import FAST_KNOWLEDGE, BomGraphGateway
from agents.bom_knowledge_nodes import BomKnowledgePathNodes
from agents.bom_mcp_tool_node import BomMcpToolNode
from core.azure_openai_client import AzureOpenAIClient
from core.settings import Settings
from mcp_client.client import DisplayBomMcpClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "query",
        nargs="?",
        default="단종 자재 교체 기준이 뭐야?",
    )
    args = parser.parse_args()
    state = {
        "messages": [HumanMessage(content=args.query)],
        "user_query": args.query,
        "tool_steps": 0,
        "error": None,
        "design_change": {"current_step": "NOT_STARTED"},
    }
    route = BomGraphGateway().route(state)
    if route != FAST_KNOWLEDGE:
        raise RuntimeError(f"Expected {FAST_KNOWLEDGE}, got {route}")

    client = AzureOpenAIClient(Settings.from_env())
    nodes = BomKnowledgePathNodes(client=client)
    query_update = nodes.query(state)
    state["messages"] = state["messages"] + query_update["messages"]

    tool_update = BomMcpToolNode(DisplayBomMcpClient())(state)
    state["messages"] = state["messages"] + tool_update["messages"]
    state["tool_steps"] = tool_update.get("tool_steps", state["tool_steps"])
    state["error"] = tool_update.get("error")
    if state["error"]:
        raise RuntimeError(state["error"])

    final = nodes.finalize(state)
    print("RAG Agent integration smoke test passed")
    print(f"- route: {route}")
    print("- answer:")
    print(final["messages"][-1].content)


if __name__ == "__main__":
    main()
