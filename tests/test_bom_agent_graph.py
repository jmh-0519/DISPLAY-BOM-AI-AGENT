from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agents.bom_agent_graph import (
    BomAgentGraph,
)


def make_assistant_message(
    content=None,
    tool_calls=None,
):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
    )


def make_tool_call(
    tool_call_id,
    name,
    arguments,
):
    return SimpleNamespace(
        id=tool_call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def make_tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_bom",
                "description": "제품 BOM 조회",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "product_id"
                    ],
                },
            },
        }
    ]


def make_design_change_tool_definitions():
    return [
        {
            "type": "function",
            "function": {
                "name": "analyze_design_change_candidates",
                "description": "설계변경 후보 분석",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        }
    ]


def test_graph_returns_direct_final_answer():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.return_value = (
        make_assistant_message(
            content="최종 답변입니다.",
            tool_calls=None,
        )
    )

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 업무 규칙",
    )

    result = graph.run(
        "BOM 관리 기준을 알려줘"
    )

    assert result == "최종 답변입니다."

    client.create_agent_completion.assert_called_once()
    mcp_client.call_tool.assert_not_called()


def test_graph_executes_tool_loop_and_finalizes_plain_bom_without_second_llm():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = make_tool_definitions()
    mcp_client.call_tool.return_value = [
        {
            "product_id": "PRD-001",
            "material_id": "MAT-001",
        }
    ]

    client.create_agent_completion.return_value = make_assistant_message(
        content=None,
        tool_calls=[
            make_tool_call(
                tool_call_id="call-001",
                name="get_bom",
                arguments='{"product_id": "PRD-001"}',
            )
        ],
    )

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = graph.run("PRD-001의 BOM을 조회해줘")

    assert result == "BOM 조회 결과를 확인해 주세요."
    assert client.create_agent_completion.call_count == 1

    mcp_client.call_tool.assert_called_once_with(
        tool_name="get_bom",
        arguments={"product_id": "PRD-001"},
    )

def test_graph_remembers_messages_in_same_thread():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content=(
                "LTA400HR01-0의 BOM 조회 결과입니다."
            ),
            tool_calls=None,
        ),
        make_assistant_message(
            content=(
                "앞서 조회한 BOM 중 "
                "DRIVER IC 항목입니다."
            ),
            tool_calls=None,
        ),
    ]

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    graph.run(
        "LTA400HR01-0의 BOM을 보여줘.",
        thread_id="thread-001",
    )

    result = graph.run(
        "그중 DRIVER IC만 알려줘.",
        thread_id="thread-001",
    )

    assert result == (
        "앞서 조회한 BOM 중 "
        "DRIVER IC 항목입니다."
    )

    second_call = (
        client
        .create_agent_completion
        .call_args_list[1]
        .kwargs
    )

    converted_messages = second_call[
        "messages"
    ]

    assert [
        message["role"]
        for message in converted_messages
    ] == [
        "user",
        "assistant",
        "user",
    ]

    assert converted_messages[0]["content"] == (
        "LTA400HR01-0의 BOM을 보여줘"
    )

    assert converted_messages[2]["content"] == (
        "그중 DRIVER IC만 알려줘."
    )        

def test_graph_separates_different_threads():
    client = Mock()
    mcp_client = Mock()

    mcp_client.get_tool_definitions.return_value = (
        make_tool_definitions()
    )

    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content="첫 번째 대화 답변",
            tool_calls=None,
        ),
        make_assistant_message(
            content="두 번째 대화 답변",
            tool_calls=None,
        ),
    ]

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    graph.run(
        "첫 번째 대화 질문",
        thread_id="thread-A",
    )

    graph.run(
        "두 번째 대화 질문",
        thread_id="thread-B",
    )

    second_call = (
        client
        .create_agent_completion
        .call_args_list[1]
        .kwargs
    )

    converted_messages = second_call[
        "messages"
    ]

    assert [
        message["role"]
        for message in converted_messages
    ] == [
        "user",
    ]

    assert converted_messages[0]["content"] == (
        "두 번째 대화 질문"
    )


def test_graph_persists_design_change_workflow_state():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = make_design_change_tool_definitions()
    mcp_client.call_tool.return_value = {
        "analysis_id": "ANL-001",
        "request": {"version_code": "MODEL-001", "plant_code": "P01"},
        "actions": [{"action_id": "ACT-001", "action_type": "REPLACE"}],
        "candidates": [],
        "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 0},
        "analysis_context": {},
    }
    client.create_agent_completion.side_effect = [
        make_assistant_message(
            content=None,
            tool_calls=[make_tool_call(
                tool_call_id="call-analysis",
                name="analyze_design_change_candidates",
                arguments=(
                    '{"request":{"version_code":"MODEL-001","plant_code":"P01"},'
                    '"actions":[{"action_type":"REPLACE",'
                    '"old_item_code":"1234-567890",'
                    '"new_item_code":"1234-567891"}]}'
                ),
            )],
        ),
        make_assistant_message(
            content="설계변경 분석 결과를 확인했습니다.",
            tool_calls=None,
        ),
    ]
    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="설계변경 규칙",
    )

    graph.run(
        "P01에서 MODEL-001의 1234-567890을 "
        "1234-567891로 교체 가능한지 분석해줘",
        thread_id="change-001",
    )
    workflow = graph.get_design_change_state("change-001")

    assert workflow["analysis_id"] == "ANL-001"
    assert workflow["request_id"] is None
    assert workflow["current_step"] == "ANALYSIS_READY"

def test_graph_returns_initial_workflow_for_new_thread():
    graph = BomAgentGraph(
        client=Mock(),
        mcp_client=Mock(),
        skill_context="설계변경 규칙",
    )

    workflow = graph.get_design_change_state("new-thread")

    assert workflow["analysis_status"] == "NOT_STARTED"
    assert workflow["current_step"] == "NOT_STARTED"


def test_graph_updates_workflow_after_streamlit_direct_action():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = []
    client.create_agent_completion.return_value = make_assistant_message(
        content="후보 승인 대기 중입니다.",
        tool_calls=None,
    )
    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="Design Change workflow",
    )
    thread_id = "design-change-ui-sync"
    graph.run("후보를 확인해줘", thread_id=thread_id)

    workflow = graph.get_design_change_state(thread_id)
    workflow.update({
        "request_id": "REQ-UI-SYNC",
        "candidate_approval_id": "APR-UI-SYNC",
        "requires_exception": True,
        "current_step": "CANDIDATE_APPROVED",
    })
    graph.update_design_change_state(workflow, thread_id=thread_id)

    synchronized = graph.get_design_change_state(thread_id)
    assert synchronized["request_id"] == "REQ-UI-SYNC"
    assert synchronized["current_step"] == "CANDIDATE_APPROVED"
    assert synchronized["requires_exception"] is True


def test_bom_query_normalization_preserves_explicit_plant_code():
    assert BomAgentGraph._normalize_bom_query(
        "P02에서 LTA400HR01-0의 BOM을 보여줘"
    ) == "P02에서 LTA400HR01-0의 BOM을 보여줘"


def test_bom_query_normalization_preserves_product_wide_cost_scan_intent():
    query = (
        "LTA550HR01-001 모델의 CF 자재 말고 대상 모델의 BOM 정보를 확인해서 "
        "BOM에 구성된 자재들의 원가를 낮출 수 있는 대체 자재들이 있는지 찾아줘. "
        "PLANT는 P01이야."
    )
    assert BomAgentGraph._normalize_bom_query(query) == query


def test_bom_query_normalization_preserves_design_change_business_intent():
    query = "P01에서 LTA400HR01-001 BOM을 확인해서 단종 자재의 대체 후보를 찾아줘"
    assert BomAgentGraph._normalize_bom_query(query) == query


def test_delete_compound_bom_question_is_not_normalized_to_simple_bom_lookup():
    raw = "LTA650HR11-001 모델 P03 PLANT BOM을 확인해서 0001-310701 자재를 제거하자."
    assert BomAgentGraph._normalize_bom_query(raw) == raw


def test_tool_execution_error_stops_without_llm_retry():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = make_tool_definitions()
    mcp_client.call_tool.side_effect = RuntimeError("deterministic tool failure")

    client.create_agent_completion.return_value = make_assistant_message(
        content=None,
        tool_calls=[
            make_tool_call(
                tool_call_id="call-fail-once",
                name="get_bom",
                arguments='{"product_id": "PRD-001"}',
            )
        ],
    )

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="BOM 조회 규칙",
    )

    result = graph.run("PRD-001의 BOM을 조회해줘")

    assert result == "deterministic tool failure"
    assert "get_bom" not in result
    assert "Tool 실행 오류" not in result
    assert client.create_agent_completion.call_count == 1
    assert mcp_client.call_tool.call_count == 1



def test_failed_candidate_analysis_keeps_error_answer_visible():
    client = Mock()
    mcp_client = Mock()
    mcp_client.get_tool_definitions.return_value = [{
        "type": "function",
        "function": {
            "name": "analyze_design_change_candidates",
            "description": "설계변경 후보 분석",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {"type": "object"},
                    "actions": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["request", "actions"],
            },
        },
    }]
    mcp_client.call_tool.side_effect = RuntimeError(
        "ACTIVE_SOURCE_BOM_RELATION_NOT_FOUND: current BOM relation missing"
    )
    client.create_agent_completion.return_value = make_assistant_message(
        content=None,
        tool_calls=[
            make_tool_call(
                tool_call_id="call-analysis-fail",
                name="analyze_design_change_candidates",
                arguments=(
                    '{"request":{"version_code":"LTA650HR11-001",'
                    '"plant_code":"P03"},'
                    '"actions":[{"action_type":"QUANTITY_CHANGE",'
                    '"old_item_code":"0001-310701","new_quantity":2}]}'
                ),
            )
        ],
    )

    graph = BomAgentGraph(
        client=client,
        mcp_client=mcp_client,
        skill_context="Design Change workflow",
    )

    response = graph.run_with_artifacts(
        "LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재 수량을 2로 바꾸자.",
        thread_id="visible-error",
    )

    assert response["answer"] == "current BOM relation missing"
    assert "analyze_design_change_candidates" not in response["answer"]
    assert "ACTIVE_SOURCE_BOM_RELATION_NOT_FOUND" not in response["answer"]
    assert response["suppress_answer"] is False
    assert response["render_design_change_panel"] is False
    assert mcp_client.call_tool.call_count == 1
    # Macro Dispatch owns this complete request; a failed Analysis
    # stays visible without an unnecessary Azure selection/retry call.
    assert client.create_agent_completion.call_count == 0
