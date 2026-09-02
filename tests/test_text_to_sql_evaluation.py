from text_to_sql.evaluation import (
    TextToSqlGenerationEvaluator,
    results_semantically_equal,
)
from text_to_sql.evaluation_cases import TextToSqlEvaluationCase
from text_to_sql.read_only_executor import SqlExecutionResult
from text_to_sql.sql_generation import SqlGenerationResult


def _result(columns, rows):
    return SqlExecutionResult(
        columns=tuple(columns),
        rows=tuple(rows),
        row_count=len(rows),
        truncated=False,
        elapsed_ms=0.0,
    )


def test_semantic_comparison_ignores_alias_column_order_and_extra_description():
    reference = _result(
        ("material_group", "count"),
        ({"material_group": "OLB", "count": 3},),
    )
    generated = _result(
        ("cnt", "description", "grp"),
        ({"cnt": 3, "description": "OLB materials", "grp": "OLB"},),
    )
    assert results_semantically_equal(
        reference,
        generated,
        ordered=False,
    )


def test_semantic_comparison_allows_different_tie_break_inside_primary_order():
    reference = _result(
        ("group", "count"),
        (
            {"group": "OLB", "count": 3},
            {"group": "BIN", "count": 2},
            {"group": "LC", "count": 2},
        ),
    )
    generated = _result(
        ("cnt", "grp"),
        (
            {"cnt": 3, "grp": "OLB"},
            {"cnt": 2, "grp": "LC"},
            {"cnt": 2, "grp": "BIN"},
        ),
    )
    assert results_semantically_equal(
        reference,
        generated,
        ordered=True,
        order_key="count",
    )


def test_semantic_comparison_rejects_wrong_primary_order():
    reference = _result(
        ("group", "count"),
        (
            {"group": "OLB", "count": 3},
            {"group": "LC", "count": 2},
        ),
    )
    generated = _result(
        ("cnt", "grp"),
        (
            {"cnt": 2, "grp": "LC"},
            {"cnt": 3, "grp": "OLB"},
        ),
    )
    assert not results_semantically_equal(
        reference,
        generated,
        ordered=True,
        order_key="count",
    )


class FakeGenerator:
    def __init__(self, mapping):
        self.mapping = mapping

    def generate(self, question):
        value = self.mapping[question]
        if isinstance(value, Exception):
            raise value
        return value


class FakeExecutor:
    def __init__(self, mapping):
        self.mapping = mapping

    def execute(self, sql):
        value = self.mapping[sql]
        if isinstance(value, Exception):
            raise value
        return value


def test_evaluator_counts_sql_semantic_and_unsupported_success():
    sql_case = TextToSqlEvaluationCase(
        case_id="SQL-1",
        category="MATERIAL",
        question="활성 자재 수",
        expected_status="SQL",
        reference_sql="SELECT 2",
    )
    unsupported_case = TextToSqlEvaluationCase(
        case_id="UNS-1",
        category="WRITE",
        question="삭제해줘",
        expected_status="UNSUPPORTED",
    )

    generator = FakeGenerator({
        "활성 자재 수": SqlGenerationResult(
            "SQL",
            "SELECT COUNT(*)",
            "",
            "",
        ),
        "삭제해줘": SqlGenerationResult(
            "UNSUPPORTED",
            None,
            "read only",
            "",
        ),
    })
    executor = FakeExecutor({
        "SELECT 2": _result(("count",), ({"count": 2},)),
        "SELECT COUNT(*)": _result(("cnt",), ({"cnt": 2},)),
    })

    summary = TextToSqlGenerationEvaluator(
        generator=generator,
        executor=executor,
    ).evaluate((sql_case, unsupported_case))

    assert summary.sql_case_count == 1
    assert summary.unsupported_case_count == 1
    assert summary.passed_count == 2
    assert summary.semantic_match_rate == 1.0
    assert summary.unsupported_accuracy == 1.0
    assert summary.model_failure_count == 0


def test_evaluator_classifies_extra_column_as_evaluator_tolerance():
    case = TextToSqlEvaluationCase(
        case_id="SQL-1",
        category="MATERIAL",
        question="count",
        expected_status="SQL",
        reference_sql="REFERENCE",
    )
    generator = FakeGenerator({
        "count": SqlGenerationResult(
            "SQL",
            "GENERATED",
            "",
            "",
        )
    })
    executor = FakeExecutor({
        "REFERENCE": _result(
            ("group", "count"),
            ({"group": "OLB", "count": 3},),
        ),
        "GENERATED": _result(
            ("group", "count", "description"),
            ({"group": "OLB", "count": 3, "description": "extra"},),
        ),
    })

    summary = TextToSqlGenerationEvaluator(
        generator=generator,
        executor=executor,
    ).evaluate((case,))

    assert summary.passed_count == 1
    assert summary.evaluator_tolerance_count == 1
    assert summary.model_failure_count == 0
    assert summary.cases[0].classification == "EVALUATOR_TOLERANCE"
    assert summary.cases[0].semantic_match is True
    assert summary.cases[0].strict_semantic_match is False


def test_evaluator_does_not_double_count_sql_case_on_execution_error():
    case = TextToSqlEvaluationCase(
        case_id="SQL-1",
        category="SUPPLIER_ITEM",
        question="query",
        expected_status="SQL",
        reference_sql="REFERENCE",
    )
    generator = FakeGenerator({
        "query": SqlGenerationResult(
            "SQL",
            "BROKEN",
            "",
            "",
        )
    })
    executor = FakeExecutor({
        "REFERENCE": _result(
            ("supplier_code",),
            ({"supplier_code": "SUP-1"},),
        ),
        "BROKEN": RuntimeError("ambiguous column"),
    })

    summary = TextToSqlGenerationEvaluator(
        generator=generator,
        executor=executor,
    ).evaluate((case,))

    assert summary.case_count == 1
    assert summary.sql_case_count == 1
    assert summary.unsupported_case_count == 0
    assert summary.sql_execution_success_rate == 0.0
    assert summary.model_failure_count == 1
    assert summary.cases[0].classification == "MODEL_EXECUTION"


def test_evaluator_marks_wrong_result_as_model_semantic_failure():
    case = TextToSqlEvaluationCase(
        case_id="SQL-1",
        category="MATERIAL",
        question="count",
        expected_status="SQL",
        reference_sql="SELECT 2",
    )
    generator = FakeGenerator({
        "count": SqlGenerationResult(
            "SQL",
            "SELECT 3",
            "",
            "",
        )
    })
    executor = FakeExecutor({
        "SELECT 2": _result(("count",), ({"count": 2},)),
        "SELECT 3": _result(("count",), ({"count": 3},)),
    })

    summary = TextToSqlGenerationEvaluator(
        generator=generator,
        executor=executor,
    ).evaluate((case,))

    assert summary.passed_count == 0
    assert summary.semantic_match_rate == 0.0
    assert summary.model_failure_count == 1
    assert summary.cases[0].classification == "MODEL_SEMANTIC"
