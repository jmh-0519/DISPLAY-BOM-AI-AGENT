from __future__ import annotations

import argparse
from pathlib import Path

from database import SQLiteDatabase, SchemaManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Display BOM SQLite DB 초기화")
    parser.add_argument("--database", default="data/display_bom.db")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="지정한 기존 DB 파일을 삭제하고 현재 Schema로 다시 생성",
    )
    args = parser.parse_args()
    path = Path(args.database)
    if args.recreate and path.exists():
        path.unlink()
    manager = SchemaManager(SQLiteDatabase(path))
    manager.initialize()
    print(f"SQLite schema v{manager.current_version()} initialized: {path}")


if __name__ == "__main__":
    main()
