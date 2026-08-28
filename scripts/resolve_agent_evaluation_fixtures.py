from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_cases
from evaluation.fixtures import EvaluationFixtureResolver


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve AE-01 dynamic fixtures from the current SQLite BOM database."
    )
    parser.add_argument("--database", default=str(PROJECT_ROOT / "data" / "display_bom.db"))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--json", action="store_true", help="Print one JSON document.")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    cases = load_evaluation_cases(args.dataset)
    resolved = EvaluationFixtureResolver(args.database).resolve()
    required = sorted({name for case in cases for name in case.fixture_requirements})
    missing = sorted(set(required) - set(resolved.values))
    if missing:
        raise SystemExit(f"Missing dataset fixtures: {missing}")

    payload = {
        "database": str(Path(args.database).resolve()),
        "dataset_case_count": len(cases),
        "required_fixture_count": len(required),
        "fixtures": resolved.values,
        "evidence": resolved.evidence,
        "validation": "PASS",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=== Agent Evaluation Dynamic Fixtures ===")
        for key, value in sorted(resolved.values.items()):
            print(f"{key:<20} {value}")
        print(f"\ncases: {len(cases)}")
        print(f"required fixtures: {len(required)}")
        print("VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
