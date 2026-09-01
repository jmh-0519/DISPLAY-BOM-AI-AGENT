from __future__ import annotations

from pathlib import Path

from rag.index_service import RagIndexService
from rag.knowledge_models import KnowledgeDocument, KnowledgeDocumentMetadata, KnowledgeSection
from rag.knowledge_corpus import KnowledgeCorpus


class FakeEmbeddingProvider:
    def embed_texts(self, texts):
        return tuple((float(len(text)), 1.0) for text in texts)

    def embed_query(self, text):
        return (float(len(text)), 1.0)


class FakeStore:
    def __init__(self):
        self.chunks = ()
        self.embeddings = ()

    def replace_all(self, chunks, embeddings):
        self.chunks = tuple(chunks)
        self.embeddings = tuple(tuple(value) for value in embeddings)
        return len(self.chunks)

    def count(self):
        return len(self.chunks)

    def search(self, query_embedding, *, top_k, filters=None):
        return ()


def _document():
    metadata = KnowledgeDocumentMetadata(
        document_id="DOC-1",
        document_title="Guide",
        document_type="DESIGN_GUIDE",
        version="1",
        effective_date="2026-01-01",
        status="ACTIVE",
        language="KO",
        source_path=Path("knowledge/documents/guide.md"),
    )
    return KnowledgeDocument(
        metadata=metadata,
        sections=(KnowledgeSection("A", ("A",), "hello world", 1),),
    )


def test_index_service_rebuilds_active_corpus():
    store = FakeStore()
    result = RagIndexService(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
    ).rebuild(KnowledgeCorpus((_document(),)))

    assert result.document_count == 1
    assert result.chunk_count == 1
    assert result.indexed_chunk_count == 1
    assert result.embedding_dimension == 2
    assert store.count() == 1
