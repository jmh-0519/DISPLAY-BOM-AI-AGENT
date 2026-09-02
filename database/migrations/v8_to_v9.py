from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


SOURCE_VERSION = 8
TARGET_VERSION = 9


VERSION_COLUMNS_V8 = (
    "version_code",
    "version_no",
    "route_code",
    "specification",
    "active_yn",
    "created_at",
    "updated_at",
)
ASSEMBLY_COLUMNS_V8 = (
    "assembly_code",
    "process_name",
    "usage_type",
    "specification",
    "active_yn",
    "created_at",
    "updated_at",
)
MATERIAL_COLUMNS_V8 = (
    "material_code",
    "material_name",
    "material_group",
    "unit",
    "supplier_code",
    "specification",
    "active_yn",
    "created_at",
    "updated_at",
)


def _columns(connection: sqlite3.Connection, table_name: str) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    )


def _current_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) FROM schema_versions"
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _validate_v8_shape(connection: sqlite3.Connection) -> None:
    expected = {
        "version_master": VERSION_COLUMNS_V8,
        "assembly_master": ASSEMBLY_COLUMNS_V8,
        "material_master": MATERIAL_COLUMNS_V8,
    }
    mismatches = {}
    for table_name, columns in expected.items():
        actual = _columns(connection, table_name)
        if actual != columns:
            mismatches[table_name] = {
                "expected": columns,
                "actual": actual,
            }
    if mismatches:
        raise RuntimeError(
            "DB v8 subtype schema does not match the migration prerequisite: "
            f"{mismatches}"
        )


def _validate_registry_consistency(connection: sqlite3.Connection) -> None:
    checks = (
        ("material_master", "material_code", "MATERIAL", "material_name"),
        ("assembly_master", "assembly_code", "ASSEMBLY", None),
        ("version_master", "version_code", "VERSION", None),
    )
    for table_name, code_column, expected_type, name_column in checks:
        missing = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM "{table_name}" s
            LEFT JOIN item_master i ON i.item_code=s."{code_column}"
            WHERE i.item_code IS NULL OR i.item_type<>?
            """,
            (expected_type,),
        ).fetchone()[0]
        if missing:
            raise RuntimeError(
                f"{table_name} has {missing} rows that do not match item_master/{expected_type}"
            )

        lifecycle_mismatch = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM "{table_name}" s
            JOIN item_master i ON i.item_code=s."{code_column}"
            WHERE COALESCE(i.active_yn,'')<>COALESCE(s.active_yn,'')
               OR COALESCE(i.created_at,'')<>COALESCE(s.created_at,'')
               OR COALESCE(i.updated_at,'')<>COALESCE(s.updated_at,'')
            """
        ).fetchone()[0]
        if lifecycle_mismatch:
            raise RuntimeError(
                f"{table_name} lifecycle values differ from item_master: "
                f"{lifecycle_mismatch} rows"
            )

        if name_column:
            name_mismatch = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM "{table_name}" s
                JOIN item_master i ON i.item_code=s."{code_column}"
                WHERE COALESCE(TRIM(i.item_name),'')
                   <> COALESCE(TRIM(s."{name_column}"),'')
                """
            ).fetchone()[0]
            if name_mismatch:
                raise RuntimeError(
                    "material_master.material_name differs from "
                    f"item_master.item_name: {name_mismatch} rows"
                )


def _parse_version_row(row: sqlite3.Row) -> tuple:
    raw = row["specification"]
    payload = {}
    if raw not in (None, ""):
        try:
            payload = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid version specification JSON for {row['version_code']}"
            ) from exc
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Version specification must be a JSON object: {row['version_code']}"
            )

    def _number(name: str):
        value = payload.get(name)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid numeric {name} for {row['version_code']}: {value!r}"
            ) from exc

    return (
        row["version_code"],
        row["version_no"],
        payload.get("product_name"),
        payload.get("product_type"),
        _number("screen_size_inch"),
        payload.get("resolution"),
        _number("refresh_hz"),
        payload.get("market"),
        payload.get("legacy_product_id"),
        payload.get("material_specification"),
        payload.get("test_dataset"),
    )


def migrate_connection_v8_to_v9(connection: sqlite3.Connection) -> dict[str, int]:
    connection.row_factory = sqlite3.Row
    version = _current_version(connection)
    if version == TARGET_VERSION:
        return {
            "source_version": TARGET_VERSION,
            "target_version": TARGET_VERSION,
            "version_rows": connection.execute(
                "SELECT COUNT(*) FROM version_master"
            ).fetchone()[0],
            "assembly_rows": connection.execute(
                "SELECT COUNT(*) FROM assembly_master"
            ).fetchone()[0],
            "material_rows": connection.execute(
                "SELECT COUNT(*) FROM material_master"
            ).fetchone()[0],
        }
    if version != SOURCE_VERSION:
        raise RuntimeError(
            f"DB v9 migration requires schema version {SOURCE_VERSION}; actual={version}"
        )

    _validate_v8_shape(connection)
    _validate_registry_consistency(connection)

    version_rows = list(
        connection.execute("SELECT * FROM version_master ORDER BY version_code")
    )
    assembly_rows = list(
        connection.execute("SELECT * FROM assembly_master ORDER BY assembly_code")
    )
    material_rows = list(
        connection.execute("SELECT * FROM material_master ORDER BY material_code")
    )
    converted_versions = [_parse_version_row(row) for row in version_rows]

    connection.commit()
    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute(
            """
            CREATE TABLE version_master_v9 (
              version_code TEXT PRIMARY KEY,
              version_no TEXT,
              product_name TEXT,
              product_type TEXT,
              screen_size_inch REAL
                CHECK(screen_size_inch IS NULL OR screen_size_inch > 0),
              resolution TEXT,
              refresh_hz REAL
                CHECK(refresh_hz IS NULL OR refresh_hz > 0),
              market TEXT,
              legacy_product_id TEXT,
              material_specification TEXT,
              dataset_tag TEXT,
              FOREIGN KEY(version_code) REFERENCES item_master(item_code)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO version_master_v9(
              version_code,version_no,product_name,product_type,
              screen_size_inch,resolution,refresh_hz,market,
              legacy_product_id,material_specification,dataset_tag
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            converted_versions,
        )

        connection.execute(
            """
            CREATE TABLE assembly_master_v9 (
              assembly_code TEXT PRIMARY KEY,
              process_name TEXT NOT NULL
                CHECK(process_name IN ('OLB','CP','BIN','LC','CF','TFT')),
              usage_type TEXT NOT NULL DEFAULT 'DEDICATED'
                CHECK(usage_type IN ('COMMON','DEDICATED')),
              specification TEXT,
              FOREIGN KEY(assembly_code) REFERENCES item_master(item_code)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO assembly_master_v9(
              assembly_code,process_name,usage_type,specification
            ) VALUES(?,?,?,?)
            """,
            [
                (
                    row["assembly_code"],
                    row["process_name"],
                    row["usage_type"],
                    row["specification"],
                )
                for row in assembly_rows
            ],
        )

        connection.execute(
            """
            CREATE TABLE material_master_v9 (
              material_code TEXT PRIMARY KEY,
              material_name TEXT NOT NULL,
              material_group TEXT,
              unit TEXT,
              specification TEXT,
              FOREIGN KEY(material_code) REFERENCES item_master(item_code)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO material_master_v9(
              material_code,material_name,material_group,unit,specification
            ) VALUES(?,?,?,?,?)
            """,
            [
                (
                    row["material_code"],
                    row["material_name"],
                    row["material_group"],
                    row["unit"],
                    row["specification"],
                )
                for row in material_rows
            ],
        )

        connection.execute("DROP TABLE version_master")
        connection.execute("DROP TABLE assembly_master")
        connection.execute("DROP TABLE material_master")

        connection.execute(
            "ALTER TABLE version_master_v9 RENAME TO version_master"
        )
        connection.execute(
            "ALTER TABLE assembly_master_v9 RENAME TO assembly_master"
        )
        connection.execute(
            "ALTER TABLE material_master_v9 RENAME TO material_master"
        )

        connection.execute(
            """
            INSERT INTO schema_versions(version,description)
            VALUES(9,'Normalized item subtype authority and typed version metadata')
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys=ON")

    fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise RuntimeError(
            f"Foreign key errors after DB v9 migration: {len(fk_errors)}"
        )

    return {
        "source_version": SOURCE_VERSION,
        "target_version": TARGET_VERSION,
        "version_rows": len(version_rows),
        "assembly_rows": len(assembly_rows),
        "material_rows": len(material_rows),
    }


def migrate_database_v8_to_v9(
    database_path: str | Path,
    *,
    create_backup: bool = True,
) -> tuple[dict[str, int], Path | None]:
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    backup_path: Path | None = None
    if create_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_name(f"{path.name}.v8_backup_{stamp}")
        shutil.copy2(path, backup_path)

    connection = sqlite3.connect(path)
    try:
        result = migrate_connection_v8_to_v9(connection)
    except Exception:
        connection.close()
        if backup_path is not None:
            shutil.copy2(backup_path, path)
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return result, backup_path


__all__ = [
    "SOURCE_VERSION",
    "TARGET_VERSION",
    "migrate_connection_v8_to_v9",
    "migrate_database_v8_to_v9",
]
