from pathlib import Path
import sqlite3

from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.workflow_cost_evidence import ScopedBomCostEvidenceQuery


VERSION = "LTA550HR11-001"
PLANT = "P01"


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "workflow_cost.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE item_master (
              item_code TEXT PRIMARY KEY,
              item_type TEXT NOT NULL,
              item_name TEXT NOT NULL,
              active_yn TEXT NOT NULL
            );
            CREATE TABLE bom_master (
              bom_id INTEGER PRIMARY KEY AUTOINCREMENT,
              plant_code TEXT NOT NULL,
              parent_item_code TEXT NOT NULL,
              child_item_code TEXT NOT NULL,
              location_code TEXT NOT NULL,
              status TEXT NOT NULL,
              valid_from TEXT NOT NULL,
              valid_to TEXT
            );
            CREATE TABLE supplier_master (
              supplier_code TEXT PRIMARY KEY,
              active_yn TEXT NOT NULL
            );
            CREATE TABLE supplier_items (
              supplier_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
              supplier_code TEXT NOT NULL,
              item_code TEXT NOT NULL,
              unit_price REAL,
              currency_code TEXT NOT NULL,
              primary_yn TEXT NOT NULL,
              valid_from TEXT NOT NULL,
              valid_to TEXT
            );
            CREATE TABLE item_attribute_values (
              item_code TEXT NOT NULL,
              attribute_name TEXT NOT NULL,
              attribute_value TEXT,
              value_type TEXT NOT NULL,
              valid_from TEXT NOT NULL,
              valid_to TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO item_master VALUES (?,?,?,?)",
            [
                (VERSION, "VERSION", "FA", "Y"),
                ("LJ94-330501", "ASSEMBLY", "OLB", "Y"),
                ("LJ94-330502", "ASSEMBLY", "CP", "Y"),
                ("LJ94-330503", "ASSEMBLY", "BIN", "Y"),
                ("LJ94-310501", "ASSEMBLY", "LC", "Y"),
                ("0001-310501", "MATERIAL", "SEALANT", "Y"),
                ("0001-310502", "MATERIAL", "LOW COST", "Y"),
            ],
        )
        connection.executemany(
            """INSERT INTO bom_master(
                 plant_code,parent_item_code,child_item_code,location_code,
                 status,valid_from,valid_to
               ) VALUES (?,?,?,?,?,?,?)""",
            [
                (PLANT, VERSION, "LJ94-330501", "N/A", "ACTIVE", "2026-01-01", None),
                (PLANT, "LJ94-330501", "LJ94-330502", "N/A", "ACTIVE", "2026-01-01", None),
                (PLANT, "LJ94-330502", "LJ94-330503", "N/A", "ACTIVE", "2026-01-01", None),
                (PLANT, "LJ94-330503", "LJ94-310501", "N/A", "ACTIVE", "2026-01-01", None),
                (PLANT, "LJ94-310501", "0001-310501", "ALL", "ACTIVE", "2026-01-01", None),
                (PLANT, VERSION, "0001-310502", "ALL", "ACTIVE", "2026-01-01", None),
            ],
        )
        connection.execute(
            "INSERT INTO supplier_master VALUES (?,?)",
            ("SUP-001", "Y"),
        )
        connection.executemany(
            """INSERT INTO supplier_items(
                 supplier_code,item_code,unit_price,currency_code,primary_yn,
                 valid_from,valid_to
               ) VALUES (?,?,?,?,?,?,?)""",
            [
                ("SUP-001", "0001-310501", 2500.0, "KRW", "Y", "2026-01-01", None),
                ("SUP-001", "0001-310502", 900.0, "KRW", "Y", "2026-01-01", None),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_scoped_cost_query_traverses_full_nested_bom(tmp_path):
    path = _database(tmp_path)
    query = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(path))

    result = query.run(
        version_code=VERSION,
        plant_code=PLANT,
        question="가장 원가가 높은 자재 1개",
        as_of_date="2026-09-03",
    )

    assert result.status == "SQL"
    assert result.row_count == 1
    assert result.rows[0]["item_code"] == "0001-310501"
    assert result.rows[0]["parent_item_code"] == "LJ94-310501"
    assert result.rows[0]["location_code"] == "ALL"
    assert result.rows[0]["unit_cost"] == 2500.0
    assert result.rows[0]["price_source"] == "PRIMARY_SUPPLIER"
    assert result.rows[0]["currency_code"] == "KRW"
    assert "WITH RECURSIVE reachable" in result.sql
    assert f"SELECT '{VERSION}'" in result.sql
    assert f"b.plant_code = '{PLANT}'" in result.sql
    assert result.sql.rstrip().endswith("LIMIT 1")


def test_scoped_cost_query_falls_back_to_unit_cost_attribute(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "DELETE FROM supplier_items WHERE item_code='0001-310501'"
        )
        connection.execute(
            """INSERT INTO item_attribute_values(
                 item_code,attribute_name,attribute_value,value_type,valid_from,valid_to
               ) VALUES (?,?,?,?,?,?)""",
            ("0001-310501", "unit_cost", "2600", "NUMBER", "2026-01-01", None),
        )
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(path)).run(
        version_code=VERSION,
        plant_code=PLANT,
        question="가장 원가가 높은 자재 1개",
        as_of_date="2026-09-03",
    )

    assert result.rows[0]["item_code"] == "0001-310501"
    assert result.rows[0]["unit_cost"] == 2600.0
    assert result.rows[0]["price_source"] == "ITEM_ATTRIBUTE"


def test_scoped_cost_query_ignores_material_outside_selected_product(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO item_master VALUES (?,?,?,?)",
            ("0001-999999", "MATERIAL", "OTHER MODEL EXPENSIVE", "Y"),
        )
        connection.execute(
            """INSERT INTO supplier_items(
                 supplier_code,item_code,unit_price,currency_code,primary_yn,
                 valid_from,valid_to
               ) VALUES (?,?,?,?,?,?,?)""",
            ("SUP-001", "0001-999999", 999999.0, "KRW", "Y", "2026-01-01", None),
        )
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(path)).run(
        version_code=VERSION,
        plant_code=PLANT,
        question="가장 원가가 높은 자재 1개",
        as_of_date="2026-09-03",
    )

    assert result.rows[0]["item_code"] == "0001-310501"


def test_scoped_cost_query_rejects_invalid_scope_before_sql(tmp_path):
    path = _database(tmp_path)
    query = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(path))

    try:
        query.run(
            version_code="LTA' OR 1=1 --",
            plant_code=PLANT,
            question="가장 원가가 높은 자재 1개",
            as_of_date="2026-09-03",
        )
    except ValueError as error:
        assert "VERSION" in str(error)
    else:
        raise AssertionError("invalid VERSION scope was not rejected")


def test_scoped_cost_query_returns_empty_when_reachable_material_has_no_cost(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DELETE FROM supplier_items")
        connection.execute("DELETE FROM item_attribute_values")
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomCostEvidenceQuery(ReadOnlySqlExecutor(path)).run(
        version_code=VERSION,
        plant_code=PLANT,
        question="가장 원가가 높은 자재 1개",
        as_of_date="2026-09-03",
    )

    assert result.status == "SQL"
    assert result.row_count == 0
    assert result.rows == ()
    assert result.truncated is False
