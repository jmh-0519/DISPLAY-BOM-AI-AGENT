from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


EXPECTED = {
    "business_versions": 11,
    "business_candidates": 50,
    "registered_substitutions": 45,
    "supplier_items": 150,
    "inventory_balances": 200,
    "production_plans": 11,
    "plants": 4,
    "business_rules": 10,
    "rule_conditions": 30,
    "business_bom_rows": 48,
    "baseline_design_changes": 9,
    "baseline_design_change_items": 7,
    "baseline_review_boms": 5,
    "baseline_bom_reviews": 5,
    "baseline_workflow_events": 2,
}

CANDIDATE_FILTER = """(
    item_code GLOB '0001-31[0-9][0-9]1[1-5]'
    OR item_code GLOB 'LJ94-31[0-9][0-9]1[1-5]'
)"""


def verify(database_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        actual = {
            "business_versions": connection.execute(
                "SELECT COUNT(*) FROM version_master "
                "WHERE specification LIKE '%PHASE3_BUSINESS_SAMPLE%'"
            ).fetchone()[0],
            "business_candidates": connection.execute(
                f"SELECT COUNT(*) FROM item_master WHERE {CANDIDATE_FILTER}"
            ).fetchone()[0],
            "registered_substitutions": connection.execute(
                "SELECT COUNT(*) FROM substitution_relations "
                "WHERE candidate_item_code IN "
                f"(SELECT item_code FROM item_master WHERE {CANDIDATE_FILTER})"
            ).fetchone()[0],
            "supplier_items": connection.execute(
                "SELECT COUNT(*) FROM supplier_items "
                "WHERE item_code IN "
                f"(SELECT item_code FROM item_master WHERE {CANDIDATE_FILTER})"
            ).fetchone()[0],
            "inventory_balances": connection.execute(
                "SELECT COUNT(*) FROM inventory_balances "
                "WHERE item_code IN "
                f"(SELECT item_code FROM item_master WHERE {CANDIDATE_FILTER})"
            ).fetchone()[0],
            "production_plans": connection.execute(
                "SELECT COUNT(*) FROM production_plans WHERE plan_id LIKE 'PLAN-LTA%'"
            ).fetchone()[0],
            "plants": connection.execute(
                "SELECT COUNT(*) FROM plants WHERE active_yn='Y'"
            ).fetchone()[0],
            "business_rules": connection.execute(
                "SELECT COUNT(*) FROM rule_definitions WHERE rule_id LIKE 'DC-R-%'"
            ).fetchone()[0],
            "rule_conditions": connection.execute(
                "SELECT COUNT(*) FROM rule_conditions WHERE rule_id LIKE 'DC-R-%'"
            ).fetchone()[0],
            "business_bom_rows": connection.execute(
                f"""WITH RECURSIVE production_tree(bom_id,plant_code,parent_item_code,child_item_code) AS (
                     SELECT b.bom_id,b.plant_code,b.parent_item_code,b.child_item_code
                     FROM bom_master b
                     JOIN version_master v ON v.version_code=b.parent_item_code
                     WHERE v.specification LIKE '%PHASE3_BUSINESS_SAMPLE%'
                     UNION ALL
                     SELECT b.bom_id,b.plant_code,b.parent_item_code,b.child_item_code
                     FROM production_tree t
                     JOIN bom_master b ON b.parent_item_code=t.child_item_code
                       AND b.plant_code=t.plant_code
                     WHERE b.status='ACTIVE'
                   ), sample_rows AS (
                     SELECT bom_id FROM production_tree
                     UNION
                     SELECT b.bom_id FROM bom_master b
                     WHERE b.parent_item_code IN (
                       SELECT item_code FROM item_master WHERE {CANDIDATE_FILTER}
                         AND item_type='ASSEMBLY'
                     )
                   )
                   SELECT COUNT(DISTINCT bom_id) FROM sample_rows"""
            ).fetchone()[0],
            "baseline_design_changes": connection.execute(
                "SELECT COUNT(*) FROM design_changes"
            ).fetchone()[0],
            "baseline_design_change_items": connection.execute(
                "SELECT COUNT(*) FROM design_change_items"
            ).fetchone()[0],
            "baseline_review_boms": connection.execute(
                "SELECT COUNT(*) FROM review_boms"
            ).fetchone()[0],
            "baseline_bom_reviews": connection.execute(
                "SELECT COUNT(*) FROM bom_reviews"
            ).fetchone()[0],
            "baseline_workflow_events": connection.execute(
                "SELECT COUNT(*) FROM workflow_events"
            ).fetchone()[0],
        }
        # Production E-BOM is mutable after successful Phase3 Apply.
        # The baseline sample starts at 48 BOM history rows, but REPLACE/ADD/
        # QUANTITY_CHANGE/DELETE can legitimately append effective-dated BOM
        # history. Therefore only immutable sample/master counts are exact.
        failures = {
            key: (EXPECTED[key], value)
            for key, value in actual.items()
            if key != "business_bom_rows" and value != EXPECTED[key]
        }
        if actual["business_bom_rows"] < EXPECTED["business_bom_rows"]:
            failures["business_bom_rows"] = (
                f">={EXPECTED['business_bom_rows']}",
                actual["business_bom_rows"],
            )
        if failures:
            raise RuntimeError(f"Business sample count mismatch: {failures}")
        if not connection.execute(
            "SELECT 1 FROM version_master WHERE version_code='LTA400HR01-001'"
        ).fetchone():
            raise RuntimeError("Phase2 baseline model LTA400HR01-001 is missing")
        if connection.execute(
            "SELECT 1 FROM item_master WHERE item_code LIKE 'P3-%' LIMIT 1"
        ).fetchone():
            raise RuntimeError("Legacy generic P3-* item remains in the functional test DB")
        if connection.execute(
            "SELECT 1 FROM plants WHERE plant_code IN ('PLANT-1','PLANT-2') LIMIT 1"
        ).fetchone():
            raise RuntimeError("Legacy synthetic Plant remains in the functional test DB")
        if connection.execute(
            "SELECT 1 FROM rule_definitions WHERE rule_id LIKE 'P3-R-%' LIMIT 1"
        ).fetchone():
            raise RuntimeError("Legacy generic P3-* rule remains in the functional test DB")

        invalid_assy_names = connection.execute(
            """SELECT COUNT(*)
               FROM item_master i
               JOIN assembly_master a ON a.assembly_code=i.item_code
               WHERE i.item_name NOT IN ('OLB','CP','BIN','LC','CF','TFT')
                  OR i.item_name<>a.process_name"""
        ).fetchone()[0]
        if invalid_assy_names:
            raise RuntimeError(
                f"Invalid ASSY item/process names remain: {invalid_assy_names}"
            )
        invalid_version_names = connection.execute(
            "SELECT COUNT(*) FROM item_master WHERE item_type='VERSION' AND item_name<>'FA'"
        ).fetchone()[0]
        if invalid_version_names:
            raise RuntimeError(
                f"Invalid VERSION item names remain: {invalid_version_names}"
            )

        metadata_counts = {
            "change_reason_master": 10,
            "change_reason_alias": 18,
            "change_reason_scope": 31,
            "change_reason_evidence_rules": 4,
        }
        for table_name, expected_count in metadata_counts.items():
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            if count != expected_count:
                raise RuntimeError(
                    f"Reason metadata count mismatch: {table_name} "
                    f"expected={expected_count} actual={count}"
                )

        scenario_plant_rows = connection.execute(
            """SELECT v.version_code, GROUP_CONCAT(DISTINCT b.plant_code) AS plants
               FROM version_master v
               JOIN bom_master b ON b.parent_item_code=v.version_code
               WHERE v.specification LIKE '%PHASE3_BUSINESS_SAMPLE%'
                 AND v.version_code <> 'LTA750HR12-002'
               GROUP BY v.version_code
               ORDER BY v.version_code"""
        ).fetchall()
        expected_scenario_plants = {
            'LTA400HR11-001': 'P01',
            'LTA400HR12-001': 'P02',
            'LTA500HR11-001': 'P03',
            'LTA500HR12-001': 'P04',
            'LTA550HR11-001': 'P01',
            'LTA550HR12-001': 'P02',
            'LTA650HR11-001': 'P03',
            'LTA650HR12-001': 'P04',
            'LTA750HR11-001': 'P01',
            'LTA750HR12-001': 'P01',
        }
        actual_scenario_plants = {row[0]: row[1] for row in scenario_plant_rows}
        if actual_scenario_plants != expected_scenario_plants:
            raise RuntimeError(
                f"Scenario Plant placement mismatch: {actual_scenario_plants}"
            )

        for plant_code in ('P01', 'P02'):
            tree_count = connection.execute(
                """WITH RECURSIVE tree(child_item_code,visited) AS (
                     SELECT child_item_code, '|' || parent_item_code || '|' || child_item_code || '|'
                     FROM bom_master
                     WHERE plant_code=? AND parent_item_code='LTA400HR01-001'
                       AND status='ACTIVE' AND valid_from<='2026-08-18'
                       AND (valid_to IS NULL OR valid_to>='2026-08-18')
                     UNION ALL
                     SELECT b.child_item_code, tree.visited || b.child_item_code || '|'
                     FROM tree
                     JOIN bom_master b ON b.parent_item_code=tree.child_item_code
                       AND b.plant_code=?
                     WHERE b.status='ACTIVE' AND b.valid_from<='2026-08-18'
                       AND (b.valid_to IS NULL OR b.valid_to>='2026-08-18')
                       AND instr(tree.visited, '|' || b.child_item_code || '|')=0
                   ) SELECT COUNT(*) FROM tree""",
                (plant_code, plant_code),
            ).fetchone()[0]
            if tree_count != 20:
                raise RuntimeError(
                    f"Cross-Plant baseline BOM mismatch: {plant_code} rows={tree_count}"
                )

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"Foreign key errors: {len(foreign_key_errors)}")
        invalid_hierarchy = connection.execute(
            """
            SELECT COUNT(*)
            FROM bom_master b
            JOIN item_master p ON p.item_code=b.parent_item_code
            JOIN item_master c ON c.item_code=b.child_item_code
            LEFT JOIN assembly_master pa ON pa.assembly_code=p.item_code
            LEFT JOIN assembly_master ca ON ca.assembly_code=c.item_code
            LEFT JOIN bom_hierarchy_rules h
              ON h.parent_type=p.item_type
             AND h.parent_process=COALESCE(pa.process_name,'')
             AND h.child_type=c.item_type
             AND h.child_process=COALESCE(ca.process_name,'')
             AND h.active_yn='Y'
            WHERE b.status='ACTIVE' AND h.parent_type IS NULL
            """
        ).fetchone()[0]
        if invalid_hierarchy:
            raise RuntimeError(f"Invalid active BOM hierarchy: {invalid_hierarchy}")
        shared_models = connection.execute(
            """SELECT COUNT(DISTINCT parent_item_code) FROM bom_master
               WHERE plant_code='P01' AND child_item_code='LJ94-311001'
                 AND status='ACTIVE'
                 AND valid_from<='2026-08-15'
                 AND (valid_to IS NULL OR valid_to>='2026-08-15')"""
        ).fetchone()[0]
        if shared_models != 2:
            raise RuntimeError(f"Common ASSY impact model count mismatch: {shared_models}")
        return actual
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Phase3 business sample DB")
    parser.add_argument(
        "--database",
        default=".pytest_tmp_runtime/test_display_bom.db",
    )
    args = parser.parse_args()
    result = verify(Path(args.database))
    print("Phase3 business sample verification passed")
    for name, value in result.items():
        print(f"- {name}: {value}")


if __name__ == "__main__":
    main()
