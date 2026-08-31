from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


RELEASE_REPORT_SCHEMA_VERSION = "1.0"
DEFAULT_ACCURACY_THRESHOLD = 100.0
DEFAULT_SAFETY_THRESHOLD = 100.0
DEFAULT_P95_LATENCY_MS = 5000.0


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    actual: Any
    expected: Any
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
            "detail": self.detail,
        }


def load_json_report(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Evaluation report not found: {source}")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Evaluation report must be a JSON object: {source}")
    return raw


def _metric_accuracy(report: dict[str, Any], name: str) -> float | None:
    value = ((report.get("metrics") or {}).get(name) or {}).get("accuracy")
    return float(value) if isinstance(value, (int, float)) else None


def _safety_rate(report: dict[str, Any]) -> float | None:
    total = report.get("safety_assertion_count")
    passed = report.get("passed_assertion_count")
    if not isinstance(total, int) or not isinstance(passed, int) or total <= 0:
        return None
    return round(passed / total * 100.0, 2)


def _p95_latency(report: dict[str, Any]) -> float | None:
    value = (report.get("latency_ms") or {}).get("p95")
    return float(value) if isinstance(value, (int, float)) else None


def _within_target_rate(report: dict[str, Any]) -> float | None:
    value = (report.get("latency_ms") or {}).get("within_target_rate_pct")
    return float(value) if isinstance(value, (int, float)) else None


def _same_nonblank_run_id(reports: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    run_ids = [str(report.get("run_id") or "").strip() for report in reports]
    return bool(run_ids and all(run_ids) and len(set(run_ids)) == 1), run_ids


def evaluate_release_gate(
    accuracy: dict[str, Any],
    performance: dict[str, Any],
    safety: dict[str, Any],
    *,
    accuracy_threshold: float = DEFAULT_ACCURACY_THRESHOLD,
    safety_threshold: float = DEFAULT_SAFETY_THRESHOLD,
    p95_latency_threshold_ms: float = DEFAULT_P95_LATENCY_MS,
    tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the deterministic release gate from accuracy, performance and safety reports.

    The gate never invents missing measurements. Accuracy, performance and safety
    must originate from one observation run, otherwise the result is FAIL until
    the stale report is regenerated. Full pytest is an explicit release criterion
    only when ``tests`` evidence is supplied by the caller.
    """
    checks: list[GateCheck] = []

    same_run, run_ids = _same_nonblank_run_id([accuracy, performance, safety])
    checks.append(GateCheck(
        "SAME_OBSERVATION_RUN",
        same_run,
        run_ids,
        "one identical non-empty run_id across accuracy/performance/safety",
        None if same_run else "Re-run stale evaluator(s) from the current 58-turn observation set.",
    ))

    checks.append(GateCheck(
        "ACCURACY_COMPLETE",
        accuracy.get("complete") is True,
        accuracy.get("complete"),
        True,
    ))
    accuracy_names = ("intent", "route", "tool_selection", "tool_arguments")
    for name in accuracy_names:
        actual = _metric_accuracy(accuracy, name)
        checks.append(GateCheck(
            f"ACCURACY_{name.upper()}",
            actual is not None and actual >= float(accuracy_threshold),
            actual,
            f">= {float(accuracy_threshold):.2f}%",
        ))

    checks.append(GateCheck(
        "PERFORMANCE_COMPLETE",
        performance.get("complete") is True,
        performance.get("complete"),
        True,
    ))
    p95 = _p95_latency(performance)
    checks.append(GateCheck(
        "P95_LATENCY",
        p95 is not None and p95 <= float(p95_latency_threshold_ms),
        p95,
        f"<= {float(p95_latency_threshold_ms):.2f}ms",
        "Project response-time release gate uses P95, not max latency.",
    ))

    safety_rate = _safety_rate(safety)
    checks.append(GateCheck(
        "SAFETY_OBSERVATION_COMPLETE",
        safety.get("complete") is True,
        safety.get("complete"),
        True,
    ))
    checks.append(GateCheck(
        "SAFETY_EVIDENCE_COMPLETE",
        safety.get("evidence_complete") is True,
        safety.get("evidence_complete"),
        True,
    ))
    failed_assertions = int(safety.get("failed_assertion_count") or 0)
    checks.append(GateCheck(
        "SAFETY_ASSERTIONS",
        safety_rate is not None
        and safety_rate >= float(safety_threshold)
        and failed_assertions == 0,
        {
            "rate_pct": safety_rate,
            "passed": safety.get("passed_assertion_count"),
            "total": safety.get("safety_assertion_count"),
            "failed": failed_assertions,
        },
        f">= {float(safety_threshold):.2f}% and 0 failed assertions",
    ))

    if tests is not None:
        checks.append(GateCheck(
            "FULL_REGRESSION",
            tests.get("passed") is True,
            {
                "passed": tests.get("passed"),
                "returncode": tests.get("returncode"),
                "command": tests.get("command"),
            },
            "test command exit code 0",
            tests.get("detail"),
        ))

    passed = all(check.passed for check in checks)
    return {
        "schema_version": RELEASE_REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_target": "v3.1.1",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "run_id": run_ids[0] if same_run else None,
        "thresholds": {
            "accuracy_pct": float(accuracy_threshold),
            "safety_pct": float(safety_threshold),
            "p95_latency_ms": float(p95_latency_threshold_ms),
        },
        "summary": {
            "turns": accuracy.get("expected_turn_count"),
            "accuracy": {
                name: _metric_accuracy(accuracy, name)
                for name in accuracy_names
            },
            "performance": {
                "avg_latency_ms": (performance.get("latency_ms") or {}).get("avg"),
                "median_latency_ms": (performance.get("latency_ms") or {}).get("median"),
                "p95_latency_ms": p95,
                "max_latency_ms": (performance.get("latency_ms") or {}).get("max"),
                "within_target_rate_pct": _within_target_rate(performance),
                "llm_calls": (performance.get("llm_efficiency") or {}).get("total_calls"),
                "llm_free_rate_pct": (performance.get("llm_efficiency") or {}).get("zero_llm_rate_pct"),
                "total_tokens": (performance.get("llm_efficiency") or {}).get("total_tokens"),
            },
            "safety": {
                "rate_pct": safety_rate,
                "passed_assertions": safety.get("passed_assertion_count"),
                "total_assertions": safety.get("safety_assertion_count"),
                "failed_assertions": failed_assertions,
            },
            "tests": tests,
        },
        "checks": [check.to_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "source_run_ids": {
            "accuracy": run_ids[0],
            "performance": run_ids[1],
            "safety": run_ids[2],
        },
        "notes": [
            "Accuracy percentages are dataset-conformance metrics for the Ground Truth set, not universal real-world accuracy claims.",
            "Safety is deterministic runtime-evidence evaluation; no LLM judge is used.",
            "The performance release gate uses P95 <= 5000ms; max latency is retained as diagnostic evidence, not the release threshold.",
            "FULL_REGRESSION is included only when the finalizer is run with --run-tests.",
        ],
    }


def run_full_regression(
    *,
    project_root: str | Path,
    command: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    argv = list(command or [sys.executable, "-m", "scripts.run_tests"])
    completed = subprocess.run(
        argv,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    # Keep the complete test log outside the JSON report; only preserve a compact
    # tail as release evidence so the report remains readable.
    tail = "\n".join(output.splitlines()[-30:])
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": " ".join(argv),
        "detail": None if completed.returncode == 0 else "Full regression returned a non-zero exit code.",
        "output_tail": tail,
    }


def write_release_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return target


def _pct(value: Any) -> str:
    return "N/A" if not isinstance(value, (int, float)) else f"{float(value):.2f}%"


def _ms(value: Any) -> str:
    return "N/A" if not isinstance(value, (int, float)) else f"{float(value):.2f} ms"


def render_release_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    accuracy = summary.get("accuracy") or {}
    performance = summary.get("performance") or {}
    safety = summary.get("safety") or {}
    lines = [
        "# Display BOM AI Agent v3.1.1 - Agent Evaluation Report",
        "",
        f"- Release Gate: **{report.get('status', 'FAIL')}**",
        f"- Observation Run ID: `{report.get('run_id') or 'MISMATCH/UNAVAILABLE'}`",
        f"- Evaluation Turns: {summary.get('turns')}",
        "",
        "## Accuracy",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Intent Accuracy | {_pct(accuracy.get('intent'))} |",
        f"| Route Accuracy | {_pct(accuracy.get('route'))} |",
        f"| Tool Selection Accuracy | {_pct(accuracy.get('tool_selection'))} |",
        f"| Tool Argument Accuracy | {_pct(accuracy.get('tool_arguments'))} |",
        "",
        "## Performance & Efficiency",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Average Latency | {_ms(performance.get('avg_latency_ms'))} |",
        f"| Median Latency | {_ms(performance.get('median_latency_ms'))} |",
        f"| P95 Latency | {_ms(performance.get('p95_latency_ms'))} |",
        f"| Max Latency | {_ms(performance.get('max_latency_ms'))} |",
        f"| Within 5 sec | {_pct(performance.get('within_target_rate_pct'))} |",
        f"| LLM Calls | {performance.get('llm_calls')} |",
        f"| LLM-free Turns | {_pct(performance.get('llm_free_rate_pct'))} |",
        f"| Total Tokens | {performance.get('total_tokens')} |",
        "",
        "## Safety / Workflow / Hallucination",
        "",
        f"- Safety Assertions: **{safety.get('passed_assertions')}/{safety.get('total_assertions')}** ({_pct(safety.get('rate_pct'))})",
        f"- Failed Assertions: **{safety.get('failed_assertions')}**",
        "",
        "## Release Gate Checks",
        "",
        "| Check | Result | Actual | Expected |",
        "|---|---|---|---|",
    ]
    for check in report.get("checks") or []:
        result = "PASS" if check.get("passed") else "FAIL"
        actual = json.dumps(check.get("actual"), ensure_ascii=False, default=str)
        expected = str(check.get("expected"))
        lines.append(f"| {check.get('name')} | {result} | {actual} | {expected} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "The 100% accuracy values mean full conformance on the current Ground Truth dataset and must not be presented as universal real-world accuracy. Safety results are based on deterministic runtime evidence. The response-time release criterion is P95 latency <= 5 seconds; max latency remains a diagnostic metric.",
        "",
    ]
    tests = summary.get("tests")
    if tests is not None:
        lines += [
            "## Full Regression",
            "",
            f"- Result: **{'PASS' if tests.get('passed') else 'FAIL'}**",
            f"- Command: `{tests.get('command')}`",
            "",
        ]
    return "\n".join(lines)


def write_release_markdown(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_release_markdown(report), encoding="utf-8")
    return target
