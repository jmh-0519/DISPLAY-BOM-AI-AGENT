import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents.context_evidence import CurrentTurnContextEvidenceCollector
from ontology.context_contract import (
    ContextAuthority,
    ContextEvidence,
    ContextSource,
)
from ontology.context_resolver import (
    ContextResolutionInput,
    DomainContextResolverFoundation,
)


def test_collector_uses_only_current_turn_tool_messages_and_safe_summary():
    messages = [
        HumanMessage(content="old"),
        ToolMessage(
            content=json.dumps({
                "request_id": "OLD",
                "secret_payload": "DO-NOT-COPY",
            }),
            tool_call_id="old-call",
            name="get_design_change_analysis",
        ),
        HumanMessage(content="current"),
        AIMessage(content=""),
        ToolMessage(
            content=json.dumps({
                "success": True,
                "analysis_id": "ANA-1",
                "candidate_count": 5,
                "raw_rows": ["sensitive"] * 50,
            }),
            tool_call_id="new-call",
            name="analyze_design_change_candidates",
        ),
    ]

    evidence = CurrentTurnContextEvidenceCollector().collect(messages)

    assert len(evidence) == 1
    assert evidence[0].reference == (
        "analyze_design_change_candidates:new-call"
    )
    assert evidence[0].source == ContextSource.TOOL_RESULT
    assert evidence[0].authority == ContextAuthority.TOOL_EVIDENCE
    assert "analysis_id=ANA-1" in evidence[0].summary
    assert "candidate_count=5" in evidence[0].summary
    assert "sensitive" not in evidence[0].summary
    assert "DO-NOT-COPY" not in evidence[0].summary


def test_collector_classifies_knowledge_and_future_text_to_sql_evidence():
    collector = CurrentTurnContextEvidenceCollector()
    messages = [
        HumanMessage(content="q"),
        ToolMessage(
            content=json.dumps({"success": True, "hit_count": 3}),
            tool_call_id="rag-1",
            name="search_knowledge",
        ),
        ToolMessage(
            content=json.dumps({"status": "SQL", "row_count": 4}),
            tool_call_id="sql-1",
            name="text_to_sql",
        ),
    ]

    evidence = collector.collect(messages)

    assert evidence[0].source == ContextSource.RAG_EVIDENCE
    assert evidence[1].source == ContextSource.TEXT_TO_SQL_RESULT


def test_resolver_accepts_only_tool_authoritative_evidence_and_deduplicates():
    evidence = ContextEvidence(
        reference="get_bom:1",
        summary="rows=10",
        source=ContextSource.TOOL_RESULT,
        authority=ContextAuthority.TOOL_EVIDENCE,
    )
    snapshot = DomainContextResolverFoundation().resolve(
        ContextResolutionInput(
            evidence=(evidence, evidence),
        )
    )
    assert snapshot.evidence == (evidence,)


def test_resolver_rejects_conversation_text_as_evidence():
    invalid = ContextEvidence(
        reference="chat:1",
        summary="user said this is true",
        source=ContextSource.CURRENT_TURN,
        authority=ContextAuthority.USER_DECLARED,
    )
    with pytest.raises(ValueError):
        DomainContextResolverFoundation().resolve(
            ContextResolutionInput(evidence=(invalid,))
        )
