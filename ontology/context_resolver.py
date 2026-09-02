"""Deterministic context-resolution foundation.

CTX-01 provides conservative scope composition only.  It is intentionally not
wired into BomGraphGateway yet; CTX-02 will integrate it after behavior tests
are frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .context_contract import (
    ContextAuthority,
    ContextPurpose,
    ContextSource,
    ContextValue,
    DomainContextSnapshot,
)


@dataclass(frozen=True)
class ContextResolutionInput:
    purpose: ContextPurpose = ContextPurpose.GENERAL

    explicit_version_code: str | None = None
    explicit_plant_code: str | None = None
    explicit_target_item_code: str | None = None
    explicit_target_item_type: str | None = None
    explicit_target_item_name: str | None = None
    business_intent: str | None = None
    action_type: str | None = None
    user_goal: str | None = None
    optimization_criterion: str | None = None

    active_bom_context: Mapping[str, Any] | None = None
    workflow_state: Mapping[str, Any] | None = None

    # Inheritance is opt-in. The existing Gateway remains the authority that
    # decides whether a current turn is eligible for contextual continuation.
    allow_active_bom_scope: bool = False
    allow_workflow_scope: bool = False


class DomainContextResolverFoundation:
    """Build a provenance-aware context snapshot without LLM inference."""

    def resolve(self, request: ContextResolutionInput) -> DomainContextSnapshot:
        active = dict(request.active_bom_context or {})
        workflow = dict(request.workflow_state or {})

        explicit_version = self._upper(request.explicit_version_code)
        explicit_plant = self._upper(request.explicit_plant_code)

        active_version = self._upper(
            active.get("version_code") or active.get("product_id")
        )
        active_plant = self._upper(active.get("plant_code"))

        workflow_version, workflow_plant = self._workflow_scope(workflow)

        version_value: ContextValue | None = None
        plant_value: ContextValue | None = None

        if explicit_version:
            # Existing Agent/Gateway safety policy: an explicitly restated MODEL
            # declares a fresh scope. PLANT must also be explicit or resolved
            # again; never silently inherit the old PLANT.
            version_value = self._explicit(explicit_version)
            if explicit_plant:
                plant_value = self._explicit(explicit_plant)
        else:
            scope_candidates = self._scope_candidates(
                purpose=request.purpose,
                allow_active_bom_scope=request.allow_active_bom_scope,
                allow_workflow_scope=request.allow_workflow_scope,
                active_version=active_version,
                active_plant=active_plant,
                workflow_version=workflow_version,
                workflow_plant=workflow_plant,
            )

            selected = self._select_compatible_scope(
                scope_candidates,
                explicit_plant=explicit_plant,
            )
            if selected is not None:
                source, authority, version_code, plant_code = selected
                version_value = ContextValue(
                    version_code,
                    source=source,
                    authority=authority,
                    inherited=True,
                )
                if explicit_plant:
                    plant_value = self._explicit(explicit_plant)
                else:
                    plant_value = ContextValue(
                        plant_code,
                        source=source,
                        authority=authority,
                        inherited=True,
                    )
            elif explicit_plant:
                # PLANT without a compatible VERSION is kept as an explicit slot,
                # but no version is guessed from stale context.
                plant_value = self._explicit(explicit_plant)

        target_item_code = self._explicit_optional(
            self._upper(request.explicit_target_item_code)
        )
        target_item_type = self._explicit_optional(
            self._upper(request.explicit_target_item_type)
        )
        target_item_name = self._explicit_optional(
            self._clean(request.explicit_target_item_name)
        )

        analysis_id = self._workflow_optional(
            self._clean(workflow.get("analysis_id"))
        )
        request_id = self._workflow_optional(
            self._clean(workflow.get("request_id"))
        )
        workflow_step = self._workflow_optional(
            self._upper(workflow.get("current_step"))
        )

        return DomainContextSnapshot(
            purpose=request.purpose,
            version_code=version_value,
            plant_code=plant_value,
            target_item_code=target_item_code,
            target_item_type=target_item_type,
            target_item_name=target_item_name,
            business_intent=self._explicit_optional(
                self._upper(request.business_intent)
            ),
            action_type=self._explicit_optional(
                self._upper(request.action_type)
            ),
            user_goal=self._explicit_optional(
                self._clean(request.user_goal)
            ),
            optimization_criterion=self._explicit_optional(
                self._upper(request.optimization_criterion)
            ),
            analysis_id=analysis_id,
            request_id=request_id,
            workflow_step=workflow_step,
        )

    @classmethod
    def _scope_candidates(
        cls,
        *,
        purpose: ContextPurpose,
        allow_active_bom_scope: bool,
        allow_workflow_scope: bool,
        active_version: str | None,
        active_plant: str | None,
        workflow_version: str | None,
        workflow_plant: str | None,
    ) -> list[
        tuple[ContextSource, ContextAuthority, str, str]
    ]:
        active_candidate = (
            (
                ContextSource.ACTIVE_BOM,
                ContextAuthority.GRAPH_STATE,
                active_version,
                active_plant,
            )
            if allow_active_bom_scope and active_version and active_plant
            else None
        )
        workflow_candidate = (
            (
                ContextSource.DESIGN_CHANGE_WORKFLOW,
                ContextAuthority.WORKFLOW_STATE,
                workflow_version,
                workflow_plant,
            )
            if allow_workflow_scope and workflow_version and workflow_plant
            else None
        )

        # Preserve existing runtime semantics:
        # - read-only scope prefers currently viewed BOM;
        # - Design Change scope prefers its active workflow transaction.
        ordered = (
            (active_candidate, workflow_candidate)
            if purpose == ContextPurpose.READ_ONLY
            else (workflow_candidate, active_candidate)
        )
        return [value for value in ordered if value is not None]

    @staticmethod
    def _select_compatible_scope(
        candidates: list[
            tuple[ContextSource, ContextAuthority, str, str]
        ],
        *,
        explicit_plant: str | None,
    ) -> tuple[ContextSource, ContextAuthority, str, str] | None:
        for candidate in candidates:
            _source, _authority, _version, plant = candidate
            if explicit_plant and explicit_plant != plant:
                # A user-declared different PLANT invalidates this inherited
                # MODEL/PLANT pair; do not mix scopes.
                continue
            return candidate
        return None

    @classmethod
    def _workflow_scope(
        cls,
        workflow: Mapping[str, Any],
    ) -> tuple[str | None, str | None]:
        analysis_request = workflow.get("analysis_request")
        analysis_context = workflow.get("analysis_context")
        request = (
            dict(analysis_request)
            if isinstance(analysis_request, Mapping)
            else {}
        )
        context = (
            dict(analysis_context)
            if isinstance(analysis_context, Mapping)
            else {}
        )

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
        return version, plant

    @staticmethod
    def _explicit(value: Any) -> ContextValue:
        return ContextValue(
            value=value,
            source=ContextSource.CURRENT_TURN,
            authority=ContextAuthority.USER_DECLARED,
            inherited=False,
        )

    @classmethod
    def _explicit_optional(cls, value: Any) -> ContextValue | None:
        return cls._explicit(value) if value not in (None, "") else None

    @staticmethod
    def _workflow_optional(value: Any) -> ContextValue | None:
        if value in (None, ""):
            return None
        return ContextValue(
            value=value,
            source=ContextSource.DESIGN_CHANGE_WORKFLOW,
            authority=ContextAuthority.WORKFLOW_STATE,
            inherited=True,
        )

    @staticmethod
    def _clean(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @classmethod
    def _upper(cls, value: Any) -> str | None:
        text = cls._clean(value)
        return text.upper() if text else None


__all__ = [
    "ContextResolutionInput",
    "DomainContextResolverFoundation",
]
