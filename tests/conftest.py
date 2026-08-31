from __future__ import annotations

import os
from pathlib import Path

from scripts.database_lifecycle import DEFAULT_TEST_DATABASE, rebuild_latest_database


# Raw `pytest` and `python -m scripts.run_tests` use the same isolated DB.
# The application runtime DB is never opened or modified by the test session.
os.environ["BOM_SQLITE_PATH"] = str(DEFAULT_TEST_DATABASE)


def _remove_test_database_artifacts() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DEFAULT_TEST_DATABASE}{suffix}").unlink(missing_ok=True)


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    _remove_test_database_artifacts()
    rebuild_latest_database(DEFAULT_TEST_DATABASE)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    _remove_test_database_artifacts()
