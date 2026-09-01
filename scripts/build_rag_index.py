from __future__ import annotations

import argparse

from rag.chunker import StructureAwareChunker
from rag.config import RagSettings
from rag.embedding_client import AzureOpenAIEmbeddingClient
from rag.index_service import RagIndexService
from rag.knowledge_corpus import KnowledgeCorpus
from rag.vector_store import ChromaVectorStore


def build_index(*, knowledge_root: str = "knowledge"):
    settings = RagSettings.from_env()
    corpus = KnowledgeCorpus.from_knowledge_root(
        knowledge_root, include_evaluation=False
    )
    service = RagIndexService(
        embedding_provider=AzureOpenAIEmbeddingClient(settings),
        vector_store=ChromaVectorStore(
            settings.vector_store_path,
            settings.collection_name,
        ),
        chunker=StructureAwareChunker(),
    )
    return service.rebuild(corpus)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the local persistent RAG vector index from managed knowledge documents."
    )
    parser.add_argument("--knowledge-root", default="knowledge")
    args = parser.parse_args()
    result = build_index(knowledge_root=args.knowledge_root)
    print("RAG index build passed")
    print(f"- document_count: {result.document_count}")
    print(f"- chunk_count: {result.chunk_count}")
    print(f"- indexed_chunk_count: {result.indexed_chunk_count}")
    print(f"- embedding_dimension: {result.embedding_dimension}")


if __name__ == "__main__":
    main()
