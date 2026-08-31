"""Retrieval-Augmented Generation support for Display BOM AI Agent."""

from .chunker import StructureAwareChunker
from .document_loader import KnowledgeDocumentError, KnowledgeDocumentLoader
from .knowledge_corpus import KnowledgeCorpus, KnowledgeCorpusError
from .knowledge_models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSection,
)
from .reason_catalog import (
    ReasonAlias,
    ReasonCatalog,
    ReasonCatalogError,
    ReasonDocument,
    ReasonScope,
)
from .rule_catalog import (
    RuleCatalog,
    RuleCatalogError,
    RuleCondition,
    RuleDocument,
)

__all__ = [
    "KnowledgeChunk",
    "KnowledgeCorpus",
    "KnowledgeCorpusError",
    "KnowledgeDocument",
    "KnowledgeDocumentError",
    "KnowledgeDocumentLoader",
    "KnowledgeDocumentMetadata",
    "KnowledgeSection",
    "ReasonAlias",
    "ReasonCatalog",
    "ReasonCatalogError",
    "ReasonDocument",
    "ReasonScope",
    "RuleCatalog",
    "RuleCatalogError",
    "RuleCondition",
    "RuleDocument",
    "StructureAwareChunker",
]
