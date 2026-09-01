from rag.evidence_enricher import enrich_design_change_evidence
from rag.retrieval_service import RagSearchResponse
from rag.vector_store import KnowledgeSearchHit


class FakeRetrieval:
    def search(self, query, *, top_k, filters):
        assert "EOL" in query
        return RagSearchResponse(
            query=query,
            hits=(KnowledgeSearchHit(
                rank=1,
                chunk_id="rule:1",
                content="EOL replacement guide",
                distance=0.2,
                document_id="DC-R-001",
                document_title="EOL MATERIAL suitability",
                document_type="CHANGE_RULE",
                section_title="Rule",
                section_path="Rule",
                source_file="knowledge/rules/DC-R-001_EOL_DRIVE_IC.md",
                source_page=None,
                metadata={},
            ),),
        )


def test_enrichment_never_changes_authoritative_status():
    payload = {
        "candidate_item_code": "X",
        "final_status": "FAIL",
        "reason_code": "EOL",
        "rule_id": "DC-R-001",
    }
    result = enrich_design_change_evidence(
        payload,
        retrieval_service=FakeRetrieval(),
        enabled=True,
    )
    assert result["final_status"] == "FAIL"
    assert result["candidate_item_code"] == "X"
    assert result["knowledge_evidence"][0]["document_id"] == "DC-R-001"
    assert result["knowledge_authority"]["may_change_business_status"] is False


def test_enrichment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RAG_DESIGN_CHANGE_EVIDENCE_ENABLED", raising=False)
    payload = {"final_status": "PASS", "reason_code": "EOL"}
    assert enrich_design_change_evidence(payload) == payload
