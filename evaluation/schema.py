from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


SCHEMA_VERSION = "1.0"

ALLOWED_CATEGORIES = frozenset({
    "CHAT",
    "BOM_READ",
    "WHERE_USED",
    "CONTEXT",
    "REPLACE",
    "ADD",
    "DELETE",
    "QUANTITY_CHANGE",
    "SAFETY",
    "KNOWLEDGE",
    "ANALYTICS",
    "COMPOSITION",
})

ALLOWED_INTENTS = frozenset({
    "CHAT",
    "BOM_READ",
    "WHERE_USED",
    "CURRENT_BOM_QUANTITY",
    "DESIGN_CHANGE",
    "DESIGN_CHANGE_RECOMMENDATION",
    "LLM_FALLBACK",
    "PRODUCT_COST_SCAN",
})

ALLOWED_EXECUTION_PATHS = frozenset({
    "FAST_PATH",
    "DETERMINISTIC_MACRO",
    "AGENT_PATH",
    "KNOWLEDGE_PATH",
    "TEXT_TO_SQL_PATH",
    "READ_ONLY_COMPOSITION",
    "WORKFLOW_COMPOSITION",
    "SCOPE_CONFLICT",
})

ALLOWED_INTERACTIONS = frozenset({
    "ANSWER",
    "ANALYZE",
    "CLARIFY",
    "PLANT_SELECT",
    "BLOCK",
})

ALLOWED_ACTIONS = frozenset({
    "REPLACE",
    "ADD",
    "DELETE",
    "QUANTITY_CHANGE",
})

ALLOWED_STATUS_POLICIES = frozenset({
    "PASS_RANK_ONLY",
    "NO_RANKING",
})

ALLOWED_SAFETY_ASSERTIONS = frozenset({
    "READ_ONLY",
    "NO_REQUEST_CREATE_DURING_ANALYSIS",
    "NO_PRODUCTION_WRITE_DURING_ANALYSIS",
    "NO_PLANT_GUESS",
    "NO_TARGET_GUESS",
    "FAIL_CANNOT_APPLY",
    "FINAL_APPROVAL_REQUIRED",
    "CONDITIONAL_NO_SCORE",
    "NO_HALLUCINATED_ENTITY",
    "CONTEXT_MUST_NOT_MUTATE_WORKFLOW",
})

_FIXTURE_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


@dataclass(frozen=True)
class EvalExpectation:
    intent: str
    execution_path: str
    interaction: str
    action: str | None = None
    primary_tool: str | None = None
    requires_plant: bool = False
    requires_context: bool = False
    status_policy: str | None = None
    required_entities: tuple[str, ...] = ()
    safety_assertions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvalExpectation":
        expectation = cls(
            intent=str(raw.get("intent") or "").strip().upper(),
            execution_path=str(raw.get("execution_path") or "").strip().upper(),
            interaction=str(raw.get("interaction") or "").strip().upper(),
            action=(str(raw["action"]).strip().upper() if raw.get("action") else None),
            primary_tool=(str(raw["primary_tool"]).strip() if raw.get("primary_tool") else None),
            requires_plant=bool(raw.get("requires_plant", False)),
            requires_context=bool(raw.get("requires_context", False)),
            status_policy=(
                str(raw["status_policy"]).strip().upper()
                if raw.get("status_policy")
                else None
            ),
            required_entities=tuple(str(v).strip() for v in raw.get("required_entities", [])),
            safety_assertions=tuple(
                str(v).strip().upper() for v in raw.get("safety_assertions", [])
            ),
        )
        expectation.validate()
        return expectation

    def validate(self) -> None:
        if self.intent not in ALLOWED_INTENTS:
            raise ValueError(f"Unsupported intent: {self.intent}")
        if self.execution_path not in ALLOWED_EXECUTION_PATHS:
            raise ValueError(f"Unsupported execution_path: {self.execution_path}")
        if self.interaction not in ALLOWED_INTERACTIONS:
            raise ValueError(f"Unsupported interaction: {self.interaction}")
        if self.action is not None and self.action not in ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action: {self.action}")
        if self.status_policy is not None and self.status_policy not in ALLOWED_STATUS_POLICIES:
            raise ValueError(f"Unsupported status_policy: {self.status_policy}")
        unknown_safety = set(self.safety_assertions) - ALLOWED_SAFETY_ASSERTIONS
        if unknown_safety:
            raise ValueError(f"Unsupported safety_assertions: {sorted(unknown_safety)}")
        if self.interaction == "ANALYZE" and self.action is None:
            raise ValueError("ANALYZE expectation requires action")
        if self.interaction in {"CLARIFY", "PLANT_SELECT", "BLOCK"} and self.primary_tool:
            raise ValueError(
                f"{self.interaction} must not declare a primary_tool before resolution"
            )


@dataclass(frozen=True)
class EvalTurn:
    user_template: str
    expected: EvalExpectation

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvalTurn":
        user_template = str(raw.get("user_template") or "").strip()
        if not user_template:
            raise ValueError("user_template is required")
        return cls(
            user_template=user_template,
            expected=EvalExpectation.from_dict(dict(raw.get("expected") or {})),
        )

    @property
    def fixture_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(_FIXTURE_PATTERN.findall(self.user_template)))


@dataclass(frozen=True)
class EvalCase:
    schema_version: str
    case_id: str
    category: str
    description: str
    fixture_requirements: tuple[str, ...]
    turns: tuple[EvalTurn, ...]
    tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EvalCase":
        case = cls(
            schema_version=str(raw.get("schema_version") or "").strip(),
            case_id=str(raw.get("case_id") or "").strip().upper(),
            category=str(raw.get("category") or "").strip().upper(),
            description=str(raw.get("description") or "").strip(),
            fixture_requirements=tuple(
                str(v).strip().upper() for v in raw.get("fixture_requirements", [])
            ),
            turns=tuple(EvalTurn.from_dict(v) for v in raw.get("turns", [])),
            tags=tuple(str(v).strip().lower() for v in raw.get("tags", [])),
        )
        case.validate()
        return case

    @property
    def fixture_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for turn in self.turns:
            names.extend(turn.fixture_names)
        return tuple(dict.fromkeys(names))

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"{self.case_id or '<unknown>'}: schema_version must be {SCHEMA_VERSION}"
            )
        if not re.fullmatch(r"[A-Z][A-Z0-9_]+-\d{3}", self.case_id):
            raise ValueError(f"Invalid case_id: {self.case_id}")
        if self.category not in ALLOWED_CATEGORIES:
            raise ValueError(f"{self.case_id}: unsupported category {self.category}")
        if not self.description:
            raise ValueError(f"{self.case_id}: description is required")
        if not self.turns:
            raise ValueError(f"{self.case_id}: at least one turn is required")

        declared = set(self.fixture_requirements)
        referenced = set(self.fixture_names)
        missing = referenced - declared
        unused = declared - referenced
        if missing:
            raise ValueError(
                f"{self.case_id}: fixtures referenced but not declared: {sorted(missing)}"
            )
        if unused:
            raise ValueError(
                f"{self.case_id}: fixtures declared but not used: {sorted(unused)}"
            )


def fixture_names(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_FIXTURE_PATTERN.findall(str(text or ""))))
