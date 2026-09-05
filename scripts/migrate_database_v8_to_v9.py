from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from database import SchemaManager, SQLiteDatabase
from database.migrations.v8_to_v9 import migrate_database_v8_to_v9


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup and migrate one Display BOM SQLite DB from v8 to v9."
    )
    parser.add_argument("--database", default="data/display_bom.db")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create the automatic pre-migration backup.",
    )
    args = parser.parse_args()

    path = Path(args.database)
    result, backup = migrate_database_v8_to_v9(
        path,
        create_backup=not args.no_backup,
    )

    try:
        database = SQLiteDatabase(path)
        SchemaManager(database).initialize()
    except Exception:
        if backup is not None and backup.is_file():
            shutil.copy2(backup, path)
        raise

    print("Display BOM DB v8 -> v9 migration completed")
    print(f"- database: {path}")
    print(f"- backup: {backup if backup else '(disabled)'}")
    for key, value in result.items():
        print(f"- {key}: {value}")
    print("- next: python -m scripts.validate_database_schema --database " + str(path))


if __name__ == "__main__":
    main()
