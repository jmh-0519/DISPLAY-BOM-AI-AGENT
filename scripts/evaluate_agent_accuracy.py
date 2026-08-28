from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_cases
from evaluation.evaluator import (
    AgentAccuracyEvaluator,
    load_fixture_manifest,
    load_observations_jsonl,
    write_accuracy_report,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Agent runtime observations with AE-01 Ground Truth."
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument(
        "--observations",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae02_observations.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Fixture manifest. Default: <observations>.manifest.json",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae03_accuracy_report.json"),
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Evaluate only selected Case IDs. Repeatable.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Return non-zero when any expected observation is missing/duplicated.",
    )
    return parser.parse_args()


def _select_cases(cases, case_ids: list[str]):
    if not case_ids:
        return list(cases)
    wanted = {value.strip().upper() for value in case_ids}
    selected = [case for case in cases if case.case_id in wanted]
    missing = wanted - {case.case_id for case in selected}
    if missing:
        raise SystemExit(f"Unknown case_id: {sorted(missing)}")
    return selected


def main() -> int:
    args = _arguments()
    observation_path = Path(args.observations).resolve()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else observation_path.with_suffix(".manifest.json")
    )
    cases = _select_cases(load_evaluation_cases(args.dataset), args.case_id)
    observations = load_observations_jsonl(observation_path)
    if args.case_id:
        wanted = {case.case_id for case in cases}
        observations = [row for row in observations if str(row.get("case_id") or "").upper() in wanted]
    fixtures = load_fixture_manifest(manifest_path)

    report = AgentAccuracyEvaluator(cases, fixtures).evaluate(observations)
    output = write_accuracy_report(report, args.output)

    labels = {
        "intent": "Intent Accuracy",
        "route": "Route Accuracy",
        "tool_selection": "Tool Selection Accuracy",
        "tool_arguments": "Tool Argument Accuracy",
    }
    print("\nAgent Evaluation - AE03 Accuracy")
    print(f"cases expected   : {report.expected_case_count}")
    print(f"turns expected   : {report.expected_turn_count}")
    print(f"turns observed   : {report.observed_turn_count}")
    print(f"turns evaluated  : {report.evaluated_turn_count}")
    print(f"complete         : {'YES' if report.complete else 'NO'}")
    print()
    for metric, label in labels.items():
        row = report.metrics[metric]
        accuracy = "N/A" if row["accuracy"] is None else f"{row['accuracy']:.2f}%"
        print(
            f"{label:<25} {accuracy:>8}  "
            f"({row['passed']}/{row['eligible']}, fail={row['failed']})"
        )

    if report.failure_counts:
        print("\nFailures")
        for name, count in report.failure_counts.items():
            print(f"  {name}: {count}")
        failed_turns = [result for result in report.turn_results if not result.passed]
        for result in failed_turns[:20]:
            print(
                f"  - {result.case_id}#{result.turn_index}: "
                f"{', '.join(result.failures)}"
            )
        if len(failed_turns) > 20:
            print(f"  ... {len(failed_turns) - 20} more failed turns (see report JSON)")

    if report.missing_observations:
        print(f"\nmissing observations: {len(report.missing_observations)}")
    if report.duplicate_observations:
        print(f"duplicate observations: {len(report.duplicate_observations)}")
    print(f"\nreport: {output}")

    if args.require_complete and not report.complete:
        print("EVALUATION: INCOMPLETE")
        return 2
    print("EVALUATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
