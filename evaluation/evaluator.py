from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from pathlib import Path
from typing import Any, Iterable

from evaluation.schema import EvalCase, EvalTurn, fixture_names


EVALUATION_REPORT_SCHEMA_VERSION = "1.0"

# Read-only helper Tools are legitimate before a CLARIFY / PLANT_SELECT
# interaction.  The accuracy evaluator originally treated *any* Tool as a mismatch when the
# Ground Truth had no primary business Tool, which undercounted correct
# resolution behavior such as querying valid PLANTs before showing buttons.
RESOLUTION_TOOL_ALLOWLIST = frozenset({
    "list_plants",
    "search_material",
    "search_product",
    "get_bom",
})


@dataclass(frozen=True)
class MetricCheck:
    eligible: bool
    passed: bool | None
    expected: Any = None
    actual: Any = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnAccuracyResult:
    case_id: str
    turn_index: int
    user_input: str
    checks: dict[str, MetricCheck] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    argument_requirements: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            check.passed is not False
            for check in self.checks.values()
            if check.eligible
        ) and not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "turn_index": self.turn_index,
            "user_input": self.user_input,
            "passed": self.passed,
            "failures": list(self.failures),
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
            "argument_requirements": list(self.argument_requirements),
        }


@dataclass
class AccuracyEvaluationReport:
    run_id: str | None
    expected_case_count: int
    expected_turn_count: int
    observed_turn_count: int
    evaluated_turn_count: int
    missing_observations: list[str]
    duplicate_observations: list[str]
    metrics: dict[str, dict[str, Any]]
    failure_counts: dict[str, int]
    turn_results: list[TurnAccuracyResult]
    schema_version: str = EVALUATION_REPORT_SCHEMA_VERSION

    @property
    def complete(self) -> bool:
        return not self.missing_observations and not self.duplicate_observations

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "complete": self.complete,
            "expected_case_count": self.expected_case_count,
            "expected_turn_count": self.expected_turn_count,
            "observed_turn_count": self.observed_turn_count,
            "evaluated_turn_count": self.evaluated_turn_count,
            "missing_observations": list(self.missing_observations),
            "duplicate_observations": list(self.duplicate_observations),
            "metrics": self.metrics,
            "failure_counts": dict(self.failure_counts),
            "turn_results": [result.to_dict() for result in self.turn_results],
        }


@dataclass(frozen=True)
class _ArgumentRequirement:
    label: str
    accepted_values: tuple[Any, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "accepted_values": list(self.accepted_values)}


class AgentAccuracyEvaluator:
    """Compare Ground Truth with runtime observations.

    The accuracy evaluator intentionally evaluates observable contracts only.  It does not judge
    answer wording or hidden reasoning.  Tool argument checks are tool-aware and
    validate business entities/action/quantity against dynamic fixtures.
    """

    def __init__(self, cases: Iterable[EvalCase], fixtures: dict[str, Any]) -> None:
        self.cases = list(cases)
        self.fixtures = {str(k).upper(): v for k, v in dict(fixtures).items()}

    def evaluate(self, observations: Iterable[dict[str, Any]]) -> AccuracyEvaluationReport:
        rows = [dict(row) for row in observations]
        by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for row in rows:
            key = (str(row.get("case_id") or "").upper(), int(row.get("turn_index") or 0))
            by_key.setdefault(key, []).append(row)

        expected_keys: list[tuple[str, int]] = []
        duplicate_observations = [
            f"{case_id}#{turn_index}"
            for (case_id, turn_index), values in sorted(by_key.items())
            if len(values) > 1
        ]
        missing_observations: list[str] = []
        results: list[TurnAccuracyResult] = []

        for case in self.cases:
            context = _CaseContext()
            for turn_index, turn in enumerate(case.turns, start=1):
                key = (case.case_id, turn_index)
                expected_keys.append(key)
                rows_for_turn = by_key.get(key, [])
                rendered_user = self._render(turn.user_template)
                if not rows_for_turn:
                    missing_observations.append(f"{case.case_id}#{turn_index}")
                    self._update_context(context, turn)
                    continue
                observation = rows_for_turn[0]
                result = self._evaluate_turn(
                    case=case,
                    turn=turn,
                    turn_index=turn_index,
                    observation=observation,
                    context=context,
                    rendered_user=rendered_user,
                )
                results.append(result)
                self._update_context(context, turn)

        metrics = self._aggregate_metrics(results)
        failure_counts: dict[str, int] = {}
        for result in results:
            for failure in result.failures:
                failure_counts[failure] = failure_counts.get(failure, 0) + 1
        for _ in missing_observations:
            failure_counts["MISSING_OBSERVATION"] = failure_counts.get("MISSING_OBSERVATION", 0) + 1
        for _ in duplicate_observations:
            failure_counts["DUPLICATE_OBSERVATION"] = failure_counts.get("DUPLICATE_OBSERVATION", 0) + 1

        run_ids = {str(row.get("run_id") or "").strip() for row in rows if row.get("run_id")}
        return AccuracyEvaluationReport(
            run_id=next(iter(run_ids)) if len(run_ids) == 1 else None,
            expected_case_count=len(self.cases),
            expected_turn_count=len(expected_keys),
            observed_turn_count=len(rows),
            evaluated_turn_count=len(results),
            missing_observations=missing_observations,
            duplicate_observations=duplicate_observations,
            metrics=metrics,
            failure_counts=dict(sorted(failure_counts.items())),
            turn_results=results,
        )

    def _evaluate_turn(
        self,
        *,
        case: EvalCase,
        turn: EvalTurn,
        turn_index: int,
        observation: dict[str, Any],
        context: "_CaseContext",
        rendered_user: str,
    ) -> TurnAccuracyResult:
        expected = turn.expected
        actual_intent = _upper_or_none(observation.get("actual_intent"))
        actual_path = _upper_or_none(observation.get("execution_path"))
        actual_tool = _none_if_blank(observation.get("primary_tool"))
        if actual_tool is None:
            calls = list(observation.get("tool_calls") or [])
            if calls:
                actual_tool = _none_if_blank(calls[0].get("name"))

        checks: dict[str, MetricCheck] = {}
        failures: list[str] = []

        intent_pass = actual_intent == expected.intent
        checks["intent"] = MetricCheck(True, intent_pass, expected.intent, actual_intent)
        if not intent_pass:
            failures.append("INTENT_MISMATCH")

        route_pass = actual_path == expected.execution_path
        checks["route"] = MetricCheck(True, route_pass, expected.execution_path, actual_path)
        if not route_pass:
            failures.append("ROUTE_MISMATCH")

        expected_tool = expected.primary_tool
        if expected_tool is None:
            calls = [
                str(call.get("name") or "").strip()
                for call in list(observation.get("tool_calls") or [])
                if isinstance(call, dict) and str(call.get("name") or "").strip()
            ]
            resolution_only = (
                expected.interaction in {"CLARIFY", "PLANT_SELECT"}
                and bool(calls)
                and all(name in RESOLUTION_TOOL_ALLOWLIST for name in calls)
            )
            tool_pass = actual_tool is None or resolution_only
            expected_tool_display: Any = (
                "no primary business tool; read-only resolution tools allowed"
                if expected.interaction in {"CLARIFY", "PLANT_SELECT"}
                else None
            )
        else:
            tool_pass = actual_tool == expected_tool
            expected_tool_display = expected_tool

        checks["tool_selection"] = MetricCheck(
            True, tool_pass, expected_tool_display, actual_tool
        )
        if not tool_pass:
            failures.append("TOOL_SELECTION_MISMATCH")

        argument_requirements: list[_ArgumentRequirement] = []
        if expected_tool is None:
            checks["tool_arguments"] = MetricCheck(
                False, None, None, None,
                "No primary business tool expected before resolution",
            )
        else:
            primary_call = self._primary_call(observation)
            if actual_tool != expected_tool or primary_call is None:
                checks["tool_arguments"] = MetricCheck(
                    True,
                    False,
                    "grounded business arguments",
                    primary_call.get("arguments") if primary_call else None,
                    "Expected primary tool was not observed",
                )
                failures.append("TOOL_ARGUMENT_MISMATCH")
            else:
                argument_requirements = self._argument_requirements(
                    case=case,
                    turn=turn,
                    context=context,
                    rendered_user=rendered_user,
                )
                arguments = dict(primary_call.get("arguments") or {})
                missing = [
                    requirement.label
                    for requirement in argument_requirements
                    if not _arguments_contain_any(arguments, requirement.accepted_values)
                ]
                args_pass = not missing
                checks["tool_arguments"] = MetricCheck(
                    True,
                    args_pass,
                    [req.to_dict() for req in argument_requirements],
                    arguments,
                    (f"Missing argument evidence: {', '.join(missing)}" if missing else None),
                )
                if not args_pass:
                    failures.append("TOOL_ARGUMENT_MISMATCH")

        return TurnAccuracyResult(
            case_id=case.case_id,
            turn_index=turn_index,
            user_input=str(observation.get("user_input") or rendered_user),
            checks=checks,
            failures=failures,
            argument_requirements=[req.to_dict() for req in argument_requirements],
        )

    def _argument_requirements(
        self,
        *,
        case: EvalCase,
        turn: EvalTurn,
        context: "_CaseContext",
        rendered_user: str,
    ) -> list[_ArgumentRequirement]:
        tool = turn.expected.primary_tool
        placeholders = fixture_names(turn.user_template)
        requirements: list[_ArgumentRequirement] = []

        if tool == "get_bom":
            if turn.expected.intent == "CURRENT_BOM_QUANTITY" and turn.expected.requires_context:
                if context.model:
                    requirements.append(_ArgumentRequirement("MODEL_CONTEXT", (context.model,)))
                if context.plant:
                    requirements.append(_ArgumentRequirement("PLANT_CONTEXT", (context.plant,)))
            else:
                requirements.extend(self._requirements_for_placeholders(placeholders, {"MODEL", "ASSY", "PLANT"}))

        elif tool == "get_bom_where_used":
            requirements.extend(self._requirements_for_placeholders(placeholders, {"MATERIAL", "ASSY", "PLANT"}))
            if turn.expected.requires_context:
                if context.plant:
                    requirements.append(_ArgumentRequirement("PLANT_CONTEXT", (context.plant,)))

        elif tool == "analyze_design_change_candidates":
            requirements.extend(
                self._requirements_for_placeholders(
                    placeholders,
                    {"MODEL", "PLANT", "MATERIAL", "MATERIAL_FAMILY", "ASSY"},
                )
            )
            if turn.expected.requires_context:
                if context.model and not any(req.label.startswith("MODEL") for req in requirements):
                    requirements.append(_ArgumentRequirement("MODEL_CONTEXT", (context.model,)))
                if context.plant and not any(req.label.startswith("PLANT") for req in requirements):
                    requirements.append(_ArgumentRequirement("PLANT_CONTEXT", (context.plant,)))
            if turn.expected.action:
                requirements.append(_ArgumentRequirement("ACTION", (turn.expected.action,)))
            if "QUANTITY" in turn.expected.required_entities:
                quantity = _extract_requested_quantity(rendered_user)
                if quantity is not None:
                    requirements.append(_ArgumentRequirement("QUANTITY", (quantity,)))

        return _deduplicate_requirements(requirements)

    def _requirements_for_placeholders(
        self,
        placeholders: Iterable[str],
        allowed_entity_types: set[str],
    ) -> list[_ArgumentRequirement]:
        requirements: list[_ArgumentRequirement] = []
        for placeholder in placeholders:
            entity_type = _fixture_entity_type(placeholder)
            if entity_type not in allowed_entity_types:
                continue
            accepted = self._accepted_fixture_values(placeholder)
            if accepted:
                requirements.append(_ArgumentRequirement(placeholder, accepted))
        return requirements

    def _accepted_fixture_values(self, placeholder: str) -> tuple[Any, ...]:
        name = str(placeholder).upper()
        value = self.fixtures.get(name)
        if value is None:
            return ()
        accepted: list[Any] = [value]

        # Name-based requests may be resolved to the concrete item code before
        # the MCP call.  Both are correct argument representations.
        match = re.fullmatch(r"MATERIAL_NAME_([A-Z0-9]+)", name)
        if match:
            code = self.fixtures.get(f"MATERIAL_{match.group(1)}")
            if code is not None:
                accepted.append(code)
        match = re.fullmatch(r"ASSY_NAME_([A-Z0-9]+)", name)
        if match:
            code = self.fixtures.get(f"ASSY_{match.group(1)}")
            if code is not None:
                accepted.append(code)
        return tuple(dict.fromkeys(accepted))

    def _render(self, template: str) -> str:
        rendered = str(template)
        for name in fixture_names(template):
            if name in self.fixtures:
                rendered = rendered.replace(f"{{{{{name}}}}}", str(self.fixtures[name]))
        return rendered

    def _update_context(self, context: "_CaseContext", turn: EvalTurn) -> None:
        for placeholder in fixture_names(turn.user_template):
            value = self.fixtures.get(placeholder)
            if value is None:
                continue
            if placeholder.startswith("MODEL_"):
                context.model = str(value)
            elif placeholder.startswith("PLANT_"):
                context.plant = str(value)

    @staticmethod
    def _primary_call(observation: dict[str, Any]) -> dict[str, Any] | None:
        calls = list(observation.get("tool_calls") or [])
        return dict(calls[0]) if calls and isinstance(calls[0], dict) else None

    @staticmethod
    def _aggregate_metrics(results: list[TurnAccuracyResult]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for metric in ("intent", "route", "tool_selection", "tool_arguments"):
            checks = [result.checks[metric] for result in results if result.checks[metric].eligible]
            passed = sum(1 for check in checks if check.passed is True)
            eligible = len(checks)
            output[metric] = {
                "passed": passed,
                "eligible": eligible,
                "failed": eligible - passed,
                "accuracy": round((passed / eligible) * 100.0, 2) if eligible else None,
            }
        return output


@dataclass
class _CaseContext:
    model: str | None = None
    plant: str | None = None


def load_observations_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Observation file not found: {target}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{target}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"{target}:{line_no}: observation must be a JSON object")
        rows.append(raw)
    return rows


def load_fixture_manifest(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Evaluation manifest not found: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    fixtures = raw.get("fixtures") if isinstance(raw, dict) else None
    if not isinstance(fixtures, dict):
        raise ValueError(f"Evaluation manifest has no fixtures mapping: {target}")
    return dict(fixtures)


def write_accuracy_report(report: AccuracyEvaluationReport, path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return target


def _fixture_entity_type(name: str) -> str | None:
    upper = str(name).upper()
    if upper.startswith("MODEL_") or upper == "INVALID_MODEL":
        return "MODEL"
    if upper.startswith("PLANT_"):
        return "PLANT"
    if upper.startswith("MATERIAL_FAMILY_"):
        return "MATERIAL_FAMILY"
    if upper.startswith("MATERIAL_NAME_") or upper.startswith("MATERIAL_") or upper == "INVALID_ITEM":
        return "MATERIAL"
    if upper.startswith("ASSY_NAME_") or upper.startswith("ASSY_"):
        return "ASSY"
    return None


def _extract_requested_quantity(text: str) -> int | float | None:
    matches = re.findall(r"수량(?:을|은|이|를)?\s*(?:약\s*)?([0-9]+(?:\.[0-9]+)?)", str(text))
    if not matches:
        # Handles forms such as "수량을 2로 바꿔줘" after particle spacing.
        matches = re.findall(r"수량[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)", str(text))
    if not matches:
        return None
    value = float(matches[-1])
    return int(value) if value.is_integer() else value


def _arguments_contain_any(arguments: dict[str, Any], accepted_values: Iterable[Any]) -> bool:
    flattened = {_canonical_scalar(value) for value in _flatten_scalars(arguments)}
    return any(_canonical_scalar(value) in flattened for value in accepted_values)


def _flatten_scalars(value: Any) -> list[Any]:
    if isinstance(value, dict):
        output: list[Any] = []
        for nested in value.values():
            output.extend(_flatten_scalars(nested))
        return output
    if isinstance(value, (list, tuple, set)):
        output = []
        for nested in value:
            output.extend(_flatten_scalars(nested))
        return output
    if value is None:
        return []
    return [value]


def _canonical_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    text = str(value).strip().upper()
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else str(number)


def _upper_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text.upper() if text else None


def _none_if_blank(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _deduplicate_requirements(requirements: list[_ArgumentRequirement]) -> list[_ArgumentRequirement]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    output: list[_ArgumentRequirement] = []
    for requirement in requirements:
        key = (
            requirement.label,
            tuple(_canonical_scalar(v) for v in requirement.accepted_values),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(requirement)
    return output
