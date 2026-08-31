from __future__ import annotations

import shutil

from scripts.database_lifecycle import DEFAULT_TEST_DATABASE
from database import SchemaManager, SQLiteDatabase
from database.schema import CORE_SCHEMA_TABLES
from scripts.seed_design_change_business_sample import seed_design_change_business_sample
from scripts.verify_design_change_business_sample import CANDIDATE_FILTER, verify
from repositories.sqlite_repository import SQLiteBomRepository
from services.repository_bom_service import RepositoryBomService
from services.design_change_workflow_service import DesignChangeWorkflowService


def make_database(tmp_path) -> SQLiteDatabase:
    target = tmp_path / "design-change-business.db"
    shutil.copyfile(DEFAULT_TEST_DATABASE, target)
    database = SQLiteDatabase(target)
    SchemaManager(database).initialize()
    seed_design_change_business_sample(database)
    return database


def test_business_seed_preserves_baseline_and_is_idempotent(tmp_path):
    database = make_database(tmp_path)
    seed_design_change_business_sample(database)
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


def test_latest_seed_uses_clean_core_schema(tmp_path):
    database = make_database(tmp_path)
    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        names.discard("sqlite_sequence")
        assert names == set(CORE_SCHEMA_TABLES)


def test_eol_material_replace_runs_through_current_workflow(tmp_path):
    database = make_database(tmp_path)
    service = DesignChangeWorkflowService(database)
    analysis = service.analyze_candidates(
        {
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "original_request": "DRIVE-IC 단종으로 대체자재 추천",
            "reasons": ["EOL"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "requested_by": "tester",
        },
        [{
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "LJ94-310101",
            "old_item_code": "0001-310101",
            "location_code": "N/A",
        }],
    )
    assert [row["status"] for row in analysis["candidates"]] == [
        "PASS", "PASS", "PASS", "CONDITIONAL", "FAIL",
    ]
    selected = analysis["candidates"][0]
    assert selected["candidate_item_code"] == "0001-310111"
    assert selected["total_score"] == 98.53
    assert selected["demand"]["quantity"] == 1.0
    assert selected["demand"]["source"] == "BOM_QUANTITY"
    assert analysis["analysis_context"]["reason_codes"] == ["EOL"]
    assert analysis["request_created"] is False

    selections = [{
        "action_id": analysis["actions"][0]["action_id"],
        "candidate_item_code": selected["candidate_item_code"],
        "supplier_item_id": selected.get("recommended_supplier_item_id"),
    }]
    impact = service.preview_analysis_impact(analysis, selections)
    committed = service.commit_analysis_as_request(
        analysis,
        selections,
        approved_by="tester",
        impact_confirmed=bool(impact.get("requires_impact_approval")),
    )
    preview = service.create_preview(committed["request_id"], "tester")
    assert preview["validation_status"] == "PASS"
    final = service.approve_final(committed["request_id"], "tester")
    applied = service.apply(committed["request_id"], final["approval_id"], "tester")
    assert applied["result"] == "APPLIED"

def test_business_analysis_normalizes_eol_reason_alias(tmp_path):
    database = make_database(tmp_path)
    service = DesignChangeWorkflowService(database)
    analysis = service.analyze_candidates(
        {
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "reasons": ["단종"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "requested_by": "tester",
        },
        [{
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "LJ94-310101",
            "old_item_code": "0001-310101",
            "location_code": "N/A",
        }],
    )
    assert analysis["request"]["reasons"] == ["EOL"]
    assert analysis["candidates"][0]["total_score"] == 98.53
    assert analysis["request_created"] is False

def test_analysis_resolves_unique_direct_parent_from_product_bom(tmp_path):
    database = make_database(tmp_path)
    service = DesignChangeWorkflowService(database)
    analysis = service.analyze_candidates(
        {
            "version_code": "LTA400HR11-001",
            "plant_code": "P01",
            "original_request": "DRIVE-IC 단종으로 대체자재 추천",
            "reasons": ["GENERAL_CHANGE"],
            "as_of_date": "2026-08-15",
            "effective_date": "2026-09-01",
            "requested_by": "tester",
        },
        [{
            "action_type": "REPLACE",
            "target_type": "MATERIAL",
            "parent_item_code": "LTA400HR11-001",
            "old_item_code": "0001-310101",
            "location_code": "ALL",
        }],
    )
    assert analysis["actions"][0]["parent_item_code"] == "LJ94-310101"
    assert analysis["actions"][0]["location_code"] == "N/A"
    assert analysis["request"]["reasons"] == ["EOL"]
    assert analysis["candidates"][0]["total_score"] == 98.53

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
            WHERE v.specification LIKE '%DESIGN_CHANGE_BUSINESS_SAMPLE%'
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
