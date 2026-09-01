import sqlite3

from text_to_sql.policy import TextToSqlPolicy
from text_to_sql.schema_catalog import SqlSchemaCatalog


def test_schema_catalog_exposes_only_allowlisted_tables(tmp_path):
    path = tmp_path / "schema.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE item_master(item_code TEXT PRIMARY KEY, item_name TEXT NOT NULL);
        CREATE TABLE material_master(
          material_code TEXT PRIMARY KEY REFERENCES item_master(item_code),
          material_name TEXT NOT NULL
        );
        CREATE TABLE secret_table(secret TEXT);
        """
    )
    connection.close()

    policy = TextToSqlPolicy(allowed_tables=frozenset({"item_master", "material_master"}))
    catalog = SqlSchemaCatalog(path, policy)
    tables = catalog.load()

    assert [table.name for table in tables] == ["item_master", "material_master"]
    context = catalog.to_prompt_context()
    assert "TABLE item_master" in context
    assert "TABLE material_master" in context
    assert "secret_table" not in context
    assert "material_master.material_code -> item_master.item_code" in context


def test_schema_catalog_fails_when_allowlist_table_is_missing(tmp_path):
    path = tmp_path / "schema.db"
    sqlite3.connect(path).close()
    policy = TextToSqlPolicy(allowed_tables=frozenset({"item_master"}))

    try:
        SqlSchemaCatalog(path, policy).load()
    except RuntimeError as error:
        assert "item_master" in str(error)
    else:
        raise AssertionError("missing allowlist table must fail")
