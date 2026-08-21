from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
HISTORY = (ROOT / "app" / "views" / "design_change_history_page.py").read_text(encoding="utf-8")
MASTER = (ROOT / "app" / "views" / "master_query_page.py").read_text(encoding="utf-8")


def test_history_selection_is_session_local_and_cleared_when_leaving_page():
    assert "phase3_history_selected_request_id" in HISTORY
    assert "history_request_id=" not in HISTORY
    assert "st.query_params" not in HISTORY
    assert 'st.session_state.pop(' in APP
    assert '"phase3_history_selected_request_id"' in APP


def test_master_views_are_nested_directly_under_master_main_menu():
    # Sidebar navigation is now rendered as one HTML block so Streamlit's
    # radio/button wrapper spacing cannot distort the menu layout.
    assert 'view_to_menu = {' in APP
    assert '●&nbsp;Master 조회' in APP
    assert '_menu_link("BOM", "bom", 24)' in APP
    assert '_menu_link("모델", "model", 24)' in APP
    assert '_menu_link("자재", "material", 24)' in APP
    assert 'st.html(menu_html)' in APP
    assert '"Master 조회 · BOM"' not in APP
    assert '"조회 유형"' not in APP
    assert "master_query_view" not in APP


def test_model_and_material_codes_drive_detail_without_selectbox():
    assert "master_model_code_" in MASTER
    assert "master_material_code_" in MASTER
    assert "상세조회 모델" not in MASTER
    assert "상세조회 자재" not in MASTER
    assert "master_model_selected_code" in MASTER
    assert "master_material_selected_code" in MASTER


def test_master_detail_sections_are_deduplicated():
    assert "_flatten_detail_attributes" in MASTER
    assert 'st.markdown("#### 상세 속성")' in MASTER
    assert 'st.markdown("#### Master 정보")' not in MASTER
    assert 'st.markdown("#### Specification")' not in MASTER
