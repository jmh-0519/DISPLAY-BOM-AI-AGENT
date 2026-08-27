from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


_FALSE_VALUES = {"0", "false", "off", "no"}


def performance_profiling_enabled() -> bool:
    return str(os.getenv("BOM_PERFORMANCE_PROFILE", "0")).strip().lower() not in _FALSE_VALUES


def performance_profile_path() -> Path:
    configured = str(os.getenv("BOM_PERFORMANCE_PROFILE_PATH", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / ".perf" / "agent_profile.jsonl").resolve()


def _safe_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in (value or {}).items():
        if item is None or isinstance(item, (str, int, float, bool)):
            result[str(key)] = item
        elif isinstance(item, (list, tuple, set)):
            result[str(key)] = len(item)
        elif isinstance(item, dict):
            result[str(key)] = len(item)
        else:
            result[str(key)] = type(item).__name__
    return result


def record_performance_event(
    *,
    category: str,
    name: str,
    duration_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Append one safe profiling event.

    The profiler deliberately stores timings/counts only. BOM rows, prompts,
    supplier values and user text are not written to the profile file.
    """
    if not performance_profiling_enabled():
        return

    path = performance_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "category": str(category),
        "name": str(name),
        "duration_ms": round(float(duration_ms), 2) if duration_ms is not None else None,
        "metadata": _safe_mapping(metadata),
        "metrics": _safe_mapping(metrics),
    }

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


@contextmanager
def performance_span(
    category: str,
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Iterator[None]:
    if not performance_profiling_enabled():
        yield
        return

    started = time.perf_counter()
    try:
        yield
    finally:
        record_performance_event(
            category=category,
            name=name,
            duration_ms=(time.perf_counter() - started) * 1000,
            metadata=metadata,
        )


def load_performance_events(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def summarize_performance_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    llm_usage = {"input": 0, "output": 0, "total": 0}
    context_stats = {
        "original_tool_chars": 0,
        "compacted_tool_chars": 0,
        "saved_tool_chars": 0,
        "compacted_tool_messages": 0,
    }
    prompt_budget = {
        "call_count": 0,
        "core_system_chars": 0,
        "skill_wrapper_chars": 0,
        "base_skill_chars": 0,
        "runtime_gate_chars": 0,
        "message_payload_chars": 0,
        "human_content_chars": 0,
        "assistant_content_chars": 0,
        "tool_content_chars": 0,
        "tool_definition_chars": 0,
        "tool_definition_count": 0,
        "approx_total_chars": 0,
    }
    skill_budget: dict[str, dict[str, int]] = defaultdict(
        lambda: {"load_count": 0, "chars": 0, "lines": 0}
    )
    tool_schema_budget: dict[str, list[int]] = defaultdict(list)

    for event in events:
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)):
            grouped[
                (str(event.get("category") or ""), str(event.get("name") or ""))
            ].append(float(duration))

        if event.get("name") == "azure_openai.usage":
            metrics = event.get("metrics") or {}
            for key in llm_usage:
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    llm_usage[key] += int(value)

        if event.get("name") == "llm.context_diet":
            metrics = event.get("metrics") or {}
            for key in context_stats:
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    context_stats[key] += int(value)

        if event.get("name") == "llm.prompt_budget":
            prompt_budget["call_count"] += 1
            metrics = event.get("metrics") or {}
            for key in prompt_budget:
                if key == "call_count":
                    continue
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    prompt_budget[key] += int(value)

        if event.get("name") == "skill.loaded":
            metadata = event.get("metadata") or {}
            metrics = event.get("metrics") or {}
            skill_name = str(metadata.get("skill_name") or "unknown")
            budget = skill_budget[skill_name]
            budget["load_count"] += 1
            for key in ("chars", "lines"):
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    budget[key] = max(budget[key], int(value))

        if event.get("name") == "llm.tool_schema_budget":
            metadata = event.get("metadata") or {}
            metrics = event.get("metrics") or {}
            tool_name = str(metadata.get("tool_name") or "unknown")
            schema_chars = metrics.get("schema_chars")
            if isinstance(schema_chars, (int, float)):
                tool_schema_budget[tool_name].append(int(schema_chars))

    rows = []
    for (category, name), durations in sorted(grouped.items()):
        rows.append({
            "category": category,
            "name": name,
            "count": len(durations),
            "total_ms": round(sum(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "max_ms": round(max(durations), 2),
        })

    prompt_calls = max(prompt_budget["call_count"], 1)
    prompt_budget_avg = {
        key: (
            value
            if key == "call_count"
            else round(value / prompt_calls, 2)
        )
        for key, value in prompt_budget.items()
    }

    tool_schema_rows = []
    for tool_name, sizes in tool_schema_budget.items():
        tool_schema_rows.append({
            "tool_name": tool_name,
            "count": len(sizes),
            "avg_schema_chars": round(sum(sizes) / len(sizes), 2),
            "max_schema_chars": max(sizes),
        })
    tool_schema_rows.sort(
        key=lambda row: row["avg_schema_chars"],
        reverse=True,
    )

    return {
        "event_count": len(events),
        "timings": rows,
        "llm_usage": llm_usage,
        "context_diet": context_stats,
        "prompt_budget": {
            "total": prompt_budget,
            "avg_per_call": prompt_budget_avg,
        },
        "skills": dict(sorted(skill_budget.items())),
        "tool_schemas": tool_schema_rows,
    }
