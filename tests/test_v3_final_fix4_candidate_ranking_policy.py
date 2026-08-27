from pathlib import Path

from services.recommendation_service import RecommendationService


class _Repository:
    def get_active_rules(self, reasons, target_type, as_of_date):
        return [{"rule_id": "R1", "conditions": []}]

    def get_item_attributes(self, item_code, as_of_date):
        return {"dummy": item_code}

    def get_item_profile(self, item_code, as_of_date):
        return {"item_name": item_code}


class _RuleEngine:
    def evaluate_rules(self, attributes, rules):
        code = attributes["dummy"]
        if code == "PASS-CAND":
            return {
                "status": "PASS",
                "total_score": 90.0,
                "grade": "A",
                "rule_results": [],
                "rule_snapshots": [],
            }
        return {
            "status": "CONDITIONAL",
            "total_score": 40.0,
            "grade": "C",
            "rule_results": [],
            "rule_snapshots": [],
        }


def test_recommendation_service_ranks_only_pass_candidates():
    service = RecommendationService(_Repository(), _RuleEngine())
    rows = service._evaluate_candidate_rows(
        source_item_code=None,
        candidates=[
            {"candidate_item_code": "COND-CAND"},
            {"candidate_item_code": "PASS-CAND"},
        ],
        reasons=["USER_REQUEST"],
        target_type="MATERIAL",
        as_of_date="2026-08-26",
        evaluation_items=[],
        discovery_mode="ADD_RULE_DISCOVERY",
    )

    by_code = {row["candidate_item_code"]: row for row in rows}
    assert by_code["PASS-CAND"]["rank"] == 1
    assert by_code["COND-CAND"]["rank"] is None


def test_candidate_ui_uses_pending_labels_and_pass_first_selection():
    source = Path("app/views/phase3_agent_view.py").read_text(encoding="utf-8")

    assert '"순위": row.get("rank") if row.get("rank") is not None else "-"' in source
    assert '"추천 점수": row.get("score") if row.get("score") is not None else "평가 보류"' in source
    assert '"추천등급": row.get("grade") or "-"' in source
    assert '"공급사 품질등급": row.get("quality_grade")' in source
    assert 'action_rows = pass_rows if pass_rows else conditional_rows' in source
    assert 'score_label = f"{row[\'score\']}점" if row.get("score") is not None else "평가 보류"' in source
    assert "None점" not in source


def test_candidate_ui_separates_pass_conditional_and_fail_groups():
    source = Path("app/views/phase3_agent_view.py").read_text(encoding="utf-8")

    assert "추천 가능 후보 (PASS)" in source
    assert "평가 보류 후보 (CONDITIONAL)" in source
    assert "검토 제외 후보 (FAIL)" in source
    assert 'cols[1].metric("추천 가능", counts["PASS"])' in source
    assert 'cols[2].metric("평가 보류", counts["CONDITIONAL"])' in source
    assert 'cols[3].metric("검토 제외", counts["FAIL"])' in source
