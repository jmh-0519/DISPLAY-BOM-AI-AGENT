from app.views.design_change_workflow_view import (
    _candidate_decision_summary,
    _candidate_display_frame,
    _reason_evidence_summary,
    _required_candidate_actions,
    _selection_review_frame,
    available_action,
    candidate_missing_attributes,
    candidate_rows,
    impact_model_rows,
    impact_rows,
    impact_spec_rows,
    preview_model_rows,
    is_workflow_visible,
)


def test_candidate_renderer_exposes_business_comparison_fields_without_internal_json():
    workflow = {
        "candidates": [{
            "action_id": "A1",
            "candidate_id": "C1",
            "candidate_item_code": "MAT-C1",
            "candidate_name": "Candidate",
            "candidate_description": "Candidate description",
            "status": "PASS",
            "technical_status": "PASS",
            "supplier_status": "PASS",
            "inventory_status": "PASS",
            "total_score": 91,
            "grade": "S",
            "rank": 1,
            "evaluation_mode": "ATTRIBUTE",
            "decision_reasons": ["기술/공급/재고 평가 조건 충족"],
            "supplier_evaluation": {"recommended": {
                "supplier_item_id": 10,
                "supplier_code": "SUP-1",
                "supplier_name": "Supplier 1",
                "lead_time_days": 5,
                "quality_grade": "A",
            }},
            "inventory": {"available_quantity": 10, "demand_quantity": 3},
        }],
    }
    row = candidate_rows(workflow)[0]
    assert row["candidate_description"] == "Candidate description"
    assert row["supplier_code"] == "SUP-1"
    assert row["technical_status"] == "PASS"
    assert "supplier_weights" not in row


def test_pre_workflow_analysis_and_real_workflow_are_separated():
    assert available_action({"current_step": "WAITING_CANDIDATE_APPROVAL"}) == "CANDIDATE_SELECTION"
    assert available_action({"current_step": "CONDITIONAL_REVIEW_REQUIRED"}) == "CONDITIONAL_REVIEW"
    assert available_action({"current_step": "IMPACT_REVIEW_REQUIRED"}) == "IMPACT_APPROVAL"
    assert is_workflow_visible({"current_step": "WAITING_CANDIDATE_APPROVAL"}) is False
    assert is_workflow_visible({"current_step": "CONDITIONAL_REVIEW_REQUIRED"}) is False
    assert is_workflow_visible({"current_step": "IMPACT_REVIEW_REQUIRED"}) is False
    assert is_workflow_visible({"current_step": "CANDIDATE_APPROVED"}) is True
    assert available_action({"current_step": "CANDIDATE_APPROVED"}) == "CREATE_PREVIEW"
    assert available_action({"current_step": "WAITING_FINAL_APPROVAL"}) == "FINAL_APPROVAL"
    assert available_action({"current_step": "FINAL_APPROVED"}) == "APPLY"
    assert available_action({"current_step": "BLOCKED"}) is None


def test_conditional_candidate_stays_in_pre_workflow_review_until_exception_gate():
    assert available_action({
        "current_step": "CONDITIONAL_REVIEW_REQUIRED",
        "requires_exception": True,
    }) == "CONDITIONAL_REVIEW"


def test_only_missing_rule_attributes_are_exposed_for_revalidation():
    candidate = {
        "missing_data": ["demand_quantity", "operating_voltage"],
        "rule_results": [{
            "evidence": {"conditions": [
                {"attribute": "material_family", "present": True, "status": "PASS"},
                {"attribute": "operating_voltage", "present": False,
                 "status": "CONDITIONAL"},
            ]},
        }],
    }
    assert candidate_missing_attributes(candidate) == ["operating_voltage"]
    assert candidate_missing_attributes({"missing_data": ["demand_quantity"]}) == []


def test_shared_impact_rows_show_models_and_before_after_specs():
    workflow = {
        "plant_code": "P01",
        "impact_review": {
            "impacted_models": [{
                "plant_code": "P01",
                "model_code": "MODEL-A",
                "model_name": "Model A",
                "model_description": "Description",
                "parent_item_code": "ASSY-A",
                "parent_name": "OLB",
                "impact_path": "MODEL-A/ASSY-A",
            }],
            "actions": [{
                "old_item_code": "OLD",
                "new_item_code": "NEW",
                "spec_changes": [
                    {"attribute": "voltage", "before": "3.3", "after": "5.0", "change_status": "CHANGED"},
                    {"attribute": "interface", "before": "LVDS", "after": "LVDS", "change_status": "SAME"},
                ],
            }],
        },
        "impacts": [{
            "impacted_item_code": "MODEL-A", "impact_type": "MODEL",
            "impact_path": "MODEL-A/ASSY-A",
        }],
    }
    assert impact_model_rows(workflow)[0]["영향 모델"] == "MODEL-A"
    assert len(impact_spec_rows(workflow, changed_only=True)) == 1
    assert len(impact_spec_rows(workflow, changed_only=False)) == 2
    assert impact_rows(workflow)[0]["item_code"] == "MODEL-A"


def test_candidate_table_places_decision_summary_and_multi_reason_before_technical_detail():
    workflow = {
        "analysis_context": {"reason_codes": ["EOL", "COST"]},
        "candidates": [{
            "action_id": "A1",
            "candidate_id": "C1",
            "candidate_item_code": "MAT-C1",
            "candidate_name": "SEALANT",
            "candidate_description": "LC/SEALANT",
            "status": "CONDITIONAL",
            "technical_status": "PASS",
            "supplier_status": "CONDITIONAL",
            "inventory_status": "CONDITIONAL",
            "total_score": 65,
            "grade": "C",
            "rank": 1,
            "decision_reasons": ["공급사 평가: CONDITIONAL", "재고 평가: CONDITIONAL"],
            "supplier_evaluation": {"recommended": None},
            "inventory": {"status": "CONDITIONAL", "demand_source": "UNAVAILABLE"},
            "missing_data": ["supplier_options", "demand_quantity"],
        }],
    }
    rows = candidate_rows(workflow)
    frame = _candidate_display_frame(rows)
    columns = list(frame.columns)
    assert columns.index("종합 적합성") < columns.index("종합 판단 요약")
    assert columns.index("종합 판단 요약") < columns.index("평가 사유")
    assert columns.index("평가 사유") < columns.index("기술 평가")
    assert frame.iloc[0]["평가 사유"] == "EOL · COST"
    assert "공급사/원가 데이터" in frame.iloc[0]["종합 판단 요약"]
    assert "재고 데이터" in frame.iloc[0]["종합 판단 요약"]
    assert "수요 데이터" not in frame.iloc[0]["종합 판단 요약"]


def test_reason_evidence_does_not_treat_user_eol_as_database_fact():
    summary = _reason_evidence_summary(
        {"reason_codes": ["EOL", "COST"]},
        {"active_yn": "Y", "status_fields": {}},
    )
    assert "사용자 입력" in summary
    assert "lifecycle_status 미등록" in summary
    assert "후보별 공급사·단가 데이터" in summary


def test_candidate_confirmation_preview_uses_required_actions_and_business_fields():
    workflow = {
        "analysis_context": {
            "target_item": {"item_code": "OLD", "description": "OLD/SPEC"},
        },
        "actions": [
            {"action_id": "A1", "action_type": "REPLACE", "old_item_code": "OLD"},
            {"action_id": "A2", "action_type": "DELETE", "old_item_code": "DEL"},
        ],
    }
    assert [row["action_id"] for row in _required_candidate_actions(workflow)] == ["A1"]
    frame = _selection_review_frame(workflow, [{
        "candidate_item_code": "NEW",
        "candidate_description": "NEW/SPEC",
        "status": "CONDITIONAL",
        "evaluation_reasons": "EOL · COST",
        "technical_status": "PASS",
        "score": 65,
        "grade": "C",
        "supplier_status": "CONDITIONAL",
        "inventory_status": "CONDITIONAL",
    }])
    assert frame.iloc[0]["변경 대상"] == "OLD"
    assert frame.iloc[0]["선택 후보"] == "NEW"
    assert frame.iloc[0]["평가 사유"] == "EOL · COST"
    assert frame.iloc[0]["종합 적합성"] == "CONDITIONAL"


def test_preview_model_rows_hides_parent_assy_hierarchy_and_keeps_top_model_only():
    workflow = {
        "plant_code": "P03",
        "version_code": "MODEL-1",
        "impacts": [
            {"plant_code": "P03", "impacted_item_code": "BIN-1", "impact_type": "TARGET", "impact_path": "BIN-1"},
            {"plant_code": "P03", "impacted_item_code": "CP-1", "impact_type": "PARENT_ASSY", "impact_path": "MODEL-1/CP-1/BIN-1"},
            {"plant_code": "P03", "impacted_item_code": "MODEL-1", "impact_type": "MODEL", "impact_path": "MODEL-1/CP-1/BIN-1"},
        ],
    }
    rows = preview_model_rows(workflow)
    assert rows == [{
        "PLANT": "P03",
        "최상위 MODEL": "MODEL-1",
        "MODEL 정보": "-",
        "상태": "-",
    }]


def test_preview_model_rows_falls_back_to_request_version_for_direct_model_parent_add():
    workflow = {
        "plant_code": "P03",
        "version_code": "MODEL-ADD",
        "impacts": [
            {"plant_code": "P03", "impacted_item_code": "MODEL-ADD", "impact_type": "TARGET", "impact_path": "MODEL-ADD"},
        ],
    }
    rows = preview_model_rows(workflow)
    assert rows[0]["최상위 MODEL"] == "MODEL-ADD"
