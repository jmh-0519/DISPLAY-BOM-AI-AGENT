from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from database import SchemaManager, SQLiteDatabase
from scripts.seed_phase3_business_sample import seed_phase3_business_sample
from scripts.verify_phase3_business_sample import verify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_DATABASE = PROJECT_ROOT / "data" / "display_bom_step27_seed.db"
DEFAULT_RUNTIME_DATABASE = PROJECT_ROOT / "data" / "display_bom.db"
DEFAULT_TEST_DATABASE = PROJECT_ROOT / "data" / "test_display_bom.db"


def rebuild_latest_database(
    target_path: str | Path,
    *,
    baseline_path: str | Path = DEFAULT_BASELINE_DATABASE,
) -> dict[str, int]:
    """Atomically build one deterministic latest-design database.

    The cleaned STEP27 seed database is the immutable business seed input.
    Existing Phase2 workflow/review history is preserved and retired P3-*
    synthetic fixtures are absent. Latest Schema, Plant data, reason metadata and
    the Phase3 business sample are
    applied to a temporary file.  The requested target is replaced only after
    all verification gates pass.
    """
    target = Path(target_path).resolve()
    baseline = Path(baseline_path).resolve()

    if target == baseline:
        raise ValueError("기준 Seed DB 자체를 재생성 대상으로 사용할 수 없습니다.")
    if not baseline.is_file():
        raise FileNotFoundError(f"기준 Seed DB가 없습니다: {baseline}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.building")
    try:
        shutil.copy2(baseline, temporary)
        database = SQLiteDatabase(temporary)
        SchemaManager(database).initialize()
        seed_phase3_business_sample(database)
        result = verify(temporary)
        os.replace(temporary, target)
        return result
    finally:
        if temporary.exists():
            temporary.unlink()

