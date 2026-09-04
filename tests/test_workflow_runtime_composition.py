import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_graph import BomAgentGraph
from agents.bom_agent_node import BomAgentNode
from agents.bom_composition_nodes import COMPOSITION_PLAN
from agents.bom_graph_gateway import AGENT_PATH, BomGraphGateway
from agents.bom_text_to_sql_nodes import BomTextToSqlPathNodes
from agents.bom_workflow_composition_nodes import (
    WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX,
    WORKFLOW_COMPOSITION_PLAN,
    BomWorkflowCompositionNodes,
    is_workflow_composition_analysis_tool_result,
    is_workflow_composition_knowledge_tool_result,
)
from agents.design_change_workflow_state import create_initial_design_change_state
from agents.workflow_evidence_handoff import (
    EvidenceToWorkflowHandoff,
    HandoffStatus,
)
from text_to_sql.pipeline import TextToSqlPipelineResult


VERSION = "LTA400HR01-001"
OLD_VERSION = "LTA550HR11-001"
PLANT = "P01"
ITEM = "0001-200007"

READ_ONLY_GOAL = "공급사별 평균 단가를 비교하고 관련 원가 절감 기준도 알려줘"
AMBIGUOUS_GOAL = (
    "이 모델의 원가가 높은 자재를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)
UNIQUE_GOAL = (
    "이 모델에서 가장 원가가 높은 자재 1개를 찾고 "
    "그 자재를 변경할 때 적용되는 기준과 영향을 알려줘"
)


class FakePipeline:
    def __init__(self, result):
        self.result = result
        self.questions = []

    def run(self, question):
        self.questions.append(question)
        return self.result


class FakeCostEvidenceQuery:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, *, version_code, plant_code, question, as_of_date=None):
        self.calls.append({
            "version_code": version_code,
            "plant_code": plant_code,
            "question": question,
            "as_of_date": as_of_date,
        })
        return self.result


class FakeAnalysisFinalizer:
    def __call__(self, state):
        assert is_workflow_composition_analysis_tool_result(state)
        return {
            "messages": [
                AIMessage(content="설계변경 후보 분석을 완료했습니다.")
            ],
            "error": None,
        }


def _sql_result():
    return TextToSqlPipelineResult(
        status="SQL",
        question=(
            f"{VERSION} {PLANT} 모델의 활성 BOM에서 "
            "현재 확인 가능한 원가 또는 단가가 가장 높은 자재 1개"
        ),
        sql=(
            "SELECT b.child_item_code AS item_code, ia.unit_cost "
            "FROM bom_master b "
            "JOIN item_attributes ia ON ia.item_code=b.child_item_code "
            f"WHERE b.parent_item_code='{VERSION}' "
            f"AND b.plant_code='{PLANT}' "
            "ORDER BY ia.unit_cost DESC LIMIT 1"
        ),
        reason="",
        columns=(
            "item_code", "item_name", "parent_item_code", "location_code",
            "unit_cost", "price_source", "currency_code",
        ),
        rows=({
            "item_code": ITEM,
            "item_name": "FILM",
            "parent_item_code": "LJ94-100003",
            "location_code": "ALL",
            "unit_cost": 1200.0,
            "price_source": "PRIMARY_SUPPLIER",
            "currency_code": "KRW",
        },),
        row_count=1,
        truncated=False,
        elapsed_ms=1.0,
    )


def _knowledge_payload(*, hits=True):
    return {
        "success": True,
        "query": "원가 절감 설계변경 기준과 영향",
        "authority": {"knowledge_evidence_only": True},
        "hit_count": 1 if hits else 0,
        "hits": ([{
            "rank": 1,
            "document_id": "COST-RULE",
            "document_title": "원가 절감 기준",
            "document_type": "CHANGE_RULE",
            "section_path": "원가 절감",
            "content": "원가 절감 설계변경 기준",
        }] if hits else []),
    }


def _state(query=UNIQUE_GOAL, *, active_scope=True):
    state = {
        "messages": [HumanMessage(content=query)],
        "user_query": query,
        "design_change": create_initial_design_change_state(),
        "tool_steps": 0,
        "error": None,
    }
    if active_scope:
        state["active_bom_context"] = {
            "product_id": VERSION,
            "plant_code": PLANT,
            "source": "get_bom",
        }
    return state


def _pre_request_analysis_workflow(version=OLD_VERSION):
    state = create_initial_design_change_state()
    state.update({
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-OLD",
        "plant_code": PLANT,
        "analysis_request": {
            "version_code": version,
            "plant_code": PLANT,
        },
    })
    return state


def _nodes():
    result = _sql_result()
    text_nodes = BomTextToSqlPathNodes(
        pipeline=FakePipeline(result)
    )
    return BomWorkflowCompositionNodes(
        text_to_sql_nodes=text_nodes,
        analysis_finalizer=FakeAnalysisFinalizer(),
        cost_evidence_query=FakeCostEvidenceQuery(result),
    )


def test_text_to_sql_execute_result_preserves_structured_evidence():
    result = _sql_result()
    pipeline = FakePipeline(result)
    nodes = BomTextToSqlPathNodes(pipeline=pipeline)

    actual = nodes.execute_result(
        f"{VERSION} {PLANT} 활성 BOM에서 원가 또는 단가가 가장 높은 자재 1개"
    )

    assert actual is result
    assert actual.rows[0]["item_code"] == ITEM
    assert actual.sql.endswith("LIMIT 1")
    assert len(pipeline.questions) == 1


def test_workflow_composition_requires_existing_safe_scope():
    nodes = _nodes()

    assert nodes.can_execute(_state(UNIQUE_GOAL, active_scope=True)) is True
    assert nodes.can_execute(_state(UNIQUE_GOAL, active_scope=False)) is False


def test_ambiguous_goal_is_stopped_before_sql_or_rag():
    nodes = _nodes()
    state = _state(AMBIGUOUS_GOAL)

    update = nodes.plan(state)

    assert update["composition_runtime"] is None
    assert "단일 변경 대상" in update["messages"][-1].content
    assert not update["messages"][-1].tool_calls


def test_unique_goal_builds_scoped_sql_and_clean_knowledge_queries():
    nodes = _nodes()
    state = _state()

    update = nodes.plan(state)
    runtime = update["composition_runtime"]

    assert runtime["status"] == "PLANNED"
    assert runtime["scope"]["version_code"] == VERSION
    assert runtime["scope"]["plant_code"] == PLANT
    assert VERSION in runtime["queries"]["TEXT_TO_SQL"]
    assert PLANT in runtime["queries"]["TEXT_TO_SQL"]
    assert "가장 높은 자재 1개" in runtime["queries"]["TEXT_TO_SQL"]
    assert runtime["queries"]["RAG"] == "원가 절감 설계변경 기준과 영향"
    assert runtime["write_authority_granted"] is False


def test_workflow_text_to_sql_keeps_raw_result_without_second_execution():
    nodes = _nodes()
    state = _state()
    state.update(nodes.plan(state))

    update = nodes.text_to_sql(state)
    runtime = update["composition_runtime"]
    raw = runtime["results"]["TEXT_TO_SQL"]["raw"]

    assert runtime["status"] == "TEXT_TO_SQL_COMPLETED"
    assert raw["rows"] == [{
        "item_code": ITEM,
        "item_name": "FILM",
        "parent_item_code": "LJ94-100003",
        "location_code": "ALL",
        "unit_cost": 1200.0,
        "price_source": "PRIMARY_SUPPLIER",
        "currency_code": "KRW",
    }]
    assert raw["row_count"] == 1
    assert raw["truncated"] is False
    assert raw["sql"].endswith("LIMIT 1")
    assert len(nodes.text_to_sql_nodes.pipeline.questions) == 0
    assert len(nodes.cost_evidence_query.calls) == 1
    assert runtime["results"]["TEXT_TO_SQL"]["execution_mode"] == (
        "DETERMINISTIC_SCOPED_BOM_SQL"
    )


def test_no_cost_evidence_stops_before_rag_or_analysis():
    empty_result = TextToSqlPipelineResult(
        status="SQL",
        question=(
            f"{VERSION} {PLANT} 모델의 활성 BOM에서 "
            "현재 확인 가능한 원가 또는 단가가 가장 높은 자재 1개"
        ),
        sql=(
            "WITH RECURSIVE reachable(item_code) AS "
            f"(SELECT '{VERSION}') "
            "SELECT item_code FROM reachable "
            f"WHERE '{PLANT}' = '{PLANT}' "
            "ORDER BY item_code DESC LIMIT 1"
        ),
        reason="",
        columns=(
            "item_code", "item_name", "parent_item_code", "location_code",
            "unit_cost", "price_source", "currency_code",
        ),
        rows=(),
        row_count=0,
        truncated=False,
        elapsed_ms=1.0,
    )
    text_nodes = BomTextToSqlPathNodes(
        pipeline=FakePipeline(empty_result)
    )
    nodes = BomWorkflowCompositionNodes(
        text_to_sql_nodes=text_nodes,
        analysis_finalizer=FakeAnalysisFinalizer(),
        cost_evidence_query=FakeCostEvidenceQuery(empty_result),
    )
    state = _state()
    state.update(nodes.plan(state))

    update = nodes.text_to_sql(state)

    assert update["composition_runtime"] is None
    assert "원가/단가 근거" in update["messages"][-1].content
    assert not update["messages"][-1].tool_calls
    assert len(nodes.cost_evidence_query.calls) == 1
    assert len(nodes.text_to_sql_nodes.pipeline.questions) == 0


def test_knowledge_result_handoff_dispatches_analysis_only_tool():
    nodes = _nodes()
    state = _state()
    state.update(nodes.plan(state))
    state.update(nodes.text_to_sql(state))

    knowledge_update = nodes.knowledge_query(state)
    state["messages"] += knowledge_update["messages"]
    state["composition_runtime"] = knowledge_update["composition_runtime"]
    tool_call = state["messages"][-1].tool_calls[0]

    assert tool_call["name"] == "search_knowledge"

    tool_message = ToolMessage(
        content=json.dumps(_knowledge_payload(), ensure_ascii=False),
        tool_call_id=tool_call["id"],
        name="search_knowledge",
    )
    state["messages"].append(tool_message)
    assert is_workflow_composition_knowledge_tool_result(state) is True

    update = nodes.handoff_and_dispatch(state)
    analysis_call = update["messages"][-1].tool_calls[0]

    assert analysis_call["name"] == "analyze_design_change_candidates"
    assert analysis_call["id"].startswith(
        WORKFLOW_COMPOSITION_ANALYSIS_TOOL_CALL_PREFIX
    )
    assert analysis_call["args"] == {
        "request": {
            "version_code": VERSION,
            "plant_code": PLANT,
            "original_request": UNIQUE_GOAL,
        },
        "actions": [{
            "action_type": "REPLACE",
            "old_item_code": ITEM,
            "parent_item_code": "LJ94-100003",
            "location_code": "ALL",
        }],
    }
    handoff = update["composition_runtime"]["handoff"]
    assert handoff["ready"] is True
    assert handoff["write_authority_granted"] is False
    assert "request_id" not in analysis_call["args"]["request"]


def test_empty_rag_evidence_never_dispatches_design_change_analysis():
    handoff = EvidenceToWorkflowHandoff()
    decision = handoff.build(
        user_goal=UNIQUE_GOAL,
        sql_result=_sql_result(),
        knowledge_payload=_knowledge_payload(hits=False),
        scope=handoff.resolve_scope(
            UNIQUE_GOAL,
            active_bom_context={
                "product_id": VERSION,
                "plant_code": PLANT,
            },
        ),
    )

    assert decision.status == HandoffStatus.KNOWLEDGE_EVIDENCE_EMPTY
    assert decision.ready is False
    assert decision.tool_arguments is None


def test_composed_analysis_finalizer_clears_ephemeral_runtime():
    nodes = _nodes()
    state = _state()
    state.update(nodes.plan(state))
    state.update(nodes.text_to_sql(state))

    knowledge_update = nodes.knowledge_query(state)
    state["messages"] += knowledge_update["messages"]
    state["composition_runtime"] = knowledge_update["composition_runtime"]
    knowledge_call = state["messages"][-1].tool_calls[0]
    state["messages"].append(
        ToolMessage(
            content=json.dumps(_knowledge_payload(), ensure_ascii=False),
            tool_call_id=knowledge_call["id"],
            name="search_knowledge",
        )
    )

    handoff_update = nodes.handoff_and_dispatch(state)
    state["messages"] += handoff_update["messages"]
    state["composition_runtime"] = handoff_update["composition_runtime"]
    analysis_call = state["messages"][-1].tool_calls[0]

    state["messages"].append(
        ToolMessage(
            content=json.dumps({
                "analysis_id": "ANA-1",
                "request_created": False,
                "request_id": None,
                "request": {
                    "version_code": VERSION,
                    "plant_code": PLANT,
                },
                "actions": [{
                    "action_type": "REPLACE",
                    "old_item_code": ITEM,
                }],
                "candidates": [],
                "status_counts": {
                    "PASS": 0,
                    "CONDITIONAL": 0,
                    "FAIL": 0,
                },
                "analysis_status": "FAIL",
                "production_bom_modified": False,
            }, ensure_ascii=False),
            tool_call_id=analysis_call["id"],
            name="analyze_design_change_candidates",
        )
    )

    update = nodes.analysis_finalize(state)

    assert update["composition_runtime"] is None
    assert "설계변경 후보 분석을 완료했습니다." in update["messages"][-1].content
    assert ITEM in update["messages"][-1].content
    assert "COST-RULE" in update["messages"][-1].content


def test_graph_runtime_promotes_only_scoped_workflow_composition():
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )

    class _ReadOnlyComposition:
        @staticmethod
        def can_execute(state):
            return False

    graph.composition_path_nodes = _ReadOnlyComposition()
    graph.workflow_composition_path_nodes = _nodes()

    scoped = _state(UNIQUE_GOAL, active_scope=True)
    unscoped = _state(UNIQUE_GOAL, active_scope=False)

    assert graph.gateway.route(scoped) == AGENT_PATH
    assert graph._runtime_route(scoped) == WORKFLOW_COMPOSITION_PLAN
    assert graph._runtime_route(unscoped) == AGENT_PATH


def test_explicit_active_bom_scope_can_replace_pre_request_analysis():
    query = (
        f"{VERSION} {PLANT} 대상으로 가장 원가가 높은 자재 1개를 찾아 "
        "변경 분석해줘"
    )
    nodes = _nodes()
    state = _state(query, active_scope=True)
    state["design_change"] = _pre_request_analysis_workflow()

    assert nodes.can_execute(state) is True


def test_relative_scope_does_not_replace_existing_pre_request_analysis():
    nodes = _nodes()
    state = _state(UNIQUE_GOAL, active_scope=True)
    state["design_change"] = _pre_request_analysis_workflow(version=VERSION)

    assert nodes.can_execute(state) is False


def test_request_backed_workflow_can_never_be_replaced_by_composition():
    query = (
        f"{VERSION} {PLANT} 대상으로 가장 원가가 높은 자재 1개를 찾아 "
        "변경 분석해줘"
    )
    nodes = _nodes()
    state = _state(query, active_scope=True)
    workflow = _pre_request_analysis_workflow()
    workflow["request_id"] = "REQ-LOCKED"
    state["design_change"] = workflow

    assert nodes.can_execute(state) is False


def test_graph_promotes_explicit_fresh_scope_after_old_analysis():
    query = (
        f"{VERSION} {PLANT} 대상으로 가장 원가가 높은 자재 1개를 찾아 "
        "변경 분석해줘"
    )
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )

    class _ReadOnlyComposition:
        @staticmethod
        def can_execute(state):
            return False

    graph.composition_path_nodes = _ReadOnlyComposition()
    graph.workflow_composition_path_nodes = _nodes()

    state = _state(query, active_scope=True)
    state["design_change"] = _pre_request_analysis_workflow()

    assert graph.gateway.route(state) == AGENT_PATH
    assert graph._runtime_route(state) == WORKFLOW_COMPOSITION_PLAN


def test_graph_runtime_still_promotes_existing_read_only_composition_first():
    graph = object.__new__(BomAgentGraph)
    graph.gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )

    class _ReadOnlyComposition:
        @staticmethod
        def can_execute(state):
            return True

    class _WorkflowComposition:
        @staticmethod
        def can_execute(state):
            raise AssertionError("workflow path must not steal read-only request")

    graph.composition_path_nodes = _ReadOnlyComposition()
    graph.workflow_composition_path_nodes = _WorkflowComposition()

    assert graph._runtime_route(_state(READ_ONLY_GOAL)) == COMPOSITION_PLAN
