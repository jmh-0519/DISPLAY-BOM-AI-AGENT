from services.recommendation_service import RecommendationService
from services.rule_engine import RuleEngine


def rule(rule_id, weight, required="N", attribute="score", expected="80"):
    return {
        "rule_id": rule_id, "revision_no": 2, "required_yn": required,
        "weight": weight, "conditions": [{
            "attribute_name": attribute, "operator": "GE", "expected_value": expected,
            "missing_result": "CONDITIONAL", "fail_result": "FAIL", "score": 100,
        }],
    }


def test_multiple_rule_weight_and_required_failure():
    engine = RuleEngine()
    result = engine.evaluate_rules(
        {"score": 90, "quality": 60},
        [rule("R1", 0.7), rule("R2", 0.3, "Y", "quality", "70")],
    )
    assert result["status"] == "FAIL"
    assert result["total_score"] == 70.0
    assert result["grade"] == "B"
    assert result["rule_snapshots"][0]["revision_no"] == 2


def test_missing_rule_data_is_conditional():
    result = RuleEngine().evaluate_rules({}, [rule("R1", 1.0)])
    assert result["status"] == "CONDITIONAL"
    assert result["total_score"] == 0


def test_attribute_fallback_is_deterministic():
    engine = RuleEngine()
    passed = engine.evaluate_attributes(
        {"size": "40", "interface": "LVDS"},
        {"size": "40", "interface": "LVDS"},
        ["size", "interface"],
    )
    conditional = engine.evaluate_attributes(
        {"size": "40"}, {"size": "40"}, ["size", "interface"],
    )
    assert passed["status"] == "PASS"
    assert passed["total_score"] == 100.0
    assert passed["grade"] == "S"
    assert passed["missing_data"] == []
    assert [row["attribute"] for row in passed["attribute_results"]] == ["size", "interface"]
    assert all(row["comparison"] == "EQ" for row in passed["attribute_results"])
    assert all(row["matched"] is True for row in passed["attribute_results"])
    assert all(row["status"] == "PASS" for row in passed["attribute_results"])
    assert passed["attribute_results"][0]["source_value"] == "40"
    assert passed["attribute_results"][0]["candidate_value"] == "40"
    assert passed["attribute_results"][0]["reason"]
    assert conditional["status"] == "CONDITIONAL"
    assert conditional["missing_data"] == ["interface"]


class FakeRepository:
    def find_registered_candidates(self, source, date):
        return [{"candidate_item_code": f"C{i}"} for i in range(1, 6)]

    def get_item_attributes(self, code, date):
        return {"fit": "Y" if code != "C5" else "N", "score": 100 - int(code[-1]) if code[0] == "C" else 100}

    def get_active_rules(self, reasons, target_type, date):
        return [{
            "rule_id": "FIT", "revision_no": 1, "required_yn": "Y", "weight": 1,
            "conditions": [{
                "attribute_name": "fit", "operator": "EQ", "expected_value": "Y",
                "missing_result": "CONDITIONAL", "fail_result": "FAIL", "score": 100,
            }],
        }]


def test_recommendation_returns_five_and_excludes_fail_from_rank():
    results = RecommendationService(FakeRepository()).evaluate_candidates(
        source_item_code="OLD", reasons=["EOL"], target_type="MATERIAL",
        as_of_date="2026-08-14", evaluation_items=["fit"],
    )
    assert len(results) == 5
    assert [row["rank"] for row in results[:4]] == [1, 2, 3, 4]
    assert results[-1]["status"] == "FAIL"
    assert results[-1]["rank"] is None
