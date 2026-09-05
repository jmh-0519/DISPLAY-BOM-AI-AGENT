"""Shared context contract for Display BOM Agent.

The contract separates:
- entity meaning (ontology),
- current runtime context,
- source/authority,
- inheritance policy.

CTX-01 does not change routing behavior.  CTX-02 will connect this contract to
the existing Gateway/Agent runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .domain_ontology import DomainEntityType


class ContextPurpose(str, Enum):
    GENERAL = "GENERAL"
    READ_ONLY = "READ_ONLY"
    DESIGN_CHANGE = "DESIGN_CHANGE"


class ContextSource(str, Enum):
    CURRENT_TURN = "CURRENT_TURN"
    ACTIVE_BOM = "ACTIVE_BOM"
    DESIGN_CHANGE_WORKFLOW = "DESIGN_CHANGE_WORKFLOW"
    PENDING_SLOT = "PENDING_SLOT"
    TOOL_RESULT = "TOOL_RESULT"
    RAG_EVIDENCE = "RAG_EVIDENCE"
    TEXT_TO_SQL_RESULT = "TEXT_TO_SQL_RESULT"
    SYSTEM = "SYSTEM"


class ContextAuthority(str, Enum):
    USER_DECLARED = "USER_DECLARED"
    GRAPH_STATE = "GRAPH_STATE"
    WORKFLOW_STATE = "WORKFLOW_STATE"
    TOOL_EVIDENCE = "TOOL_EVIDENCE"
    SYSTEM_POLICY = "SYSTEM_POLICY"
    DERIVED = "DERIVED"


class ContextInheritanceMode(str, Enum):
    CONDITIONAL_SCOPE = "CONDITIONAL_SCOPE"
    EXPLICIT_OR_WORKFLOW = "EXPLICIT_OR_WORKFLOW"
    CURRENT_TURN_ONLY = "CURRENT_TURN_ONLY"
    WORKFLOW_ONLY = "WORKFLOW_ONLY"
    TOOL_EVIDENCE_ONLY = "TOOL_EVIDENCE_ONLY"


@dataclass(frozen=True)
class ContextFieldPolicy:
    field_name: str
    entity_type: DomainEntityType | None
    inheritance_mode: ContextInheritanceMode
    allowed_sources: tuple[ContextSource, ...]
    description: str


@dataclass(frozen=True)
class ContextValue:
    value: Any
    source: ContextSource
    authority: ContextAuthority
    inherited: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "source": self.source.value,
            "authority": self.authority.value,
            "inherited": self.inherited,
        }


@dataclass(frozen=True)
class ContextEvidence:
    reference: str
    summary: str
    source: ContextSource = ContextSource.TOOL_RESULT
    authority: ContextAuthority = ContextAuthority.TOOL_EVIDENCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "summary": self.summary,
            "source": self.source.value,
            "authority": self.authority.value,
        }


@dataclass(frozen=True)
class DomainContextSnapshot:
    """Resolved context values with provenance.

    This object deliberately contains no approval/write authority.  IDs and
    workflow_step are observational references to authoritative workflow state.
    """

    purpose: ContextPurpose = ContextPurpose.GENERAL
    version_code: ContextValue | None = None
    plant_code: ContextValue | None = None
    target_item_code: ContextValue | None = None
    target_item_type: ContextValue | None = None
    target_item_name: ContextValue | None = None
    target_parent_item_code: ContextValue | None = None
    target_location_code: ContextValue | None = None
    business_intent: ContextValue | None = None
    action_type: ContextValue | None = None
    user_goal: ContextValue | None = None
    optimization_criterion: ContextValue | None = None
    analysis_id: ContextValue | None = None
    request_id: ContextValue | None = None
    workflow_step: ContextValue | None = None
    evidence: tuple[ContextEvidence, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        values: dict[str, Any] = {"purpose": self.purpose.value}
        for field_name in (
            "version_code",
            "plant_code",
            "target_item_code",
            "target_item_type",
            "target_item_name",
            "target_parent_item_code",
            "target_location_code",
            "business_intent",
            "action_type",
            "user_goal",
            "optimization_criterion",
            "analysis_id",
            "request_id",
            "workflow_step",
        ):
            value = getattr(self, field_name)
            values[field_name] = value.as_dict() if value is not None else None
        values["evidence"] = [value.as_dict() for value in self.evidence]
        return values


CONTEXT_FIELD_POLICIES: dict[str, ContextFieldPolicy] = {
    "version_code": ContextFieldPolicy(
        "version_code",
        DomainEntityType.VERSION,
        ContextInheritanceMode.CONDITIONAL_SCOPE,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.ACTIVE_BOM,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
        ),
        "VERSION may be inherited only from an explicit validated scope.",
    ),
    "plant_code": ContextFieldPolicy(
        "plant_code",
        DomainEntityType.PLANT,
        ContextInheritanceMode.CONDITIONAL_SCOPE,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.ACTIVE_BOM,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
        ),
        "PLANT may be inherited only when MODEL/VERSION scope is unchanged.",
    ),
    "target_item_code": ContextFieldPolicy(
        "target_item_code",
        DomainEntityType.ITEM,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
            ContextSource.TOOL_RESULT,
        ),
        "A change target is never inherited from generic chat or active BOM alone.",
    ),
    "target_item_type": ContextFieldPolicy(
        "target_item_type",
        DomainEntityType.ITEM,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
            ContextSource.TOOL_RESULT,
        ),
        "Target type must be explicit or come from authoritative workflow/tool state.",
    ),
    "target_item_name": ContextFieldPolicy(
        "target_item_name",
        DomainEntityType.ITEM,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
            ContextSource.TOOL_RESULT,
        ),
        "Target name must not be guessed from unrelated previous conversation.",
    ),
    "target_parent_item_code": ContextFieldPolicy(
        "target_parent_item_code",
        DomainEntityType.ITEM,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.TOOL_RESULT,
        ),
        "Parent ITEM is part of the exact BOM edge and must be explicit or workflow/tool authoritative.",
    ),
    "target_location_code": ContextFieldPolicy(
        "target_location_code",
        None,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.TOOL_RESULT,
        ),
        "LOCATION is part of the exact BOM edge and must not be inferred from generic chat history.",
    ),
    "business_intent": ContextFieldPolicy(
        "business_intent",
        None,
        ContextInheritanceMode.CURRENT_TURN_ONLY,
        (ContextSource.CURRENT_TURN,),
        "Current-turn intent is authoritative; history must not redefine it.",
    ),
    "action_type": ContextFieldPolicy(
        "action_type",
        None,
        ContextInheritanceMode.EXPLICIT_OR_WORKFLOW,
        (
            ContextSource.CURRENT_TURN,
            ContextSource.DESIGN_CHANGE_WORKFLOW,
            ContextSource.PENDING_SLOT,
        ),
        "Action may continue only from an explicit workflow transaction, never generic chat.",
    ),
    "user_goal": ContextFieldPolicy(
        "user_goal",
        None,
        ContextInheritanceMode.CURRENT_TURN_ONLY,
        (ContextSource.CURRENT_TURN,),
        "Current user goal is not silently copied from historical conversation.",
    ),
    "optimization_criterion": ContextFieldPolicy(
        "optimization_criterion",
        None,
        ContextInheritanceMode.CURRENT_TURN_ONLY,
        (ContextSource.CURRENT_TURN,),
        "Cost/lead-time/inventory optimization is current-turn intent unless explicitly persisted later.",
    ),
    "analysis_id": ContextFieldPolicy(
        "analysis_id",
        DomainEntityType.ANALYSIS_SESSION,
        ContextInheritanceMode.WORKFLOW_ONLY,
        (ContextSource.DESIGN_CHANGE_WORKFLOW,),
        "Analysis ID can only come from workflow state.",
    ),
    "request_id": ContextFieldPolicy(
        "request_id",
        DomainEntityType.CHANGE_REQUEST,
        ContextInheritanceMode.WORKFLOW_ONLY,
        (ContextSource.DESIGN_CHANGE_WORKFLOW,),
        "Request ID can only come from workflow state.",
    ),
    "workflow_step": ContextFieldPolicy(
        "workflow_step",
        DomainEntityType.DESIGN_CHANGE,
        ContextInheritanceMode.WORKFLOW_ONLY,
        (ContextSource.DESIGN_CHANGE_WORKFLOW,),
        "Workflow step is authoritative workflow state, not LLM inference.",
    ),
    "evidence": ContextFieldPolicy(
        "evidence",
        None,
        ContextInheritanceMode.TOOL_EVIDENCE_ONLY,
        (
            ContextSource.TOOL_RESULT,
            ContextSource.RAG_EVIDENCE,
            ContextSource.TEXT_TO_SQL_RESULT,
        ),
        "Evidence must originate from an actual retrieval/tool execution.",
    ),
}


def validate_context_snapshot(snapshot: DomainContextSnapshot) -> None:
    """Enforce the declared field-source contract at runtime.

    The current release turns CONTEXT_FIELD_POLICIES from documentation into an
    executable safety invariant. The resolver calls this before returning a
    snapshot, and tests may validate externally constructed snapshots as well.
    """
    if not isinstance(snapshot, DomainContextSnapshot):
        raise TypeError("snapshot must be DomainContextSnapshot")

    for field_name, policy in CONTEXT_FIELD_POLICIES.items():
        if field_name == "evidence":
            for evidence in snapshot.evidence:
                if evidence.source not in policy.allowed_sources:
                    raise ValueError(
                        f"context field {field_name} disallows source {evidence.source.value}"
                    )
                if evidence.authority != ContextAuthority.TOOL_EVIDENCE:
                    raise ValueError("context evidence must remain TOOL_EVIDENCE authoritative")
            continue

        value = getattr(snapshot, field_name)
        if value is None:
            continue
        if value.source not in policy.allowed_sources:
            raise ValueError(
                f"context field {field_name} disallows source {value.source.value}"
            )
        if value.source == ContextSource.CURRENT_TURN and value.inherited:
            raise ValueError(f"current-turn context cannot be inherited: {field_name}")
        if (
            policy.inheritance_mode == ContextInheritanceMode.WORKFLOW_ONLY
            and value.source != ContextSource.DESIGN_CHANGE_WORKFLOW
        ):
            raise ValueError(f"workflow-only context has invalid source: {field_name}")
        if (
            policy.inheritance_mode == ContextInheritanceMode.CURRENT_TURN_ONLY
            and value.source != ContextSource.CURRENT_TURN
        ):
            raise ValueError(f"current-turn-only context has invalid source: {field_name}")


__all__ = [
    "CONTEXT_FIELD_POLICIES",
    "ContextAuthority",
    "ContextEvidence",
    "ContextFieldPolicy",
    "ContextInheritanceMode",
    "ContextPurpose",
    "ContextSource",
    "ContextValue",
    "DomainContextSnapshot",
    "validate_context_snapshot",
]
