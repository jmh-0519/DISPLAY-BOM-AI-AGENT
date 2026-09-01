import sqlite3

import pytest

from text_to_sql.policy import TextToSqlPolicy
from text_to_sql.read_only_executor import ReadOnlySqlExecutor
from text_to_sql.sql_guard import SqlSafetyError


def _database(tmp_path):
    path = tmp_path / "runtime.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE item_master(
          item_code TEXT PRIMARY KEY,
          item_name TEXT NOT NULL,
          item_type TEXT NOT NULL,
          active_yn TEXT NOT NULL
        );
        CREATE TABLE material_master(
          material_code TEXT PRIMARY KEY,
          material_name TEXT NOT NULL,
          material_group TEXT,
          active_yn TEXT NOT NULL
        );
        CREATE TABLE change_requests(request_id TEXT PRIMARY KEY);
        INSERT INTO item_master VALUES
          ('M1','Film A','MATERIAL','Y'),
          ('M2','Film B','MATERIAL','Y'),
          ('M3','Film C','MATERIAL','Y');
        INSERT INTO material_master VALUES
          ('M1','Film A','FILM','Y'),
          ('M2','Film B','FILM','Y'),
          ('M3','Film C','FILM','Y');
        INSERT INTO change_requests VALUES ('REQ-1');
        """
    )
    connection.commit()
    connection.close()
    return path


def _policy(max_rows=200):
    return TextToSqlPolicy(
        allowed_tables=frozenset({"item_master", "material_master"}),
        max_rows=max_rows,
    )


def test_executor_runs_select_and_cte(tmp_path):
    executor = ReadOnlySqlExecutor(_database(tmp_path), _policy())
    result = executor.execute(
        "WITH m AS (SELECT material_group FROM material_master) "
        "SELECT material_group, COUNT(*) AS cnt FROM m GROUP BY material_group"
    )
    assert result.row_count == 1
    assert result.rows[0]["material_group"] == "FILM"
    assert result.rows[0]["cnt"] == 3


def test_executor_blocks_non_allowlisted_table(tmp_path):
    executor = ReadOnlySqlExecutor(_database(tmp_path), _policy())
    with pytest.raises(SqlSafetyError, match="authorizer"):
        executor.execute("SELECT * FROM change_requests")


def test_executor_blocks_write_even_when_with_prefix_is_used(tmp_path):
    path = _database(tmp_path)
    executor = ReadOnlySqlExecutor(path, _policy())
    sql = "WITH x AS (SELECT 'M1' AS code) UPDATE material_master SET active_yn='N' WHERE material_code IN (SELECT code FROM x)"
    with pytest.raises(SqlSafetyError, match="authorizer"):
        executor.execute(sql)

    connection = sqlite3.connect(path)
    active_yn = connection.execute("SELECT active_yn FROM material_master WHERE material_code='M1'").fetchone()[0]
    connection.close()
    assert active_yn == "Y"


def test_executor_caps_returned_rows(tmp_path):
    executor = ReadOnlySqlExecutor(_database(tmp_path), _policy(max_rows=2))
    result = executor.execute("SELECT material_code FROM material_master ORDER BY material_code")
    assert result.row_count == 2
    assert result.truncated is True
