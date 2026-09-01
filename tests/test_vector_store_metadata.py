from __future__ import annotations

from pathlib import Path

from rag.knowledge_models import KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentMetadata, KnowledgeSection
from rag.vector_store import KnowledgeSearchFilter, _metadata_for_chroma, _passes_post_filter


def _chunk():
    metadata = KnowledgeDocumentMetadata(
        document_id="DOC-1",
        document_title="Guide",
        document_type="DESIGN_GUIDE",
        version="1",
        effective_date="2026-01-01",
        status="ACTIVE",
        language="KO",
        source_path=Path("knowledge/documents/guide.md"),
        product_families=("LCD", "OLED"),
        material_types=("DRIVE-IC",),
        tags=("EOL", "REPLACE"),
    )
    document = KnowledgeDocument(
        metadata=metadata,
        sections=(KnowledgeSection("Section", ("Section",), "content", 1),),
    )
    return KnowledgeChunk.create(
        document=document,
        section=document.sections[0],
        sequence=1,
        content="content",
    )


def test_chroma_metadata_is_scalar_and_post_filterable():
    metadata = _metadata_for_chroma(_chunk())
    assert all(isinstance(value, (str, int, float, bool)) for value in metadata.values())
    assert _passes_post_filter(
        metadata,
        KnowledgeSearchFilter(
            product_family="lcd",
            material_type="drive-ic",
            tag="eol",
        ).normalized(),
    )
    assert not _passes_post_filter(
        metadata,
        KnowledgeSearchFilter(material_type="FILM").normalized(),
    )
