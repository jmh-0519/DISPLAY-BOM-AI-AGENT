from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.release_gate import (
    evaluate_release_gate,
    load_json_report,
    run_full_regression,
    write_release_markdown,
    write_release_report,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consolidate Accuracy, Performance and Safety reports and enforce the v3.1.1 release gate."
    )
    root = PROJECT_ROOT / ".perf" / "evaluation"
    parser.add_argument("--accuracy", default=str(root / "accuracy_report.json"))
    parser.add_argument("--performance", default=str(root / "performance_report.json"))
    parser.add_argument("--safety", default=str(root / "safety_report.json"))
    parser.add_argument("--output", default=str(root / "release_gate_report.json"))
    parser.add_argument("--markdown", default=str(root / "evaluation_report.md"))
    parser.add_argument("--accuracy-threshold", type=float, default=100.0)
    parser.add_argument("--safety-threshold", type=float, default=100.0)
    parser.add_argument("--p95-ms", type=float, default=5000.0)
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run the complete project regression and include it in the release gate.",
    )
    parser.add_argument(
        "--require-tests",
        action="store_true",
        help="Fail immediately unless --run-tests is supplied.",
    )
    return parser.parse_args()


def _print_metric(name: str, value, suffix: str = "%") -> None:
    if isinstance(value, (int, float)):
        print(f"  {name:<24}: {float(value):.2f}{suffix}")
    else:
        print(f"  {name:<24}: N/A")


def main() -> int:
    args = _arguments()
    if args.require_tests and not args.run_tests:
        print("RELEASE GATE: FAIL (--require-tests requires --run-tests)")
        return 2

    accuracy = load_json_report(args.accuracy)
    performance = load_json_report(args.performance)
    safety = load_json_report(args.safety)

    tests = None
    if args.run_tests:
        print("Running full regression...")
        tests = run_full_regression(project_root=PROJECT_ROOT)
        print(tests.get("output_tail") or "")

    report = evaluate_release_gate(
        accuracy,
        performance,
        safety,
        accuracy_threshold=args.accuracy_threshold,
        safety_threshold=args.safety_threshold,
        p95_latency_threshold_ms=args.p95_ms,
        tests=tests,
    )
    output = write_release_report(report, args.output)
    markdown = write_release_markdown(report, args.markdown)

    summary = report.get("summary") or {}
    print("\nAgent Evaluation - v3.1.1 Release Gate")
    print(f"run_id           : {report.get('run_id') or 'MISMATCH/UNAVAILABLE'}")
    print(f"turns            : {summary.get('turns')}")

    print("\nAccuracy")
    for label, key in (
        ("Intent", "intent"),
        ("Route", "route"),
        ("Tool Selection", "tool_selection"),
        ("Tool Argument", "tool_arguments"),
    ):
        _print_metric(label, (summary.get("accuracy") or {}).get(key))

    perf = summary.get("performance") or {}
    print("\nPerformance")
    _print_metric("P95 latency", perf.get("p95_latency_ms"), "ms")
    _print_metric("<= 5 sec turns", perf.get("within_target_rate_pct"))
    _print_metric("LLM-free turns", perf.get("llm_free_rate_pct"))

    safe = summary.get("safety") or {}
    print("\nSafety")
    print(
        f"  assertions              : {safe.get('passed_assertions')}/{safe.get('total_assertions')} "
        f"(fail={safe.get('failed_assertions')})"
    )

    print("\nRelease Checks")
    for check in report.get("checks") or []:
        print(f"  [{'PASS' if check.get('passed') else 'FAIL'}] {check.get('name')}")

    print(f"\njson report : {output}")
    print(f"md report   : {markdown}")
    print(f"RELEASE GATE: {report.get('status')}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
