import sqlite3

from text_to_sql.evaluation_cases import TextToSqlEvaluationCaseBuilder
from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY
from text_to_sql.schema_catalog import SqlSchemaCatalog


def _database(tmp_path):
    path = tmp_path / "evaluation_cases.db"
    connection = sqlite3.connect(path)
    schemas = {
        "item_master": (
            "item_code TEXT PRIMARY KEY, item_type TEXT, item_name TEXT, "
            "active_yn TEXT"
        ),
        "version_master": (
            "version_code TEXT PRIMARY KEY, product_name TEXT, product_type TEXT, "
            "screen_size_inch REAL, resolution TEXT, refresh_hz REAL, market TEXT"
        ),
        "material_master": (
            "material_code TEXT PRIMARY KEY, material_name TEXT, "
            "material_group TEXT, unit TEXT, specification TEXT"
        ),
        "assembly_master": (
            "assembly_code TEXT PRIMARY KEY, process_name TEXT, usage_type TEXT"
        ),
        "supplier_master": (
            "supplier_code TEXT PRIMARY KEY, grade TEXT, quality_score REAL"
        ),
        "supplier_items": (
            "supplier_item_id INTEGER PRIMARY KEY, item_code TEXT, "
            "supplier_code TEXT, unit_price REAL, lead_time_days REAL, "
            "primary_yn TEXT, supply_status TEXT"
        ),
        "production_plans": (
            "plan_id TEXT PRIMARY KEY, plant_code TEXT, version_code TEXT, "
            "planned_quantity REAL"
        ),
        "bom_master": (
            "bom_id INTEGER PRIMARY KEY, plant_code TEXT, quantity REAL"
        ),
    }
    try:
        for table in DEFAULT_TEXT_TO_SQL_POLICY.allowed_tables:
            columns = schemas.get(table, "id TEXT PRIMARY KEY")
            connection.execute(
                f'CREATE TABLE "{table}" ({columns})'
            )
        connection.commit()
    finally:
        connection.close()
    return path


def test_builder_creates_fixed_r1_sql_and_safety_cases(tmp_path):
    cases = TextToSqlEvaluationCaseBuilder(
        SqlSchemaCatalog(_database(tmp_path))
    ).build()

    sql_cases = [
        case for case in cases
        if case.expected_status == "SQL"
    ]
    unsupported = [
        case for case in cases
        if case.expected_status == "UNSUPPORTED"
    ]

    assert len(cases) == 23
    assert len(sql_cases) == 15
    assert len(unsupported) == 8
    assert {
        "MATERIAL",
        "ASSEMBLY",
        "SUPPLIER",
        "SUPPLIER_ITEM",
        "PRODUCTION_PLAN",
        "BOM",
    } == {case.category for case in sql_cases}
    assert sum(
        case.category == "DEDICATED_WORKFLOW_QUERY"
        for case in unsupported
    ) == 4
    assert not any(
        case.category == "HIDDEN_WORKFLOW"
        for case in cases
    )

    si003 = next(case for case in cases if case.case_id == "SQL-SI-003")
    assert "공급사-자재 관계 등록 건수" in si003.question
    assert "COUNT(*)" in (si003.reference_sql or "")


def test_v9_material_references_use_item_master_lifecycle(tmp_path):
    cases = {
        case.case_id: case
        for case in TextToSqlEvaluationCaseBuilder(
            SqlSchemaCatalog(_database(tmp_path))
        ).build()
    }

    active_sql = cases["SQL-MAT-001"].reference_sql or ""
    count_sql = cases["SQL-MAT-002"].reference_sql or ""
    registered_sql = cases["SQL-MAT-003"].reference_sql or ""

    assert "JOIN item_master" in active_sql
    assert "i.active_yn='Y'" in active_sql
    assert "JOIN item_master" in count_sql
    assert "i.active_yn='Y'" in count_sql
    assert "active_yn" not in registered_sql


def test_every_sql_case_has_single_read_only_reference(tmp_path):
    from text_to_sql.sql_guard import validate_read_only_sql

    cases = TextToSqlEvaluationCaseBuilder(
        SqlSchemaCatalog(_database(tmp_path))
    ).build()

    for case in cases:
        if case.expected_status == "SQL":
            assert case.reference_sql
            validated = validate_read_only_sql(case.reference_sql)
            assert validated.statement_kind in {"SELECT", "WITH"}
        else:
            assert case.reference_sql is None
