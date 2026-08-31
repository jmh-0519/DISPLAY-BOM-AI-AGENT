from __future__ import annotations

import shutil
from datetime import date

from database import SchemaManager, SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.design_change_workflow_service import DesignChangeWorkflowService


def make_database(tmp_path) -> SQLiteDatabase:
    target = tmp_path / "generalized-design-change.db"
    shutil.copyfile("data/test_display_bom.db", target)
    database = SQLiteDatabase(target)
    SchemaManager(database).initialize()
    return database


def find_dynamic_material_case(database: SQLiteDatabase) -> dict:
    """Find a real BOM material dynamically; no product/material fixture code is assumed."""
    repository = SQLiteDesignChangeRepository(database)
    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT b.plant_code,b.child_item_code
            FROM bom_master b
            JOIN item_master i ON i.item_code=b.child_item_code
            JOIN material_master m ON m.material_code=b.child_item_code
            WHERE i.item_type='MATERIAL'
              AND i.active_yn='Y'
              AND m.active_yn='Y'
              AND b.status='ACTIVE'
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
                  AND m2.active_yn='Y' AND i2.active_yn='Y'
              )
            ORDER BY b.plant_code,b.child_item_code
            """
        ).fetchall()

    for row in rows:
        ancestors = repository.get_recursive_ancestors(
            row["child_item_code"], row["plant_code"], date.today().isoformat()
        )
        for ancestor in ancestors:
            if ancestor["item_type"] != "VERSION":
                continue
            relations = repository.find_version_source_relations(
                version_code=ancestor["item_code"],
                child_item_code=row["child_item_code"],
                plant_code=row["plant_code"],
                as_of_date=date.today().isoformat(),
            )
            if len(relations) == 1:
                return {
                    "plant_code": row["plant_code"],
                    "version_code": ancestor["item_code"],
                    "source_item_code": row["child_item_code"],
                    "relation": relations[0],
                }
    raise AssertionError("No dynamic material case suitable for generalized test was found")


def test_minimal_natural_language_request_derives_metadata_and_bom_context(tmp_path):
    database = make_database(tmp_path)
    case = find_dynamic_material_case(database)
    service = DesignChangeWorkflowService(database)

    analysis = service.analyze_candidates(
        {
            "plant_code": case["plant_code"],
            "version_code": case["version_code"],
            "original_request": (
                f"{case['version_code']}의 {case['source_item_code']}가 단종됐어. "
                "변경 가능한 자재를 찾아줘."
            ),
        },
        [{
            "action_type": "REPLACE",
            "old_item_code": case["source_item_code"],
        }],
    )

    action = analysis["actions"][0]
    assert analysis["request"]["reasons"] == ["EOL"]
    assert action["target_type"] == "MATERIAL"
    assert action["parent_item_code"] == case["relation"]["parent_item_code"]
    assert action["location_code"] == case["relation"]["location_code"]
    assert action["old_quantity"] == float(case["relation"]["quantity"])
    assert analysis["request"]["as_of_date"] == date.today().isoformat()
    assert analysis["request"]["effective_date"] == date.today().isoformat()
    assert analysis["request_created"] is False


def test_unregistered_material_uses_dynamic_candidate_discovery_and_attribute_evaluation(tmp_path):
    database = make_database(tmp_path)
    case = find_dynamic_material_case(database)
    repository = SQLiteDesignChangeRepository(database)
    service = DesignChangeWorkflowService(database)

    assert repository.find_registered_candidates(
        case["source_item_code"], date.today().isoformat()
    ) == []

    analysis = service.analyze_candidates(
        {
            "plant_code": case["plant_code"],
            "version_code": case["version_code"],
            "original_request": "단종됐어. 변경 가능한 자재를 찾아줘.",
        },
        [{"action_type": "REPLACE", "old_item_code": case["source_item_code"]}],
    )

    assert analysis["candidates"]
    assert all(
        row["candidate_item_code"] != case["source_item_code"]
        for row in analysis["candidates"]
    )
    assert all(row["discovery_mode"] == "ATTRIBUTE_DISCOVERY"
               for row in analysis["candidates"])
    assert all(row["evaluation_mode"] == "ATTRIBUTE"
               for row in analysis["candidates"])
    assert all(row.get("rule_results") == [] for row in analysis["candidates"])
    assert any(row["status"] in {"PASS", "CONDITIONAL"}
               for row in analysis["candidates"])

    source_profile = repository.get_item_profile(
        case["source_item_code"], date.today().isoformat()
    )
    top_profile = repository.get_item_profile(
        analysis["candidates"][0]["candidate_item_code"], date.today().isoformat()
    )
    assert top_profile.get("material_name") == source_profile.get("material_name")
    assert top_profile.get("material_group") == source_profile.get("material_group")
    assert top_profile.get("specification") == source_profile.get("specification")


def test_candidate_pool_is_derived_from_each_selected_source_not_a_scenario_mapping(tmp_path):
    database = make_database(tmp_path)
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    with database.connection() as connection:
        source_rows = connection.execute(
            """
            SELECT m.material_code
            FROM material_master m
            JOIN item_master i ON i.item_code=m.material_code
            WHERE m.active_yn='Y' AND i.active_yn='Y'
              AND EXISTS (
                SELECT 1 FROM material_master m2
                JOIN item_master i2 ON i2.item_code=m2.material_code
                WHERE m2.material_code<>m.material_code
                  AND m2.material_name=m.material_name
                  AND COALESCE(m2.material_group,'')=COALESCE(m.material_group,'')
                  AND COALESCE(m2.specification,'')=COALESCE(m.specification,'')
                  AND m2.active_yn='Y' AND i2.active_yn='Y'
              )
            GROUP BY m.material_code
            ORDER BY m.material_name,m.material_code
            """
        ).fetchall()

    selected = []
    seen_signatures = set()
    for row in source_rows:
        profile = repository.get_item_profile(row["material_code"], today)
        signature = (
            profile.get("material_name"), profile.get("material_group"),
            profile.get("specification"),
        )
        if signature in seen_signatures:
            continue
        candidates = repository.find_attribute_candidates(
            row["material_code"], "MATERIAL", today
        )
        if candidates:
            selected.append((row["material_code"], signature, candidates))
            seen_signatures.add(signature)
        if len(selected) == 2:
            break

    assert len(selected) == 2
    first_source, first_signature, first_candidates = selected[0]
    second_source, second_signature, second_candidates = selected[1]
    assert first_source != second_source
    assert first_signature != second_signature
    assert first_candidates[0]["candidate_item_code"] != second_candidates[0]["candidate_item_code"]


def test_dynamic_candidate_discovery_returns_each_item_code_once(tmp_path):
    database = make_database(tmp_path)
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        row = connection.execute(
            """SELECT i.item_code
               FROM item_master i
               JOIN assembly_master a ON a.assembly_code=i.item_code
               WHERE i.active_yn='Y'
               ORDER BY i.item_code
               LIMIT 1"""
        ).fetchone()
    assert row is not None
    candidates = repository.find_attribute_candidates(row["item_code"], "ASSY", today)
    codes = [value["candidate_item_code"] for value in candidates]
    assert len(codes) == len(set(codes))
