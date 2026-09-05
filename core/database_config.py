from __future__ import annotations

import os
from pathlib import Path


def sqlite_database_path() -> Path:
    """Return the single runtime database path.

    The current release uses a single SQLite storage mode.  The path remains configurable so
    tests and deployments can use an isolated SQLite file.
    """
    return Path(os.getenv("BOM_SQLITE_PATH", "data/display_bom.db"))

