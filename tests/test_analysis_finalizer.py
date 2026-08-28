import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.analysis_macro_dispatch import MACRO_ANALYZE_TOOL_CALL_PREFIX
from agents.bom_agent_graph import AGENT, BomAgentGraph
from agents.bom_analysis_finalizer_node import (
    ANALYSIS_FINALIZE,
    BomAnalysisFinalizerNode,
    is_macro_analysis_tool_result,
)
from core.azure_openai_client import AzureOpenAIClient


def _macro_tool_message(candidate_count=12):
    candidates = []
    for index in range(candidate_count):
        candidates.append({
            "candidate_id": f"C-{index}",
            "candidate_item_code": f"0002-{210000 + index:06d}",
            "candidate_item_name": "SEALANT",
            "status": "PASS" if index < 4 else "FAIL",
            "total_score": 90 - index,
            "decision_reasons": ["test evidence"],
            "large_unused_blob": "X" * 2000,
        })

    return ToolMessage(
        content=json.dumps(
            {
                "analysis_id": "ANA-1",
                "request": {
                    "version_code": "LTA400HR01-001",
                    "plant_code": "P01",
                },
                "actions": [{
                    "action_type": "REPLACE",
                    "old_item_code": "0001-200010",
                    "target_item_name": "SEALANT",
                }],
                "status_counts": {
                    "PASS": 4,
                    "CONDITIONAL": 0,
                    "FAIL": candidate_count - 4,
                },
                "candidates": candidates,
            }
        ),
        tool_call_id=f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}test",
        name="analyze_design_change_candidates",
    )


class _FakeFinalizerClient:
    def __init__(self):
        self.calls = []

    def create_analysis_final_answer(self, *, user_message, analysis_evidence):
        self.calls.append({
            "user_message": user_message,
            "analysis_evidence": analysis_evidence,
        })
        return "후보 분석 결과입니다."


def test_macro_analysis_result_routes_to_dedicated_finalizer():
    state = {
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "analyze_design_change_candidates",
                    "args": {},
                    "id": f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}test",
                    "type": "tool_call",
                }],
            ),
            _macro_tool_message(),
        ],
        "error": None,
    }

    assert is_macro_analysis_tool_result(state) is True
    assert BomAgentGraph._route_mcp_tool_result(state) == ANALYSIS_FINALIZE


def test_regular_agent_analysis_result_still_returns_to_agent():
    state = {
        "messages": [
            HumanMessage(content="후보를 다시 분석해줘"),
            ToolMessage(
                content=json.dumps({"analysis_id": "ANA-2", "candidates": []}),
                tool_call_id="normal-agent-tool-call",
                name="analyze_design_change_candidates",
            ),
        ],
        "error": None,
    }

    assert is_macro_analysis_tool_result(state) is False
    assert BomAgentGraph._route_mcp_tool_result(state) == AGENT


def test_finalizer_compacts_analysis_evidence_and_returns_ai_message():
    client = _FakeFinalizerClient()
    node = BomAnalysisFinalizerNode(client=client)
    original_tool = _macro_tool_message()

    result = node({
        "messages": [
            HumanMessage(
                content="LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
            ),
            original_tool,
        ],
    })

    assert result["messages"][0].content == "후보 분석 결과입니다."
    assert len(client.calls) == 1

    compacted = client.calls[0]["analysis_evidence"]
    assert len(compacted) < len(str(original_tool.content))
    payload = json.loads(compacted)
    assert payload["candidate_count"] == 12
    assert len(payload["candidates"]) <= 6

    # The finalizer receives a compact copy only; original Graph evidence is intact.
    original_payload = json.loads(str(original_tool.content))
    assert len(original_payload["candidates"]) == 12


def test_azure_analysis_finalizer_sends_zero_tools_and_zero_skill_context():
    client = object.__new__(AzureOpenAIClient)
    client.settings = SimpleNamespace(azure_openai_deployment="test-deployment")
    captured = {}

    def fake_create_completion(**request):
        captured.update(request)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="분석 결과입니다.")
                )
            ]
        )

    client._create_completion = fake_create_completion

    answer = client.create_analysis_final_answer(
        user_message="SEALANT를 변경하고싶어",
        analysis_evidence='{"candidate_count":5}',
    )

    assert answer == "분석 결과입니다."
    assert "tools" not in captured
    assert len(captured["messages"]) == 2
    assert captured["messages"][0]["role"] == "system"
    assert "Skill" not in captured["messages"][0]["content"]
    assert "Analysis Evidence" in captured["messages"][1]["content"]
