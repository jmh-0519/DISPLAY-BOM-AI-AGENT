from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable

from core.performance_profiler import load_performance_events


PERFORMANCE_REPORT_SCHEMA_VERSION = "1.0"
KNOWN_EXECUTION_PATHS = ("FAST_PATH", "DETERMINISTIC_MACRO", "AGENT_PATH")


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def percentile(values: Iterable[float], percentile_value: float) -> float:
    """Return a deterministic linearly interpolated percentile.

    The implementation is standard-library only so evaluation does not add a
    NumPy/Pandas dependency.  Empty input returns 0.0.
    """
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    if len(rows) == 1:
        return rows[0]
    p = min(100.0, max(0.0, float(percentile_value))) / 100.0
    position = (len(rows) - 1) * p
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return rows[lower]
    weight = position - lower
    return rows[lower] + ((rows[upper] - rows[lower]) * weight)


def distribution(values: Iterable[float]) -> dict[str, Any]:
    rows = [float(value) for value in values]
    if not rows:
        return {
            "count": 0,
            "avg": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    ordered = sorted(rows)
    return {
        "count": len(rows),
        "avg": _round(sum(rows) / len(rows)),
        "median": _round(percentile(ordered, 50)),
        "p95": _round(percentile(ordered, 95)),
        "min": _round(ordered[0]),
        "max": _round(ordered[-1]),
    }


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Evaluation file not found: {source}")
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at {source}:{line_no}") from error
        if isinstance(value, dict):
            rows.append(value)
    return rows


def load_performance_observations(path: str | Path) -> list[dict[str, Any]]:
    return _load_jsonl(path)


@dataclass
class AgentPerformanceEvaluator:
    target_latency_ms: float = 5000.0
    slowest_limit: int = 10

    def evaluate(
        self,
        observations: Iterable[dict[str, Any]],
        *,
        profile_events: Iterable[dict[str, Any]] = (),
        expected_turn_count: int | None = None,
    ) -> dict[str, Any]:
        rows = [dict(row) for row in observations]
        events = [dict(event) for event in profile_events]
        turn_count = len(rows)
        run_ids = sorted({str(row.get("run_id") or "") for row in rows if row.get("run_id")})
        run_id = run_ids[0] if len(run_ids) == 1 else None

        expected = int(expected_turn_count) if expected_turn_count is not None else None
        complete = expected is None or turn_count == expected

        latencies = [float(row.get("latency_ms") or 0.0) for row in rows]
        latency = distribution(latencies)
        target_ms = float(self.target_latency_ms)
        within_target = sum(1 for value in latencies if value <= target_ms)
        over_target = turn_count - within_target
        latency["target_ms"] = _round(target_ms)
        latency["within_target_turns"] = within_target
        latency["over_target_turns"] = over_target
        latency["within_target_rate_pct"] = _round((within_target / turn_count * 100.0) if turn_count else 0.0)

        by_path: dict[str, Any] = {}
        path_names = list(KNOWN_EXECUTION_PATHS)
        extra_paths = sorted({str(row.get("execution_path") or "UNKNOWN") for row in rows} - set(path_names))
        for path in path_names + extra_paths:
            path_rows = [row for row in rows if str(row.get("execution_path") or "UNKNOWN") == path]
            stats = distribution(float(row.get("latency_ms") or 0.0) for row in path_rows)
            stats["rate_pct"] = _round((len(path_rows) / turn_count * 100.0) if turn_count else 0.0)
            by_path[path] = stats

        llm_calls = sum(int(row.get("llm_call_count") or 0) for row in rows)
        turns_with_llm = sum(1 for row in rows if int(row.get("llm_call_count") or 0) > 0)
        zero_llm_turns = turn_count - turns_with_llm
        input_tokens = sum(int(row.get("llm_input_tokens") or 0) for row in rows)
        output_tokens = sum(int(row.get("llm_output_tokens") or 0) for row in rows)
        total_tokens = sum(int(row.get("llm_total_tokens") or 0) for row in rows)
        per_turn_tokens = [int(row.get("llm_total_tokens") or 0) for row in rows]
        weighted_prompt_chars = sum(
            float(row.get("prompt_budget_avg_chars") or 0.0) * int(row.get("llm_call_count") or 0)
            for row in rows
        )
        llm = {
            "total_calls": llm_calls,
            "turns_with_llm": turns_with_llm,
            "zero_llm_turns": zero_llm_turns,
            "zero_llm_rate_pct": _round((zero_llm_turns / turn_count * 100.0) if turn_count else 0.0),
            "avg_calls_per_turn": _round((llm_calls / turn_count) if turn_count else 0.0),
            "avg_calls_per_llm_turn": _round((llm_calls / turns_with_llm) if turns_with_llm else 0.0),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "avg_total_tokens_per_turn": _round((total_tokens / turn_count) if turn_count else 0.0),
            "avg_total_tokens_per_llm_call": _round((total_tokens / llm_calls) if llm_calls else 0.0),
            "p95_total_tokens_per_turn": _round(percentile(per_turn_tokens, 95)),
            "avg_prompt_budget_chars_per_llm_call": _round((weighted_prompt_chars / llm_calls) if llm_calls else 0.0),
        }

        tool_counts: dict[str, int] = {}
        for row in rows:
            for call in row.get("tool_calls") or []:
                name = str((call or {}).get("name") or "").strip()
                if name:
                    tool_counts[name] = tool_counts.get(name, 0) + 1

        mcp_events, mcp_source = self._mcp_duration_events(events)
        by_mcp_tool: dict[str, list[float]] = {}
        for event in mcp_events:
            name = self._mcp_tool_name(event)
            duration = event.get("duration_ms")
            if not name or not isinstance(duration, (int, float)):
                continue
            by_mcp_tool.setdefault(name, []).append(float(duration))
        mcp_rows = []
        for name, durations in by_mcp_tool.items():
            stats = distribution(durations)
            mcp_rows.append({"tool_name": name, **stats})
        mcp_rows.sort(key=lambda row: (row["p95"], row["avg"]), reverse=True)

        slowest = sorted(
            rows,
            key=lambda row: float(row.get("latency_ms") or 0.0),
            reverse=True,
        )[: max(0, int(self.slowest_limit))]
        slowest_turns = [
            {
                "case_id": str(row.get("case_id") or ""),
                "turn_index": int(row.get("turn_index") or 0),
                "execution_path": row.get("execution_path"),
                "primary_tool": row.get("primary_tool"),
                "latency_ms": _round(float(row.get("latency_ms") or 0.0)),
                "llm_call_count": int(row.get("llm_call_count") or 0),
                "llm_total_tokens": int(row.get("llm_total_tokens") or 0),
                "error": row.get("error"),
            }
            for row in slowest
        ]

        timing_summary = self._profile_timing_summary(events)
        diagnostic_coverage = {
            "request_total_timing": self._has_timing(events, "request", "agent.request"),
            "llm_timing": self._has_timing(events, "llm", "azure_openai.chat_completion"),
            "mcp_tool_timing": bool(mcp_events),
            "gateway_route_observed": any(event.get("name") == "graph.gateway.route" for event in events),
            # Current profiler records route/context counters but does not wrap
            # their internal computation with a dedicated duration span.
            "gateway_internal_timing": False,
            "context_builder_internal_timing": False,
        }

        return {
            "schema_version": PERFORMANCE_REPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "complete": complete,
            "expected_turn_count": expected,
            "observed_turn_count": turn_count,
            "latency_ms": latency,
            "latency_by_execution_path": by_path,
            "hybrid_execution": {
                path: {
                    "count": by_path[path]["count"],
                    "rate_pct": by_path[path]["rate_pct"],
                }
                for path in by_path
            },
            "llm_efficiency": llm,
            "business_tool_call_counts": dict(sorted(tool_counts.items())),
            "mcp_tool_latency_ms": {
                "source": mcp_source,
                "rows": mcp_rows,
            },
            "profile_timing_ms": timing_summary,
            "diagnostic_coverage": diagnostic_coverage,
            "slowest_turns": slowest_turns,
            "notes": [
                "PERFORMANCE: PASS means the report was generated successfully; it is not a latency SLA pass/fail verdict.",
                "MCP latency prefers outer mcp_tool spans when present to avoid double-counting nested mcp.call.* spans.",
                "Gateway/context internal latency is not invented when the current profiler has no dedicated duration span.",
            ],
        }

    @staticmethod
    def _has_timing(events: list[dict[str, Any]], category: str, name: str) -> bool:
        return any(
            event.get("category") == category
            and event.get("name") == name
            and isinstance(event.get("duration_ms"), (int, float))
            for event in events
        )

    @staticmethod
    def _mcp_duration_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        outer = [
            event for event in events
            if event.get("category") == "mcp_tool"
            and isinstance(event.get("duration_ms"), (int, float))
        ]
        if outer:
            return outer, "mcp_tool"
        inner = [
            event for event in events
            if event.get("category") == "tool"
            and str(event.get("name") or "").startswith("mcp.call.")
            and isinstance(event.get("duration_ms"), (int, float))
        ]
        return inner, "mcp.call.*" if inner else "unavailable"

    @staticmethod
    def _mcp_tool_name(event: dict[str, Any]) -> str:
        if event.get("category") == "mcp_tool":
            return str(event.get("name") or "").strip()
        name = str(event.get("name") or "").strip()
        if name.startswith("mcp.call."):
            return name[len("mcp.call."):]
        return str((event.get("metadata") or {}).get("tool_name") or "").strip()

    @staticmethod
    def _profile_timing_summary(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[float]] = {}
        for event in events:
            duration = event.get("duration_ms")
            if not isinstance(duration, (int, float)):
                continue
            key = (str(event.get("category") or ""), str(event.get("name") or ""))
            grouped.setdefault(key, []).append(float(duration))
        rows = []
        for (category, name), durations in grouped.items():
            stats = distribution(durations)
            rows.append({"category": category, "name": name, **stats})
        rows.sort(key=lambda row: (row["p95"], row["avg"]), reverse=True)
        return rows


def evaluate_performance_files(
    observation_path: str | Path,
    profile_path: str | Path,
    *,
    expected_turn_count: int | None = None,
    target_latency_ms: float = 5000.0,
    slowest_limit: int = 10,
) -> dict[str, Any]:
    observations = load_performance_observations(observation_path)
    events = load_performance_events(profile_path)
    evaluator = AgentPerformanceEvaluator(
        target_latency_ms=target_latency_ms,
        slowest_limit=slowest_limit,
    )
    return evaluator.evaluate(
        observations,
        profile_events=events,
        expected_turn_count=expected_turn_count,
    )


def write_performance_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
