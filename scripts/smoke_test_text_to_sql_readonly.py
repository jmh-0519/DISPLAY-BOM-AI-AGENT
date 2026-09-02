from __future__ import annotations

from core.database_config import sqlite_database_path
from text_to_sql.read_only_executor import ReadOnlySqlExecutor


def main() -> None:
    executor = ReadOnlySqlExecutor(sqlite_database_path())
    sql = """
    SELECT
        COALESCE(m.material_group, '(UNSPECIFIED)') AS material_group,
        COUNT(*) AS material_count
    FROM material_master m
    JOIN item_master i ON i.item_code=m.material_code
    WHERE i.item_type='MATERIAL' AND i.active_yn='Y'
    GROUP BY COALESCE(m.material_group, '(UNSPECIFIED)')
    ORDER BY material_count DESC, material_group
    LIMIT 10
    """.strip()
    result = executor.execute(sql)
    print("Text-to-SQL read-only smoke test passed")
    print(f"- rows: {result.row_count}")
    print(f"- truncated: {result.truncated}")
    print(f"- elapsed_ms: {result.elapsed_ms:.2f}")
    for row in result.rows:
        print(f"  - {row}")


if __name__ == "__main__":
    main()
