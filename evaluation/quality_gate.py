from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import subprocess
import sys


QUALITY_GATE_SCHEMA_VERSION = "1.0"
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
            "detail": self.detail,
        }


def load_report(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Evaluation report not found: {source}")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Evaluation report must be a JSON object: {source}")
    return raw


def _accuracy(report: dict[str, Any], name: str) -> float | None:
    value = ((report.get("metrics") or {}).get(name) or {}).get("accuracy")
    return float(value) if isinstance(value, (int, float)) else None


def _safety_rate(report: dict[str, Any]) -> float | None:
    total = report.get("safety_assertion_count")
    passed = report.get("passed_assertion_count")
    if not isinstance(total, int) or not isinstance(passed, int) or total <= 0:
        return None
    return round(passed / total * 100.0, 2)


def _same_run_id(*reports: dict[str, Any]) -> tuple[bool, list[str]]:
    values = [str(report.get("run_id") or "").strip() for report in reports]
    return bool(values and all(values) and len(set(values)) == 1), values


def evaluate_quality_gate(
    *,
    foundation: dict[str, Any],
    accuracy: dict[str, Any],
    performance: dict[str, Any],
    safety: dict[str, Any],
    rag: dict[str, Any],
    text_to_sql: dict[str, Any],
    tests: dict[str, Any] | None = None,
    accuracy_threshold: float = DEFAULT_ACCURACY_THRESHOLD,
    safety_threshold: float = DEFAULT_SAFETY_THRESHOLD,
    p95_latency_threshold_ms: float = DEFAULT_P95_LATENCY_MS,
) -> dict[str, Any]:
    checks: list[GateCheck] = []

    checks.append(GateCheck(
        "FOUNDATION",
        foundation.get("passed") is True,
        foundation.get("status"),
        "PASS",
    ))

    same_run, run_ids = _same_run_id(accuracy, performance, safety)
    checks.append(GateCheck(
        "SAME_AGENT_OBSERVATION_RUN",
        same_run,
        run_ids,
        "one identical non-empty run_id across accuracy/performance/safety",
    ))
    checks.append(GateCheck(
        "AGENT_ACCURACY_COMPLETE",
        accuracy.get("complete") is True,
        accuracy.get("complete"),
        True,
    ))
    accuracy_names = ("intent", "route", "tool_selection", "tool_arguments")
    for name in accuracy_names:
        actual = _accuracy(accuracy, name)
        checks.append(GateCheck(
            f"AGENT_{name.upper()}_ACCURACY",
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
    p95 = (performance.get("latency_ms") or {}).get("p95")
    p95_value = float(p95) if isinstance(p95, (int, float)) else None
    checks.append(GateCheck(
        "P95_LATENCY",
        p95_value is not None and p95_value <= float(p95_latency_threshold_ms),
        p95_value,
        f"<= {float(p95_latency_threshold_ms):.2f}ms",
    ))

    safety_rate = _safety_rate(safety)
    failed_safety = int(safety.get("failed_assertion_count") or 0)
    checks.append(GateCheck(
        "SAFETY_COMPLETE",
        safety.get("complete") is True and safety.get("evidence_complete") is True,
        {"observation": safety.get("complete"), "evidence": safety.get("evidence_complete")},
        {"observation": True, "evidence": True},
    ))
    checks.append(GateCheck(
        "SAFETY_ASSERTIONS",
        safety_rate is not None
        and safety_rate >= float(safety_threshold)
        and failed_safety == 0,
        {"rate_pct": safety_rate, "failed": failed_safety},
        f">= {float(safety_threshold):.2f}% and 0 failed assertions",
    ))

    checks.append(GateCheck(
        "RAG_RETRIEVAL_GATE",
        rag.get("gate_pass") is True,
        {
            "gate_pass": rag.get("gate_pass"),
            "case_count": rag.get("case_count"),
            "metrics": rag.get("metrics"),
        },
        True,
    ))
    checks.append(GateCheck(
        "TEXT_TO_SQL_GATE",
        text_to_sql.get("gate_pass") is True,
        {
            "gate_pass": text_to_sql.get("gate_pass"),
            "case_count": text_to_sql.get("case_count"),
            "overall_accuracy": text_to_sql.get("overall_accuracy"),
            "semantic_match_rate": text_to_sql.get("semantic_match_rate"),
        },
        True,
    ))

    if tests is not None:
        checks.append(GateCheck(
            "FULL_REGRESSION",
            tests.get("passed") is True,
            {"passed": tests.get("passed"), "returncode": tests.get("returncode")},
            "test command exit code 0",
            tests.get("detail"),
        ))

    passed = all(check.passed for check in checks)
    perf = performance.get("llm_efficiency") or {}
    latency = performance.get("latency_ms") or {}
    return {
        "schema_version": QUALITY_GATE_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "QUALITY_GATE",
        "release_candidate": "v4.0.0",
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "run_id": run_ids[0] if same_run else None,
        "thresholds": {
            "agent_accuracy_pct": float(accuracy_threshold),
            "safety_pct": float(safety_threshold),
            "p95_latency_ms": float(p95_latency_threshold_ms),
        },
        "summary": {
            "agent_cases": accuracy.get("expected_case_count"),
            "agent_turns": accuracy.get("expected_turn_count"),
            "accuracy": {name: _accuracy(accuracy, name) for name in accuracy_names},
            "performance": {
                "avg_latency_ms": latency.get("avg"),
                "p95_latency_ms": latency.get("p95"),
                "within_target_rate_pct": latency.get("within_target_rate_pct"),
                "llm_calls": perf.get("total_calls"),
                "llm_free_rate_pct": perf.get("zero_llm_rate_pct"),
                "total_tokens": perf.get("total_tokens"),
            },
            "safety": {
                "rate_pct": safety_rate,
                "passed_assertions": safety.get("passed_assertion_count"),
                "total_assertions": safety.get("safety_assertion_count"),
                "failed_assertions": failed_safety,
            },
            "foundation": {
                "planner_accuracy_pct": (foundation.get("planner") or {}).get("accuracy_pct"),
                "context_gate_passed": (foundation.get("context") or {}).get("gate_passed"),
                "context_gate_count": (foundation.get("context") or {}).get("gate_case_count"),
                "architecture_validators_passed": (foundation.get("validators") or {}).get("passed_count"),
                "architecture_validators_count": (foundation.get("validators") or {}).get("count"),
            },
            "rag": {
                "case_count": rag.get("case_count"),
                "metrics": rag.get("metrics"),
            },
            "text_to_sql": {
                "case_count": text_to_sql.get("case_count"),
                "overall_accuracy": text_to_sql.get("overall_accuracy"),
                "status_accuracy": text_to_sql.get("status_accuracy"),
                "semantic_match_rate": text_to_sql.get("semantic_match_rate"),
                "unsupported_accuracy": text_to_sql.get("unsupported_accuracy"),
            },
            "tests": tests,
        },
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "source_run_ids": {
            "accuracy": run_ids[0],
            "performance": run_ids[1],
            "safety": run_ids[2],
        },
        "notes": [
            "Agent accuracy is Ground Truth dataset conformance, not universal real-world accuracy.",
            "RAG and Text-to-SQL keep their domain-specific quality gates instead of forcing 100% retrieval/generation accuracy.",
            "Safety is deterministic runtime-evidence evaluation without an LLM judge.",
            "LLM-free rate and <=5s rate are reported as diagnostics; the release latency gate is P95 <= 5000ms.",
            "The evaluation layer does not grant Request, Approval, or Production BOM write authority.",
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
    tail = "\n".join(output.splitlines()[-30:])
    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": " ".join(argv),
        "detail": None if completed.returncode == 0 else "Full regression returned a non-zero exit code.",
        "output_tail": tail,
    }


def write_quality_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return target


def write_quality_markdown(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary") or {}
    accuracy = summary.get("accuracy") or {}
    perf = summary.get("performance") or {}
    safety = summary.get("safety") or {}
    foundation = summary.get("foundation") or {}
    rag = summary.get("rag") or {}
    t2s = summary.get("text_to_sql") or {}
    lines = [
        "# Display BOM AI Agent - Evaluation / Stability / Safety",
        "",
        f"- Status: **{report.get('status')}**",
        f"- Release candidate: `{report.get('release_candidate')}`",
        f"- Agent cases / turns: {summary.get('agent_cases')} / {summary.get('agent_turns')}",
        "",
        "## Agent Accuracy",
    ]
    for name in ("intent", "route", "tool_selection", "tool_arguments"):
        lines.append(f"- {name}: {accuracy.get(name)}%")
    lines += [
        "",
        "## Context / Planning / Composition",
        f"- Planner accuracy: {foundation.get('planner_accuracy_pct')}%",
        f"- Context gate: {foundation.get('context_gate_passed')}/{foundation.get('context_gate_count')}",
        f"- Architecture validators: {foundation.get('architecture_validators_passed')}/{foundation.get('architecture_validators_count')}",
        "",
        "## RAG",
        f"- Cases: {rag.get('case_count')}",
        f"- Metrics: `{json.dumps(rag.get('metrics') or {}, ensure_ascii=False)}`",
        "",
        "## Text-to-SQL",
        f"- Cases: {t2s.get('case_count')}",
        f"- Overall accuracy: {t2s.get('overall_accuracy')}",
        f"- Semantic match: {t2s.get('semantic_match_rate')}",
        "",
        "## Performance",
        f"- Average latency: {perf.get('avg_latency_ms')} ms",
        f"- P95 latency: {perf.get('p95_latency_ms')} ms",
        f"- <=5s rate: {perf.get('within_target_rate_pct')}%",
        f"- LLM-free rate: {perf.get('llm_free_rate_pct')}%",
        f"- LLM calls: {perf.get('llm_calls')}",
        "",
        "## Safety",
        f"- Safety rate: {safety.get('rate_pct')}%",
        f"- Assertions: {safety.get('passed_assertions')}/{safety.get('total_assertions')} (failed={safety.get('failed_assertions')})",
        "",
        "## Gate Checks",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- [{'PASS' if check.get('passed') else 'FAIL'}] {check.get('name')}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_ACCURACY_THRESHOLD",
    "DEFAULT_P95_LATENCY_MS",
    "DEFAULT_SAFETY_THRESHOLD",
    "QUALITY_GATE_SCHEMA_VERSION",
    "evaluate_quality_gate",
    "load_report",
    "run_full_regression",
    "write_quality_markdown",
    "write_quality_report",
]
