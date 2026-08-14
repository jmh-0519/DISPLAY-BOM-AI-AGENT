from mcp_server.capabilities.query import (
    get_bom_data, list_materials_data, list_products_data,
    search_material_data, search_product_data,
)


def test_sqlite_query_capabilities(monkeypatch, tmp_path):
    import shutil
    target = tmp_path / "display_bom.db"
    shutil.copy2("data/display_bom.db", target)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(target))
    bom = get_bom_data("LTA400HR01-0", "2026-08-11")
    assert bom and all(row["root_code"] == "LTA400HR01-001" for row in bom)
    assert {row["level"] for row in bom} >= {1, 2}
    assert list_products_data()
    assert search_product_data("LTA400HR01")
    assert list_materials_data()
    assert search_material_data("GATE-IC")


def test_sqlite_assembly_root_uses_common_contract(monkeypatch, tmp_path):
    import shutil
    target = tmp_path / "display_bom.db"
    shutil.copy2("data/display_bom.db", target)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(target))
    rows = get_bom_data("LJ94-100004", "2026-08-13")
    assert rows
    assert rows[0]["bom_title"] == "ASSY BOM"
    assert all(row["root_code"] == "LJ94-100004" for row in rows)
