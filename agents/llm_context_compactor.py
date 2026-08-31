from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)


@dataclass(frozen=True)
class LlmContextDietStats:
    original_tool_chars: int = 0
    compacted_tool_chars: int = 0
    compacted_tool_messages: int = 0

    @property
    def saved_tool_chars(self) -> int:
        return max(0, self.original_tool_chars - self.compacted_tool_chars)


class LlmContextCompactor:
    """Build a smaller LLM-only copy of LangGraph message history.

    Important boundary:
    - LangGraph state keeps the original ToolMessage payloads.
    - Streamlit renderers and Workflow Evidence keep the original payloads.
    - Only the copy sent to Azure OpenAI is compacted.

    This preserves business evidence while reducing TTFT/input-token cost.
    """

    HIGH_VOLUME_TOOLS = {
        "get_bom",
        "get_bom_where_used",
        "analyze_design_change_candidates",
        "revalidate_design_change_analysis",
        "scan_product_cost_reduction_candidates",
        "get_design_change_analysis",
        "get_candidate_evaluation_detail",
        "compare_design_change_candidates",
        "explain_design_change_analysis_session",
        "explain_design_change_analysis_candidate",
        "compare_design_change_analysis_candidates",
    }

    ID_KEYS = (
        "analysis_id", "request_id", "action_id", "candidate_id",
        "approval_id", "application_id", "change_id", "review_id",
    )
    STATUS_KEYS = (
        "status", "workflow_status", "evaluation_status", "analysis_status",
        "validation_status", "review_result", "result", "success",
        "request_created", "production_bom_modified",
    )
    SUMMARY_KEYS = (
        "summary", "message", "error_code", "status_counts",
        "candidate_count", "cost_reduction_status", "requires_impact_approval",
    )

    CANDIDATE_KEYS = (
        "candidate_id", "action_id", "candidate_item_code",
        "candidate_item_name", "candidate_name", "description", "status",
        "total_score", "rank", "recommended_supplier_item_id",
        "recommended_supplier_name", "supplier_name", "unit_cost",
        "price", "lead_time", "quality_grade", "decision_reason",
        "decision_reasons", "evaluation_reason", "reasons",
    )
    ACTION_KEYS = (
        "action_id", "action_type", "target_type", "old_item_code",
        "new_item_code", "target_item_name", "parent_item_code",
        "location_code", "old_quantity", "new_quantity", "status",
        "evaluation_status", "inventory_status", "available_quantity",
        "shortage_quantity", "decision_reasons",
    )
    BOM_KEYS = (
        "plant_code", "PLANT", "bom_parent", "PARENT_CODE",
        "bom_parent_name", "PARENT_NAME", "bom_child", "CHILD_CODE",
        "bom_child_name", "CHILD_NAME", "description", "DESCRIPTION",
        "location", "LOCATION", "quantity", "수량", "required_quantity",
        "소요수량",
    )

    QUERY_STOPWORDS = {
        "BOM", "제품", "모델", "자재", "품목", "수량", "변경", "바꾸고싶어",
        "바꿔줘", "알려줘", "보여줘", "조회", "후보", "분석", "왜", "이야",
        "인가", "얼마", "몇", "어디", "사용", "포함", "PLANT",
    }

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        current_tool_char_limit: int = 5000,
        historical_tool_char_limit: int = 1200,
        max_candidates: int = 6,
        max_bom_rows: int = 12,
    ) -> None:
        if enabled is None:
            enabled = str(os.getenv("BOM_LLM_CONTEXT_DIET", "1")).strip().lower() not in {
                "0", "false", "off", "no",
            }
        self.enabled = bool(enabled)
        self.current_tool_char_limit = current_tool_char_limit
        self.historical_tool_char_limit = historical_tool_char_limit
        self.max_candidates = max_candidates
        self.max_bom_rows = max_bom_rows

    def compact(
        self,
        messages: list[BaseMessage],
        *,
        current_user_query: str,
    ) -> tuple[list[BaseMessage], LlmContextDietStats]:
        if not self.enabled:
            total = sum(
                len(str(message.content or ""))
                for message in messages
                if isinstance(message, ToolMessage)
            )
            return list(messages), LlmContextDietStats(total, total, 0)

        current_human_index = -1
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                current_human_index = index
                break

        result: list[BaseMessage] = []
        original_chars = 0
        compacted_chars = 0
        compacted_count = 0

        for index, message in enumerate(messages):
            if not isinstance(message, ToolMessage):
                result.append(message)
                continue

            content = str(message.content or "")
            original_chars += len(content)
            current_turn = index > current_human_index
            compacted = self._compact_tool_content(
                tool_name=str(message.name or ""),
                content=content,
                current_turn=current_turn,
                current_user_query=current_user_query,
            )
            compacted_chars += len(compacted)
            if compacted != content:
                compacted_count += 1
                result.append(ToolMessage(
                    content=compacted,
                    tool_call_id=message.tool_call_id,
                    name=message.name,
                ))
            else:
                result.append(message)

        return result, LlmContextDietStats(
            original_tool_chars=original_chars,
            compacted_tool_chars=compacted_chars,
            compacted_tool_messages=compacted_count,
        )

    def _compact_tool_content(
        self,
        *,
        tool_name: str,
        content: str,
        current_turn: bool,
        current_user_query: str,
    ) -> str:
        limit = (
            self.current_tool_char_limit
            if current_turn
            else self.historical_tool_char_limit
        )
        if len(content) <= limit and tool_name not in self.HIGH_VOLUME_TOOLS:
            return content

        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            if len(content) <= limit:
                return content
            return json.dumps({
                "_context_diet": True,
                "tool_name": tool_name,
                "text_preview": content[:limit],
                "original_chars": len(content),
            }, ensure_ascii=False)

        if self._is_error_payload(payload):
            return self._serialize(self._error_summary(tool_name, payload))

        if not current_turn:
            return self._serialize(self._historical_summary(tool_name, payload))

        if tool_name == "get_bom":
            summary = self._bom_summary(payload, current_user_query)
        elif tool_name == "get_bom_where_used":
            summary = self._where_used_summary(payload)
        elif tool_name in {
            "analyze_design_change_candidates",
            "revalidate_design_change_analysis",
            }:
            summary = self._analysis_summary(tool_name, payload)
        elif tool_name == "scan_product_cost_reduction_candidates":
            summary = self._scan_summary(payload)
        elif tool_name in {
            "get_design_change_analysis",
            "get_candidate_evaluation_detail",
            "compare_design_change_candidates",
            "explain_design_change_analysis_session",
            "explain_design_change_analysis_candidate",
            "compare_design_change_analysis_candidates",
        }:
            summary = self._explain_summary(tool_name, payload)
        else:
            summary = self._generic_summary(tool_name, payload)

        serialized = self._serialize(summary)
        if len(serialized) <= limit:
            return serialized

        # Last-resort hard ceiling applies only to the LLM copy. The original
        # payload remains intact in Graph State and Workflow Evidence.
        return self._serialize({
            "_context_diet": True,
            "tool_name": tool_name,
            "summary_preview": serialized[: max(200, limit - 200)],
            "original_chars": len(content),
        })

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _is_error_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and (
            payload.get("success") is False
            or bool(payload.get("error"))
            or bool(payload.get("error_code"))
        )

    def _error_summary(self, tool_name: str, payload: dict) -> dict:
        return {
            "_context_diet": True,
            "tool_name": tool_name,
            "success": payload.get("success"),
            "error_code": payload.get("error_code"),
            "error": payload.get("error"),
            "message": payload.get("message"),
            "production_bom_modified": payload.get("production_bom_modified"),
        }

    def _historical_summary(self, tool_name: str, payload: Any) -> dict:
        summary: dict[str, Any] = {
            "_context_diet": True,
            "historical": True,
            "tool_name": tool_name,
        }
        if isinstance(payload, list):
            summary["row_count"] = len(payload)
            if tool_name == "get_bom" and payload:
                first = payload[0] if isinstance(payload[0], dict) else {}
                summary["scope"] = self._pick(first, (
                    "plant_code", "PLANT", "bom_parent", "PARENT_CODE",
                ))
            return summary

        if not isinstance(payload, dict):
            summary["value_type"] = type(payload).__name__
            return summary

        summary.update(self._pick(payload, self.ID_KEYS + self.STATUS_KEYS + self.SUMMARY_KEYS))
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            summary["candidate_count"] = len(candidates)
        actions = payload.get("actions")
        if isinstance(actions, list):
            summary["action_count"] = len(actions)
        return summary

    def _analysis_summary(self, tool_name: str, payload: Any) -> dict:
        if not isinstance(payload, dict):
            return self._generic_summary(tool_name, payload)
        result = {
            "_context_diet": True,
            "tool_name": tool_name,
        }
        result.update(self._pick(payload, self.ID_KEYS + self.STATUS_KEYS + self.SUMMARY_KEYS))
        if isinstance(payload.get("request"), dict):
            result["request"] = self._compact_mapping(payload["request"], max_items=20)

        actions = payload.get("actions")
        if isinstance(actions, list):
            result["actions"] = [
                self._pick(row, self.ACTION_KEYS)
                for row in actions[:8]
                if isinstance(row, dict)
            ]
            if len(actions) > 8:
                result["omitted_actions"] = len(actions) - 8

        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            result["candidate_count"] = len(candidates)
            result["candidates"] = [
                self._pick(row, self.CANDIDATE_KEYS)
                for row in candidates[: self.max_candidates]
                if isinstance(row, dict)
            ]
            if len(candidates) > self.max_candidates:
                result["omitted_candidates"] = len(candidates) - self.max_candidates

        if isinstance(payload.get("analysis_context"), dict):
            result["analysis_context"] = self._compact_mapping(
                payload["analysis_context"], max_items=20
            )
        if isinstance(payload.get("revalidation"), dict):
            result["revalidation"] = self._compact_mapping(
                payload["revalidation"], max_items=16
            )
        return result

    def _scan_summary(self, payload: Any) -> dict:
        if not isinstance(payload, dict):
            return self._generic_summary("scan_product_cost_reduction_candidates", payload)
        result = {
            "_context_diet": True,
            "tool_name": "scan_product_cost_reduction_candidates",
        }
        result.update(self._pick(payload, self.ID_KEYS + self.STATUS_KEYS + self.SUMMARY_KEYS))
        for key in ("opportunities", "candidates", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                result[f"{key}_count"] = len(rows)
                result[key] = [
                    self._compact_mapping(row, max_items=14)
                    for row in rows[: self.max_candidates]
                    if isinstance(row, dict)
                ]
                if len(rows) > self.max_candidates:
                    result[f"omitted_{key}"] = len(rows) - self.max_candidates
                break
        return result

    def _explain_summary(self, tool_name: str, payload: Any) -> dict:
        if not isinstance(payload, dict):
            return self._generic_summary(tool_name, payload)
        result = {"_context_diet": True, "tool_name": tool_name}
        result.update(self._pick(payload, self.ID_KEYS + self.STATUS_KEYS + self.SUMMARY_KEYS))
        for key in ("actions", "candidates", "evidence", "reasons", "details"):
            value = payload.get(key)
            if isinstance(value, list):
                result[key] = [
                    self._compact_mapping(row, max_items=14)
                    if isinstance(row, dict) else row
                    for row in value[: self.max_candidates]
                ]
                if len(value) > self.max_candidates:
                    result[f"omitted_{key}"] = len(value) - self.max_candidates
            elif isinstance(value, dict):
                result[key] = self._compact_mapping(value, max_items=18)
        return result

    def _where_used_summary(self, payload: Any) -> dict:
        if not isinstance(payload, dict):
            return self._generic_summary("get_bom_where_used", payload)
        result = {
            "_context_diet": True,
            "tool_name": "get_bom_where_used",
        }
        result.update(self._pick(payload, (
            "plant_code", "item_code", "item_name", "description",
            "top_models", "direct_parents", "summary", "message",
        )))
        paths = payload.get("paths") or payload.get("bom_paths")
        if isinstance(paths, list):
            result["path_count"] = len(paths)
            result["paths"] = paths[:6]
            if len(paths) > 6:
                result["omitted_paths"] = len(paths) - 6
        return result

    def _bom_summary(self, payload: Any, current_user_query: str) -> dict:
        if not isinstance(payload, list):
            return self._generic_summary("get_bom", payload)
        rows = [row for row in payload if isinstance(row, dict)]
        result: dict[str, Any] = {
            "_context_diet": True,
            "tool_name": "get_bom",
            "row_count": len(rows),
        }
        if not rows:
            return result

        result["scope"] = self._pick(rows[0], (
            "plant_code", "PLANT", "product_id", "version_code",
            "bom_parent", "PARENT_CODE",
        ))

        matched = self._matching_bom_rows(rows, current_user_query)
        selected = matched[: self.max_bom_rows]
        if not selected:
            selected = rows[: min(self.max_bom_rows, len(rows))]
            result["selection"] = "sample_rows"
        else:
            result["selection"] = "query_matching_rows"

        result["rows"] = [self._pick(row, self.BOM_KEYS) for row in selected]
        if len(rows) > len(selected):
            result["omitted_rows"] = len(rows) - len(selected)
        return result

    def _matching_bom_rows(self, rows: list[dict], query: str) -> list[dict]:
        upper_query = str(query or "").upper()
        word_terms = self._query_match_terms(upper_query)

        scored: list[tuple[int, dict]] = []
        ordered_codes = list(re.findall(
            r"[A-Z0-9]+(?:-[A-Z0-9]+)+", upper_query
        ))
        for row in rows:
            haystack = " ".join(str(row.get(key) or "") for key in self.BOM_KEYS).upper()
            score = 0
            # Later codes in a normal design-change sentence are usually the
            # target item, while the first code is commonly the product root.
            for code_index, code in enumerate(ordered_codes):
                if code in haystack:
                    score += 100 + (code_index * 25)
            # Name/alias terms (e.g. SEALANT) are target evidence and therefore
            # outrank a generic product-root match.
            for term in word_terms:
                if term in haystack:
                    score += 200
            if score:
                scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in scored]

    @classmethod
    def _query_match_terms(cls, query: str) -> set[str]:
        """Return lexical terms that can safely match BOM row evidence.

        Important: Korean particles can be attached directly to English BOM
        terminology, e.g. ``SEALANT를``. A mixed-script token regex would keep
        that as one token and fail to match the canonical BOM value
        ``SEALANT``.

        Split ASCII/domain terms and Korean words independently so:

            SEALANT를 -> SEALANT
            0001-200010을 -> 0001-200010 (codes are handled separately too)

        Korean words keep a small particle trim for normal phrases, while
        routing/intent stopwords are excluded.
        """
        upper_query = str(query or "").upper()

        # Keep ASCII domain terms independent from attached Korean particles.
        ascii_terms = re.findall(r"[A-Z][A-Z0-9_-]+", upper_query)

        korean_terms: list[str] = []
        for token in re.findall(r"[가-힣]{2,}", upper_query):
            normalized = token
            for suffix in (
                "에서", "으로", "에게", "부터", "까지",
                "은", "는", "이", "가", "을", "를", "의", "와", "과", "로",
            ):
                if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
                    normalized = normalized[: -len(suffix)]
                    break
            if normalized:
                korean_terms.append(normalized)

        return {
            token
            for token in (*ascii_terms, *korean_terms)
            if (
                len(token) >= 2
                and token not in cls.QUERY_STOPWORDS
                and not token.startswith("P0")
            )
        }

    def _generic_summary(self, tool_name: str, payload: Any) -> dict:
        result: dict[str, Any] = {
            "_context_diet": True,
            "tool_name": tool_name,
        }
        if isinstance(payload, list):
            result["row_count"] = len(payload)
            result["sample"] = [
                self._compact_mapping(row, max_items=10)
                if isinstance(row, dict) else row
                for row in payload[:4]
            ]
            return result
        if isinstance(payload, dict):
            result.update(self._pick(payload, self.ID_KEYS + self.STATUS_KEYS + self.SUMMARY_KEYS))
            if len(result) <= 2:
                result["data"] = self._compact_mapping(payload, max_items=16)
            return result
        result["value"] = payload
        return result

    @staticmethod
    def _pick(mapping: dict, keys: tuple[str, ...]) -> dict:
        return {
            key: mapping.get(key)
            for key in keys
            if key in mapping and mapping.get(key) is not None
        }

    @classmethod
    def _compact_mapping(cls, mapping: dict, *, max_items: int) -> dict:
        result: dict[str, Any] = {}
        for key, value in mapping.items():
            if len(result) >= max_items:
                break
            if isinstance(value, str):
                result[key] = value if len(value) <= 500 else value[:500] + "…"
            elif isinstance(value, (int, float, bool)) or value is None:
                result[key] = value
            elif isinstance(value, list) and len(value) <= 6 and all(
                isinstance(item, (str, int, float, bool, type(None))) for item in value
            ):
                result[key] = [
                    item if not isinstance(item, str) or len(item) <= 300
                    else item[:300] + "…"
                    for item in value
                ]
            elif isinstance(value, dict):
                simple = {
                    nested_key: nested_value
                    for nested_key, nested_value in value.items()
                    if isinstance(nested_value, (str, int, float, bool, type(None)))
                }
                if simple:
                    result[key] = dict(list(simple.items())[:8])
        return result
