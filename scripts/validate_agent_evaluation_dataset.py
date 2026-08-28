from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, dataset_summary, load_evaluation_cases



def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Display BOM Agent Evaluation Dataset."
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Evaluation JSONL dataset path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    cases = load_evaluation_cases(args.dataset)
    summary = dataset_summary(cases)

    print("=== Display BOM Agent Evaluation Dataset ===")
    print(f"dataset: {Path(args.dataset).resolve()}")
    print(f"cases: {summary['case_count']}")
    print(f"turns: {summary['turn_count']}")
    print("\nCategory coverage")
    for name, count in summary["by_category"].items():
        print(f"  {name:<18} {count:>3}")
    print("\nExecution path coverage")
    for name, count in summary["by_execution_path"].items():
        print(f"  {name:<22} {count:>3}")
    print("\nInteraction coverage")
    for name, count in summary["by_interaction"].items():
        print(f"  {name:<22} {count:>3}")

    print("\nVALIDATION: PASS")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
