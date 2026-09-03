"""PLAN-01 bounded planner contract for multi-capability goals.

This module plans only. It does not execute capabilities and grants no
Request/approval/Production BOM authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agents.capability_requirement_resolver import (
    Capability,
    CapabilityRequirementDecision,
    CapabilityRequirementResolver,
    DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER,
)


class PlanStepMode(str, Enum):
    READ_ONLY_ANALYTICS = "READ_ONLY_ANALYTICS"
    READ_ONLY_KNOWLEDGE = "READ_ONLY_KNOWLEDGE"
    READ_ONLY_DOMAIN = "READ_ONLY_DOMAIN"
    WORKFLOW_ANALYSIS_ONLY = "WORKFLOW_ANALYSIS_ONLY"


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    sequence: int
    capability: Capability
    mode: PlanStepMode
    depends_on: tuple[str, ...] = ()
    evidence_output: str = ""
    request_creation_allowed: bool = False
    approval_allowed: bool = False
    production_write_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "sequence": self.sequence,
            "capability": self.capability.value,
            "mode": self.mode.value,
            "depends_on": list(self.depends_on),
            "evidence_output": self.evidence_output,
            "request_creation_allowed": self.request_creation_allowed,
            "approval_allowed": self.approval_allowed,
            "production_write_allowed": self.production_write_allowed,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    user_goal: str
    required_capabilities: tuple[Capability, ...]
    steps: tuple[PlanStep, ...]
    workflow_managed: bool
    final_synthesis_required: bool = True
    execution_enabled: bool = False
    planner_mode: str = "DETERMINISTIC_SELECTIVE_FOUNDATION"

    @property
    def capability_names(self) -> tuple[str, ...]:
        return tuple(x.value for x in self.required_capabilities)

    @property
    def write_authority_granted(self) -> bool:
        return any(
            s.request_creation_allowed or s.approval_allowed
            or s.production_write_allowed
            for s in self.steps
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "required_capabilities": list(self.capability_names),
            "steps": [s.as_dict() for s in self.steps],
            "workflow_managed": self.workflow_managed,
            "final_synthesis_required": self.final_synthesis_required,
            "execution_enabled": self.execution_enabled,
            "planner_mode": self.planner_mode,
            "write_authority_granted": self.write_authority_granted,
        }


class SelectivePlanner:
    """Plan only when CTX-05 says composition_required=True."""

    SUPPORTED = frozenset({
        Capability.BOM_READ,
        Capability.WHERE_USED,
        Capability.CURRENT_BOM_QUANTITY,
        Capability.TEXT_TO_SQL,
        Capability.RAG,
        Capability.PRODUCT_COST_SCAN,
        Capability.DESIGN_CHANGE_ANALYSIS,
    })
    ORDER = {
        Capability.BOM_READ: 10,
        Capability.WHERE_USED: 20,
        Capability.CURRENT_BOM_QUANTITY: 30,
        Capability.TEXT_TO_SQL: 40,
        Capability.RAG: 50,
        Capability.PRODUCT_COST_SCAN: 60,
        Capability.DESIGN_CHANGE_ANALYSIS: 70,
    }

    def __init__(
        self,
        *,
        capability_resolver: CapabilityRequirementResolver | None = None,
    ) -> None:
        self.capability_resolver = (
            capability_resolver or DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
        )

    def plan_if_needed(
        self,
        user_goal: str,
        requirement: CapabilityRequirementDecision | None = None,
    ) -> ExecutionPlan | None:
        req = requirement or self.capability_resolver.resolve(user_goal)
        if not req.composition_required:
            return None
        return self.build_plan(user_goal, req)

    def build_plan(
        self,
        user_goal: str,
        requirement: CapabilityRequirementDecision,
    ) -> ExecutionPlan:
        goal = " ".join(str(user_goal or "").strip().split())
        if not goal:
            raise ValueError("planner requires a non-empty user goal")
        if not requirement.composition_required or len(requirement.capabilities) < 2:
            raise ValueError("planner accepts multi-capability requirements only")

        unsupported = [c for c in requirement.capabilities if c not in self.SUPPORTED]
        if unsupported:
            raise ValueError(
                "unsupported composition capability: "
                + ",".join(c.value for c in unsupported)
            )

        ordered = tuple(sorted(requirement.capabilities, key=self.ORDER.__getitem__))
        steps: list[PlanStep] = []
        prior_ids: list[str] = []
        for i, capability in enumerate(ordered, start=1):
            step_id = f"step_{i:02d}_{capability.value.lower()}"
            depends = (
                tuple(prior_ids)
                if capability == Capability.DESIGN_CHANGE_ANALYSIS
                else ()
            )
            step = PlanStep(
                step_id=step_id,
                sequence=i,
                capability=capability,
                mode=self._mode(capability),
                depends_on=depends,
                evidence_output=self._evidence(capability),
            )
            steps.append(step)
            prior_ids.append(step_id)

        plan = ExecutionPlan(
            user_goal=goal,
            required_capabilities=ordered,
            steps=tuple(steps),
            workflow_managed=requirement.workflow_managed,
        )
        self.validate(plan)
        return plan

    @classmethod
    def validate(cls, plan: ExecutionPlan) -> None:
        if plan.execution_enabled:
            raise ValueError("PLAN-01 must not enable runtime execution")
        if plan.write_authority_granted:
            raise ValueError("planner must not grant write authority")

        seen: set[str] = set()
        for expected, step in enumerate(plan.steps, start=1):
            if step.sequence != expected:
                raise ValueError("plan sequence must be contiguous")
            if any(dep not in seen for dep in step.depends_on):
                raise ValueError("dependencies must reference earlier steps")
            seen.add(step.step_id)

        if Capability.DESIGN_CHANGE_ANALYSIS in plan.required_capabilities:
            last = plan.steps[-1]
            if last.capability != Capability.DESIGN_CHANGE_ANALYSIS:
                raise ValueError("Design Change Analysis must be last")
            expected = tuple(s.step_id for s in plan.steps[:-1])
            if expected and last.depends_on != expected:
                raise ValueError(
                    "Design Change Analysis must depend on prior evidence"
                )

    @staticmethod
    def _mode(capability: Capability) -> PlanStepMode:
        if capability == Capability.TEXT_TO_SQL:
            return PlanStepMode.READ_ONLY_ANALYTICS
        if capability == Capability.RAG:
            return PlanStepMode.READ_ONLY_KNOWLEDGE
        if capability in {
            Capability.PRODUCT_COST_SCAN,
            Capability.DESIGN_CHANGE_ANALYSIS,
        }:
            return PlanStepMode.WORKFLOW_ANALYSIS_ONLY
        return PlanStepMode.READ_ONLY_DOMAIN

    @staticmethod
    def _evidence(capability: Capability) -> str:
        if capability == Capability.TEXT_TO_SQL:
            return "TEXT_TO_SQL_RESULT"
        if capability == Capability.RAG:
            return "RAG_EVIDENCE"
        return "TOOL_RESULT"


DEFAULT_SELECTIVE_PLANNER = SelectivePlanner()
