from __future__ import annotations

import shutil
from datetime import date
from scripts.database_lifecycle import DEFAULT_TEST_DATABASE
from database import SchemaManager, SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.design_change_workflow_service import DesignChangeWorkflowService
from services.rule_engine import RuleEngine


def make_database(tmp_path) -> SQLiteDatabase:
    target = tmp_path / "design-change-explainability.db"
    shutil.copyfile(DEFAULT_TEST_DATABASE, target)
    database = SQLiteDatabase(target)
    SchemaManager(database).initialize()
    return database


def find_dynamic_material_case(database: SQLiteDatabase) -> dict:
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT b.plant_code,b.child_item_code
            FROM bom_master b
            JOIN item_master i ON i.item_code=b.child_item_code
            JOIN material_master m ON m.material_code=b.child_item_code
            WHERE i.item_type='MATERIAL' AND i.active_yn='Y'               AND b.status='ACTIVE'
              AND NOT EXISTS (
                SELECT 1 FROM substitution_relations r
                WHERE r.source_item_code=b.child_item_code AND r.active_yn='Y'
              )
              AND EXISTS (
                SELECT 1 FROM material_master m2
                JOIN item_master i2 ON i2.item_code=m2.material_code
                WHERE m2.material_code<>m.material_code
                  AND m2.material_name=m.material_name
                  AND COALESCE(m2.material_group,'')=COALESCE(m.material_group,'')
                  AND COALESCE(m2.specification,'')=COALESCE(m.specification,'')
                  AND i2.active_yn='Y'
              )
            ORDER BY b.plant_code,b.child_item_code
            """
        ).fetchall()
    for row in rows:
        ancestors = repository.get_recursive_ancestors(
            row["child_item_code"], row["plant_code"], today
        )
        for ancestor in ancestors:
            if ancestor["item_type"] != "VERSION":
                continue
            relations = repository.find_version_source_relations(
                version_code=ancestor["item_code"],
                child_item_code=row["child_item_code"],
                plant_code=row["plant_code"],
                as_of_date=today,
            )
            if len(relations) == 1:
                return {
                    "plant_code": row["plant_code"],
                    "version_code": ancestor["item_code"],
                    "source_item_code": row["child_item_code"],
                }
    raise AssertionError("No dynamic explainability material case was found")


def create_committed_analysis(database: SQLiteDatabase) -> tuple[DesignChangeWorkflowService, dict, dict]:
    case = find_dynamic_material_case(database)
    service = DesignChangeWorkflowService(database)
    analysis = service.analyze_candidates(
        {
            "plant_code": case["plant_code"],
            "version_code": case["version_code"],
            "original_request": "단종됐어. 변경 가능한 자재를 찾아줘.",
            "requested_by": "pytest",
        },
        [{"action_type": "REPLACE", "old_item_code": case["source_item_code"]}],
    )
    candidate = next(
        (row for row in analysis["candidates"] if row["status"] in {"PASS", "CONDITIONAL"}),
        None,
    )
    assert candidate is not None
    selections = [{
        "action_id": analysis["actions"][0]["action_id"],
        "candidate_item_code": candidate["candidate_item_code"],
        "supplier_item_id": candidate.get("recommended_supplier_item_id"),
    }]
    impact = service.preview_analysis_impact(analysis, selections)
    committed = service.commit_analysis_as_request(
        analysis,
        selections,
        approved_by="pytest",
        exception_reason=(
            "pytest conditional evidence acceptance"
            if candidate["status"] == "CONDITIONAL" else None
        ),
        impact_confirmed=bool(impact.get("requires_impact_approval")),
    )
    return service, committed, analysis

def test_attribute_evidence_keeps_before_and_candidate_values():
    result = RuleEngine().evaluate_attributes(
        {"resolution": "FHD", "refresh_rate": "60HZ"},
        {"resolution": "UHD", "refresh_rate": "60HZ"},
        ["resolution", "refresh_rate"],
    )
    failed = next(row for row in result["attribute_results"] if row["attribute"] == "resolution")
    assert failed["source_value"] == "FHD"
    assert failed["candidate_value"] == "UHD"
    assert failed["matched"] is False
    assert failed["status"] == "FAIL"


def test_rule_evidence_keeps_actual_expected_and_operator():
    rule = {
        "rule_id": "R1",
        "revision_no": 1,
        "required_yn": "Y",
        "weight": 1.0,
        "conditions": [{
            "attribute_name": "voltage",
            "operator": "LE",
            "expected_value": "3.3",
            "missing_result": "CONDITIONAL",
            "fail_result": "FAIL",
            "score": 100,
        }],
    }
    result = RuleEngine().evaluate_rules({"voltage": 5.0}, [rule])
    evidence = result["rule_results"][0]["evidence"]["conditions"][0]
    assert evidence["actual_value"] == 5.0
    assert evidence["expected_value"] == "3.3"
    assert evidence["operator"] == "LE"
    assert evidence["status"] == "FAIL"


def test_analysis_explanation_distinguishes_no_eligible_from_no_candidates(tmp_path):
    database = make_database(tmp_path)
    service, created, evaluated = create_committed_analysis(database)
    analysis = service.get_analysis_explanation(created["request_id"])

    assert analysis["candidate_count"] == len(evaluated["candidates"])
    assert sum(analysis["status_counts"].values()) == analysis["candidate_count"]
    if analysis["status_counts"]["PASS"] + analysis["status_counts"]["CONDITIONAL"] == 0:
        assert analysis["candidate_search_status"] == "NO_ELIGIBLE_CANDIDATES"
        assert "후보는" in analysis["summary"]
        assert "0개" in analysis["summary"]
    else:
        assert analysis["candidate_search_status"] == "ELIGIBLE_CANDIDATES"
    assert analysis["production_bom_modified"] is False


def test_candidate_detail_exposes_technical_and_inventory_evidence(tmp_path):
    database = make_database(tmp_path)
    service, created, evaluated = create_committed_analysis(database)
    candidate = evaluated["candidates"][0]
    detail = service.get_candidate_evaluation_detail(
        created["request_id"], candidate["candidate_item_code"], created["actions"][0]["action_id"]
    )

    assert detail["candidate_item"]["item_code"] == candidate["candidate_item_code"]
    assert "technical_evaluation" in detail
    assert "inventory_evaluation" in detail
    assert isinstance(detail["technical_evaluation"]["checks"], list)
    assert detail["production_bom_modified"] is False



def test_candidate_detail_persists_evidence_supply_and_inventory_evidence(tmp_path):
    database = make_database(tmp_path)
    service, created, evaluated = create_committed_analysis(database)
    candidate = evaluated["candidates"][0]
    detail = service.get_candidate_evaluation_detail(
        created["request_id"], candidate["candidate_item_code"], created["actions"][0]["action_id"]
    )

    inventory = detail["inventory_evaluation"]
    assert "calculation" in inventory
    assert "location_breakdown" in inventory
    assert "demand_source" in inventory
    assert "missing_requirements" in detail
    supplier = detail["supplier_evaluation"]
    assert "weights" in supplier
    assert "component_scores" in supplier
    assert "decision_reason" in supplier


def test_candidate_comparison_includes_before_after_technical_differences(tmp_path):
    database = make_database(tmp_path)
    service, created, evaluated = create_committed_analysis(database)
    compared = service.compare_candidates(
        created["request_id"],
        candidate_item_codes=[row["candidate_item_code"] for row in evaluated["candidates"][:3]],
        action_id=created["actions"][0]["action_id"],
        criterion="SPEC_SIMILARITY",
    )

    assert compared["candidates"]
    first = compared["candidates"][0]
    assert "technical_differences" in first
    assert "failed_attributes" in first
    assert "conditional_attributes" in first
    for difference in first["technical_differences"]:
        assert {"attribute", "before", "candidate", "status", "evaluation_mode"} <= set(difference)
