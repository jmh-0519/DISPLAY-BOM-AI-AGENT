from __future__ import annotations

from datetime import date

import pytest

from database import SQLiteDatabase
from repositories.sqlite_repository import SQLiteBomRepository
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService


def _database(tmp_path) -> SQLiteDatabase:
    path = tmp_path / "add-plant-quantity-policy.db"
    rebuild_latest_database(path)
    return SQLiteDatabase(path)


def test_list_plants_for_version_matches_actual_active_bom_plants(tmp_path):
    database = _database(tmp_path)
    repository = SQLiteBomRepository(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        row = connection.execute(
            """SELECT b.parent_item_code AS version_code
               FROM bom_master b
               JOIN item_master i ON i.item_code=b.parent_item_code AND i.item_type='VERSION'
               WHERE b.status='ACTIVE'
               GROUP BY b.parent_item_code
               HAVING COUNT(DISTINCT b.plant_code) < (SELECT COUNT(*) FROM plants WHERE active_yn='Y')
               ORDER BY b.parent_item_code LIMIT 1"""
        ).fetchone()
        assert row is not None
        expected = {
            value[0] for value in connection.execute(
                """SELECT DISTINCT plant_code FROM bom_master
                   WHERE parent_item_code=? AND status='ACTIVE'
                     AND valid_from<=? AND (valid_to IS NULL OR valid_to>=?)""",
                (row["version_code"], today, today),
            ).fetchall()
        }
    actual = {
        value["plant_code"]
        for value in repository.list_plants(row["version_code"], today)
    }
    assert actual == expected
    assert actual


def test_analysis_rejects_plant_where_version_has_no_active_bom(tmp_path):
    database = _database(tmp_path)
    service = DesignChangeWorkflowService(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        row = connection.execute(
            """SELECT b.parent_item_code AS version_code,b.plant_code
               FROM bom_master b
               JOIN item_master i ON i.item_code=b.parent_item_code AND i.item_type='VERSION'
               WHERE b.status='ACTIVE'
               ORDER BY b.parent_item_code,b.plant_code LIMIT 1"""
        ).fetchone()
        assert row is not None
        other = connection.execute(
            """SELECT plant_code FROM plants
               WHERE active_yn='Y' AND plant_code<>?
                 AND NOT EXISTS(
                   SELECT 1 FROM bom_master b
                   WHERE b.parent_item_code=? AND b.plant_code=plants.plant_code
                     AND b.status='ACTIVE'
                 )
               ORDER BY plant_code LIMIT 1""",
            (row["plant_code"], row["version_code"]),
        ).fetchone()
        if other is None:
            pytest.skip("No product with a distinct invalid Plant is available")

    with pytest.raises(ValueError, match="활성 BOM이 없습니다"):
        service.analyze_candidates(
            {
                "version_code": row["version_code"],
                "plant_code": other["plant_code"],
                "original_request": "신규 자재 추가 후보를 찾아줘",
                "reasons": ["GENERAL_CHANGE"],
                "as_of_date": today,
                "effective_date": today,
            },
            [{"action_type": "ADD", "target_type": "MATERIAL", "target_item_name": "신규 자재"}],
        )


def test_add_discovery_is_scoped_by_rule_identity_instead_of_all_materials(tmp_path):
    database = _database(tmp_path)
    service = DesignChangeWorkflowService(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        rule = connection.execute(
            """SELECT r.rule_id,r.change_reason,r.target_type,r.evaluation_item,
                      c.attribute_name,c.expected_value
               FROM rule_revisions r
               JOIN change_reason_scope s
                 ON s.reason_code=r.change_reason AND s.target_type=r.target_type
                AND s.action_type='ADD' AND s.active_yn='Y'
               JOIN rule_conditions c
                 ON c.rule_id=r.rule_id AND c.revision_no=r.revision_no
               WHERE r.active_yn='Y' AND r.target_type='MATERIAL'
                 AND LOWER(c.attribute_name) LIKE '%family%'
                 AND c.operator='EQ'
               ORDER BY r.rule_id LIMIT 1"""
        ).fetchone()
        assert rule is not None
        product = connection.execute(
            """SELECT b.parent_item_code AS version_code,b.plant_code
               FROM bom_master b
               JOIN item_master i ON i.item_code=b.parent_item_code AND i.item_type='VERSION'
               WHERE b.status='ACTIVE'
               ORDER BY b.parent_item_code,b.plant_code LIMIT 1"""
        ).fetchone()
        assert product is not None

    analysis = service.analyze_candidates(
        {
            "version_code": product["version_code"],
            "plant_code": product["plant_code"],
            "original_request": f"{rule['evaluation_item']} 추가 후보를 찾아줘",
            "reasons": [rule["change_reason"]],
            "as_of_date": today,
            "effective_date": today,
        },
        [{
            "action_type": "ADD",
            "target_type": "MATERIAL",
            "target_item_name": rule["evaluation_item"],
        }],
    )
    assert analysis["candidates"]
    for candidate in analysis["candidates"]:
        profile = service.repository.get_item_profile(candidate["candidate_item_code"], today)
        assert str(profile.get(rule["attribute_name"])) == str(rule["expected_value"])


def test_replace_inventory_uses_current_bom_quantity_not_production_plan(tmp_path):
    database = _database(tmp_path)
    service = DesignChangeWorkflowService(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        row = connection.execute(
            """SELECT b.*
               FROM bom_master b
               JOIN item_master child ON child.item_code=b.child_item_code AND child.item_type='MATERIAL'
               WHERE b.status='ACTIVE'
                 AND EXISTS(SELECT 1 FROM substitution_relations s
                            WHERE s.source_item_code=b.child_item_code AND s.active_yn='Y')
               ORDER BY b.bom_id LIMIT 1"""
        ).fetchone()
        assert row is not None
        reason = connection.execute(
            """SELECT reason_code FROM change_reason_scope
               WHERE action_type='REPLACE' AND target_type='MATERIAL' AND active_yn='Y'
               ORDER BY reason_code LIMIT 1"""
        ).fetchone()
        assert reason is not None
    # Resolve the actual version ancestor rather than assuming the SQL's first version.
    ancestors = service.repository.get_recursive_ancestors(row["child_item_code"], row["plant_code"], today)
    version = next(value for value in ancestors if value.get("item_type") == "VERSION")
    analysis = service.analyze_candidates(
        {
            "version_code": version["item_code"],
            "plant_code": row["plant_code"],
            "original_request": "기존 자재 변경 후보를 찾아줘",
            "reasons": [reason["reason_code"]],
            "as_of_date": today,
            "effective_date": today,
        },
        [{
            "action_type": "REPLACE",
            "old_item_code": row["child_item_code"],
            "parent_item_code": row["parent_item_code"],
            "location_code": row["location_code"],
        }],
    )
    assert analysis["candidates"]
    demand = analysis["candidates"][0]["demand"]
    assert demand["source"] == "BOM_QUANTITY"
    assert demand["required_quantity_basis"] == "BOM_QUANTITY"
    assert demand["quantity"] == float(row["quantity"])
    assert demand["production_plan_quantity"] is None


def test_sidebar_no_longer_contains_plant_instruction_copy():
    source = open("app/streamlit_app.py", encoding="utf-8").read()
    assert "PLANT는 좌측에서 고정하지 않습니다" not in source
    assert "요청에 PLANT가 빠져 있으면" not in source
    assert "plant_options" in source
    assert "st.button" in source
