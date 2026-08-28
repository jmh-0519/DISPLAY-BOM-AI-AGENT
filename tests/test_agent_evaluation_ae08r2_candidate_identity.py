from services.design_change_workflow_service import DesignChangeWorkflowService


def test_public_score_policy_keeps_identity_fields():
    row = {
        "candidate_id": "CAN-1",
        "action_id": "ACT-1",
        "candidate_item_code": "0001-TEST",
        "status": "CONDITIONAL",
        "total_score": 0.0,
        "grade": "C",
        "ranking_score": None,
        "ranking_grade": None,
        "rank": None,
        "rule_score": 0.0,
    }

    DesignChangeWorkflowService._apply_public_candidate_score_policy(row)

    assert row["candidate_id"] == "CAN-1"
    assert row["action_id"] == "ACT-1"
    assert row["total_score"] is None
    assert row["grade"] == "평가 보류"
    assert row["rank"] is None


def test_public_score_policy_does_not_remove_pass_identity_or_score():
    row = {
        "candidate_id": "CAN-2",
        "action_id": "ACT-2",
        "candidate_item_code": "0001-PASS",
        "status": "PASS",
        "total_score": 91.5,
        "grade": "S",
        "ranking_score": 91.5,
        "ranking_grade": "S",
        "rank": 1,
    }

    DesignChangeWorkflowService._apply_public_candidate_score_policy(row)

    assert row["candidate_id"] == "CAN-2"
    assert row["action_id"] == "ACT-2"
    assert row["total_score"] == 91.5
    assert row["grade"] == "S"
    assert row["rank"] == 1
