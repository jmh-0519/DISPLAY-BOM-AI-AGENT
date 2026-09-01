from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from .knowledge_models import KnowledgeChunk


@dataclass(frozen=True)
class KnowledgeSearchFilter:
    document_type: str | None = None
    status: str | None = "ACTIVE"
    language: str | None = None
    product_family: str | None = None
    material_type: str | None = None
    tag: str | None = None

    def normalized(self) -> "KnowledgeSearchFilter":
        return KnowledgeSearchFilter(
            document_type=_upper_or_none(self.document_type),
            status=_upper_or_none(self.status),
            language=_upper_or_none(self.language),
            product_family=_upper_or_none(self.product_family),
            material_type=_upper_or_none(self.material_type),
            tag=_upper_or_none(self.tag),
        )


@dataclass(frozen=True)
class KnowledgeSearchHit:
    rank: int
    chunk_id: str
    content: str
    distance: float | None
    document_id: str
    document_title: str
    document_type: str
    section_title: str
    section_path: str
    source_file: str
    source_page: int | None
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    def replace_all(
        self,
        chunks: Iterable[KnowledgeChunk],
        embeddings: Iterable[Iterable[float]],
    ) -> int: ...

    def search(
        self,
        query_embedding: Iterable[float],
        *,
        top_k: int,
        filters: KnowledgeSearchFilter | None = None,
    ) -> tuple[KnowledgeSearchHit, ...]: ...

    def count(self) -> int: ...


def _upper_or_none(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized.upper() if normalized else None


def _json_list(value: Any) -> str:
    if not isinstance(value, list):
        value = list(value or ()) if value else []
    return json.dumps([str(item) for item in value], ensure_ascii=False)


def _metadata_for_chroma(chunk: KnowledgeChunk) -> dict[str, str | int | float | bool]:
    metadata = dict(chunk.metadata)
    return {
        "document_id": chunk.document_id,
        "document_title": chunk.document_title,
        "document_type": chunk.document_type,
        "section_title": chunk.section_title,
        "section_path": chunk.section_path,
        "source_file": chunk.source_file,
        "source_page": int(chunk.source_page or 0),
        "content_hash": chunk.content_hash,
        "chunk_sequence": int(chunk.sequence),
        "status": str(metadata.get("status") or "").upper(),
        "language": str(metadata.get("language") or "").upper(),
        "version": str(metadata.get("version") or ""),
        "effective_date": str(metadata.get("effective_date") or ""),
        "product_families_json": _json_list(metadata.get("product_families")),
        "material_types_json": _json_list(metadata.get("material_types")),
        "tags_json": _json_list(metadata.get("tags")),
        "attributes_json": json.dumps(
            metadata.get("attributes") or {}, ensure_ascii=False, sort_keys=True
        ),
    }


def _decode_list(value: Any) -> tuple[str, ...]:
    try:
        raw = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def _passes_post_filter(
    metadata: dict[str, Any], filters: KnowledgeSearchFilter
) -> bool:
    product_families = {value.upper() for value in _decode_list(metadata.get("product_families_json"))}
    material_types = {value.upper() for value in _decode_list(metadata.get("material_types_json"))}
    tags = {value.upper() for value in _decode_list(metadata.get("tags_json"))}
    if filters.product_family and filters.product_family not in product_families:
        return False
    if filters.material_type and filters.material_type not in material_types:
        return False
    if filters.tag and filters.tag not in tags:
        return False
    return True


class ChromaVectorStore:
    """Persistent local Chroma store isolated from the BOM authority database."""

    def __init__(self, path: str | Path, collection_name: str) -> None:
        self.path = Path(path)
        self.collection_name = str(collection_name or "").strip()
        if not self.collection_name:
            raise ValueError("collection_name은 비어 있을 수 없습니다.")
        self.path.mkdir(parents=True, exist_ok=True)
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:
            raise RuntimeError(
                "chromadb가 설치되어 있지 않습니다. pip install -r requirements.txt를 실행하세요."
            ) from exc
        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name
        )

    def _reset_collection(self) -> None:
        try:
            self._client.delete_collection(name=self.collection_name)
        except Exception:
            # The collection may not exist yet. Recreate deterministically below.
            pass
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name
        )

    def replace_all(
        self,
        chunks: Iterable[KnowledgeChunk],
        embeddings: Iterable[Iterable[float]],
    ) -> int:
        chunk_list = list(chunks)
        embedding_list = [list(map(float, value)) for value in embeddings]
        if len(chunk_list) != len(embedding_list):
            raise ValueError("chunk 수와 embedding 수가 다릅니다.")
        if chunk_list and any(not value for value in embedding_list):
            raise ValueError("빈 embedding vector는 저장할 수 없습니다.")

        self._reset_collection()
        if not chunk_list:
            return 0
        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in chunk_list],
            embeddings=embedding_list,
            documents=[chunk.content for chunk in chunk_list],
            metadatas=[_metadata_for_chroma(chunk) for chunk in chunk_list],
        )
        return len(chunk_list)

    def count(self) -> int:
        return int(self._collection.count())

    def search(
        self,
        query_embedding: Iterable[float],
        *,
        top_k: int,
        filters: KnowledgeSearchFilter | None = None,
    ) -> tuple[KnowledgeSearchHit, ...]:
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")
        query_vector = list(map(float, query_embedding))
        if not query_vector:
            raise ValueError("query_embedding은 비어 있을 수 없습니다.")

        normalized_filter = (filters or KnowledgeSearchFilter()).normalized()
        where_parts: list[dict[str, Any]] = []
        for key, value in (
            ("document_type", normalized_filter.document_type),
            ("status", normalized_filter.status),
            ("language", normalized_filter.language),
        ):
            if value:
                where_parts.append({key: value})
        where: dict[str, Any] | None
        if not where_parts:
            where = None
        elif len(where_parts) == 1:
            where = where_parts[0]
        else:
            where = {"$and": where_parts}

        needs_post_filter = any(
            (
                normalized_filter.product_family,
                normalized_filter.material_type,
                normalized_filter.tag,
            )
        )
        requested = min(max(top_k * 5 if needs_post_filter else top_k, top_k), max(self.count(), top_k))
        if self.count() == 0:
            return ()

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": requested,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            kwargs["where"] = where
        result = self._collection.query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits: list[KnowledgeSearchHit] = []
        for chunk_id, content, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            metadata = dict(metadata or {})
            if not _passes_post_filter(metadata, normalized_filter):
                continue
            source_page = int(metadata.get("source_page") or 0) or None
            hits.append(
                KnowledgeSearchHit(
                    rank=len(hits) + 1,
                    chunk_id=str(chunk_id),
                    content=str(content or ""),
                    distance=float(distance) if distance is not None else None,
                    document_id=str(metadata.get("document_id") or ""),
                    document_title=str(metadata.get("document_title") or ""),
                    document_type=str(metadata.get("document_type") or ""),
                    section_title=str(metadata.get("section_title") or ""),
                    section_path=str(metadata.get("section_path") or ""),
                    source_file=str(metadata.get("source_file") or ""),
                    source_page=source_page,
                    metadata=metadata,
                )
            )
            if len(hits) >= top_k:
                break
        return tuple(hits)


__all__ = [
    "ChromaVectorStore",
    "KnowledgeSearchFilter",
    "KnowledgeSearchHit",
    "VectorStore",
]
