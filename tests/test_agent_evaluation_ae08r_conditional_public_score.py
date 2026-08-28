from types import SimpleNamespace

from services.phase3_workflow_service import Phase3WorkflowService


class _RuleEngine:
    @staticmethod
    def grade(score: float) -> str:
        if score >= 90:
            return "S"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        return "C"


def _service_without_db() -> Phase3WorkflowService:
    service = object.__new__(Phase3WorkflowService)
    service.recommendation = SimpleNamespace(rule_engine=_RuleEngine())
    return service


def test_conditional_public_projection_hides_numeric_recommendation_fields():
    row = {
        "status": "CONDITIONAL",
        "total_score": 0.0,
        "grade": "C",
        "rank": 2,
        "ranking_score": 61.0,
        "ranking_grade": "C",
        "rule_score": 0.0,
    }

    Phase3WorkflowService._apply_public_candidate_score_policy(row)

    assert row["total_score"] is None
    assert row["grade"] == "평가 보류"
    assert row["rank"] is None
    assert row["ranking_score"] is None
    assert row["ranking_grade"] is None
    assert row["rule_score"] == 0.0


def test_fail_public_projection_hides_score_grade_and_rank():
    row = {
        "status": "FAIL",
        "total_score": 72.0,
        "grade": "B",
        "rank": 3,
        "ranking_score": 72.0,
        "ranking_grade": "B",
        "rule_score": 72.0,
    }

    Phase3WorkflowService._apply_public_candidate_score_policy(row)

    assert row["total_score"] is None
    assert row["grade"] is None
    assert row["rank"] is None
    assert row["ranking_score"] is None
    assert row["ranking_grade"] is None
    assert row["rule_score"] == 72.0


def test_pass_public_projection_preserves_recommendation_fields():
    row = {
        "status": "PASS",
        "total_score": 91.5,
        "grade": "S",
        "rank": 1,
        "ranking_score": 91.5,
        "ranking_grade": "S",
        "rule_score": 88.0,
    }
    before = dict(row)

    Phase3WorkflowService._apply_public_candidate_score_policy(row)

    assert row == before


def test_persistence_projection_restores_legacy_numeric_fields_from_rule_score():
    service = _service_without_db()
    public_row = {
        "status": "CONDITIONAL",
        "total_score": None,
        "grade": "평가 보류",
        "rank": None,
        "rule_score": 0.0,
    }

    persisted = service._candidate_for_persistence(public_row)

    assert persisted["total_score"] == 0.0
    assert persisted["grade"] == "C"
    # The public object must remain untouched.
    assert public_row["total_score"] is None
    assert public_row["grade"] == "평가 보류"


def test_final_conditional_status_never_gets_ranking_even_if_technical_passes():
    service = _service_without_db()
    row = {
        "status": "CONDITIONAL",
        "technical_status": "PASS",
        "rule_score": 90.0,
        "total_score": 90.0,
        "grade": "S",
    }
    supplier = {
        "status": "CONDITIONAL",
        "recommended": {"score": 100.0},
    }
    inventory = {"status": "PASS"}

    service._apply_candidate_ranking_score(row, supplier, inventory)

    assert row["ranking_score"] is None
    assert row["ranking_grade"] is None
    # Legacy internal values are deliberately retained until public projection.
    assert row["total_score"] == 90.0
    assert row["grade"] == "S"
