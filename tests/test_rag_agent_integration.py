import json

from langchain_core.messages import HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import FAST_KNOWLEDGE, BomGraphGateway
from agents.bom_knowledge_nodes import BomKnowledgePathNodes, is_knowledge_tool_result


class FakeClient:
    def create_knowledge_final_answer(self, *, user_message, knowledge_evidence):
        assert "단종" in user_message
        assert "EOL" in knowledge_evidence
        return "단종 자재 교체는 EOL 관련 기준을 참고합니다."


def test_gateway_routes_knowledge_without_exposing_tool_to_agent():
    state = {
        "messages": [HumanMessage(content="단종 자재 교체 기준이 뭐야?")],
        "design_change": {"current_step": "NOT_STARTED"},
    }
    assert BomGraphGateway().route(state) == FAST_KNOWLEDGE
    definitions = [
        {"function": {"name": "get_bom"}},
        {"function": {"name": "search_knowledge"}},
    ]
    filtered = BomAgentNode._filter_tool_definitions(
        definitions,
        "NOT_STARTED",
        design_change_mode=False,
        bom_context_ready=False,
    )
    assert [value["function"]["name"] for value in filtered] == ["get_bom"]


def test_knowledge_nodes_create_deterministic_tool_and_grounded_answer():
    nodes = BomKnowledgePathNodes(client=FakeClient())
    state = {
        "messages": [HumanMessage(content="단종 자재 교체 기준이 뭐야?")],
        "user_query": "단종 자재 교체 기준이 뭐야?",
    }
    query_update = nodes.query(state)
    tool_call = query_update["messages"][0].tool_calls[0]
    assert tool_call["name"] == "search_knowledge"

    payload = {
        "success": True,
        "query": state["user_query"],
        "hit_count": 1,
        "authority": {"knowledge_evidence_only": True},
        "hits": [{
            "rank": 1,
            "document_id": "EOL",
            "document_title": "단종 대응",
            "document_type": "CHANGE_REASON",
            "section_path": "단종 대응",
            "source_file": "knowledge/reasons/EOL.md",
            "content": "EOL 단종 대응 기준",
        }],
    }
    tool_message = ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=tool_call["id"],
        name="search_knowledge",
    )
    final_state = {
        "messages": state["messages"] + query_update["messages"] + [tool_message]
    }
    assert is_knowledge_tool_result(final_state) is True
    final = nodes.finalize(final_state)
    answer = final["messages"][-1].content
    assert "참고 근거" in answer
    assert "knowledge/reasons/EOL.md" in answer
