import json
import sqlite3
from pathlib import Path

from text_to_sql.pipeline import TextToSqlPipeline
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_generation import SqlGenerator


class FakeModel:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, prompt: str) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


def _database(tmp_path: Path) -> Path:
    from text_to_sql.policy import DEFAULT_TEXT_TO_SQL_POLICY

    path = tmp_path / "pipeline.db"
    connection = sqlite3.connect(path)
    try:
        for table in DEFAULT_TEXT_TO_SQL_POLICY.allowed_tables:
            if table == "item_master":
                connection.execute(
                    "CREATE TABLE item_master ("
                    "item_code TEXT PRIMARY KEY, item_type TEXT, item_name TEXT, "
                    "active_yn TEXT)"
                )
                connection.executemany(
                    "INSERT INTO item_master VALUES (?, 'MATERIAL', ?, ?)",
                    [
                        ("M1", "MAT-1", "Y"),
                        ("M2", "MAT-2", "Y"),
                        ("M3", "MAT-3", "Y"),
                        ("M4", "MAT-4", "N"),
                    ],
                )
            elif table == "material_master":
                connection.execute(
                    "CREATE TABLE material_master ("
                    "material_code TEXT PRIMARY KEY, material_name TEXT, "
                    "material_group TEXT, unit TEXT, specification TEXT)"
                )
                connection.executemany(
                    "INSERT INTO material_master VALUES (?, ?, ?, 'EA', NULL)",
                    [
                        ("M1", "MAT-1", "OLB"),
                        ("M2", "MAT-2", "OLB"),
                        ("M3", "MAT-3", "LC"),
                        ("M4", "MAT-4", "LC"),
                    ],
                )
            else:
                connection.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY)')
        connection.commit()
    finally:
        connection.close()
    return path


def test_pipeline_executes_generated_v9_active_material_sql(tmp_path):
    path = _database(tmp_path)
    model = FakeModel({
        "status": "SQL",
        "sql": (
            "SELECT m.material_group, COUNT(*) AS material_count "
            "FROM material_master m "
            "JOIN item_master i ON i.item_code=m.material_code "
            "WHERE i.item_type='MATERIAL' AND i.active_yn='Y' "
            "GROUP BY m.material_group "
            "ORDER BY material_count DESC, m.material_group"
        ),
        "reason": "활성 자재를 그룹별 집계합니다.",
    })
    pipeline = TextToSqlPipeline(
        generator=SqlGenerator(
            model=model,
            schema_catalog=SqlSchemaCatalog(path),
        ),
        executor=ReadOnlySqlExecutor(path),
    )
    result = pipeline.run("활성 자재 그룹별 개수")
    assert result.status == "SQL"
    assert result.row_count == 2
    assert result.rows[0]["material_count"] == 2


def test_pipeline_does_not_execute_unsupported_request(tmp_path):
    path = _database(tmp_path)
    model = FakeModel({
        "status": "UNSUPPORTED",
        "sql": None,
        "reason": "변경 요청은 지원하지 않습니다.",
    })
    pipeline = TextToSqlPipeline(
        generator=SqlGenerator(
            model=model,
            schema_catalog=SqlSchemaCatalog(path),
        ),
        executor=ReadOnlySqlExecutor(path),
    )
    result = pipeline.run("자재를 삭제해줘")
    assert result.status == "UNSUPPORTED"
    assert result.rows == ()
    assert result.sql is None
