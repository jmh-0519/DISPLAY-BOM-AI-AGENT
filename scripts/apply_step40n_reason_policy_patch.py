from __future__ import annotations

import argparse
from pathlib import Path

from database import SQLiteDatabase


USER_REQUEST_SCOPES = [
    ("MATERIAL", "REPLACE"),
    ("MATERIAL", "ADD"),
    ("MATERIAL", "DELETE"),
    ("MATERIAL", "QUANTITY_CHANGE"),
    ("ASSY", "REPLACE"),
    ("ASSY", "ADD"),
    ("ASSY", "DELETE"),
    ("ASSY", "QUANTITY_CHANGE"),
]


def apply(database_path: Path) -> None:
    database = SQLiteDatabase(database_path)
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO change_reason_master(
                reason_code, reason_name_ko, description, category,
                active_yn, valid_from
            ) VALUES(
                'USER_REQUEST', '사용자 요청',
                '사용자가 별도 업무 사유를 명시하지 않은 직접 설계변경 요청',
                'GENERAL', 'Y', '2026-01-01'
            )
            """
        )
        for target_type, action_type in USER_REQUEST_SCOPES:
            connection.execute(
                """
                INSERT OR IGNORE INTO change_reason_scope(
                    reason_code, target_type, action_type, active_yn
                ) VALUES('USER_REQUEST', ?, ?, 'Y')
                """,
                (target_type, action_type),
            )

    print(f"STEP40-N reason policy patch applied: {database_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        default="data/display_bom.db",
        help="SQLite database path",
    )
    args = parser.parse_args()
    apply(Path(args.database))


if __name__ == "__main__":
    main()
