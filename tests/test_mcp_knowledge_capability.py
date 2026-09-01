from rag.retrieval_service import RagSearchResponse
from rag.vector_store import KnowledgeSearchHit
from mcp_server.capabilities.knowledge import search_knowledge_data


class FakeRetrieval:
    def search(self, query, *, top_k, filters):
        return RagSearchResponse(
            query=query,
            hits=(KnowledgeSearchHit(
                rank=1,
                chunk_id="EOL:1",
                content="단종 대응 교체 기준",
                distance=0.1,
                document_id="EOL",
                document_title="단종 대응",
                document_type="CHANGE_REASON",
                section_title="단종 대응",
                section_path="단종 대응",
                source_file="knowledge/reasons/EOL.md",
                source_page=None,
                metadata={},
            ),),
        )


def test_search_knowledge_data_serializes_read_only_evidence():
    result = search_knowledge_data(
        "단종 자재 교체 기준",
        retrieval_service=FakeRetrieval(),
    )
    assert result["success"] is True
    assert result["hit_count"] == 1
    assert result["hits"][0]["document_id"] == "EOL"
    assert result["authority"]["knowledge_evidence_only"] is True
    assert result["authority"]["production_bom_modified"] is False
