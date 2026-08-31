from pathlib import Path

import pytest

from rag.knowledge_corpus import KnowledgeCorpus, KnowledgeCorpusError
from rag.knowledge_models import KnowledgeDocument, KnowledgeDocumentMetadata, KnowledgeSection


def test_current_reason_and_rule_catalogs_are_exposed_as_rag_documents():
    corpus = KnowledgeCorpus.from_knowledge_root("knowledge")

    assert len(corpus.by_type("CHANGE_REASON")) == 10
    assert len(corpus.by_type("CHANGE_RULE")) == 10
    assert all(document.metadata.status == "ACTIVE" for document in corpus.documents)
    assert any(
        "EOL" in document.metadata.tags
        for document in corpus.by_type("CHANGE_RULE")
    )


def test_corpus_rejects_duplicate_document_ids():
    metadata = KnowledgeDocumentMetadata(
        document_id="DUP",
        document_title="Duplicate",
        document_type="FAQ",
        version="1",
        effective_date="2026-08-31",
        status="ACTIVE",
        language="KO",
        source_path=Path("duplicate.md"),
    )
    document = KnowledgeDocument(
        metadata=metadata,
        sections=(KnowledgeSection("FAQ", ("FAQ",), "content", 1),),
    )

    with pytest.raises(KnowledgeCorpusError, match="duplicate document_id"):
        KnowledgeCorpus((document, document))
