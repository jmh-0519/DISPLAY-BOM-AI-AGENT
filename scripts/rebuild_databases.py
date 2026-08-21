from __future__ import annotations

import argparse
from pathlib import Path

from scripts.database_lifecycle import (
    DEFAULT_BASELINE_DATABASE,
    DEFAULT_RUNTIME_DATABASE,
    DEFAULT_TEST_DATABASE,
    rebuild_latest_database,
)


def _targets(profile: str, runtime: Path, test: Path) -> tuple[Path, ...]:
    if profile == "runtime":
        return (runtime,)
    if profile == "test":
        return (test,)
    return (runtime, test)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="현재 확정 설계 기준으로 Runtime/Test SQLite DB를 재생성합니다."
    )
    parser.add_argument(
        "--profile",
        choices=("runtime", "test", "all"),
        default="all",
    )
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE_DATABASE))
    parser.add_argument("--runtime-database", default=str(DEFAULT_RUNTIME_DATABASE))
    parser.add_argument("--test-database", default=str(DEFAULT_TEST_DATABASE))
    args = parser.parse_args()

    for target in _targets(
        args.profile,
        Path(args.runtime_database),
        Path(args.test_database),
    ):
        result = rebuild_latest_database(target, baseline_path=args.baseline)
        print(f"Latest-design database rebuilt: {target}")
        for name, value in result.items():
            print(f"- {name}: {value}")


if __name__ == "__main__":
    main()

