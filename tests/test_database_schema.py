import sqlite3

import pytest

from database import IncompatibleSchemaError, SQLiteDatabase, SchemaManager


EXPECTED_TABLES = {
    "schema_versions",
    "supplier_master",
    "customer_master",
    "item_master",
    "version_master",
    "assembly_master",
    "material_master",
    "location_master",
    "bom_master",
    "material_attributes",
    "material_compatibility",
    "design_rules",
    "bom_hierarchy_rules",
    "design_changes",
    "design_change_items",
    "design_change_checks",
    "design_change_snapshots",
    "design_change_snapshot_items",
    "review_boms",
    "review_bom_revisions",
    "review_bom_items",
    "bom_reviews",
    "bom_review_checks",
    "review_checklists",
    "production_apply_history",
    "workflow_events",
    "legacy_change_history",
    "query_aliases",
}


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(tmp_path / "test.db")
    SchemaManager(db).initialize()
    return db


def _insert_item(connection, code, item_type, name):
    connection.execute(
        "INSERT INTO item_master(item_code,item_type,item_name) VALUES(?,?,?)",
        (code, item_type, name),
    )


def test_schema_creates_all_domain_tables(database):
    with database.connection() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert EXPECTED_TABLES <= names
    assert "products" not in names
    assert "production_bom_items" not in names


def test_schema_initialization_is_idempotent(database):
    manager = SchemaManager(database)
    manager.initialize()
    assert manager.current_version() == 6

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM location_master"
        ).fetchone()[0] == 11
        assert connection.execute(
            "SELECT COUNT(*) FROM bom_hierarchy_rules"
        ).fetchone()[0] == 13


def test_legacy_draft_schema_requires_explicit_recreate(tmp_path):
    db = SQLiteDatabase(tmp_path / "legacy.db")
    with db.connection() as connection:
        connection.execute("CREATE TABLE products(product_id TEXT PRIMARY KEY)")

    with pytest.raises(IncompatibleSchemaError, match="--recreate"):
        SchemaManager(db).initialize()


def test_connection_enables_foreign_keys(database):
    with database.connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transaction_commits_fa_version(database):
    with database.transaction() as connection:
        _insert_item(connection, "FA10000001", "VERSION", "FA")
        connection.execute(
            "INSERT INTO version_master(version_code,version_no,route_code) "
            "VALUES(?,?,?)",
            ("FA10000001", "01", "ROUTE-A"),
        )

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM version_master WHERE version_code='FA10000001'"
        ).fetchone()[0] == 1


def test_transaction_rolls_back_on_error(database):
    with pytest.raises(RuntimeError):
        with database.transaction() as connection:
            _insert_item(connection, "FA-ROLLBACK", "VERSION", "FA")
            connection.execute(
                "INSERT INTO version_master(version_code) VALUES(?)",
                ("FA-ROLLBACK",),
            )
            raise RuntimeError("rollback")

    with database.connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM item_master WHERE item_code='FA-ROLLBACK'"
        ).fetchone()[0] == 0


def test_subtype_master_requires_matching_item_type(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "WRONG-01", "MATERIAL", "FILM")
            connection.execute(
                "INSERT INTO assembly_master(assembly_code,process_name) "
                "VALUES(?,?)",
                ("WRONG-01", "OLB"),
            )


def test_bom_accepts_same_material_at_different_locations(database):
    with database.transaction() as connection:
        _insert_item(connection, "OLB20001", "ASSEMBLY", "OLB")
        connection.execute(
            "INSERT INTO assembly_master(assembly_code,process_name) VALUES(?,?)",
            ("OLB20001", "OLB"),
        )
        _insert_item(connection, "MAT10001", "MATERIAL", "FILM")
        connection.execute(
            "INSERT INTO material_master(material_code,material_name,unit) "
            "VALUES(?,?,?)",
            ("MAT10001", "FILM", "EA"),
        )
        connection.executemany(
            "INSERT INTO bom_master("
            "parent_item_code,child_item_code,location_code,quantity,valid_from"
            ") VALUES(?,?,?,?,?)",
            [
                ("OLB20001", "MAT10001", "TOP", 1, "2026-01-01"),
                ("OLB20001", "MAT10001", "BOTTOM", 1, "2026-01-01"),
            ],
        )

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT location_code FROM bom_master "
            "WHERE parent_item_code='OLB20001' ORDER BY location_code"
        ).fetchall()
    assert [row["location_code"] for row in rows] == ["BOTTOM", "TOP"]


def test_bom_rejects_duplicate_relation_at_same_location(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "LC500001", "ASSEMBLY", "LC")
            connection.execute(
                "INSERT INTO assembly_master(assembly_code,process_name) "
                "VALUES('LC500001','LC')"
            )
            _insert_item(connection, "CF600001", "ASSEMBLY", "CF")
            connection.execute(
                "INSERT INTO assembly_master(assembly_code,process_name) "
                "VALUES('CF600001','CF')"
            )
            relation = ("LC500001", "CF600001", "N/A", 1, "2026-01-01")
            connection.execute(
                "INSERT INTO bom_master("
                "parent_item_code,child_item_code,location_code,quantity,valid_from"
                ") VALUES(?,?,?,?,?)",
                relation,
            )
            connection.execute(
                "INSERT INTO bom_master("
                "parent_item_code,child_item_code,location_code,quantity,valid_from"
                ") VALUES(?,?,?,?,?)",
                relation,
            )


def test_bom_rejects_self_reference_and_unknown_location(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "OLB-SELF", "ASSEMBLY", "OLB")
            connection.execute(
                "INSERT INTO assembly_master(assembly_code,process_name) "
                "VALUES('OLB-SELF','OLB')"
            )
            connection.execute(
                "INSERT INTO bom_master("
                "parent_item_code,child_item_code,location_code,quantity,valid_from"
                ") VALUES('OLB-SELF','OLB-SELF','N/A',1,'2026-01-01')"
            )

    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "FA-LOC", "VERSION", "FA")
            connection.execute(
                "INSERT INTO version_master(version_code) VALUES('FA-LOC')"
            )
            _insert_item(connection, "MAT-LOC", "MATERIAL", "SEALANT")
            connection.execute(
                "INSERT INTO material_master(material_code,material_name) "
                "VALUES('MAT-LOC','SEALANT')"
            )
            connection.execute(
                "INSERT INTO bom_master("
                "parent_item_code,child_item_code,location_code,quantity,valid_from"
                ") VALUES('FA-LOC','MAT-LOC','UNKNOWN',1,'2026-01-01')"
            )


def test_hierarchy_seed_has_cf_and_tft_as_lc_siblings(database):
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT child_process FROM bom_hierarchy_rules "
            "WHERE parent_type='ASSEMBLY' AND parent_process='LC' "
            "AND child_type='ASSEMBLY' ORDER BY child_process"
        ).fetchall()
        wrong_edge = connection.execute(
            "SELECT COUNT(*) FROM bom_hierarchy_rules "
            "WHERE parent_process='CF' AND child_process='TFT'"
        ).fetchone()[0]

    assert [row["child_process"] for row in rows] == ["CF", "TFT"]
    assert wrong_edge == 0


def test_assy_item_name_accepts_only_process_domain_values(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "ASSY-BAD-NAME", "ASSEMBLY", "OLB ASSY ALT-1")


def test_assy_item_name_must_match_process_name(database):
    with pytest.raises(sqlite3.IntegrityError):
        with database.transaction() as connection:
            _insert_item(connection, "ASSY-MISMATCH", "ASSEMBLY", "OLB")
            connection.execute(
                "INSERT INTO assembly_master(assembly_code,process_name) VALUES(?,?)",
                ("ASSY-MISMATCH", "CF"),
            )


def test_step32_schema_has_persisted_supply_and_demand_evidence(tmp_path):
    database = SQLiteDatabase(tmp_path / "step32-schema.db")
    SchemaManager(database).initialize()
    assert SchemaManager(database).current_version() == 6
    with database.connection() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(candidate_evaluations)")}
    assert {"supplier_evaluation_json", "demand_context_json"} <= columns
