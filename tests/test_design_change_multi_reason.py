from __future__ import annotations

from unittest.mock import Mock

from database import SchemaManager, SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.change_reason_resolver import ChangeReasonResolver
from services.design_change_workflow_service import DesignChangeWorkflowService
from services.supply_evaluation_service import SupplyEvaluationService


def make_database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "multi-reason.db")
    SchemaManager(database).initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO item_master(item_code,item_type,item_name) VALUES('MODEL-1','VERSION','FA')"
        )
        connection.execute("INSERT INTO version_master(version_code) VALUES('MODEL-1')")
        for code, name in (("MAT-1", "SOURCE"), ("MAT-2", "CANDIDATE")):
            connection.execute(
                "INSERT INTO item_master(item_code,item_type,item_name) VALUES(?, 'MATERIAL', ?)",
                (code, name),
            )
            connection.execute(
                "INSERT INTO material_master(material_code,material_name) VALUES(?, ?)",
                (code, name),
            )
        connection.execute(
            """INSERT INTO bom_master(
                 plant_code,parent_item_code,child_item_code,location_code,
                 sequence_no,quantity,valid_from,status)
               VALUES('P01','MODEL-1','MAT-1','N/A',1,1,'2026-01-01','ACTIVE')"""
        )
    return database


def test_resolver_preserves_primary_and_secondary_reasons_in_natural_language_order(tmp_path):
    repository = SQLiteDesignChangeRepository(make_database(tmp_path))
    resolved = ChangeReasonResolver(repository).resolve_all(
        proposed_reasons=[],
        original_request="MAT-1이 단종됐고 원가도 너무 높아서 변경하고 싶어",
        target_type="MATERIAL",
        action_type="REPLACE",
    )

    assert [row.reason_code for row in resolved] == ["EOL", "COST"]
    assert [row.is_primary for row in resolved] == ["Y", "N"]
    assert resolved[0].evidence["all_detected_reason_codes"] == ["EOL", "COST"]


def test_analysis_preserves_all_reasons_and_primary_secondary_roles(tmp_path):
    service = DesignChangeWorkflowService(make_database(tmp_path))
    analysis = service.analyze_candidates(
        {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "MAT-1이 단종됐고 원가도 너무 높아서 변경하고 싶어",
            "reasons": [],
            "as_of_date": "2026-08-18",
            "effective_date": "2026-08-18",
            "requested_by": "tester",
        },
        [{
            "action_type": "REPLACE",
            "old_item_code": "MAT-1",
        }],
    )

    assert analysis["request"]["reasons"] == ["EOL", "COST"]
    action = analysis["actions"][0]
    assert action["primary_reason"]["reason_code"] == "EOL"
    assert [row["reason_code"] for row in action["secondary_reasons"]] == ["COST"]
    assert [row["reason_code"] for row in action["reasons"]] == ["EOL", "COST"]
    assert analysis["request_created"] is False


def test_candidate_analysis_uses_all_resolved_reason_codes(tmp_path):
    service = DesignChangeWorkflowService(make_database(tmp_path))
    service.recommendation.evaluate_candidates = Mock(return_value=[{
        "candidate_item_code": "MAT-2",
        "status": "PASS",
        "total_score": 80.0,
        "grade": "A",
        "missing_data": [],
        "conditional_reasons": [],
        "attribute_results": [],
        "rule_results": [],
        "rule_snapshots": [],
        "evaluation_mode": "RULE",
    }])
    service.supply.resolve_demand = Mock(return_value={
        "quantity": None,
        "source": "UNAVAILABLE",
        "production_plan_quantity": None,
    })
    service.supply.recommend_supplier = Mock(return_value={
        "status": "CONDITIONAL",
        "recommended": None,
        "options": [],
        "missing_data": ["supplier_options"],
        "weights": {},
        "reason_codes": ["COST", "EOL"],
        "decision_reason": "no supplier",
    })
    service.supply.evaluate_inventory = Mock(return_value={
        "status": "CONDITIONAL",
        "available_quantity": 0.0,
        "demand_quantity": None,
        "missing_data": ["demand_quantity"],
    })

    result = service.analyze_candidates(
        {
            "plant_code": "P01",
            "version_code": "MODEL-1",
            "original_request": "MAT-1이 단종됐고 원가도 높아서 변경하고 싶어",
            "reasons": [],
            "as_of_date": "2026-08-18",
            "effective_date": "2026-08-18",
            "requested_by": "tester",
        },
        [{"action_type": "REPLACE", "old_item_code": "MAT-1"}],
    )

    assert result["analysis_context"]["reason_codes"] == ["EOL", "COST"]
    assert result["analysis_context"]["primary_reason_code"] == "EOL"
    assert result["analysis_context"]["secondary_reason_codes"] == ["COST"]
    assert service.recommendation.evaluate_candidates.call_args.kwargs["reasons"] == ["EOL", "COST"]
    assert service.supply.recommend_supplier.call_args.args[2] == ["EOL", "COST"]

def test_supplier_weights_blend_multiple_reason_profiles():
    weights, applied = SupplyEvaluationService._weights_for_reasons({"COST", "QUALITY"})

    assert applied == ["COST", "QUALITY"]
    assert weights == {
        "quality": 0.35,
        "lead": 0.10,
        "stability": 0.25,
        "cost": 0.30,
    }
    assert round(sum(weights.values()), 6) == 1.0


def test_explicit_action_reason_becomes_primary_but_other_detected_reason_is_preserved(tmp_path):
    repository = SQLiteDesignChangeRepository(make_database(tmp_path))
    resolved = ChangeReasonResolver(repository).resolve_all(
        proposed_reasons=[],
        original_request="MAT-1이 단종됐고 원가도 높아서 변경하고 싶어",
        target_type="MATERIAL",
        action_type="REPLACE",
        explicit_action_reason="COST",
    )

    assert [row.reason_code for row in resolved] == ["COST", "EOL"]
    assert [row.is_primary for row in resolved] == ["Y", "N"]
