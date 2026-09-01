import pytest

from text_to_sql.sql_guard import SqlSafetyError, validate_read_only_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM item_master",
        "WITH x AS (SELECT item_code FROM item_master) SELECT * FROM x",
        "-- comment\nSELECT COUNT(*) FROM material_master;",
        "SELECT ';' AS literal_value",
    ],
)
def test_guard_accepts_single_read_query(sql):
    validated = validate_read_only_sql(sql)
    assert validated.statement_kind in {"SELECT", "WITH"}


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE material_master SET active_yn='N'",
        "DELETE FROM material_master",
        "DROP TABLE material_master",
        "PRAGMA table_info(material_master)",
        "SELECT * FROM material_master; SELECT * FROM item_master",
        "",
    ],
)
def test_guard_rejects_obvious_unsafe_sql(sql):
    with pytest.raises(SqlSafetyError):
        validate_read_only_sql(sql)
