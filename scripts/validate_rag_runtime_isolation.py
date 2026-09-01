from __future__ import annotations

from rag.chunker import StructureAwareChunker
from rag.config import RagSettings
from rag.knowledge_corpus import KnowledgeCorpus
from rag.vector_store import ChromaVectorStore


def main() -> None:
    runtime = KnowledgeCorpus.from_knowledge_root("knowledge", include_evaluation=False)
    evaluation = KnowledgeCorpus.from_knowledge_root("knowledge", include_evaluation=True)
    runtime_chunks = StructureAwareChunker().chunk_documents(runtime.active_documents)
    settings = RagSettings.from_env()
    store = ChromaVectorStore(settings.vector_store_path, settings.collection_name)
    actual = store.count()
    expected = len(runtime_chunks)
    if actual != expected:
        raise RuntimeError(
            "Runtime RAG index is stale or contaminated: "
            f"index_chunks={actual}, runtime_chunks={expected}. "
            "Run python -m scripts.build_rag_index."
        )
    eval_sources = [
        doc.metadata.source_path.as_posix()
        for doc in runtime.documents
        if "/documents/evaluation/" in "/" + doc.metadata.source_path.as_posix().lower().strip("/") + "/"
    ]
    if eval_sources:
        raise RuntimeError(f"Evaluation documents leaked into runtime corpus: {eval_sources}")
    print("RAG runtime isolation validation passed")
    print(f"- runtime_documents: {len(runtime.documents)}")
    print(f"- evaluation_documents: {len(evaluation.documents)}")
    print(f"- runtime_chunks: {expected}")
    print(f"- runtime_index_chunks: {actual}")
    print(f"- runtime_collection: {settings.collection_name}")


if __name__ == "__main__":
    main()
