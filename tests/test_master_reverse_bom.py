from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path

from scripts.database_lifecycle import DEFAULT_TEST_DATABASE
from mcp_server.capabilities.query import (
    get_item_detail_data,
    get_product_detail_data,
    get_where_used_data,
)


def _copy_db(tmp_path: Path) -> Path:
    target = tmp_path / "display_bom.db"
    shutil.copy2(DEFAULT_TEST_DATABASE, target)
    return target


def _dynamic_used_material(db_path: Path):
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            """SELECT b.plant_code,b.child_item_code
               FROM bom_master b
               JOIN item_master i ON i.item_code=b.child_item_code
               WHERE b.status='ACTIVE' AND i.item_type='MATERIAL'
               ORDER BY b.plant_code,b.child_item_code LIMIT 1"""
        ).fetchone()
    assert row is not None
    return row["plant_code"], row["child_item_code"]


def test_reverse_bom_returns_parent_and_top_model(monkeypatch, tmp_path):
    db_path = _copy_db(tmp_path)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(db_path))
    plant_code, material_code = _dynamic_used_material(db_path)

    result = get_where_used_data(material_code, plant_code, "2026-08-20")

    assert result["item_code"] == material_code
    assert result["where_used"]
    assert result["direct_parents"]
    assert result["top_models"]
    assert all(row["model_code"] for row in result["top_models"])


def test_reverse_bom_unused_material_returns_business_message(monkeypatch, tmp_path):
    db_path = _copy_db(tmp_path)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(db_path))
    plant_code, _ = _dynamic_used_material(db_path)
    suffix = uuid.uuid4().hex[:8].upper()
    material_code = f"UNUSED-{suffix}"
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO item_master(item_code,item_type,item_name,description,active_yn) VALUES(?,?,?,?, 'Y')",
            (material_code, "MATERIAL", "UNUSED MATERIAL", "TEST ONLY"),
        )
        con.execute(
            "INSERT INTO material_master(material_code,material_name,material_group,unit,active_yn) VALUES(?,?,?,?, 'Y')",
            (material_code, "UNUSED MATERIAL", "TEST", "EA"),
        )
        con.commit()

    result = get_where_used_data(material_code, plant_code, "2026-08-20")

    assert result["where_used"] == []
    assert "BOM에 구성되어 있지 않습니다" in result["message"]


def test_master_detail_tools_return_model_and_item_attributes(monkeypatch, tmp_path):
    db_path = _copy_db(tmp_path)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(db_path))
    plant_code, material_code = _dynamic_used_material(db_path)
    used = get_where_used_data(material_code, plant_code, "2026-08-20")
    model_code = used["top_models"][0]["model_code"]

    item = get_item_detail_data(material_code, "2026-08-20")
    model = get_product_detail_data(model_code, "2026-08-20")

    assert item["item_code"] == material_code
    assert item["item_type"] == "MATERIAL"
    assert "attributes" in item
    assert model["item_code"] == model_code
    assert model["item_type"] == "VERSION"
    assert "specification" in model


def test_master_query_ui_contract():
    app_source = Path("app/streamlit_app.py").read_text(encoding="utf-8")
    bom_source = Path("app/views/bom_query_page.py").read_text(encoding="utf-8")
    master_source = Path("app/views/master_query_page.py").read_text(encoding="utf-8")

    # Current sidebar is a single HTML navigation block. Master 조회 is a
    # non-clickable parent and BOM/모델/자재 are direct child links.
    assert 'view_to_menu = {' in app_source
    assert '"bom": "BOM"' in app_source
    assert '"model": "모델"' in app_source
    assert '"material": "자재"' in app_source
    assert '_menu_link("BOM", "bom", 24)' in app_source
    assert '_menu_link("모델", "model", 24)' in app_source
    assert '_menu_link("자재", "material", 24)' in app_source
    assert '●&nbsp;Master 조회' in app_source
    assert 'st.html(menu_html)' in app_source
    assert '"조회 유형"' not in app_source
    assert "get_bom_where_used" in bom_source
    assert "현재 BOM에 구성되어 있지 않습니다" in Path(
        "app/views/where_used_view.py"
    ).read_text(encoding="utf-8")
    assert "master_model_code_" in master_source
    assert "master_material_code_" in master_source
    assert "모델 상세" in master_source
    assert "자재 상세" in master_source
    assert "상세조회 모델" not in master_source
    assert "상세조회 자재" not in master_source
    assert 'st.markdown("#### Master 정보")' not in master_source
    assert 'st.markdown("#### Specification")' not in master_source
