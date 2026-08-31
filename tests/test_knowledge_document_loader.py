from pathlib import Path

import pytest

from rag.document_loader import KnowledgeDocumentError, KnowledgeDocumentLoader


MARKDOWN = '''+++
document_id = "DG-TEST-001"
document_title = "Drive IC Guide"
document_type = "DESIGN_GUIDE"
version = "1.0"
effective_date = "2026-08-31"
status = "ACTIVE"
language = "KO"
product_families = ["LCD"]
material_types = ["DRIVE-IC"]
tags = ["TEST"]

[attributes]
owner = "DISPLAY_ENGINEERING"
+++

# Overview

Drive IC replacement guidance.

## Electrical

Voltage compatibility must be verified.
'''


def test_markdown_loader_preserves_metadata_and_heading_structure(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text(MARKDOWN, encoding="utf-8")

    document = KnowledgeDocumentLoader().load(path)

    assert document.metadata.document_id == "DG-TEST-001"
    assert document.metadata.document_type == "DESIGN_GUIDE"
    assert document.metadata.material_types == ("DRIVE-IC",)
    assert document.metadata.attributes["owner"] == "DISPLAY_ENGINEERING"
    assert [section.title for section in document.sections] == ["Overview", "Electrical"]
    assert document.sections[1].section_path == "Overview > Electrical"


def test_text_document_requires_sidecar_metadata(tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("Supplier qualification is required.", encoding="utf-8")

    with pytest.raises(KnowledgeDocumentError, match="metadata sidecar is required"):
        KnowledgeDocumentLoader().load(path)


def test_text_document_loads_with_sidecar_metadata(tmp_path: Path):
    path = tmp_path / "policy.txt"
    path.write_text("Supplier qualification is required.", encoding="utf-8")
    (tmp_path / "policy.meta.toml").write_text(
        '''document_id = "POL-001"\n'
        'document_title = "Supplier Policy"\n'
        'document_type = "CHANGE_POLICY"\n'
        'version = "1.0"\n'
        'effective_date = "2026-08-31"\n'
        'status = "ACTIVE"\n'
        'language = "KO"\n'''.replace("'", ""),
        encoding="utf-8",
    )

    document = KnowledgeDocumentLoader().load(path)

    assert document.metadata.document_id == "POL-001"
    assert document.sections[0].content == "Supplier qualification is required."


def test_loader_rejects_unknown_document_type(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text(MARKDOWN.replace("DESIGN_GUIDE", "UNKNOWN"), encoding="utf-8")

    with pytest.raises(KnowledgeDocumentError, match="unsupported document_type"):
        KnowledgeDocumentLoader().load(path)
