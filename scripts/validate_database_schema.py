from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from database.schema import CORE_SCHEMA_VERSION


EXPECTED_VERSION_COLUMNS = (
    "version_code",
    "version_no",
    "product_name",
    "product_type",
    "screen_size_inch",
    "resolution",
    "refresh_hz",
    "market",
    "legacy_product_id",
    "material_specification",
    "dataset_tag",
)
EXPECTED_ASSEMBLY_COLUMNS = (
    "assembly_code",
    "process_name",
    "usage_type",
    "specification",
)
EXPECTED_MATERIAL_COLUMNS = (
    "material_code",
    "material_name",
    "material_group",
    "unit",
    "specification",
)


def _columns(connection, table_name: str) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    )


def validate(path: str | Path) -> dict[str, object]:
    database_path = Path(path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_versions"
        ).fetchone()[0]
        if version != CORE_SCHEMA_VERSION or version != 9:
            raise RuntimeError(
                f"Schema version mismatch: expected=9 actual={version}"
            )

        expected = {
            "version_master": EXPECTED_VERSION_COLUMNS,
            "assembly_master": EXPECTED_ASSEMBLY_COLUMNS,
            "material_master": EXPECTED_MATERIAL_COLUMNS,
        }
        for table_name, columns in expected.items():
            actual = _columns(connection, table_name)
            if actual != columns:
                raise RuntimeError(
                    f"{table_name} columns mismatch: expected={columns} actual={actual}"
                )

        item_count = connection.execute(
            "SELECT COUNT(*) FROM item_master"
        ).fetchone()[0]
        subtype_count = sum(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("version_master", "assembly_master", "material_master")
        )
        if item_count != subtype_count:
            raise RuntimeError(
                f"Item registry/subtype count mismatch: item={item_count} subtype={subtype_count}"
            )

        wrong_subtype = connection.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT v.version_code code FROM version_master v
              JOIN item_master i ON i.item_code=v.version_code
              WHERE i.item_type<>'VERSION'
              UNION ALL
              SELECT a.assembly_code FROM assembly_master a
              JOIN item_master i ON i.item_code=a.assembly_code
              WHERE i.item_type<>'ASSEMBLY'
              UNION ALL
              SELECT m.material_code FROM material_master m
              JOIN item_master i ON i.item_code=m.material_code
              WHERE i.item_type<>'MATERIAL'
            )
            """
        ).fetchone()[0]
        if wrong_subtype:
            raise RuntimeError(f"Wrong subtype registry mapping: {wrong_subtype}")

        mirror_mismatch = connection.execute(
            """
            SELECT COUNT(*)
            FROM material_master m
            JOIN item_master i ON i.item_code=m.material_code
            WHERE COALESCE(TRIM(m.material_name),'')
               <> COALESCE(TRIM(i.item_name),'')
            """
        ).fetchone()[0]
        if mirror_mismatch:
            raise RuntimeError(
                f"material_name compatibility mirror mismatch: {mirror_mismatch}"
            )

        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key errors: {len(fk_errors)}")

        typed_versions = connection.execute(
            """
            SELECT COUNT(*)
            FROM version_master
            WHERE screen_size_inch IS NOT NULL
              AND resolution IS NOT NULL
              AND refresh_hz IS NOT NULL
              AND market IS NOT NULL
            """
        ).fetchone()[0]

        return {
            "schema_version": version,
            "item_rows": item_count,
            "subtype_rows": subtype_count,
            "version_rows": connection.execute(
                "SELECT COUNT(*) FROM version_master"
            ).fetchone()[0],
            "assembly_rows": connection.execute(
                "SELECT COUNT(*) FROM assembly_master"
            ).fetchone()[0],
            "material_rows": connection.execute(
                "SELECT COUNT(*) FROM material_master"
            ).fetchone()[0],
            "typed_version_rows": typed_versions,
            "business_sample_versions": connection.execute(
                "SELECT COUNT(*) FROM version_master "
                "WHERE dataset_tag='DESIGN_CHANGE_BUSINESS_SAMPLE'"
            ).fetchone()[0],
            "supplier_item_rows": connection.execute(
                "SELECT COUNT(*) FROM supplier_items"
            ).fetchone()[0],
            "foreign_key_errors": 0,
            "material_name_mirror_mismatch": 0,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Display BOM database schema normalized subtype schema."
    )
    parser.add_argument("--database", default="data/display_bom.db")
    args = parser.parse_args()
    result = validate(args.database)
    print("Display BOM database schema validation passed")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
