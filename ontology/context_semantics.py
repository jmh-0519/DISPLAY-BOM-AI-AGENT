"""Deterministic relative-reference and scope semantics for Display BOM context.

This module centralizes language-independent runtime meaning that was previously
spread across Gateway guards.  This module never calls an LLM, database, Tool,
or workflow mutation API.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class RelativeReferenceType(str, Enum):
    MODEL_SCOPE = "MODEL_SCOPE"
    BOM_SCOPE = "BOM_SCOPE"
    TARGET_ITEM = "TARGET_ITEM"
    TARGET_ASSY = "TARGET_ASSY"
    WORKFLOW_ANALYSIS = "WORKFLOW_ANALYSIS"


class ScopeRelation(str, Enum):
    SAME = "SAME"
    DIFFERENT = "DIFFERENT"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ScopeIdentity:
    version_code: str
    plant_code: str
    source: str

    @property
    def key(self) -> str:
        return f"{self.version_code}/{self.plant_code}"


@dataclass(frozen=True)
class RelativeReferenceDecision:
    references: tuple[RelativeReferenceType, ...]

    @property
    def has_relative_reference(self) -> bool:
        return bool(self.references)

    @property
    def requires_scope_alignment(self) -> bool:
        return any(
            value in {
                RelativeReferenceType.MODEL_SCOPE,
                RelativeReferenceType.BOM_SCOPE,
                RelativeReferenceType.TARGET_ITEM,
                RelativeReferenceType.TARGET_ASSY,
            }
            for value in self.references
        )

    @property
    def workflow_only_reference(self) -> bool:
        return bool(self.references) and all(
            value == RelativeReferenceType.WORKFLOW_ANALYSIS
            for value in self.references
        )


class ContextSemanticResolver:
    """Resolve relative-reference meaning and compare runtime scope identities."""

    REFERENCE_MARKERS: tuple[tuple[RelativeReferenceType, tuple[str, ...]], ...] = (
        (
            RelativeReferenceType.MODEL_SCOPE,
            (
                "이 모델", "이모델", "현재 모델", "현재모델", "그 모델",
                "해당 모델", "방금 본 모델",
            ),
        ),
        (
            RelativeReferenceType.BOM_SCOPE,
            (
                "이 BOM", "이BOM", "현재 BOM", "현재BOM", "그 BOM",
                "해당 BOM", "방금 본 BOM",
            ),
        ),
        (
            RelativeReferenceType.TARGET_ITEM,
            (
                "이 자재", "이자재", "그 자재", "해당 자재", "방금 본 자재",
                "이 품목", "이품목", "그 품목", "해당 품목", "방금 본 품목",
            ),
        ),
        (
            RelativeReferenceType.TARGET_ASSY,
            (
                "이 ASSY", "이ASSY", "그 ASSY", "해당 ASSY", "방금 본 ASSY",
                "이 어셈블리", "그 어셈블리", "해당 어셈블리",
            ),
        ),
        (
            RelativeReferenceType.WORKFLOW_ANALYSIS,
            (
                "이 분석", "현재 분석", "기존 분석", "방금 분석",
                "이 분석 결과", "현재 분석 결과", "기존 분석 결과",
            ),
        ),
    )

    def classify_relative_references(
        self,
        user_query: str,
    ) -> RelativeReferenceDecision:
        compact = " ".join(str(user_query or "").strip().split())
        lowered = compact.lower()
        found: list[RelativeReferenceType] = []
        for reference_type, markers in self.REFERENCE_MARKERS:
            if any(marker.lower() in lowered for marker in markers):
                found.append(reference_type)
        return RelativeReferenceDecision(tuple(found))

    @classmethod
    def active_bom_scope(
        cls,
        active_bom_context: Mapping[str, Any] | None,
    ) -> ScopeIdentity | None:
        active = dict(active_bom_context or {})
        version = cls._upper(active.get("version_code") or active.get("product_id"))
        plant = cls._upper(active.get("plant_code"))
        if not version or not plant:
            return None
        return ScopeIdentity(version, plant, "ACTIVE_BOM")

    @classmethod
    def workflow_scope(
        cls,
        workflow_state: Mapping[str, Any] | None,
    ) -> ScopeIdentity | None:
        workflow = dict(workflow_state or {})
        analysis_request = workflow.get("analysis_request")
        analysis_context = workflow.get("analysis_context")
        request = dict(analysis_request) if isinstance(analysis_request, Mapping) else {}
        context = dict(analysis_context) if isinstance(analysis_context, Mapping) else {}

        version = cls._upper(
            request.get("version_code")
            or request.get("product_id")
            or context.get("version_code")
            or context.get("product_id")
            or workflow.get("product_id")
        )
        plant = cls._upper(
            workflow.get("plant_code")
            or request.get("plant_code")
            or context.get("plant_code")
        )
        if not version or not plant:
            return None
        return ScopeIdentity(version, plant, "DESIGN_CHANGE_WORKFLOW")

    @classmethod
    def compare_runtime_scopes(
        cls,
        *,
        active_bom_context: Mapping[str, Any] | None,
        workflow_state: Mapping[str, Any] | None,
    ) -> tuple[ScopeRelation, ScopeIdentity | None, ScopeIdentity | None]:
        active = cls.active_bom_scope(active_bom_context)
        workflow = cls.workflow_scope(workflow_state)
        if active is None or workflow is None:
            return ScopeRelation.INCOMPLETE, active, workflow
        relation = (
            ScopeRelation.SAME
            if (active.version_code, active.plant_code)
            == (workflow.version_code, workflow.plant_code)
            else ScopeRelation.DIFFERENT
        )
        return relation, active, workflow

    @staticmethod
    def _upper(value: Any) -> str | None:
        text = str(value or "").strip()
        return text.upper() if text else None


DEFAULT_CONTEXT_SEMANTIC_RESOLVER = ContextSemanticResolver()


__all__ = [
    "ContextSemanticResolver",
    "DEFAULT_CONTEXT_SEMANTIC_RESOLVER",
    "RelativeReferenceDecision",
    "RelativeReferenceType",
    "ScopeIdentity",
    "ScopeRelation",
]
