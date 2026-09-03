import json
from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_composition_nodes import (
    COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX,
    COMPOSITION_PLAN,
    BomReadOnlyCompositionNodes,
    is_composition_knowledge_tool_result,
)
from agents.bom_graph_gateway import (
    AGENT_PATH,
    FAST_KNOWLEDGE,
    FAST_TEXT_TO_SQL,
    BomGraphGateway,
)
from agents.design_change_workflow_state import create_initial_design_change_state


D01 = "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
D02 = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


class FakeTextToSqlNodes:
    def query(self, state):
        query = state["messages"][-1].content
        assert "공급사별 평균 단가" in query
        assert "기준" not in query
        return {
            "messages": [
                AIMessage(
                    content=(
                        "조회 결과입니다. 총 2건입니다.\n\n"
                        "| supplier_id | avg_price |\n"
                        "| --- | --- |\n"
                        "| SUP-101 | 1,361.32 |\n"
                        "| SUP-102 | 1,300.46 |"
                    )
                )
            ],
            "error": None,
        }


class FakeKnowledgeNodes:
    def finalize(self, state):
        assert isinstance(state["messages"][0], HumanMessage)
        assert isinstance(state["messages"][-1], ToolMessage)
        return {
            "messages": [
                AIMessage(
                    content=(
                        "원가 절감 변경은 등록된 설계변경 기준과 "
                        "근거 데이터를 함께 확인해야 합니다.\n\n"
                        "참고 근거\n- [설계변경 규칙] 원가 절감 기준"
                    )
                )
            ],
            "error": None,
        }


def _state(query, workflow=None):
    return {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": workflow or create_initial_design_change_state(),
        "tool_steps": 0,
        "error": None,
    }


def _nodes():
    return BomReadOnlyCompositionNodes(
        text_to_sql_nodes=FakeTextToSqlNodes(),
        knowledge_nodes=FakeKnowledgeNodes(),
    )


def test_runtime_admits_only_read_only_text_to_sql_plus_rag():
    nodes = _nodes()

    assert nodes.can_execute(_state(D01)) is True
    assert nodes.can_execute(_state(D02)) is False
    assert nodes.can_execute(_state("단종 자재 교체 기준이 뭐야?")) is False
    assert nodes.can_execute(_state("공급사별 평균 단가를 알려줘")) is False


def test_active_workflow_cannot_enter_read_only_composition():
    workflow = create_initial_design_change_state()
    workflow["current_step"] = "ANALYSIS_READY"
    workflow["analysis_id"] = "ANA-1"

    assert _nodes().can_execute(_state(D01, workflow)) is False


def test_composition_plan_derives_router_approved_subqueries():
    nodes = _nodes()
    update = nodes.plan(_state(D01))
    runtime = update["composition_runtime"]

    assert runtime["write_authority_granted"] is False
    assert runtime["plan"]["required_capabilities"] == [
        "TEXT_TO_SQL",
        "RAG",
    ]
    assert "기준" not in runtime["queries"]["TEXT_TO_SQL"]
    assert "공급사별 평균 단가" in runtime["queries"]["TEXT_TO_SQL"]
    assert "원가 절감 기준" in runtime["queries"]["RAG"]


def test_composition_executes_analytics_then_grounded_knowledge_and_merges():
    nodes = _nodes()
    state = _state(D01)

    state.update(nodes.plan(state))
    state.update(nodes.text_to_sql(state))
    knowledge_update = nodes.knowledge_query(state)
    state["messages"] += knowledge_update["messages"]
    state["composition_runtime"] = knowledge_update["composition_runtime"]

    tool_call = state["messages"][-1].tool_calls[0]
    assert tool_call["name"] == "search_knowledge"
    assert tool_call["id"].startswith(COMPOSITION_KNOWLEDGE_TOOL_CALL_PREFIX)

    tool_message = ToolMessage(
        content=json.dumps({
            "success": True,
            "query": tool_call["args"]["query"],
            "hit_count": 1,
            "authority": {"knowledge_evidence_only": True},
            "hits": [{
                "rank": 1,
                "document_id": "COST-RULE",
                "document_title": "원가 절감 기준",
                "document_type": "CHANGE_RULE",
                "section_path": "원가 절감",
                "content": "원가 절감 설계변경 기준",
            }],
        }, ensure_ascii=False),
        tool_call_id=tool_call["id"],
        name="search_knowledge",
    )
    state["messages"].append(tool_message)

    assert is_composition_knowledge_tool_result(state) is True
    state.update(nodes.knowledge_finalize(state))
    final = nodes.finalize(state)

    answer = final["messages"][-1].content
    assert "### 데이터 분석" in answer
    assert "SUP-101" in answer
    assert "### 관련 업무 기준" in answer
    assert "참고 근거" in answer
    assert final["composition_runtime"] is None


def test_graph_runtime_route_promotes_d01_but_keeps_workflow_composition_on_agent():
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )
    graph.composition_path_nodes = _nodes()

    # Gateway itself remains conservative for backwards compatibility.
    assert graph.gateway.route(_state(D01)) == AGENT_PATH
    # Graph runtime selectively promotes the safe read-only composition.
    assert graph._runtime_route(_state(D01)) == COMPOSITION_PLAN
    # Workflow-managed composition is not promoted.
    assert graph._runtime_route(_state(D02)) == AGENT_PATH


def test_graph_runtime_route_preserves_single_capability_fast_paths():
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )
    graph.composition_path_nodes = _nodes()

    assert (
        graph._runtime_route(_state("단종 자재 교체 기준이 뭐야?"))
        == FAST_KNOWLEDGE
    )
    assert (
        graph._runtime_route(_state("공급사별 평균 단가를 알려줘"))
        == FAST_TEXT_TO_SQL
    )
