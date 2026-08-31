from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import Counter, defaultdict
from typing import Any, Iterable


TRIAGE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class FailureTriageRow:
    case_id: str
    turn_index: int
    user_input: str
    primary_cause: str
    failures: tuple[str, ...]
    expected_intent: Any = None
    actual_intent: Any = None
    expected_route: Any = None
    actual_route: Any = None
    expected_tool: Any = None
    actual_tool: Any = None
    expected_arguments: Any = None
    actual_arguments: Any = None
    notes: tuple[str, ...] = ()

    @property
    def turn_key(self) -> str:
        return f"{self.case_id}#{self.turn_index}"

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["turn_key"] = self.turn_key
        return raw


def _check(result: dict[str, Any], name: str) -> dict[str, Any]:
    value = (result.get("checks") or {}).get(name) or {}
    return dict(value) if isinstance(value, dict) else {}


def _primary_cause(result: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    failures = tuple(result.get("failures") or ())
    failure_set = set(failures)
    notes: list[str] = []

    if "INTENT_MISMATCH" in failure_set:
        # Intent can alter downstream route/tool, so treat it as the first root cause.
        if "ROUTE_MISMATCH" in failure_set or "TOOL_SELECTION_MISMATCH" in failure_set:
            notes.append("downstream route/tool mismatch may be caused by intent mismatch")
        return "INTENT_ROOT", tuple(notes)

    route = _check(result, "route")
    tool = _check(result, "tool_selection")
    args = _check(result, "tool_arguments")

    route_failed = route.get("eligible") and route.get("passed") is False
    tool_failed = tool.get("eligible") and tool.get("passed") is False
    args_failed = args.get("eligible") and args.get("passed") is False

    if route_failed and tool_failed:
        notes.append("tool mismatch is treated as downstream of route mismatch for triage")
        if args_failed:
            detail = str(args.get("detail") or "")
            if "Expected primary tool was not observed" in detail:
                notes.append("argument mismatch is cascade-only because expected tool was not observed")
        return "ROUTE_TOOL_CASCADE", tuple(notes)

    if route_failed:
        return "ROUTE_ROOT", tuple(notes)

    if tool_failed:
        if args_failed and "Expected primary tool was not observed" in str(args.get("detail") or ""):
            notes.append("argument mismatch is cascade-only because expected tool was not observed")
        return "TOOL_SELECTION_ROOT", tuple(notes)

    if args_failed:
        return "TOOL_ARGUMENT_ROOT", tuple(notes)

    return "OTHER", tuple(notes)


def triage_accuracy_report(report: dict[str, Any]) -> dict[str, Any]:
    rows: list[FailureTriageRow] = []
    for result in report.get("turn_results") or []:
        if not result.get("failures"):
            continue
        primary_cause, notes = _primary_cause(result)
        intent = _check(result, "intent")
        route = _check(result, "route")
        tool = _check(result, "tool_selection")
        args = _check(result, "tool_arguments")
        rows.append(
            FailureTriageRow(
                case_id=str(result.get("case_id") or ""),
                turn_index=int(result.get("turn_index") or 0),
                user_input=str(result.get("user_input") or ""),
                primary_cause=primary_cause,
                failures=tuple(result.get("failures") or ()),
                expected_intent=intent.get("expected"),
                actual_intent=intent.get("actual"),
                expected_route=route.get("expected"),
                actual_route=route.get("actual"),
                expected_tool=tool.get("expected"),
                actual_tool=tool.get("actual"),
                expected_arguments=args.get("expected"),
                actual_arguments=args.get("actual"),
                notes=notes,
            )
        )

    by_primary = Counter(row.primary_cause for row in rows)
    by_category = Counter(row.case_id.split("-", 1)[0] for row in rows)
    by_signature = Counter(" + ".join(row.failures) for row in rows)

    # Separate strict architecture conformance from user-facing semantics. This is
    # diagnostic only and does not change accuracy scores.
    strict_conformance_turns = len(rows)
    semantic_root_turns = sum(
        1
        for row in rows
        if row.primary_cause in {"INTENT_ROOT", "TOOL_ARGUMENT_ROOT"}
    )
    architecture_root_turns = sum(
        1
        for row in rows
        if row.primary_cause in {"ROUTE_TOOL_CASCADE", "ROUTE_ROOT", "TOOL_SELECTION_ROOT"}
    )

    return {
        "schema_version": TRIAGE_SCHEMA_VERSION,
        "run_id": report.get("run_id"),
        "evaluated_turn_count": int(report.get("evaluated_turn_count") or 0),
        "failed_turn_count": len(rows),
        "strict_conformance_failed_turns": strict_conformance_turns,
        "semantic_root_failed_turns": semantic_root_turns,
        "architecture_root_failed_turns": architecture_root_turns,
        "by_primary_cause": dict(sorted(by_primary.items())),
        "by_category": dict(sorted(by_category.items())),
        "by_failure_signature": dict(sorted(by_signature.items())),
        "rows": [row.to_dict() for row in rows],
        "note": (
            "Failure triage does not alter Ground Truth or accuracy scores. "
            "It only separates root causes from downstream/cascade mismatches."
        ),
    }
