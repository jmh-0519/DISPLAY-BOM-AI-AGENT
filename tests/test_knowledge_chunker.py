from pathlib import Path

from rag.chunker import StructureAwareChunker
from rag.knowledge_models import KnowledgeDocument, KnowledgeDocumentMetadata, KnowledgeSection


def _document(content: str) -> KnowledgeDocument:
    metadata = KnowledgeDocumentMetadata(
        document_id="DOC-1",
        document_title="Test Document",
        document_type="DESIGN_GUIDE",
        version="1.0",
        effective_date="2026-08-31",
        status="ACTIVE",
        language="KO",
        source_path=Path("knowledge/documents/test.md"),
    )
    section = KnowledgeSection(
        title="Electrical",
        path=("Replacement", "Electrical"),
        content=content,
        order=1,
    )
    return KnowledgeDocument(metadata=metadata, sections=(section,))


def test_chunker_keeps_short_section_as_single_chunk():
    chunks = StructureAwareChunker(max_chars=256, overlap_chars=32).chunk_document(
        _document("Voltage compatibility must be verified.")
    )

    assert len(chunks) == 1
    assert chunks[0].section_path == "Replacement > Electrical"
    assert chunks[0].embedding_text.startswith("Test Document\nSection: Replacement > Electrical")


def test_chunker_splits_long_text_with_stable_ids_and_overlap():
    content = "A" * 700
    chunker = StructureAwareChunker(max_chars=256, overlap_chars=32)

    first = chunker.chunk_document(_document(content))
    second = chunker.chunk_document(_document(content))

    assert len(first) > 1
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(len(chunk.content) <= 256 for chunk in first)
    assert first[0].content[-32:] == first[1].content[:32]
