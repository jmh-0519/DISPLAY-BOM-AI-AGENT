from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ActionType(StrEnum):
    REPLACE = "REPLACE"
    ADD = "ADD"
    DELETE = "DELETE"
    QUANTITY_CHANGE = "QUANTITY_CHANGE"


class TargetType(StrEnum):
    MATERIAL = "MATERIAL"
    ASSY = "ASSY"


class EvaluationStatus(StrEnum):
    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ChangeAction:
    action_id: str
    action_type: ActionType
    target_type: TargetType
    parent_item_code: str
    location_code: str
    old_item_code: str | None = None
    new_item_code: str | None = None
    old_quantity: float | None = None
    new_quantity: float | None = None


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    revision_no: int
    status: EvaluationStatus
    raw_score: float
    weight: float
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.raw_score * self.weight


@dataclass(frozen=True)
class SupplierSelection:
    supplier_item_id: int
    supplier_code: str
    unit_price: float | None
    lead_time_days: int | None
    quality_grade: str | None
    stability_score: float | None


@dataclass(frozen=True)
class Candidate:
    candidate_item_code: str
    status: EvaluationStatus
    total_score: float
    grade: str
    rank: int | None
    supplier: SupplierSelection | None = None
    rule_results: tuple[RuleResult, ...] = ()
    missing_data: tuple[str, ...] = ()
    conditional_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Approval:
    approval_id: str
    stage: str
    decision: str
    approved_by: str
    reason: str | None = None


@dataclass(frozen=True)
class Impact:
    impacted_item_code: str
    impact_type: str
    impact_path: str


@dataclass(frozen=True)
class ApplyResult:
    apply_id: str
    request_id: str
    result: str
    action_count: int
