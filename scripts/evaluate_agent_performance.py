from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_cases
from evaluation.performance import evaluate_performance_files, write_performance_report


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AE-07: aggregate latency, LLM/token efficiency and Hybrid path metrics."
    )
    parser.add_argument(
        "--observations",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae02_observations.jsonl"),
    )
    parser.add_argument(
        "--profile",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae02_profile.jsonl"),
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae07_performance_report.json"),
    )
    parser.add_argument("--target-ms", type=float, default=5000.0)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args()


def _expected_turn_count(dataset_path: str | Path) -> int:
    return sum(len(case.turns) for case in load_evaluation_cases(dataset_path))


def _fmt_stats(stats: dict) -> str:
    return (
        f"avg={stats.get('avg', 0):.2f}ms "
        f"median={stats.get('median', 0):.2f}ms "
        f"p95={stats.get('p95', 0):.2f}ms "
        f"max={stats.get('max', 0):.2f}ms"
    )


def main() -> int:
    args = _arguments()
    expected_turns = _expected_turn_count(args.dataset)
    report = evaluate_performance_files(
        args.observations,
        args.profile,
        expected_turn_count=expected_turns,
        target_latency_ms=args.target_ms,
        slowest_limit=args.top,
    )
    output = write_performance_report(report, args.output)

    print("\nAgent Evaluation - AE07 Performance & Efficiency")
    print(f"turns expected   : {report.get('expected_turn_count')}")
    print(f"turns observed   : {report.get('observed_turn_count')}")
    print(f"complete         : {'YES' if report.get('complete') else 'NO'}")

    latency = report.get("latency_ms") or {}
    print("\nLatency")
    print(f"  overall        : {_fmt_stats(latency)}")
    print(
        f"  <= {latency.get('target_ms', 0):.0f}ms       : "
        f"{latency.get('within_target_rate_pct', 0):.2f}% "
        f"({latency.get('within_target_turns', 0)}/{report.get('observed_turn_count', 0)})"
    )

    print("\nHybrid Execution")
    for path, stats in (report.get("latency_by_execution_path") or {}).items():
        print(
            f"  {path:<20} {stats.get('count', 0):>3} turns "
            f"({stats.get('rate_pct', 0):>6.2f}%)  {_fmt_stats(stats)}"
        )

    llm = report.get("llm_efficiency") or {}
    print("\nLLM / Token Efficiency")
    print(f"  LLM calls               : {llm.get('total_calls', 0)}")
    print(
        f"  LLM-free turns          : {llm.get('zero_llm_turns', 0)} "
        f"({llm.get('zero_llm_rate_pct', 0):.2f}%)"
    )
    print(f"  input tokens            : {llm.get('input_tokens', 0)}")
    print(f"  output tokens           : {llm.get('output_tokens', 0)}")
    print(f"  total tokens            : {llm.get('total_tokens', 0)}")
    print(f"  avg tokens / turn       : {llm.get('avg_total_tokens_per_turn', 0):.2f}")
    print(f"  avg tokens / LLM call   : {llm.get('avg_total_tokens_per_llm_call', 0):.2f}")
    print(f"  p95 tokens / turn       : {llm.get('p95_total_tokens_per_turn', 0):.2f}")

    mcp = report.get("mcp_tool_latency_ms") or {}
    print(f"\nMCP Tool Latency (source={mcp.get('source', 'unavailable')})")
    for row in (mcp.get("rows") or [])[:10]:
        print(
            f"  {row.get('tool_name', '-'):<42} "
            f"count={row.get('count', 0):>3} "
            f"avg={row.get('avg', 0):>8.2f}ms "
            f"p95={row.get('p95', 0):>8.2f}ms"
        )

    print("\nSlowest Turns")
    for row in report.get("slowest_turns") or []:
        print(
            f"  - {row.get('case_id')}#{row.get('turn_index')} "
            f"{row.get('latency_ms', 0):.2f}ms "
            f"path={row.get('execution_path') or '-'} "
            f"tool={row.get('primary_tool') or '-'} "
            f"llm={row.get('llm_call_count', 0)} "
            f"tokens={row.get('llm_total_tokens', 0)}"
        )

    coverage = report.get("diagnostic_coverage") or {}
    missing_internal = [
        name
        for name in ("gateway_internal_timing", "context_builder_internal_timing")
        if coverage.get(name) is False
    ]
    if missing_internal:
        print("\nDiagnostic Coverage")
        print(
            "  exact internal timing unavailable: " + ", ".join(missing_internal)
        )
        print("  (not inferred; current profiler has no dedicated duration span)")

    print(f"\nreport: {output}")
    if args.require_complete and not report.get("complete"):
        print("PERFORMANCE: FAIL (incomplete observations)")
        return 2
    print("PERFORMANCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
