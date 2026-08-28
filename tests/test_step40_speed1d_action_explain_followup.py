from agents.bom_agent_node import BomAgentNode
from services.design_change_workflow_service import DesignChangeWorkflowService


def test_quantity_change_fail_question_is_analysis_explain_even_without_candidates():
    workflow = {
        "current_step": "ANALYSIS_READY",
        "analysis_id": "ANA-1",
        "request_id": None,
        "candidates": [],
        "actions": [
            {"action_type": "QUANTITY_CHANGE", "evaluation_status": "FAIL"}
        ],
    }

    assert (
        BomAgentNode._classify_analysis_follow_up("왜 fail 이야?", workflow)
        == "EXPLAIN_ANALYSIS"
    )


def test_action_only_analysis_explanation_contains_inventory_reason():
    service = object.__new__(DesignChangeWorkflowService)

    result = service.explain_analysis_session({
        "analysis_id": "ANA-1",
        "candidates": [],
        "actions": [{
            "action_id": "A1",
            "action_type": "QUANTITY_CHANGE",
            "old_item_code": "LJ94-100006",
            "old_quantity": 1.0,
            "new_quantity": 3.0,
            "evaluation_status": "FAIL",
            "inventory_status": "FAIL",
            "inventory": {
                "status": "FAIL",
                "available_quantity": 0.0,
                "shortage_quantity": 3.0,
            },
            "decision_reasons": [
                "재고 평가: FAIL",
                "변경 후 BOM QUANTITY(3.0)를 기준으로 검증했습니다.",
            ],
        }],
    })

    assert "QUANTITY_CHANGE 평가 결과는 FAIL" in result["summary"]
    assert "가용재고는 0.0" in result["summary"]
    assert "부족수량은 3.0" in result["summary"]
    assert result["actions"][0]["status"] == "FAIL"
