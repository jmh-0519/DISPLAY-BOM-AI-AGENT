"""Display BOM domain ontology and context-contract foundation."""

from .context_contract import (
    CONTEXT_FIELD_POLICIES,
    ContextAuthority,
    ContextEvidence,
    ContextFieldPolicy,
    ContextInheritanceMode,
    ContextPurpose,
    ContextSource,
    ContextValue,
    DomainContextSnapshot,
    validate_context_snapshot,
)
from .context_semantics import (
    ContextSemanticResolver,
    DEFAULT_CONTEXT_SEMANTIC_RESOLVER,
    RelativeReferenceDecision,
    RelativeReferenceType,
    ScopeIdentity,
    ScopeRelation,
)
from .context_resolver import (
    ContextResolutionInput,
    DEFAULT_DOMAIN_CONTEXT_RESOLVER,
    DomainContextResolverFoundation,
)
from .context_projection import (
    ContextProjectionResult,
    DEFAULT_LLM_CONTEXT_PROJECTOR,
    LlmContextProjector,
)
from .domain_ontology import (
    DEFAULT_DOMAIN_ONTOLOGY,
    DomainEntityType,
    DomainOntology,
    DomainRelationType,
    OntologyRelation,
)

__all__ = [
    "CONTEXT_FIELD_POLICIES",
    "ContextAuthority",
    "ContextEvidence",
    "ContextFieldPolicy",
    "ContextInheritanceMode",
    "ContextPurpose",
    "ContextProjectionResult",
    "ContextResolutionInput",
    "ContextSemanticResolver",
    "ContextSource",
    "DEFAULT_CONTEXT_SEMANTIC_RESOLVER",
    "DEFAULT_DOMAIN_CONTEXT_RESOLVER",
    "DEFAULT_LLM_CONTEXT_PROJECTOR",
    "ContextValue",
    "DEFAULT_DOMAIN_ONTOLOGY",
    "DomainContextResolverFoundation",
    "DomainContextSnapshot",
    "DomainEntityType",
    "DomainOntology",
    "DomainRelationType",
    "LlmContextProjector",
    "OntologyRelation",
    "RelativeReferenceDecision",
    "RelativeReferenceType",
    "ScopeIdentity",
    "ScopeRelation",
    "validate_context_snapshot",
]
