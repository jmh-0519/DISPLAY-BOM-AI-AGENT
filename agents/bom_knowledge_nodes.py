"""Deterministic LangGraph path for high-confidence Knowledge RAG questions."""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.bom_agent_state import BomAgentState
from rag.query_router import DEFAULT_KNOWLEDGE_QUERY_ROUTER, KnowledgeQueryRouter


KNOWLEDGE_FINALIZE = "knowledge_finalize"
KNOWLEDGE_TOOL_CALL_PREFIX = "knowledge-fast-"


class BomKnowledgePathNodes:
    def __init__(self, *, client, router: KnowledgeQueryRouter | None = None) -> None:
        self.client = client
        self.router = router or DEFAULT_KNOWLEDGE_QUERY_ROUTER

    def query(self, state: BomAgentState) -> BomAgentState:
        user_query = self._last_user_query(state)
        decision = self.router.route(user_query)
        if not decision.eligible:
            raise ValueError("Knowledge Path received a non-knowledge request.")
        args: dict[str, object] = {"query": user_query, "top_k": 5}
        if decision.document_type:
            args["document_type"] = decision.document_type
        return {
            "messages": [AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_knowledge",
                    "args": args,
                    "id": f"{KNOWLEDGE_TOOL_CALL_PREFIX}{uuid.uuid4().hex[:12]}",
                    "type": "tool_call",
                }],
            )],
            "error": None,
        }

    def finalize(self, state: BomAgentState) -> BomAgentState:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], ToolMessage):
            raise ValueError("Knowledge Finalizer requires a ToolMessage result.")
        tool_message = messages[-1]
        try:
            payload = json.loads(str(tool_message.content or "{}"))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        hits = payload.get("hits") if isinstance(payload.get("hits"), list) else []
        if not payload.get("success") or not hits:
            answer = (
                "관련 Knowledge 근거를 찾지 못했습니다. "
                "현재 Knowledge 문서 범위를 확인해 주세요."
            )
        else:
            compact = {
                "query": payload.get("query"),
                "authority": payload.get("authority"),
                "hits": [
                    {
                        "rank": hit.get("rank"),
                        "document_id": hit.get("document_id"),
                        "document_title": hit.get("document_title"),
                        "document_type": hit.get("document_type"),
                        "section_path": hit.get("section_path"),
                        "source_file": hit.get("source_file"),
                        "content": str(hit.get("content") or "")[:1200],
                    }
                    for hit in hits[:5]
                    if isinstance(hit, dict)
                ],
            }
            answer = self.client.create_knowledge_final_answer(
                user_message=self._last_user_query(state),
                knowledge_evidence=json.dumps(compact, ensure_ascii=False),
            )
            references = self._reference_lines(hits)
            if references:
                answer = f"{answer.rstrip()}\n\n참고 근거\n" + "\n".join(references)
        return {"messages": [AIMessage(content=answer)], "error": None}

    @staticmethod
    def _reference_lines(hits: list[dict]) -> list[str]:
        lines: list[str] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            source = str(hit.get("source_file") or "").strip()
            title = str(hit.get("document_title") or "").strip()
            key = (str(hit.get("document_id") or ""), source)
            if not source or key in seen:
                continue
            seen.add(key)
            doc_type = str(hit.get("document_type") or "KNOWLEDGE").strip()
            section = str(hit.get("section_path") or "").strip()
            suffix = f" / {section}" if section else ""
            lines.append(f"- [{doc_type}] {title}{suffix} — {source}")
            if len(lines) >= 5:
                break
        return lines

    @staticmethod
    def _last_user_query(state: BomAgentState) -> str:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content or "").strip()
        return str(state.get("user_query") or "").strip()


def is_knowledge_tool_result(state: BomAgentState) -> bool:
    messages = state.get("messages", [])
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False
    message = messages[-1]
    return (
        message.name == "search_knowledge"
        and str(message.tool_call_id or "").startswith(KNOWLEDGE_TOOL_CALL_PREFIX)
    )


__all__ = [
    "BomKnowledgePathNodes",
    "KNOWLEDGE_FINALIZE",
    "KNOWLEDGE_TOOL_CALL_PREFIX",
    "is_knowledge_tool_result",
]
