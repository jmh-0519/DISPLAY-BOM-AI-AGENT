from __future__ import annotations

from collections import Counter

from rag.chunker import StructureAwareChunker
from rag.knowledge_corpus import KnowledgeCorpus


def main() -> None:
    corpus = KnowledgeCorpus.from_knowledge_root("knowledge")
    chunks = StructureAwareChunker().chunk_documents(corpus.active_documents)
    counts = Counter(document.metadata.document_type for document in corpus.documents)

    if not corpus.documents:
        raise RuntimeError("knowledge corpus is empty")
    if not chunks:
        raise RuntimeError("knowledge corpus produced no chunks")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        raise RuntimeError("duplicate chunk_id detected")

    print("Knowledge document contract validation passed")
    print(f"- document_count: {len(corpus.documents)}")
    print(f"- active_document_count: {len(corpus.active_documents)}")
    print(f"- chunk_count: {len(chunks)}")
    print(f"- document_types: {dict(sorted(counts.items()))}")


if __name__ == "__main__":
    main()
