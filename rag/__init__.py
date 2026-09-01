"""Retrieval-Augmented Generation support for Display BOM AI Agent."""

from .config import RagSettings
from .embedding_client import AzureOpenAIEmbeddingClient, EmbeddingProvider
from .index_service import RagIndexBuildResult, RagIndexService
from .retrieval_service import RagRetrievalService, RagSearchResponse
from .vector_store import (
    ChromaVectorStore,
    KnowledgeSearchFilter,
    KnowledgeSearchHit,
    VectorStore,
)
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
    "RagSettings",
    "AzureOpenAIEmbeddingClient",
    "EmbeddingProvider",
    "RagIndexBuildResult",
    "RagIndexService",
    "RagRetrievalService",
    "RagSearchResponse",
    "ChromaVectorStore",
    "KnowledgeSearchFilter",
    "KnowledgeSearchHit",
    "VectorStore",
]
