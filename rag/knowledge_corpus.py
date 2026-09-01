from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .document_loader import KnowledgeDocumentLoader
from .knowledge_models import KnowledgeDocument, KnowledgeDocumentMetadata, KnowledgeSection
from .reason_catalog import ReasonCatalog, ReasonDocument
from .rule_catalog import RuleCatalog, RuleDocument


class KnowledgeCorpusError(ValueError):
    """Knowledge sources cannot be composed into a deterministic corpus."""


def _rule_to_document(rule: RuleDocument) -> KnowledgeDocument:
    metadata = KnowledgeDocumentMetadata(
        document_id=f"RULE:{rule.rule_id}:R{rule.revision_no}",
        document_title=rule.rule_name,
        document_type="CHANGE_RULE",
        version=str(rule.revision_no),
        effective_date=rule.valid_from,
        status=rule.status,
        language="KO",
        source_path=rule.source_path,
        material_types=(rule.evaluation_item,),
        tags=tuple(
            dict.fromkeys(
                (*rule.tags, *rule.reason_codes, *rule.action_types, *rule.target_types)
            )
        ),
        attributes={
            "rule_id": rule.rule_id,
            "reason_codes": list(rule.reason_codes),
            "action_types": list(rule.action_types),
            "target_types": list(rule.target_types),
            "evaluation_item": rule.evaluation_item,
        },
    )
    section = KnowledgeSection(
        title=rule.rule_name,
        path=(rule.rule_name,),
        content=rule.rag_text(),
        order=1,
    )
    return KnowledgeDocument(metadata=metadata, sections=(section,))


def _reason_to_document(reason: ReasonDocument) -> KnowledgeDocument:
    metadata = KnowledgeDocumentMetadata(
        document_id=f"REASON:{reason.reason_code}",
        document_title=reason.reason_name_ko,
        document_type="CHANGE_REASON",
        version="1",
        effective_date=reason.valid_from,
        status=reason.status,
        language="KO",
        source_path=reason.source_path,
        tags=tuple(dict.fromkeys((*reason.tags, reason.reason_code, reason.category))),
        attributes={
            "reason_code": reason.reason_code,
            "category": reason.category,
            "scopes": [
                f"{scope.target_type}/{scope.action_type}" for scope in reason.scopes
            ],
        },
    )
    section = KnowledgeSection(
        title=reason.reason_name_ko,
        path=(reason.reason_name_ko,),
        content=reason.rag_text(),
        order=1,
    )
    return KnowledgeDocument(metadata=metadata, sections=(section,))


@dataclass(frozen=True)
class KnowledgeCorpus:
    documents: tuple[KnowledgeDocument, ...]

    def __post_init__(self) -> None:
        ids = [document.metadata.document_id for document in self.documents]
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        if duplicates:
            raise KnowledgeCorpusError(f"duplicate document_id values: {duplicates}")

    @classmethod
    def from_knowledge_root(
        cls,
        root: str | Path = "knowledge",
        *,
        include_evaluation: bool = True,
    ) -> "KnowledgeCorpus":
        knowledge_root = Path(root)
        documents: list[KnowledgeDocument] = []

        reason_dir = knowledge_root / "reasons"
        if reason_dir.exists():
            documents.extend(
                _reason_to_document(reason)
                for reason in ReasonCatalog.from_directory(reason_dir).reasons
            )

        rule_dir = knowledge_root / "rules"
        if rule_dir.exists():
            documents.extend(
                _rule_to_document(rule)
                for rule in RuleCatalog.from_directory(rule_dir).rules
            )

        loaded_documents = list(
            KnowledgeDocumentLoader().load_directory(knowledge_root / "documents")
        )
        if not include_evaluation:
            loaded_documents = [
                document
                for document in loaded_documents
                if "/documents/evaluation/" not in (
                    "/"
                    + str(document.metadata.source_path).replace("\\", "/").lower().strip("/")
                    + "/"
                )
            ]
        documents.extend(loaded_documents)
        return cls(tuple(sorted(documents, key=lambda value: value.metadata.document_id)))

    def by_type(self, document_type: str) -> tuple[KnowledgeDocument, ...]:
        requested = str(document_type or "").strip().upper()
        return tuple(
            document
            for document in self.documents
            if document.metadata.document_type == requested
        )

    @property
    def active_documents(self) -> tuple[KnowledgeDocument, ...]:
        return tuple(
            document for document in self.documents if document.metadata.status == "ACTIVE"
        )


__all__ = ["KnowledgeCorpus", "KnowledgeCorpusError"]
