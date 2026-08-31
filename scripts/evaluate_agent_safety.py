from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_cases
from evaluation.evaluator import load_fixture_manifest, load_observations_jsonl
from evaluation.safety import AgentSafetyEvaluator, write_safety_report


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Ground Truth safety/workflow assertions from deterministic runtime evidence."
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument(
        "--observations",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "agent_observations.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Fixture manifest. Default: <observations>.manifest.json",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "safety_report.json"),
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
        help="Return non-zero when expected observations or safety evidence are missing.",
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
        observations = [
            row for row in observations
            if str(row.get("case_id") or "").upper() in wanted
        ]
    fixtures = load_fixture_manifest(manifest_path)

    report = AgentSafetyEvaluator(cases, fixtures).evaluate(observations)
    output = write_safety_report(report, args.output)

    print("\nAgent Evaluation - Safety / Workflow / Hallucination")
    print(f"cases expected      : {report.expected_case_count}")
    print(f"turns expected      : {report.expected_turn_count}")
    print(f"turns observed      : {report.observed_turn_count}")
    print(f"safety turns        : {report.evaluated_turn_count}")
    print(f"assertions          : {report.safety_assertion_count}")
    print(f"observation complete: {'YES' if report.complete else 'NO'}")
    print(f"evidence complete   : {'YES' if report.evidence_complete else 'NO'}")

    print("\nSafety Assertions")
    for name, metric in report.assertion_metrics.items():
        accuracy = "N/A" if metric["accuracy"] is None else f"{metric['accuracy']:.2f}%"
        print(
            f"  {name:<38} {accuracy:>8}  "
            f"({metric['passed']}/{metric['eligible']}, fail={metric['failed']})"
        )

    if report.failure_counts:
        print("\nViolations")
        for name, count in report.failure_counts.items():
            print(f"  {name}: {count}")
        failed_turns = [row for row in report.turn_results if not row.passed]
        for row in failed_turns[:20]:
            print(f"  - {row.case_id}#{row.turn_index}: {', '.join(row.failures)}")
        if len(failed_turns) > 20:
            print(f"  ... {len(failed_turns) - 20} more failed turns (see report JSON)")

    if report.evidence_missing_turns:
        print("\nEvidence Missing")
        for value in report.evidence_missing_turns[:20]:
            print(f"  - {value}")
        if len(report.evidence_missing_turns) > 20:
            print(f"  ... {len(report.evidence_missing_turns) - 20} more")

    print(f"\nreport: {output}")

    if args.require_complete and (not report.complete or not report.evidence_complete):
        print("SAFETY: INCOMPLETE")
        return 2
    if report.failed_assertion_count:
        print("SAFETY: FAIL")
        return 1
    print("SAFETY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
