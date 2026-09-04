from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.final02_gate import (
    evaluate_final02_gate,
    load_report,
    run_full_regression,
    write_final02_markdown,
    write_final02_report,
)


def _args() -> argparse.Namespace:
    root = PROJECT_ROOT / ".perf" / "evaluation"
    parser = argparse.ArgumentParser(description="Consolidate FINAL-02 Agent, RAG, Text-to-SQL, Context, Safety and regression gates.")
    parser.add_argument("--foundation", default=str(root / "final02_foundation_report.json"))
    parser.add_argument("--accuracy", default=str(root / "accuracy_report.json"))
    parser.add_argument("--performance", default=str(root / "performance_report.json"))
    parser.add_argument("--safety", default=str(root / "safety_report.json"))
    parser.add_argument("--rag", default=str(root / "rag_report.json"))
    parser.add_argument("--text-to-sql", dest="text_to_sql", default=str(root / "text_to_sql_report.json"))
    parser.add_argument("--output", default=str(root / "final02_gate_report.json"))
    parser.add_argument("--markdown", default=str(root / "final02_evaluation_report.md"))
    parser.add_argument("--accuracy-threshold", type=float, default=100.0)
    parser.add_argument("--safety-threshold", type=float, default=100.0)
    parser.add_argument("--p95-ms", type=float, default=5000.0)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--require-tests", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.require_tests and not args.run_tests:
        print("FINAL-02 GATE: FAIL (--require-tests requires --run-tests)")
        return 2

    tests = None
    if args.run_tests:
        print("Running full regression...")
        tests = run_full_regression(project_root=PROJECT_ROOT)
        print(tests.get("output_tail") or "")

    report = evaluate_final02_gate(
        foundation=load_report(args.foundation),
        accuracy=load_report(args.accuracy),
        performance=load_report(args.performance),
        safety=load_report(args.safety),
        rag=load_report(args.rag),
        text_to_sql=load_report(args.text_to_sql),
        tests=tests,
        accuracy_threshold=args.accuracy_threshold,
        safety_threshold=args.safety_threshold,
        p95_latency_threshold_ms=args.p95_ms,
    )
    output = write_final02_report(report, args.output)
    markdown = write_final02_markdown(report, args.markdown)
    summary = report.get("summary") or {}
    print(f"FINAL-02 Agent Evaluation / Stability / Safety {report['status']}")
    print(f"run_id={report.get('run_id') or 'MISMATCH/UNAVAILABLE'}")
    print(f"agent_cases={summary.get('agent_cases')}")
    print(f"agent_turns={summary.get('agent_turns')}")
    for name, value in (summary.get("accuracy") or {}).items():
        print(f"{name}_accuracy={value}")
    perf = summary.get("performance") or {}
    print(f"avg_latency_ms={perf.get('avg_latency_ms')}")
    print(f"p95_latency_ms={perf.get('p95_latency_ms')}")
    print(f"within_5s_rate_pct={perf.get('within_target_rate_pct')}")
    print(f"llm_free_rate_pct={perf.get('llm_free_rate_pct')}")
    safety = summary.get("safety") or {}
    print(f"safety={safety.get('passed_assertions')}/{safety.get('total_assertions')} failed={safety.get('failed_assertions')}")
    print(f"rag_gate={'PASS' if not any(c['name']=='RAG_RETRIEVAL_GATE' and not c['passed'] for c in report['checks']) else 'FAIL'}")
    print(f"text_to_sql_gate={'PASS' if not any(c['name']=='TEXT_TO_SQL_GATE' and not c['passed'] for c in report['checks']) else 'FAIL'}")
    print(f"json_report={output}")
    print(f"md_report={markdown}")
    print(f"FINAL-02 GATE: {report['status']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
