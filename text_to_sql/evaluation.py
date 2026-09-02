from __future__ import annotations

import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from text_to_sql.evaluation_cases import TextToSqlEvaluationCase


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return round(value, 8)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _canonical_row(row: dict[str, Any]) -> tuple[Any, ...]:
    values = [_normalize_scalar(value) for value in row.values()]
    return tuple(
        sorted(
            values,
            key=lambda value: (
                type(value).__name__,
                repr(value),
            ),
        )
    )


def _strict_results_equal(reference, generated, *, ordered: bool) -> bool:
    """Legacy 02B comparison, retained only for evaluator diagnostics."""
    if reference.row_count != generated.row_count:
        return False
    if len(reference.columns) != len(generated.columns):
        return False

    reference_rows = [_canonical_row(row) for row in reference.rows]
    generated_rows = [_canonical_row(row) for row in generated.rows]
    if ordered:
        return reference_rows == generated_rows
    return Counter(reference_rows) == Counter(generated_rows)


def _value_counter(row: dict[str, Any]) -> Counter:
    return Counter(_normalize_scalar(value) for value in row.values())


def _contains_required_values(
    generated_row: dict[str, Any],
    reference_row: dict[str, Any],
) -> bool:
    generated_values = _value_counter(generated_row)
    required_values = _value_counter(reference_row)
    return all(
        generated_values[value] >= count
        for value, count in required_values.items()
    )


def _match_generated_rows_to_reference(
    reference_rows: list[dict[str, Any]],
    generated_rows: list[dict[str, Any]],
) -> list[int] | None:
    if len(reference_rows) != len(generated_rows):
        return None

    unmatched = list(range(len(reference_rows)))
    mapped: list[int] = []
    for generated_row in generated_rows:
        candidates = [
            index
            for index in unmatched
            if _contains_required_values(
                generated_row,
                reference_rows[index],
            )
        ]
        if not candidates:
            return None

        candidates.sort(
            key=lambda index: (
                -len(reference_rows[index]),
                index,
            )
        )
        selected = candidates[0]
        unmatched.remove(selected)
        mapped.append(selected)
    return mapped


def results_semantically_equal(
    reference,
    generated,
    *,
    ordered: bool,
    order_key: str | None = None,
) -> bool:
    """Compare actual DB results while tolerating evaluator-only differences.

    Aliases/column order are ignored. Generated rows may contain extra
    descriptive columns, but all reference rows/values remain required.
    With order_key, permutations inside equal-key tie groups are accepted while
    the requested primary ordering is still enforced.
    """
    reference_rows = [dict(row) for row in reference.rows]
    generated_rows = [dict(row) for row in generated.rows]
    mapped = _match_generated_rows_to_reference(
        reference_rows,
        generated_rows,
    )
    if mapped is None:
        return False

    if not ordered:
        return True

    if not order_key:
        return mapped == list(range(len(reference_rows)))

    if any(order_key not in row for row in reference_rows):
        raise ValueError(
            f"Reference result does not contain order_key={order_key!r}"
        )

    groups: list[set[int]] = []
    start = 0
    while start < len(reference_rows):
        key_value = _normalize_scalar(
            reference_rows[start][order_key]
        )
        end = start + 1
        while (
            end < len(reference_rows)
            and _normalize_scalar(reference_rows[end][order_key])
            == key_value
        ):
            end += 1
        groups.append(set(range(start, end)))
        start = end

    offset = 0
    for group in groups:
        width = len(group)
        if set(mapped[offset : offset + width]) != group:
            return False
        offset += width
    return True


@dataclass(frozen=True)
class TextToSqlCaseResult:
    case_id: str
    category: str
    question: str
    expected_status: str
    actual_status: str
    passed: bool
    generation_ms: float
    execution_ms: float
    semantic_match: bool | None
    strict_semantic_match: bool | None
    classification: str
    generated_sql: str | None
    reference_sql: str | None
    error: str | None


@dataclass(frozen=True)
class TextToSqlEvaluationSummary:
    case_count: int
    sql_case_count: int
    unsupported_case_count: int
    passed_count: int
    overall_accuracy: float
    status_accuracy: float
    sql_execution_success_rate: float
    semantic_match_rate: float
    unsupported_accuracy: float
    model_failure_count: int
    evaluator_tolerance_count: int
    evaluator_error_count: int
    generation_latency_p50_ms: float
    generation_latency_p95_ms: float
    gate_pass: bool
    category_metrics: dict[str, dict[str, float | int]]
    cases: tuple[TextToSqlCaseResult, ...]

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["cases"] = [
            asdict(case)
            for case in self.cases
        ]
        return payload


class TextToSqlGenerationEvaluator:
    """Evaluate LLM SQL by actual DB result semantics, not SQL string equality."""

    def __init__(self, *, generator, executor) -> None:
        self.generator = generator
        self.executor = executor

    def evaluate(
        self,
        cases: Iterable[TextToSqlEvaluationCase],
    ) -> TextToSqlEvaluationSummary:
        case_list = tuple(cases)
        results: list[TextToSqlCaseResult] = []
        generation_latencies: list[float] = []

        sql_case_count = sum(
            case.expected_status == "SQL"
            for case in case_list
        )
        unsupported_case_count = sum(
            case.expected_status == "UNSUPPORTED"
            for case in case_list
        )

        sql_execution_successes = 0
        sql_semantic_matches = 0
        unsupported_passes = 0
        status_passes = 0

        for case in case_list:
            started = time.perf_counter()
            try:
                generated = self.generator.generate(case.question)
            except Exception as exc:
                generation_ms = (
                    time.perf_counter() - started
                ) * 1000.0
                generation_latencies.append(generation_ms)
                results.append(
                    TextToSqlCaseResult(
                        case.case_id,
                        case.category,
                        case.question,
                        case.expected_status,
                        "ERROR",
                        False,
                        generation_ms,
                        0.0,
                        False if case.expected_status == "SQL" else None,
                        None,
                        "MODEL_GENERATION",
                        None,
                        case.reference_sql,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            generation_ms = (
                time.perf_counter() - started
            ) * 1000.0
            generation_latencies.append(generation_ms)

            actual_status = generated.status
            status_ok = actual_status == case.expected_status
            if status_ok:
                status_passes += 1

            if case.expected_status == "UNSUPPORTED":
                passed = status_ok and generated.sql is None
                if passed:
                    unsupported_passes += 1
                results.append(
                    TextToSqlCaseResult(
                        case.case_id,
                        case.category,
                        case.question,
                        case.expected_status,
                        actual_status,
                        passed,
                        generation_ms,
                        0.0,
                        None,
                        None,
                        "PASS" if passed else "MODEL_STATUS",
                        generated.sql,
                        None,
                        None,
                    )
                )
                continue

            if not status_ok or not generated.sql:
                results.append(
                    TextToSqlCaseResult(
                        case.case_id,
                        case.category,
                        case.question,
                        case.expected_status,
                        actual_status,
                        False,
                        generation_ms,
                        0.0,
                        False,
                        None,
                        "MODEL_STATUS",
                        generated.sql,
                        case.reference_sql,
                        None,
                    )
                )
                continue

            execution_started = time.perf_counter()
            try:
                reference = self.executor.execute(
                    case.reference_sql or ""
                )
            except Exception as exc:
                execution_ms = (
                    time.perf_counter() - execution_started
                ) * 1000.0
                results.append(
                    TextToSqlCaseResult(
                        case.case_id,
                        case.category,
                        case.question,
                        case.expected_status,
                        actual_status,
                        False,
                        generation_ms,
                        execution_ms,
                        False,
                        None,
                        "EVALUATOR_REFERENCE_ERROR",
                        generated.sql,
                        case.reference_sql,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            try:
                generated_result = self.executor.execute(
                    generated.sql
                )
            except Exception as exc:
                execution_ms = (
                    time.perf_counter() - execution_started
                ) * 1000.0
                results.append(
                    TextToSqlCaseResult(
                        case.case_id,
                        case.category,
                        case.question,
                        case.expected_status,
                        actual_status,
                        False,
                        generation_ms,
                        execution_ms,
                        False,
                        None,
                        "MODEL_EXECUTION",
                        generated.sql,
                        case.reference_sql,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue

            execution_ms = (
                time.perf_counter() - execution_started
            ) * 1000.0
            sql_execution_successes += 1

            semantic_match = results_semantically_equal(
                reference,
                generated_result,
                ordered=case.ordered,
                order_key=case.order_key,
            )
            strict_match = _strict_results_equal(
                reference,
                generated_result,
                ordered=case.ordered,
            )

            if semantic_match:
                sql_semantic_matches += 1
                classification = (
                    "PASS"
                    if strict_match
                    else "EVALUATOR_TOLERANCE"
                )
            else:
                classification = "MODEL_SEMANTIC"

            results.append(
                TextToSqlCaseResult(
                    case.case_id,
                    case.category,
                    case.question,
                    case.expected_status,
                    actual_status,
                    semantic_match,
                    generation_ms,
                    execution_ms,
                    semantic_match,
                    strict_match,
                    classification,
                    generated.sql,
                    case.reference_sql,
                    None,
                )
            )

        case_count = len(results)
        passed_count = sum(result.passed for result in results)

        overall_accuracy = (
            passed_count / case_count
            if case_count else 0.0
        )
        status_accuracy = (
            status_passes / case_count
            if case_count else 0.0
        )
        execution_rate = (
            sql_execution_successes / sql_case_count
            if sql_case_count else 0.0
        )
        semantic_rate = (
            sql_semantic_matches / sql_case_count
            if sql_case_count else 0.0
        )
        unsupported_accuracy = (
            unsupported_passes / unsupported_case_count
            if unsupported_case_count else 0.0
        )

        model_failure_count = sum(
            result.classification.startswith("MODEL_")
            for result in results
        )
        evaluator_tolerance_count = sum(
            result.classification == "EVALUATOR_TOLERANCE"
            for result in results
        )
        evaluator_error_count = sum(
            result.classification.startswith("EVALUATOR_")
            and result.classification != "EVALUATOR_TOLERANCE"
            for result in results
        )

        buckets: dict[str, list[TextToSqlCaseResult]] = defaultdict(list)
        for result in results:
            buckets[result.category].append(result)

        category_metrics = {
            category: {
                "case_count": len(values),
                "passed_count": sum(value.passed for value in values),
                "accuracy": (
                    sum(value.passed for value in values)
                    / len(values)
                ),
            }
            for category, values in sorted(buckets.items())
        }

        p50 = (
            statistics.median(generation_latencies)
            if generation_latencies else 0.0
        )
        if generation_latencies:
            ordered_latencies = sorted(generation_latencies)
            index = min(
                len(ordered_latencies) - 1,
                max(
                    0,
                    math.ceil(
                        0.95 * len(ordered_latencies)
                    ) - 1,
                ),
            )
            p95 = ordered_latencies[index]
        else:
            p95 = 0.0

        gate_pass = (
            case_count >= 20
            and sql_case_count >= 12
            and unsupported_case_count >= 6
            and unsupported_accuracy == 1.0
            and status_accuracy >= 0.95
            and execution_rate >= 0.90
            and semantic_rate >= 0.85
            and overall_accuracy >= 0.90
            and evaluator_error_count == 0
        )

        return TextToSqlEvaluationSummary(
            case_count=case_count,
            sql_case_count=sql_case_count,
            unsupported_case_count=unsupported_case_count,
            passed_count=passed_count,
            overall_accuracy=overall_accuracy,
            status_accuracy=status_accuracy,
            sql_execution_success_rate=execution_rate,
            semantic_match_rate=semantic_rate,
            unsupported_accuracy=unsupported_accuracy,
            model_failure_count=model_failure_count,
            evaluator_tolerance_count=evaluator_tolerance_count,
            evaluator_error_count=evaluator_error_count,
            generation_latency_p50_ms=p50,
            generation_latency_p95_ms=p95,
            gate_pass=gate_pass,
            category_metrics=category_metrics,
            cases=tuple(results),
        )


__all__ = [
    "TextToSqlCaseResult",
    "TextToSqlEvaluationSummary",
    "TextToSqlGenerationEvaluator",
    "results_semantically_equal",
]
