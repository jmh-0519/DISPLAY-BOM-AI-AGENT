from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocumentMetadata:
    document_id: str
    document_title: str
    document_type: str
    version: str
    effective_date: str
    status: str
    language: str
    source_path: Path
    product_families: tuple[str, ...] = field(default_factory=tuple)
    material_types: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "document_type": self.document_type,
            "version": self.version,
            "effective_date": self.effective_date,
            "status": self.status,
            "language": self.language,
            "source_file": self.source_path.as_posix(),
            "product_families": list(self.product_families),
            "material_types": list(self.material_types),
            "tags": list(self.tags),
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class KnowledgeSection:
    title: str
    path: tuple[str, ...]
    content: str
    order: int
    page_number: int | None = None

    @property
    def section_path(self) -> str:
        return " > ".join(self.path)


@dataclass(frozen=True)
class KnowledgeDocument:
    metadata: KnowledgeDocumentMetadata
    sections: tuple[KnowledgeSection, ...]

    @property
    def content(self) -> str:
        return "\n\n".join(section.content for section in self.sections if section.content.strip())


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    sequence: int
    document_id: str
    document_title: str
    document_type: str
    section_title: str
    section_path: str
    content: str
    source_file: str
    source_page: int | None
    content_hash: str
    metadata: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        document: KnowledgeDocument,
        section: KnowledgeSection,
        sequence: int,
        content: str,
    ) -> "KnowledgeChunk":
        normalized = content.strip()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        chunk_id = f"{document.metadata.document_id}:{sequence:04d}:{digest[:12]}"
        metadata = document.metadata.as_dict()
        metadata.update(
            {
                "section_title": section.title,
                "section_path": section.section_path,
                "source_page": section.page_number,
                "chunk_sequence": sequence,
                "content_hash": digest,
            }
        )
        return cls(
            chunk_id=chunk_id,
            sequence=sequence,
            document_id=document.metadata.document_id,
            document_title=document.metadata.document_title,
            document_type=document.metadata.document_type,
            section_title=section.title,
            section_path=section.section_path,
            content=normalized,
            source_file=document.metadata.source_path.as_posix(),
            source_page=section.page_number,
            content_hash=digest,
            metadata=metadata,
        )

    @property
    def embedding_text(self) -> str:
        heading = self.document_title
        if self.section_path:
            heading = f"{heading}\nSection: {self.section_path}"
        return f"{heading}\n\n{self.content}".strip()
