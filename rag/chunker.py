from __future__ import annotations

from dataclasses import dataclass

from .knowledge_models import KnowledgeChunk, KnowledgeDocument, KnowledgeSection


@dataclass(frozen=True)
class StructureAwareChunker:
    """Deterministic section-preserving chunker used before embedding."""

    max_chars: int = 3200
    overlap_chars: int = 400

    def __post_init__(self) -> None:
        if self.max_chars < 256:
            raise ValueError("max_chars must be >= 256")
        if self.overlap_chars < 0:
            raise ValueError("overlap_chars must be >= 0")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")

    def chunk_document(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        sequence = 0
        for section in document.sections:
            for content in self._split_section(section):
                sequence += 1
                chunks.append(
                    KnowledgeChunk.create(
                        document=document,
                        section=section,
                        sequence=sequence,
                        content=content,
                    )
                )
        return tuple(chunks)

    def chunk_documents(self, documents: tuple[KnowledgeDocument, ...] | list[KnowledgeDocument]) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        for document in documents:
            chunks.extend(self.chunk_document(document))
        return tuple(chunks)

    def _split_section(self, section: KnowledgeSection) -> tuple[str, ...]:
        text = section.content.strip()
        if not text:
            return ()
        if len(text) <= self.max_chars:
            return (text,)

        paragraphs = [value.strip() for value in text.split("\n\n") if value.strip()]
        if len(paragraphs) <= 1:
            return self._sliding_windows(text)

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._sliding_windows(paragraph))
                continue

            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= self.max_chars:
                current = candidate
                continue

            chunks.append(current.strip())
            overlap = current[-self.overlap_chars :].strip() if self.overlap_chars else ""
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
            if len(current) > self.max_chars:
                windows = self._sliding_windows(current)
                chunks.extend(windows[:-1])
                current = windows[-1]

        if current:
            chunks.append(current.strip())
        return tuple(value for value in chunks if value)

    def _sliding_windows(self, text: str) -> tuple[str, ...]:
        step = self.max_chars - self.overlap_chars
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.max_chars)
            value = text[start:end].strip()
            if value:
                chunks.append(value)
            if end >= len(text):
                break
            start += step
        return tuple(chunks)
