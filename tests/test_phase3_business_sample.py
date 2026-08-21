from __future__ import annotations

import shutil

from database import SchemaManager, SQLiteDatabase
from scripts.seed_phase3_business_sample import seed_phase3_business_sample
from scripts.verify_phase3_business_sample import CANDIDATE_FILTER, verify
from repositories.sqlite_repository import SQLiteBomRepository
from services.repository_bom_service import RepositoryBomService
from services.phase3_workflow_service import Phase3WorkflowService


def make_database(tmp_path) -> SQLiteDatabase:
    target = tmp_path / "phase3-business.db"
    shutil.copyfile("data/test_display_bom.db", target)
    database = SQLiteDatabase(target)
    SchemaManager(database).initialize()
    seed_phase3_business_sample(database)
    return database


def complete_candidate_selection(service, request_id: str, selections: list[dict]) -> dict:
    result = service.prepare_candidate_selection(request_id, selections, "tester")
    if result.get("workflow_status") == "IMPACT_REVIEW_REQUIRED":
        result = service.approve_candidate_impact(request_id, "tester")
    return result


def test_business_seed_preserves_baseline_and_is_idempotent(tmp_path):
    database = make_database(tmp_path)
    seed_phase3_business_sample(database)
    result = verify(database.database_path)
    assert result["business_versions"] == 11
    assert result["business_candidates"] == 50
    assert result["supplier_items"] == 150




def test_baseline_product_is_queryable_in_p01_and_p02(tmp_path):
    database = make_database(tmp_path)
    service = RepositoryBomService(SQLiteBomRepository(database))

    p01 = service.get_bom_explosion("P01", "LTA400HR01-001", "2026-08-18")
    p02 = service.get_bom_explosion("P02", "LTA400HR01-001", "2026-08-18")

    assert len(p01) == 20
    assert len(p02) == 20
    assert set(p01["plant_code"]) == {"P01"}
    assert set(p02["plant_code"]) == {"P02"}
    assert p01[["bom_parent", "bom_child", "location", "quantity"]].to_dict("records") == (
        p02[["bom_parent", "bom_child", "location", "quantity"]].to_dict("records")
    )


def test_latest_seed_preserves_pre_step27_workflow_history(tmp_path):
    database = make_database(tmp_path)
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM design_changes").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM design_change_items").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM review_boms").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM bom_reviews").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM workflow_events").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM item_master WHERE item_code LIKE 'P3-%'"
        ).fetchone()[0] == 0


def test_eol_material_replace_runs_through_two_approvals(tmp_path):
    database = make_database(tmp_path)
    service = Phase3WorkflowService(database)
    service.create_request(
        {
            "request_id": "REQ-BIZ-EOL",
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "original_request": "DRIVE-IC 단종으로 대체자재 추천",
            "normalized_request": "EOL REPLACE",
            "reasons": ["EOL"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "demand_quantity": None,
            "demand_source": "BOM_QUANTITY",
            "requested_by": "tester",
        },
        [
            {
                "action_id": "ACT-BIZ-EOL",
                "action_type": "REPLACE",
                "target_type": "MATERIAL",
                "parent_item_code": "LJ94-310101",
                "old_item_code": "0001-310101",
                "old_quantity": 1,
                "location_code": "N/A",
            }
        ],
    )
    # LLM-derived values must not override the validated request context.
    evaluated = service.evaluate_action(
        "ACT-BIZ-EOL",
        ["UNRELATED_REASON"],
        "2026-09-01",
        ["rule", "supplier", "lead_time", "stock", "score"],
    )
    assert [row["status"] for row in evaluated["candidates"]] == [
        "PASS", "PASS", "PASS", "CONDITIONAL", "FAIL",
    ]
    selected = evaluated["candidates"][0]
    assert selected["candidate_item_code"] == "0001-310111"
    assert selected["total_score"] == 98.53
    assert selected["demand"]["quantity"] == 1.0
    assert selected["demand"]["source"] == "BOM_QUANTITY"
    assert selected["demand"]["production_plan_quantity"] is None
    assert selected["demand"]["plant_code"] == "P01"
    assert evaluated["evaluation_context"] == {
        "reasons": ["EOL"],
        "as_of_date": "2026-08-15",
        "demand_source": "BOM_QUANTITY",
        "plant_code": "P01",
    }

    complete_candidate_selection(
        service,
        "REQ-BIZ-EOL",
        [{
            "action_id": "ACT-BIZ-EOL",
            "candidate_id": selected["candidate_id"],
            "supplier_item_id": selected["recommended_supplier_item_id"],
        }],
    )
    preview = service.create_preview("REQ-BIZ-EOL", "tester")
    assert preview["validation_status"] == "PASS"
    final = service.approve_final("REQ-BIZ-EOL", "tester")
    applied = service.apply("REQ-BIZ-EOL", final["approval_id"], "tester")
    assert applied["result"] == "APPLIED"


def test_business_request_normalizes_eol_reason_alias(tmp_path):
    database = make_database(tmp_path)
    service = Phase3WorkflowService(database)
    created = service.create_request(
        {
            "request_id": "REQ-BIZ-EOL-ALIAS",
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "reasons": ["단종"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "demand_source": "BOM_QUANTITY",
            "requested_by": "tester",
        },
        [{
            "action_id": "ACT-BIZ-EOL-ALIAS",
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "LJ94-310101",
            "old_item_code": "0001-310101",
            "location_code": "N/A",
        }],
    )
    assert created["request_id"] == "REQ-BIZ-EOL-ALIAS"
    assert service.get_result("REQ-BIZ-EOL-ALIAS")["reasons"] == ["EOL"]
    assert service.evaluate_action("ACT-BIZ-EOL-ALIAS")["candidates"][0]["total_score"] == 98.53


def test_request_resolves_unique_direct_parent_from_product_bom(tmp_path):
    database = make_database(tmp_path)
    service = Phase3WorkflowService(database)
    created = service.create_request(
        {
            "request_id": "REQ-BIZ-PARENT-RESOLVE",
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "original_request": "DRIVE-IC 단종으로 대체자재 추천",
            "reasons": ["GENERAL_CHANGE"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "demand_source": "BOM_QUANTITY",
            "requested_by": "tester",
        },
        [{
            "action_id": "ACT-BIZ-PARENT-RESOLVE",
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "LTA400HR11-001",
            "old_item_code": "0001-310101",
            "location_code": "ALL",
        }],
    )
    assert created["actions"][0]["parent_item_code"] == "LJ94-310101"
    assert created["actions"][0]["location_code"] == "N/A"
    stored = service.get_result("REQ-BIZ-PARENT-RESOLVE")
    assert stored["reasons"] == ["EOL"]
    assert service.evaluate_action("ACT-BIZ-PARENT-RESOLVE")["candidates"][0]["total_score"] == 98.53


def test_common_assy_reports_two_models_and_applies_multi_action(tmp_path):
    database = make_database(tmp_path)
    service = Phase3WorkflowService(database)
    service.create_request(
        {
            "request_id": "REQ-BIZ-COMMON",
            "version_code": "LTA750HR12-001",
            "plant_code": "P01",
            "original_request": "공용 OLB ASSY 교체 및 GATE-IC 수량 변경",
            "normalized_request": "COMMON ASSY MULTI ACTION",
            "reasons": ["COMMONIZATION"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "demand_quantity": None,
            "demand_source": "BOM_QUANTITY",
            "requested_by": "tester",
        },
        [
            {
                "action_id": "ACT-BIZ-COMMON-REPLACE",
                "action_type": "REPLACE",
                "target_type": "ASSY",
                "parent_item_code": "LTA750HR12-001",
                "old_item_code": "LJ94-311001",
                "old_quantity": 1,
                "location_code": "N/A",
            },
            {
                "action_id": "ACT-BIZ-COMMON-QTY",
                "action_type": "QUANTITY_CHANGE",
                "target_type": "MATERIAL",
                "parent_item_code": "LJ94-311001",
                "old_item_code": "0001-311001",
                "old_quantity": 1,
                "new_quantity": 2,
                "location_code": "N/A",
            },
        ],
    )
    evaluated = service.evaluate_action(
        "ACT-BIZ-COMMON-REPLACE",
        ["COMMONIZATION"],
        "2026-08-15",
        ["process_name", "panel_size_inch", "resolution"],
    )
    selected = evaluated["candidates"][0]
    selection = service.prepare_candidate_selection(
        "REQ-BIZ-COMMON",
        [{
            "action_id": "ACT-BIZ-COMMON-REPLACE",
            "candidate_id": selected["candidate_id"],
            "supplier_item_id": selected["recommended_supplier_item_id"],
        }],
        "tester",
    )
    assert selection["workflow_status"] == "IMPACT_REVIEW_REQUIRED"
    assert selection["impact_review"]["requires_impact_approval"] is True
    service.approve_candidate_impact("REQ-BIZ-COMMON", "tester")
    preview = service.create_preview("REQ-BIZ-COMMON", "tester")
    impacted_models = {
        row["impacted_item_code"]
        for row in preview["impacts"]
        if row["impact_type"] == "MODEL"
    }
    assert impacted_models == {"LTA750HR12-001", "LTA750HR12-002"}
    assert {row["plant_code"] for row in preview["impacts"]} == {"P01"}
    final = service.approve_final("REQ-BIZ-COMMON", "tester")
    assert service.apply(
        "REQ-BIZ-COMMON", final["approval_id"], "tester"
    )["result"] == "APPLIED"


def test_all_assy_item_names_are_process_names_after_business_seed(tmp_path):
    database = make_database(tmp_path)
    with database.connection() as connection:
        invalid = connection.execute(
            """SELECT i.item_code,i.item_name,a.process_name
               FROM item_master i
               JOIN assembly_master a ON a.assembly_code=i.item_code
               WHERE i.item_name NOT IN ('OLB','CP','BIN','LC','CF','TFT')
                  OR i.item_name<>a.process_name"""
        ).fetchall()
    assert invalid == []


def test_business_verify_allows_effective_dated_runtime_bom_history_growth(tmp_path):
    """Successful design changes may grow runtime BOM history beyond seed baseline."""
    database = make_database(tmp_path)
    with database.transaction() as connection:
        context = connection.execute(
            """
            SELECT v.version_code,p.plant_code
            FROM version_master v
            JOIN production_plans p ON p.version_code=v.version_code
            WHERE v.specification LIKE '%PHASE3_BUSINESS_SAMPLE%'
            ORDER BY v.version_code,p.plant_code
            LIMIT 1
            """
        ).fetchone()
        assert context is not None
        candidates = connection.execute(
            f"""
            SELECT i.item_code
            FROM item_master i
            WHERE {CANDIDATE_FILTER}
              AND i.item_type='MATERIAL'
              AND NOT EXISTS (
                  SELECT 1 FROM bom_master b
                  WHERE b.plant_code=?
                    AND b.parent_item_code=?
                    AND b.child_item_code=i.item_code
                    AND b.location_code='N/A'
                    AND b.valid_from='2099-01-01'
              )
            ORDER BY i.item_code
            LIMIT 2
            """,
            (context["plant_code"], context["version_code"]),
        ).fetchall()
        assert len(candidates) == 2
        for seq, row in enumerate(candidates, start=9000):
            connection.execute(
                """
                INSERT INTO bom_master(
                    plant_code,parent_item_code,child_item_code,location_code,
                    sequence_no,quantity,valid_from,valid_to,row_revision,status
                ) VALUES(?,?,?,?,?,1,'2099-01-01',NULL,1,'ACTIVE')
                """,
                (
                    context["plant_code"], context["version_code"],
                    row["item_code"], "N/A", seq,
                ),
            )

    result = verify(database.database_path)
    assert result["business_bom_rows"] >= 48
