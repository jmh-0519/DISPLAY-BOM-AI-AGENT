from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import hashlib
import os
import sqlite3
import time
from typing import Any
import uuid

from core.performance_profiler import (
    load_performance_events,
    summarize_performance_events,
)


OBSERVATION_SCHEMA_VERSION = "1.1"

ROUTE_TO_EXECUTION_PATH = {
    "fast_chat": "FAST_PATH",
    "fast_bom_read": "FAST_PATH",
    "fast_where_used": "FAST_PATH",
    "fast_current_bom_quantity": "FAST_PATH",
    "fast_knowledge": "KNOWLEDGE_PATH",
    "fast_text_to_sql": "TEXT_TO_SQL_PATH",
    "composition_plan": "READ_ONLY_COMPOSITION",
    "workflow_composition_plan": "WORKFLOW_COMPOSITION",
    "scope_conflict": "SCOPE_CONFLICT",
    "macro_analyze": "DETERMINISTIC_MACRO",
    "agent": "AGENT_PATH",
}
# Backward-compatible private alias used by older tests/importers.
_ROUTE_TO_EXECUTION_PATH = ROUTE_TO_EXECUTION_PATH


@dataclass(frozen=True)
class ObservedToolCall:
    name: str
    arguments: dict[str, Any]
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ObservedToolResult:
    name: str
    payload: Any
    tool_call_id: str | None = None
    parse_error: str | None = None


@dataclass
class AgentTurnObservation:
    schema_version: str = OBSERVATION_SCHEMA_VERSION
    run_id: str = ""
    case_id: str = ""
    turn_index: int = 0
    thread_id: str = ""
    user_input: str = ""
    normalized_user_input: str = ""
    actual_intent: str | None = None
    gateway_route: str | None = None
    execution_path: str | None = None
    interaction_hint: str | None = None
    tool_calls: list[ObservedToolCall] = field(default_factory=list)
    tool_results: list[ObservedToolResult] = field(default_factory=list)
    answer: str = ""
    error: str | None = None
    plant_option_count: int = 0
    workflow_before: dict[str, Any] = field(default_factory=dict)
    workflow_after: dict[str, Any] = field(default_factory=dict)
    active_bom_context_before: dict[str, Any] | None = None
    active_bom_context_after: dict[str, Any] | None = None
    database_before: dict[str, Any] = field(default_factory=dict)
    database_after: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    llm_call_count: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_total_tokens: int = 0
    prompt_budget_avg_chars: float = 0.0
    profile_event_count: int = 0
    timing_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def primary_tool(self) -> str | None:
        return self.tool_calls[0].name if self.tool_calls else None

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["primary_tool"] = self.primary_tool
        raw["tool_call_count"] = self.tool_call_count
        return raw


class RuntimeObservationCollector:
    """Collect raw runtime evidence for one Agent evaluation turn.

    This class does not judge PASS/FAIL.  It records what actually happened so
    Evaluators can compare it against the Ground Truth dataset.
    """

    def __init__(
        self,
        agent: Any,
        *,
        profile_path: str | Path,
        run_id: str | None = None,
    ) -> None:
        self.agent = agent
        self.profile_path = Path(profile_path).expanduser().resolve()
        self.run_id = run_id or f"eval-{uuid.uuid4().hex[:12]}"

    def collect_turn(
        self,
        *,
        case_id: str,
        turn_index: int,
        user_input: str,
        thread_id: str,
    ) -> AgentTurnObservation:
        normalized = self._normalize(user_input)
        before_state = self._snapshot(thread_id)
        workflow_before = self._workflow_summary(before_state.get("design_change"))
        context_before = self._copy_mapping(before_state.get("active_bom_context"))
        actual_intent = self._resolve_intent(normalized, before_state.get("design_change"))

        database_before = self._database_snapshot()
        before_event_count = len(load_performance_events(self.profile_path))
        started = time.perf_counter()
        result: dict[str, Any]
        caught_error: str | None = None
        try:
            result = self.agent.run_with_artifacts(user_input, thread_id=thread_id)
        except Exception as error:  # evaluator records failures instead of aborting the run
            caught_error = f"{type(error).__name__}: {error}"
            result = {"answer": "", "plant_options": [], "tool_names": []}
        latency_ms = (time.perf_counter() - started) * 1000.0
        database_after = self._database_snapshot()

        after_state = self._snapshot(thread_id)
        workflow_after = self._workflow_summary(after_state.get("design_change"))
        context_after = self._copy_mapping(after_state.get("active_bom_context"))
        current_messages = self._current_turn_messages(after_state, normalized)
        tool_calls = self.extract_tool_calls(current_messages)
        tool_results = self.extract_tool_results(current_messages)

        all_events = load_performance_events(self.profile_path)
        turn_events = all_events[before_event_count:]
        profile = summarize_performance_events(turn_events)
        gateway_route = self._gateway_route(turn_events)
        execution_path = ROUTE_TO_EXECUTION_PATH.get(gateway_route)
        if execution_path is None:
            execution_path = self._fallback_execution_path(tool_calls, profile)

        state_error = str(after_state.get("error") or "").strip() or None
        error_text = caught_error or state_error
        plant_options = list(result.get("plant_options") or [])
        interaction_hint = self._interaction_hint(
            execution_path=execution_path,
            tool_calls=tool_calls,
            plant_options=plant_options,
            workflow_before=workflow_before,
            workflow_after=workflow_after,
            error=error_text,
        )
        usage = profile.get("llm_usage") or {}
        prompt_avg = (profile.get("prompt_budget") or {}).get("avg_per_call") or {}
        llm_call_count = sum(
            1 for event in turn_events if event.get("name") == "azure_openai.usage"
        )

        return AgentTurnObservation(
            run_id=self.run_id,
            case_id=str(case_id).upper(),
            turn_index=int(turn_index),
            thread_id=str(thread_id),
            user_input=str(user_input),
            normalized_user_input=normalized,
            actual_intent=actual_intent,
            gateway_route=gateway_route,
            execution_path=execution_path,
            interaction_hint=interaction_hint,
            tool_calls=tool_calls,
            tool_results=tool_results,
            answer=str(result.get("answer") or ""),
            error=error_text,
            plant_option_count=len(plant_options),
            workflow_before=workflow_before,
            workflow_after=workflow_after,
            active_bom_context_before=context_before,
            active_bom_context_after=context_after,
            database_before=database_before,
            database_after=database_after,
            latency_ms=round(latency_ms, 2),
            llm_call_count=llm_call_count,
            llm_input_tokens=int(usage.get("input") or 0),
            llm_output_tokens=int(usage.get("output") or 0),
            llm_total_tokens=int(usage.get("total") or 0),
            prompt_budget_avg_chars=float(prompt_avg.get("approx_total_chars") or 0.0),
            profile_event_count=len(turn_events),
            timing_rows=list(profile.get("timings") or []),
        )

    def _snapshot(self, thread_id: str) -> dict[str, Any]:
        graph = getattr(self.agent, "graph", None)
        if graph is None or not hasattr(graph, "get_state"):
            return {}
        state = graph.get_state({"configurable": {"thread_id": str(thread_id)}})
        values = getattr(state, "values", {})
        return dict(values) if isinstance(values, dict) else {}

    def _normalize(self, user_input: str) -> str:
        normalizer = getattr(self.agent, "_normalize_bom_query", None)
        return str(normalizer(user_input) if callable(normalizer) else user_input).strip()

    def _resolve_intent(self, user_input: str, workflow_state: Any) -> str | None:
        gateway = getattr(self.agent, "gateway", None)
        router = getattr(gateway, "router", None)
        if router is None or not hasattr(router, "route"):
            return None
        workflow = workflow_state if isinstance(workflow_state, dict) else {}
        step = str(workflow.get("current_step") or "NOT_STARTED").upper()
        active = step not in {"NOT_STARTED", "APPLIED", "REPORT_COMPLETED", "BLOCKED"}
        try:
            # Intent accuracy is a current-turn classification metric.
            # Historical workflow activity must not suppress an explicit read
            # intent such as "MODEL PLANT BOM 조회해줘".  Runtime authority and
            # scope are evaluated separately by gateway route/context metrics.
            decision = router.route(
                user_input,
                workflow_active=False,
                workflow_state=workflow,
            )
        except Exception:
            return None
        return str(getattr(decision, "intent", "") or "").upper() or None

    def _current_turn_messages(
        self,
        state: dict[str, Any],
        normalized_user_input: str,
    ) -> list[Any]:
        messages = list(state.get("messages") or [])
        extractor = getattr(self.agent, "_current_turn_messages", None)
        if callable(extractor):
            try:
                return list(extractor(messages, normalized_user_input))
            except Exception:
                pass
        # Fallback for fake agents/tests: last turn is sufficient for raw call parsing.
        return messages

    @staticmethod
    def extract_tool_calls(messages: list[Any]) -> list[ObservedToolCall]:
        observed: list[ObservedToolCall] = []
        for message in messages:
            for call in list(getattr(message, "tool_calls", None) or []):
                if not isinstance(call, dict):
                    continue
                name = str(call.get("name") or "").strip()
                if not name:
                    continue
                args = call.get("args")
                observed.append(
                    ObservedToolCall(
                        name=name,
                        arguments=dict(args) if isinstance(args, dict) else {},
                        tool_call_id=(str(call.get("id")) if call.get("id") else None),
                    )
                )
        return observed


    @staticmethod
    def extract_tool_results(messages: list[Any]) -> list[ObservedToolResult]:
        observed: list[ObservedToolResult] = []
        for message in messages:
            name = str(getattr(message, "name", None) or "").strip()
            tool_call_id = str(getattr(message, "tool_call_id", None) or "").strip() or None
            if not name or not tool_call_id:
                continue
            content = getattr(message, "content", "")
            payload: Any = content
            parse_error: str | None = None
            if isinstance(content, str):
                text = content.strip()
                if text:
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError as error:
                        parse_error = str(error)
                        payload = text
                else:
                    payload = ""
            observed.append(ObservedToolResult(
                name=name,
                payload=payload,
                tool_call_id=tool_call_id,
                parse_error=parse_error,
            ))
        return observed

    @staticmethod
    def _database_snapshot() -> dict[str, Any]:
        """Capture protected business-table fingerprints for deterministic safety checks.

        The snapshot is taken outside the measured Agent latency window.  It is
        intentionally read-only and ignores audit/profiling tables so evaluation
        can distinguish harmless observation writes from Request/Approval/Apply or
        Production BOM mutations.
        """
        raw_path = str(os.environ.get("BOM_SQLITE_PATH") or "").strip()
        if not raw_path:
            return {"available": False, "reason": "BOM_SQLITE_PATH is not set", "tables": {}}
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            return {"available": False, "reason": f"database not found: {path}", "tables": {}}

        protected_tables = (
            "bom_master",
            "change_requests",
            "change_actions",
            "candidate_evaluations",
            "change_approvals",
            "change_previews",
            "change_apply_results",
                )
        tables: dict[str, Any] = {}
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                existing = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                for table in protected_tables:
                    if table not in existing:
                        tables[table] = {"available": False, "count": 0, "sha256": None}
                        continue
                    columns = [
                        str(row[1])
                        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                    ]
                    quoted = ", ".join(f'"{name}"' for name in columns)
                    order_by = f" ORDER BY {quoted}" if quoted else ""
                    rows = connection.execute(
                        f'SELECT {quoted or "*"} FROM "{table}"{order_by}'
                    ).fetchall()
                    digest = hashlib.sha256()
                    for row in rows:
                        digest.update(
                            json.dumps(list(row), ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
                        )
                        digest.update(b"\n")
                    tables[table] = {
                        "available": True,
                        "count": len(rows),
                        "sha256": digest.hexdigest(),
                    }
            finally:
                connection.close()
        except Exception as error:
            return {
                "available": False,
                "reason": f"{type(error).__name__}: {error}",
                "tables": tables,
            }
        return {"available": True, "path": str(path), "tables": tables}

    @staticmethod
    def _gateway_route(events: list[dict[str, Any]]) -> str | None:
        for event in events:
            if event.get("name") != "graph.gateway.route":
                continue
            route = str((event.get("metadata") or {}).get("route") or "").strip()
            if route:
                return route
        return None

    @staticmethod
    def _fallback_execution_path(
        tool_calls: list[ObservedToolCall],
        profile: dict[str, Any],
    ) -> str | None:
        ids = [str(call.tool_call_id or "") for call in tool_calls]
        if any(value.startswith("graph-fast-") for value in ids):
            return "FAST_PATH"
        # macro-analysis IDs can also be emitted inside Agent Path on a pending
        # slot completion, so use this only when no Agent node timing exists.
        agent_node_seen = any(
            row.get("name") == "langgraph.agent"
            for row in profile.get("timings") or []
        )
        if any(value.startswith("macro-analysis-") for value in ids) and not agent_node_seen:
            return "DETERMINISTIC_MACRO"
        if agent_node_seen:
            return "AGENT_PATH"
        if not tool_calls and int((profile.get("llm_usage") or {}).get("total") or 0) == 0:
            return "FAST_PATH"
        return None

    @staticmethod
    def _interaction_hint(
        *,
        execution_path: str | None,
        tool_calls: list[ObservedToolCall],
        plant_options: list[dict[str, Any]],
        workflow_before: dict[str, Any],
        workflow_after: dict[str, Any],
        error: str | None,
    ) -> str | None:
        if plant_options:
            return "PLANT_SELECT"
        names = {call.name for call in tool_calls}
        if "analyze_design_change_candidates" in names:
            return "ANALYZE"
        if error:
            return "BLOCK_OR_ERROR"
        if execution_path == "SCOPE_CONFLICT":
            return "BLOCK"
        if execution_path in {
            "FAST_PATH",
            "KNOWLEDGE_PATH",
            "TEXT_TO_SQL_PATH",
            "READ_ONLY_COMPOSITION",
        }:
            return "ANSWER"
        pending_keys = (
            "pending_quantity_request",
            "pending_add_target_request",
            "pending_add_parent_request",
            "pending_delete_target_request",
        )
        if any(workflow_after.get(key) and not workflow_before.get(key) for key in pending_keys):
            return "CLARIFY"
        return None

    @staticmethod
    def _workflow_summary(value: Any) -> dict[str, Any]:
        workflow = value if isinstance(value, dict) else {}
        keys = (
            "current_step",
            "analysis_id",
            "request_id",
            "candidate_approval_id",
            "final_approval_id",
            "apply_status",
            "pending_quantity_request",
            "pending_add_target_request",
            "pending_add_parent_request",
            "pending_delete_target_request",
        )
        return {key: workflow.get(key) for key in keys}

    @staticmethod
    def _copy_mapping(value: Any) -> dict[str, Any] | None:
        return dict(value) if isinstance(value, dict) else None


def write_observations_jsonl(
    observations: list[AgentTurnObservation],
    path: str | Path,
    *,
    append: bool = False,
) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(observation.to_dict(), ensure_ascii=False, default=str) + "\n")
    return target
