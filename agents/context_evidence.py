"""Current-turn Tool evidence references for ontology context.

Only safe metadata summaries are projected. Raw Tool payloads remain in
LangGraph state and continue to be handled by LlmContextCompactor.
"""

from __future__ import annotations

import json

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from ontology.context_contract import (
    ContextAuthority,
    ContextEvidence,
    ContextSource,
)


class CurrentTurnContextEvidenceCollector:
    KNOWLEDGE_TOOLS = {"search_knowledge"}
    TEXT_TO_SQL_TOOLS = {
        "text_to_sql",
        "run_text_to_sql",
        "execute_text_to_sql",
    }
    SAFE_SCALARS = (
        "success",
        "status",
        "analysis_id",
        "request_id",
        "action_id",
        "candidate_count",
        "hit_count",
        "row_count",
        "cost_reduction_status",
    )

    def __init__(
        self,
        *,
        max_evidence: int = 8,
        max_summary_chars: int = 240,
    ) -> None:
        self.max_evidence = max(0, int(max_evidence))
        self.max_summary_chars = max(80, int(max_summary_chars))

    def collect(
        self,
        messages: list[BaseMessage],
    ) -> tuple[ContextEvidence, ...]:
        start = -1
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                start = index
                break

        result: list[ContextEvidence] = []
        seen: set[str] = set()
        for message in messages[start + 1:]:
            if not isinstance(message, ToolMessage):
                continue

            tool_name = str(message.name or "tool").strip() or "tool"
            call_id = (
                str(message.tool_call_id or "unknown").strip()
                or "unknown"
            )
            reference = f"{tool_name}:{call_id}"
            if reference in seen:
                continue
            seen.add(reference)

            result.append(
                ContextEvidence(
                    reference=reference,
                    summary=self._summary(
                        tool_name,
                        str(message.content or ""),
                    ),
                    source=self._source(tool_name),
                    authority=ContextAuthority.TOOL_EVIDENCE,
                )
            )
            if len(result) >= self.max_evidence:
                break
        return tuple(result)

    def _source(self, tool_name: str) -> ContextSource:
        if tool_name in self.KNOWLEDGE_TOOLS:
            return ContextSource.RAG_EVIDENCE
        if tool_name in self.TEXT_TO_SQL_TOOLS:
            return ContextSource.TEXT_TO_SQL_RESULT
        return ContextSource.TOOL_RESULT

    def _summary(
        self,
        tool_name: str,
        content: str,
    ) -> str:
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return self._clip(f"{tool_name}: result observed")

        details: list[str] = []
        if isinstance(payload, list):
            details.append(f"rows={len(payload)}")
        elif isinstance(payload, dict):
            for key in self.SAFE_SCALARS:
                value = payload.get(key)
                if (
                    value is None
                    or isinstance(value, (dict, list))
                ):
                    continue
                details.append(f"{key}={value}")

            for key, label in (
                ("hits", "hits"),
                ("rows", "rows"),
                ("candidates", "candidates"),
                ("actions", "actions"),
                ("top_models", "top_models"),
            ):
                value = payload.get(key)
                if isinstance(value, list):
                    details.append(f"{label}={len(value)}")

        suffix = "; ".join(details[:6]) or "result observed"
        return self._clip(f"{tool_name}: {suffix}")

    def _clip(self, value: str) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > self.max_summary_chars:
            return text[: self.max_summary_chars - 1] + "…"
        return text


DEFAULT_CONTEXT_EVIDENCE_COLLECTOR = (
    CurrentTurnContextEvidenceCollector()
)


__all__ = [
    "CurrentTurnContextEvidenceCollector",
    "DEFAULT_CONTEXT_EVIDENCE_COLLECTOR",
]
