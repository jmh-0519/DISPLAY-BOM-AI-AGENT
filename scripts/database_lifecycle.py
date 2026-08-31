from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from database import SchemaManager, SQLiteDatabase
from scripts.seed_phase3_business_sample import seed_phase3_business_sample
from scripts.verify_phase3_business_sample import verify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_DATABASE = PROJECT_ROOT / "data" / "display_bom_seed.db"
DEFAULT_RUNTIME_DATABASE = PROJECT_ROOT / "data" / "display_bom.db"
DEFAULT_TEST_DATABASE = PROJECT_ROOT / "data" / "test_display_bom.db"


def rebuild_latest_database(
    target_path: str | Path,
    *,
    seed_path: str | Path = DEFAULT_SEED_DATABASE,
) -> dict[str, int]:
    """Atomically build one deterministic latest-design database.

    The canonical seed database is the immutable business-data input.
    Latest schema and current business sample data are applied to a temporary
    file. The requested target is replaced only after all verification gates pass.
    """
    target = Path(target_path).resolve()
    seed = Path(seed_path).resolve()

    if target == seed:
        raise ValueError("기준 Seed DB 자체를 재생성 대상으로 사용할 수 없습니다.")
    if not seed.is_file():
        raise FileNotFoundError(f"기준 Seed DB가 없습니다: {seed}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.building")
    try:
        shutil.copy2(seed, temporary)
        database = SQLiteDatabase(temporary)
        SchemaManager(database).initialize()
        seed_phase3_business_sample(database)
        result = verify(temporary)
        os.replace(temporary, target)
        return result
    finally:
        if temporary.exists():
            temporary.unlink()

