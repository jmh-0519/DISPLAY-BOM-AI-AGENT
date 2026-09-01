from __future__ import annotations

from dataclasses import dataclass

from .chunker import StructureAwareChunker
from .embedding_client import EmbeddingProvider
from .knowledge_corpus import KnowledgeCorpus
from .vector_store import VectorStore


@dataclass(frozen=True)
class RagIndexBuildResult:
    document_count: int
    chunk_count: int
    indexed_chunk_count: int
    embedding_dimension: int


class RagIndexService:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        chunker: StructureAwareChunker | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.chunker = chunker or StructureAwareChunker()

    def rebuild(self, corpus: KnowledgeCorpus) -> RagIndexBuildResult:
        active_documents = corpus.active_documents
        chunks = self.chunker.chunk_documents(active_documents)
        embeddings = self.embedding_provider.embed_texts(
            chunk.embedding_text for chunk in chunks
        )
        if len(embeddings) != len(chunks):
            raise RuntimeError("생성된 embedding 수가 chunk 수와 다릅니다.")
        dimension = len(embeddings[0]) if embeddings else 0
        indexed = self.vector_store.replace_all(chunks, embeddings)
        return RagIndexBuildResult(
            document_count=len(active_documents),
            chunk_count=len(chunks),
            indexed_chunk_count=indexed,
            embedding_dimension=dimension,
        )


__all__ = ["RagIndexBuildResult", "RagIndexService"]
