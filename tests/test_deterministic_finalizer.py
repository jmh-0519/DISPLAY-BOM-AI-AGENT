import json

from langchain_core.messages import HumanMessage, ToolMessage

from agents.analysis_macro_dispatch import MACRO_ANALYZE_TOOL_CALL_PREFIX
from agents.bom_analysis_finalizer_node import BomAnalysisFinalizerNode


class _Client:
    def __init__(self):
        self.calls = []

    def create_analysis_final_answer(self, *, user_message, analysis_evidence):
        self.calls.append((user_message, analysis_evidence))
        return "LLM fallback"


def _message(payload):
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}macro-finalizer",
        name="analyze_design_change_candidates",
    )


def test_deterministic_macro_finalizer_skips_llm_and_uses_verified_evidence():
    client = _Client()
    node = BomAnalysisFinalizerNode(client=client, deterministic=True)
    payload = {
        "request": {"version_code": "MODEL-001", "plant_code": "P01"},
        "actions": [{"action_type": "REPLACE", "old_item_code": "OLD-001"}],
        "status_counts": {"PASS": 1, "CONDITIONAL": 1, "FAIL": 1},
        "candidates": [
            {
                "candidate_item_code": "NEW-001",
                "candidate_name": "Candidate A",
                "status": "PASS",
                "total_score": 95.5,
                "decision_reasons": ["검증된 근거"],
            },
            {
                "candidate_item_code": "NEW-002",
                "status": "CONDITIONAL",
                "total_score": None,
                "grade": "평가 보류",
            },
            {"candidate_item_code": "NEW-003", "status": "FAIL"},
        ],
        "analysis_status": "PASS",
        "request_created": False,
        "production_bom_modified": False,
    }

    result = node({
        "messages": [HumanMessage(content="후보를 분석해줘"), _message(payload)],
    })

    answer = result["messages"][0].content
    assert client.calls == []
    assert "MODEL-001 / P01" in answer
    assert "NEW-001" in answer
    assert "점수 95.5" in answer
    assert "NEW-002" in answer
    assert "추천 점수 평가 보류" in answer
    assert "Request 생성이나 Production E-BOM 변경은 수행되지 않았습니다" in answer


def test_deterministic_macro_finalizer_falls_back_to_llm_for_unexpected_payload():
    client = _Client()
    node = BomAnalysisFinalizerNode(client=client, deterministic=True)
    message = ToolMessage(
        content="not-json",
        tool_call_id=f"{MACRO_ANALYZE_TOOL_CALL_PREFIX}fallback",
        name="analyze_design_change_candidates",
    )

    result = node({
        "messages": [HumanMessage(content="후보를 분석해줘"), message],
    })

    assert result["messages"][0].content == "LLM fallback"
    assert len(client.calls) == 1
