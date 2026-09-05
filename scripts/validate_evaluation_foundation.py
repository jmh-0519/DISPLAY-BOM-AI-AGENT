from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import CURRENT_DATASET_PATH
from evaluation.foundation import evaluate_foundation, write_foundation_report


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the current evaluation foundation without live Azure evaluation calls.")
    parser.add_argument("--dataset", default=str(CURRENT_DATASET_PATH))
    parser.add_argument("--output", default=str(PROJECT_ROOT / ".perf" / "evaluation" / "foundation_report.json"))
    parser.add_argument("--skip-validators", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    report = evaluate_foundation(
        project_root=PROJECT_ROOT,
        dataset_path=args.dataset,
        run_validators=not args.skip_validators,
    )
    output = write_foundation_report(report, args.output)
    data = report["dataset"]
    planner = report["planner"]
    context = report["context"]
    mapping = report["route_mapping"]
    validators = report["validators"]

    print(f"Evaluation Foundation {report['status']}")
    print(f"agent_eval_cases={data['case_count']}")
    print(f"agent_eval_turns={data['turn_count']}")
    print("execution_paths=" + ",".join(f"{k}:{v}" for k, v in data["required_execution_path_coverage"].items()))
    print(f"planner_accuracy={planner['accuracy_pct']:.2f}% ({planner['passed_count']}/{planner['case_count']})")
    print(f"context_gate={context['gate_passed']}/{context['gate_case_count']}")
    print(f"route_mapping={mapping['mapped_count']}/{mapping['required_count']}")
    print(f"architecture_validators={validators['passed_count']}/{validators['count']}")
    print("request_creation_authority=NO")
    print("approval_authority=NO")
    print("production_bom_write_authority=NO")
    print(f"report={output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
