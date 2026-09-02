from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from database.schema import CORE_SCHEMA_TABLES, CORE_SCHEMA_VERSION
from scripts.database_lifecycle import DEFAULT_RUNTIME_DATABASE, DEFAULT_SEED_DATABASE
from scripts.verify_design_change_business_sample import verify as verify_business_sample


SEED_EMPTY_TABLES = (
    "change_requests",
    "change_actions",
    "change_action_reasons",
    "candidate_evaluations",
    "candidate_rule_results",
    "change_approvals",
    "change_impacts",
    "change_previews",
    "change_apply_results",
)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def verify_schema_contract(path: str | Path) -> dict[str, object]:
    database_path = Path(path)
    if not database_path.is_file():
        raise FileNotFoundError(f"DB file does not exist: {database_path}")

    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_versions"
        ).fetchone()[0]
        if version != CORE_SCHEMA_VERSION:
            raise RuntimeError(
                f"Schema version mismatch: expected={CORE_SCHEMA_VERSION} actual={version}"
            )

        tables = _table_names(connection)
        expected = set(CORE_SCHEMA_TABLES)
        if tables != expected:
            raise RuntimeError(
                "Clean Core table contract mismatch: "
                f"missing={sorted(expected - tables)} "
                f"unexpected={sorted(tables - expected)}"
            )

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"Foreign key errors: {len(foreign_key_errors)}")

        return {
            "schema_version": version,
            "table_count": len(tables),
            "foreign_key_errors": 0,
        }
    finally:
        connection.close()


def verify_seed_baseline(path: str | Path) -> dict[str, object]:
    schema_result = verify_schema_contract(path)
    connection = sqlite3.connect(Path(path))
    try:
        non_empty = {
            table_name: connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            for table_name in SEED_EMPTY_TABLES
        }
        non_empty = {name: count for name, count in non_empty.items() if count}
        if non_empty:
            raise RuntimeError(
                f"Canonical Seed DB contains workflow history: {non_empty}"
            )

        sample_versions = connection.execute(
            "SELECT COUNT(*) FROM version_master "
            "WHERE dataset_tag='DESIGN_CHANGE_BUSINESS_SAMPLE'"
        ).fetchone()[0]
        if sample_versions:
            raise RuntimeError(
                "Canonical Seed DB must not contain generated design-change sample versions"
            )

        baseline_exists = connection.execute(
            "SELECT 1 FROM version_master WHERE version_code='LTA400HR01-001'"
        ).fetchone()
        if not baseline_exists:
            raise RuntimeError("Canonical Seed DB baseline model is missing")

        return {
            **schema_result,
            "workflow_history_rows": 0,
            "generated_sample_versions": 0,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify canonical Seed and Runtime databases for Clean Core freeze."
    )
    parser.add_argument("--seed-database", default=str(DEFAULT_SEED_DATABASE))
    parser.add_argument("--runtime-database", default=str(DEFAULT_RUNTIME_DATABASE))
    args = parser.parse_args()

    seed_result = verify_seed_baseline(args.seed_database)
    runtime_result = verify_schema_contract(args.runtime_database)
    business_result = verify_business_sample(Path(args.runtime_database))

    print("Clean Core database verification passed")
    print(f"- seed: {seed_result}")
    print(f"- runtime: {runtime_result}")
    print(f"- business_sample: {business_result}")


if __name__ == "__main__":
    main()
