from __future__ import annotations

from rag.retrieval_service import RagRetrievalService
from rag.vector_store import KnowledgeSearchFilter, KnowledgeSearchHit


class FakeEmbeddingProvider:
    def embed_texts(self, texts):
        return tuple((1.0, 0.0) for _ in texts)

    def embed_query(self, text):
        assert text == "단종 자재 교체 기준"
        return (1.0, 0.0)


class FakeStore:
    def __init__(self):
        self.received = None

    def replace_all(self, chunks, embeddings):
        return 0

    def count(self):
        return 1

    def search(self, query_embedding, *, top_k, filters=None):
        self.received = (tuple(query_embedding), top_k, filters)
        return (
            KnowledgeSearchHit(
                rank=1,
                chunk_id="RULE:DC-R-001:R1:0001",
                content="EOL replacement policy",
                distance=0.12,
                document_id="RULE:DC-R-001:R1",
                document_title="EOL MATERIAL suitability",
                document_type="CHANGE_RULE",
                section_title="EOL MATERIAL suitability",
                section_path="EOL MATERIAL suitability",
                source_file="knowledge/rules/DC-R-001_EOL_DRIVE_IC.md",
                source_page=None,
            ),
        )


def test_retrieval_service_returns_structured_hits():
    store = FakeStore()
    service = RagRetrievalService(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
    )
    filters = KnowledgeSearchFilter(document_type="change_rule")

    result = service.search("단종 자재 교체 기준", top_k=5, filters=filters)

    assert result.query == "단종 자재 교체 기준"
    assert len(result.hits) == 1
    assert result.hits[0].document_type == "CHANGE_RULE"
    assert store.received[0] == (1.0, 0.0)
    assert store.received[1] == 5
    assert store.received[2] == filters
