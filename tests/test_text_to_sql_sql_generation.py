import json
from pathlib import Path

import pytest

from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_generation import (
    SqlGenerationError,
    SqlGenerator,
    build_sql_generation_prompt,
)


class FakeModel:
    def __init__(self, response: str):
        self.response = response
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _catalog(tmp_path: Path) -> SqlSchemaCatalog:
    import sqlite3

    path = tmp_path / "test.db"
    connection = sqlite3.connect(path)
    try:
        from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY

        for table in DEFAULT_TEXT_TO_SQL_POLICY.allowed_tables:
            if table == "item_master":
                connection.execute(
                    "CREATE TABLE item_master ("
                    "item_code TEXT PRIMARY KEY, item_type TEXT, item_name TEXT, "
                    "active_yn TEXT)"
                )
            elif table == "material_master":
                connection.execute(
                    "CREATE TABLE material_master ("
                    "material_code TEXT PRIMARY KEY, material_name TEXT, "
                    "material_group TEXT, unit TEXT, specification TEXT)"
                )
            elif table == "version_master":
                connection.execute(
                    "CREATE TABLE version_master ("
                    "version_code TEXT PRIMARY KEY, product_name TEXT, "
                    "product_type TEXT, screen_size_inch REAL, resolution TEXT, "
                    "refresh_hz REAL, market TEXT)"
                )
            else:
                connection.execute(
                    f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY)'
                )
        connection.commit()
    finally:
        connection.close()
    return SqlSchemaCatalog(path)


def test_prompt_contains_schema_and_v9_semantic_contract(tmp_path):
    catalog = _catalog(tmp_path)
    prompt = build_sql_generation_prompt(
        "활성 자재 수를 알려줘",
        catalog.to_prompt_context(),
    )
    assert "TRUSTED_SCHEMA" in prompt
    assert "material_master" in prompt
    assert "item_master" in prompt
    assert "SELECT" in prompt
    assert "UNSUPPORTED" in prompt
    assert "Do not modify data" in prompt
    assert "item_master is the global item identity/lifecycle authority" in prompt
    assert "item_master.item_type stored values are VERSION, ASSEMBLY and MATERIAL" in prompt
    assert "the user term ASSY means ASSEMBLY" in prompt
    assert "never filter item_type='ASSY'" in prompt
    assert "Do not silently add active/current filters" in prompt
    assert "supplier_items is the only item-to-supplier relationship authority" in prompt
    assert "version_master exposes typed product attributes" in prompt
    assert "Qualify selected, filtered, grouped, and ordered columns" in prompt


def test_generator_accepts_json_sql_and_validates_guard(tmp_path):
    model = FakeModel(json.dumps({
        "status": "SQL",
        "sql": "SELECT material_group, COUNT(*) AS cnt "
               "FROM material_master GROUP BY material_group",
        "reason": "자재 그룹별 건수를 조회합니다.",
    }))
    generator = SqlGenerator(model=model, schema_catalog=_catalog(tmp_path))
    result = generator.generate("자재 그룹별 개수")
    assert result.status == "SQL"
    assert result.sql.startswith("SELECT")
    assert model.prompts


def test_generator_accepts_fenced_json(tmp_path):
    model = FakeModel(
        '```json\n{"status":"SQL","sql":"SELECT COUNT(*) AS cnt '
        'FROM material_master","reason":"count"}\n```'
    )
    result = SqlGenerator(model=model, schema_catalog=_catalog(tmp_path)).generate(
        "자재 수"
    )
    assert result.is_sql


def test_generator_rejects_write_sql_even_when_llm_labels_sql(tmp_path):
    model = FakeModel(json.dumps({
        "status": "SQL",
        "sql": "DELETE FROM material_master",
        "reason": "bad",
    }))
    generator = SqlGenerator(model=model, schema_catalog=_catalog(tmp_path))
    with pytest.raises(Exception, match="Only SELECT|read-only|allowed"):
        generator.generate("자재를 삭제해줘")


def test_generator_supports_explicit_unsupported(tmp_path):
    model = FakeModel(json.dumps({
        "status": "UNSUPPORTED",
        "sql": None,
        "reason": "데이터 변경 요청은 Text-to-SQL에서 지원하지 않습니다.",
    }))
    result = SqlGenerator(model=model, schema_catalog=_catalog(tmp_path)).generate(
        "자재를 삭제해줘"
    )
    assert result.status == "UNSUPPORTED"
    assert result.sql is None


def test_generator_rejects_invalid_json(tmp_path):
    generator = SqlGenerator(
        model=FakeModel("SELECT * FROM material_master"),
        schema_catalog=_catalog(tmp_path),
    )
    with pytest.raises(SqlGenerationError, match="JSON"):
        generator.generate("자재 보여줘")
