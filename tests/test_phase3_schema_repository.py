from __future__ import annotations

from datetime import date
from uuid import uuid4

from database import SchemaManager, SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database


PHASE3_TABLES = {
    "item_attribute_values",
    "substitution_relations",
    "supplier_items",
    "plants",
    "warehouses",
    "inventory_locations",
    "inventory_balances",
    "production_plans",
    "rule_definitions",
    "rule_revisions",
    "rule_conditions",
    "change_reason_master",
    "change_reason_alias",
    "change_reason_scope",
    "change_reason_evidence_rules",
    "change_requests",
    "change_actions",
    "change_action_reasons",
    "candidate_evaluations",
    "candidate_rule_results",
    "change_approvals",
    "change_impacts",
    "change_previews",
    "change_apply_results",
    "decision_traces",
    "performance_outcomes",
    "dataset_exports",
}


def make_latest_database(tmp_path) -> SQLiteDatabase:
    target = tmp_path / "phase3-schema-repository.db"
    rebuild_latest_database(target)
    database = SQLiteDatabase(target)
    SchemaManager(database).initialize()
    return database


def find_dynamic_material_relation(database: SQLiteDatabase) -> dict:
    """Find one real active material/BOM relation without assuming any fixture code."""
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    with database.connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT b.plant_code, b.child_item_code
            FROM bom_master b
            JOIN item_master i ON i.item_code=b.child_item_code
            WHERE i.item_type='MATERIAL'
              AND i.active_yn='Y'
              AND b.status='ACTIVE'
              AND b.valid_from<=?
              AND (b.valid_to IS NULL OR b.valid_to>=?)
            ORDER BY b.plant_code, b.child_item_code
            """,
            (today, today),
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
                    "relation": relations[0],
                }

    raise AssertionError("No active material relation suitable for repository test was found")


def find_dynamic_replace_reason(database: SQLiteDatabase, target_type: str) -> dict:
    """Select an active REPLACE reason/alias from metadata instead of hardcoding one."""
    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT s.reason_code, a.alias_text
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.active_yn='Y'
              AND s.target_type=?
              AND s.action_type='REPLACE'
            ORDER BY a.priority, s.reason_code, a.alias_id
            LIMIT 1
            """,
            (target_type,),
        ).fetchone()
    if not row:
        raise AssertionError("No active REPLACE reason metadata was found")
    return dict(row)


def test_phase3_schema_is_idempotent_and_complete(tmp_path):
    database = make_latest_database(tmp_path)

    # Applying the current schema repeatedly must be safe.
    SchemaManager(database).initialize()
    SchemaManager(database).initialize()

    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert PHASE3_TABLES <= names
    assert not any(name.startswith("phase3_") for name in names)
    assert foreign_key_errors == []


def test_latest_database_lifecycle_is_repeatable_without_legacy_fixture_data(tmp_path):
    target = tmp_path / "latest.db"

    first = rebuild_latest_database(target)
    second = rebuild_latest_database(target)

    assert first == second
    assert all(value > 0 for value in first.values())

    with SQLiteDatabase(target).connection() as connection:
        assert connection.execute(
            "SELECT 1 FROM item_master WHERE item_code LIKE 'P3-%' LIMIT 1"
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM rule_definitions WHERE rule_id LIKE 'P3-R-%' LIMIT 1"
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM plants WHERE plant_code IN ('PLANT-1','PLANT-2') LIMIT 1"
        ).fetchone() is None


def test_repository_candidate_lookup_and_request_persistence_use_dynamic_data(tmp_path):
    database = make_latest_database(tmp_path)
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    # Candidate lookup: choose any currently registered source dynamically and compare
    # repository output with the database ordering contract.
    with database.connection() as connection:
        source = connection.execute(
            """
            SELECT r.source_item_code
            FROM substitution_relations r
            JOIN item_master i ON i.item_code=r.source_item_code
            WHERE r.active_yn='Y'
              AND i.active_yn='Y'
              AND r.valid_from<=?
              AND (r.valid_to IS NULL OR r.valid_to>=?)
            GROUP BY r.source_item_code
            ORDER BY r.source_item_code
            LIMIT 1
            """,
            (today, today),
        ).fetchone()
        assert source is not None
        expected = [
            row["candidate_item_code"]
            for row in connection.execute(
                """
                SELECT r.candidate_item_code
                FROM substitution_relations r
                JOIN item_master i ON i.item_code=r.candidate_item_code
                WHERE r.source_item_code=?
                  AND r.active_yn='Y'
                  AND i.active_yn='Y'
                  AND r.valid_from<=?
                  AND (r.valid_to IS NULL OR r.valid_to>=?)
                ORDER BY r.priority, r.candidate_item_code
                """,
                (source["source_item_code"], today, today),
            ).fetchall()
        ]

    candidates = repository.find_registered_candidates(source["source_item_code"], today)
    assert [row["candidate_item_code"] for row in candidates] == expected

    # Request persistence: choose a real BOM relation and an allowed reason from metadata.
    case = find_dynamic_material_relation(database)
    reason = find_dynamic_replace_reason(database, "MATERIAL")
    request_id = f"REQ-{uuid4().hex.upper()}"
    action_id = f"ACT-{uuid4().hex.upper()}"

    repository.create_request(
        {
            "request_id": request_id,
            "plant_code": case["plant_code"],
            "version_code": case["version_code"],
            "original_request": reason["alias_text"],
            "normalized_request": reason["reason_code"],
            "reasons": [reason["reason_code"]],
            "as_of_date": today,
            "effective_date": today,
            "demand_quantity": None,
            "demand_source": "UNAVAILABLE",
            "requested_by": "pytest",
        },
        [
            {
                "action_id": action_id,
                "action_type": "REPLACE",
                "target_type": "MATERIAL",
                "parent_item_code": case["relation"]["parent_item_code"],
                "old_item_code": case["source_item_code"],
                "location_code": case["relation"]["location_code"],
                "old_quantity": float(case["relation"]["quantity"]),
            }
        ],
        [
            {
                "reason_code": reason["reason_code"],
                "raw_reason_text": reason["alias_text"],
                "llm_reason_code": None,
                "resolution_status": "RESOLVED",
                "resolution_source": "ALIAS",
                "confidence": 1.0,
                "is_primary": "Y",
                "confirmed_by": None,
                "evidence": {"test_source": "dynamic_metadata"},
            }
        ],
    )

    saved = repository.get_request(request_id)
    assert saved is not None
    assert saved["plant_code"] == case["plant_code"]
    assert saved["version_code"] == case["version_code"]
    assert saved["reasons"] == [reason["reason_code"]]
    assert saved["actions"][0]["old_item_code"] == case["source_item_code"]
    assert saved["actions"][0]["parent_item_code"] == case["relation"]["parent_item_code"]
    assert saved["actions"][0]["primary_reason"]["reason_code"] == reason["reason_code"]
