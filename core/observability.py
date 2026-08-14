from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


_SENSITIVE_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)

_ALLOWED_STATUSES = {
    "PASS",
    "FAIL",
    "CONDITIONAL",
    "SUCCESS",
    "ERROR",
    "PENDING",
    "APPROVED",
    "REJECTED",
}

def summarize_text(value: Any) -> dict[str, Any]:
    """Return non-content metadata for text sent to observability."""
    text = "" if value is None else str(value)
    return {
        "type": "text",
        "character_count": len(text),
        "is_empty": not bool(text.strip()),
    }


def summarize_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    roles: dict[str, int] = {}
    tool_call_count = 0
    for message in messages:
        role = str(message.get("role", "unknown"))
        roles[role] = roles.get(role, 0) + 1
        tool_call_count += len(message.get("tool_calls") or [])
    return {
        "type": "messages",
        "message_count": len(messages),
        "roles": roles,
        "tool_call_count": tool_call_count,
    }


def summarize_value(value: Any) -> dict[str, Any]:
    """Summarize shape/status without storing BOM, supplier, or cost values."""
    if isinstance(value, dict):
        safe_keys = sorted(
            str(key)
            for key in value
            if not any(marker in str(key).lower() for marker in _SENSITIVE_MARKERS)
        )
        summary: dict[str, Any] = {
            "type": "object",
            "field_count": len(safe_keys),
            "fields": safe_keys,
        }
        status_value = value.get("status")

        if isinstance(status_value, str):
            normalized_status = status_value.strip().upper()

            if normalized_status in _ALLOWED_STATUSES:
                summary["status"] = normalized_status
            else:
                summary["status_present"] = True
        elif status_value is not None:
            summary["status_present"] = True

        for boolean_key in (
            "success",
            "changeable",
        ):
            boolean_value = value.get(boolean_key)

            if isinstance(boolean_value, bool):
                summary[boolean_key] = boolean_value
            elif boolean_value is not None:
                summary[f"{boolean_key}_present"] = True

        return summary
    
    if isinstance(value, (list, tuple, set)):
        return {"type": "list", "item_count": len(value)}
    if isinstance(value, str):
        return summarize_text(value)
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


@dataclass
class Observation:
    delegate: Any = None
    started_at: float = 0.0

    def finish(
        self,
        *,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
        usage_details: dict[str, int] | None = None,
    ) -> None:
        if self.delegate is None:
            return
        details = dict(metadata or {})
        details["duration_ms"] = round(
            (time.perf_counter() - self.started_at) * 1000,
            2,
        )
        kwargs: dict[str, Any] = {
            "output": output,
            "metadata": details,
            "level": "DEFAULT",
        }
        if usage_details:
            kwargs["usage_details"] = usage_details
        try:
            self.delegate.update(**kwargs)
        except Exception:
            pass

    def fail(self, error: BaseException) -> None:
        if self.delegate is None:
            return
        try:
            self.delegate.update(
                output={"type": "error"},
                metadata={
                    "duration_ms": round(
                        (time.perf_counter() - self.started_at) * 1000,
                        2,
                    ),
                    "error_type": type(error).__name__,
                },
                level="ERROR",
                status_message=type(error).__name__,
            )
        except Exception:
            pass


class LangfuseObservability:
    """Fail-open Langfuse adapter; business execution never depends on tracing."""

    def __init__(self, client: Any = None) -> None:
        self.client = client if client is not None else self._create_client()

    @staticmethod
    def _create_client() -> Any:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return None
        if os.getenv("LANGFUSE_TRACING_ENABLED", "true").strip().lower() in {
            "0", "false", "no", "off",
        }:
            return None
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        if not public_key or not secret_key:
            return None
        try:
            from langfuse import Langfuse

            return Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=(
                    os.getenv(
                        "LANGFUSE_BASE_URL",
                        "",
                    ).strip()
                    or None
                ),
                environment=(
                    os.getenv(
                        "LANGFUSE_TRACING_ENVIRONMENT",
                        "",
                    ).strip()
                    or None
                ),
            )
        except Exception:
            return None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        as_type: str = "span",
        input_summary: Any = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> Iterator[Observation]:
        if self.client is None:
            yield Observation(started_at=time.perf_counter())
            return

        manager = None
        observation = Observation(started_at=time.perf_counter())
        try:
            kwargs: dict[str, Any] = {
                "name": name,
                "as_type": as_type,
                "input": input_summary,
                "metadata": metadata or {},
            }
            if model:
                kwargs["model"] = model
            manager = self.client.start_as_current_observation(**kwargs)
            observation.delegate = manager.__enter__()
        except Exception:
            manager = None
            observation.delegate = None

        try:
            yield observation
        except BaseException as error:
            observation.fail(error)
            raise
        finally:
            if manager is not None:
                try:
                    manager.__exit__(None, None, None)
                except Exception:
                    pass


_default_observability: LangfuseObservability | None = None


def get_observability() -> LangfuseObservability:
    global _default_observability
    if _default_observability is None:
        _default_observability = LangfuseObservability()
    return _default_observability
