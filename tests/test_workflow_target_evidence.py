from pathlib import Path
import sqlite3

from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.workflow_target_evidence import (
    ScopedBomTargetEvidenceQuery,
    TargetQueryStatus,
)


V1 = "TSTMODEL-001"
V2 = "TSTMODEL-002"
PLANT = "P01"


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "workflow_target.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE item_master (
              item_code TEXT PRIMARY KEY,
              item_type TEXT NOT NULL,
              item_name TEXT NOT NULL,
              description TEXT,
              active_yn TEXT NOT NULL
            );
            CREATE TABLE version_master (
              version_code TEXT PRIMARY KEY
            );
            CREATE TABLE bom_master (
              bom_id INTEGER PRIMARY KEY AUTOINCREMENT,
              plant_code TEXT NOT NULL,
              parent_item_code TEXT NOT NULL,
              child_item_code TEXT NOT NULL,
              location_code TEXT NOT NULL,
              quantity REAL NOT NULL,
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
              currency_code TEXT,
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
            "INSERT INTO item_master VALUES (?,?,?,?,?)",
            [
                (V1, "VERSION", "MODEL 1", "", "Y"),
                (V2, "VERSION", "MODEL 2", "", "Y"),
                ("ASSY-001", "ASSEMBLY", "LC", "LC ASSY", "Y"),
                ("MAT-100001", "MATERIAL", "SEALANT", "SEALANT A", "Y"),
                ("MAT-100002", "MATERIAL", "SPACER", "SPACER A", "Y"),
                ("MAT-100003", "MATERIAL", "SHARED FILM", "COMMON", "Y"),
                ("MAT-100004", "MATERIAL", "DUP EDGE", "DUPLICATED", "Y"),
                ("MAT-100005", "MATERIAL", "GLUE", "GLUE A", "Y"),
                ("MAT-100006", "MATERIAL", "GLUE", "GLUE B", "Y"),
            ],
        )
        connection.executemany(
            "INSERT INTO version_master VALUES (?)",
            [(V1,), (V2,)],
        )
        connection.executemany(
            """INSERT INTO bom_master(
                 plant_code,parent_item_code,child_item_code,location_code,
                 quantity,status,valid_from,valid_to
               ) VALUES (?,?,?,?,?,?,?,?)""",
            [
                (PLANT, V1, "ASSY-001", "ALL", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100001", "LEFT", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100002", "RIGHT", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, V1, "MAT-100003", "ALL", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, V2, "MAT-100003", "ALL", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100004", "LEFT", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100004", "RIGHT", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100005", "ALL", 1, "ACTIVE", "2026-01-01", None),
                (PLANT, "ASSY-001", "MAT-100006", "ALL", 1, "ACTIVE", "2026-01-01", None),
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
                ("SUP-001", "MAT-100001", 2500.0, "KRW", "Y", "2026-01-01", None),
                ("SUP-001", "MAT-100002", 900.0, "KRW", "Y", "2026-01-01", None),
                ("SUP-001", "MAT-100003", 1200.0, "KRW", "Y", "2026-01-01", None),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _query(tmp_path: Path) -> ScopedBomTargetEvidenceQuery:
    return ScopedBomTargetEvidenceQuery(ReadOnlySqlExecutor(_database(tmp_path)))


def test_policy_allows_recursive_cycle_guard_function():
    assert "instr" in DEFAULT_TEXT_TO_SQL_POLICY.allowed_functions


def test_explicit_code_resolves_exact_nested_bom_edge(tmp_path):
    result = _query(tmp_path).resolve_explicit(
        version_code=V1,
        plant_code=PLANT,
        item_code="MAT-100001",
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.READY
    assert result.row == {
        "item_code": "MAT-100001",
        "item_name": "SEALANT",
        "description": "SEALANT A",
        "target_item_type": "MATERIAL",
        "parent_item_code": "ASSY-001",
        "location_code": "LEFT",
        "bom_quantity": 1.0,
    }
    assert "WITH RECURSIVE reachable" in result.sql


def test_explicit_name_resolves_one_item(tmp_path):
    result = _query(tmp_path).resolve_explicit(
        version_code=V1,
        plant_code=PLANT,
        target_name="SEALANT",
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.READY
    assert result.row["item_code"] == "MAT-100001"


def test_explicit_name_with_multiple_item_codes_is_ambiguous(tmp_path):
    result = _query(tmp_path).resolve_explicit(
        version_code=V1,
        plant_code=PLANT,
        target_name="GLUE",
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.AMBIGUOUS
    assert result.ready is False
    assert len(result.rows) == 2


def test_same_item_on_multiple_edges_is_ambiguous(tmp_path):
    result = _query(tmp_path).resolve_explicit(
        version_code=V1,
        plant_code=PLANT,
        item_code="MAT-100004",
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.AMBIGUOUS
    assert result.ready is False
    assert len(result.rows) == 2


def test_cost_rank_supports_high_and_low_without_llm(tmp_path):
    query = _query(tmp_path)
    high = query.resolve_cost_rank(
        version_code=V1,
        plant_code=PLANT,
        direction="HIGH",
        as_of_date="2026-09-04",
    )
    low = query.resolve_cost_rank(
        version_code=V1,
        plant_code=PLANT,
        direction="LOW",
        as_of_date="2026-09-04",
    )

    assert high.status == TargetQueryStatus.READY
    assert high.row["item_code"] == "MAT-100001"
    assert high.row["unit_cost"] == 2500.0
    assert low.status == TargetQueryStatus.READY
    assert low.row["item_code"] == "MAT-100002"
    assert low.row["unit_cost"] == 900.0


def test_cost_rank_tie_requires_user_selection(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE supplier_items SET unit_price=2500 WHERE item_code='MAT-100003'"
        )
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomTargetEvidenceQuery(ReadOnlySqlExecutor(path)).resolve_cost_rank(
        version_code=V1,
        plant_code=PLANT,
        direction="HIGH",
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.AMBIGUOUS
    assert len(result.rows) == 2
    assert "임의" not in result.reason  # Resolver reports facts; caller decides UX.


def test_cost_rank_returns_empty_when_no_comparable_cost_exists(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DELETE FROM supplier_items")
        connection.execute("DELETE FROM item_attribute_values")
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomTargetEvidenceQuery(ReadOnlySqlExecutor(path)).resolve_cost_rank(
        version_code=V1,
        plant_code=PLANT,
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.EMPTY
    assert result.rows == ()


def test_commonality_counts_active_versions_and_returns_unique_target(tmp_path):
    result = _query(tmp_path).resolve_commonality_rank(
        version_code=V1,
        plant_code=PLANT,
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.READY
    assert result.row["item_code"] == "MAT-100003"
    assert result.row["active_version_usage_count"] == 2


def test_commonality_tie_never_auto_selects(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "DELETE FROM bom_master WHERE parent_item_code=? AND child_item_code='MAT-100003'",
            (V2,),
        )
        connection.commit()
    finally:
        connection.close()

    result = ScopedBomTargetEvidenceQuery(ReadOnlySqlExecutor(path)).resolve_commonality_rank(
        version_code=V1,
        plant_code=PLANT,
        as_of_date="2026-09-04",
    )

    assert result.status == TargetQueryStatus.AMBIGUOUS
    assert result.ready is False
    assert len(result.rows) >= 2
