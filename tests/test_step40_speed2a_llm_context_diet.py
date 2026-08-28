import json
from types import SimpleNamespace
from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_node import BomAgentNode
from agents.llm_context_compactor import LlmContextCompactor


def test_analysis_candidate_payload_is_compacted_but_keeps_decision_fields():
    payload = {
        "analysis_id": "ANA-1",
        "request": {"plant_code": "P01", "version_code": "LTA400HR01-001"},
        "status_counts": {"PASS": 8, "CONDITIONAL": 7, "FAIL": 15},
        "actions": [{"action_id": "A1", "action_type": "REPLACE", "old_item_code": "OLD"}],
        "candidates": [
            {
                "candidate_id": f"C{i}",
                "candidate_item_code": f"0001-{300000+i}",
                "status": "PASS" if i < 8 else "FAIL",
                "total_score": 99 - i,
                "recommended_supplier_item_id": f"SUP-{i}",
                "rule_results": [{"rule": f"R{j}", "evidence": "X" * 300} for j in range(20)],
                "huge_debug": "Y" * 2000,
            }
            for i in range(30)
        ],
        "analysis_context": {"primary_reason_code": "COST", "debug": "Z" * 5000},
    }
    original = json.dumps(payload, ensure_ascii=False)
    messages = [
        HumanMessage(content="원가 낮은 후보를 비교해줘"),
        ToolMessage(
            content=original,
            tool_call_id="call-1",
            name="analyze_design_change_candidates",
        ),
    ]

    compacted, stats = LlmContextCompactor().compact(
        messages,
        current_user_query="원가 낮은 후보를 비교해줘",
    )
    compact_payload = json.loads(compacted[-1].content)

    assert compact_payload["analysis_id"] == "ANA-1"
    assert compact_payload["status_counts"]["PASS"] == 8
    assert compact_payload["candidate_count"] == 30
    assert len(compact_payload["candidates"]) == 6
    assert compact_payload["omitted_candidates"] == 24
    assert "huge_debug" not in compacted[-1].content
    assert stats.saved_tool_chars > 10000


def test_historical_tool_result_becomes_small_envelope():
    payload = {
        "analysis_id": "ANA-OLD",
        "status_counts": {"PASS": 3, "CONDITIONAL": 1, "FAIL": 2},
        "candidates": [{"candidate_item_code": f"C{i}", "evidence": "X" * 1000} for i in range(20)],
    }
    messages = [
        HumanMessage(content="예전 질문"),
        AIMessage(content=""),
        ToolMessage(
            content=json.dumps(payload),
            tool_call_id="old-call",
            name="analyze_design_change_candidates",
        ),
        AIMessage(content="예전 답변"),
        HumanMessage(content="지금 다시 설명해줘"),
    ]

    compacted, _ = LlmContextCompactor().compact(
        messages,
        current_user_query="지금 다시 설명해줘",
    )
    old_payload = json.loads(compacted[2].content)

    assert old_payload["historical"] is True
    assert old_payload["analysis_id"] == "ANA-OLD"
    assert old_payload["candidate_count"] == 20
    assert "candidates" not in old_payload


def test_large_bom_keeps_query_matching_target_rows_for_agent_resolution():
    rows = []
    for i in range(120):
        rows.append({
            "plant_code": "P01",
            "bom_parent": "LJ94-100004",
            "bom_child": f"0001-{200000+i:06d}",
            "bom_child_name": f"PART-{i}",
            "description": "GENERAL",
            "quantity": 1,
        })
    rows[77].update({
        "bom_child": "0001-200010",
        "bom_child_name": "SEALANT",
        "description": "LC SEALANT",
    })
    messages = [
        HumanMessage(content="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"),
        ToolMessage(
            content=json.dumps(rows),
            tool_call_id="bom-call",
            name="get_bom",
        ),
    ]

    compacted, _ = LlmContextCompactor().compact(
        messages,
        current_user_query="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어",
    )
    payload = json.loads(compacted[-1].content)

    assert payload["row_count"] == 120
    assert payload["selection"] == "query_matching_rows"
    assert any(row.get("bom_child") == "0001-200010" for row in payload["rows"])
    assert len(payload["rows"]) < 120


def test_agent_sends_compacted_explain_observation_to_azure_only():
    client = Mock()
    client.create_agent_completion.return_value = SimpleNamespace(
        content="FAIL 근거를 설명합니다.",
        tool_calls=None,
    )
    mcp = Mock()
    mcp.get_tool_definitions.return_value = [
        {"type": "function", "function": {"name": "explain_design_change_analysis_session"}}
    ]
    node = BomAgentNode(client, mcp, "Design Change skill")

    huge_result = {
        "analysis_id": "ANA-1",
        "summary": "재고 부족으로 FAIL입니다.",
        "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 1},
        "actions": [{
            "action_id": "A1",
            "action_type": "QUANTITY_CHANGE",
            "evaluation_status": "FAIL",
            "old_quantity": 1,
            "new_quantity": 5,
            "available_quantity": 0,
            "shortage_quantity": 5,
            "decision_reasons": ["재고 부족"],
            "debug": "X" * 15000,
        }],
        "evidence": [{"raw": "Y" * 4000} for _ in range(10)],
    }
    original_content = json.dumps(huge_result, ensure_ascii=False)
    messages = [
        HumanMessage(content="왜 FAIL이야?"),
        AIMessage(
            content="",
            tool_calls=[{
                "name": "explain_design_change_analysis_session",
                "args": {"analysis_id": "ANA-1"},
                "id": "explain-1",
                "type": "tool_call",
            }],
        ),
        ToolMessage(
            content=original_content,
            tool_call_id="explain-1",
            name="explain_design_change_analysis_session",
        ),
    ]
    workflow = {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "request_id": None,
        "actions": [{"action_id": "A1"}],
        "candidates": [],
        "analysis_memory": {
            "candidate_count": 0,
            "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 1},
        },
    }

    node({
        "messages": messages,
        "user_query": "왜 FAIL이야?",
        "design_change": workflow,
    })

    sent_messages = client.create_agent_completion.call_args.kwargs["messages"]
    sent_tool = next(value for value in sent_messages if value["role"] == "tool")
    assert len(sent_tool["content"]) < len(original_content) / 3
    assert "재고 부족으로 FAIL" in sent_tool["content"]
    # Original state message is never mutated.
    assert messages[-1].content == original_content
