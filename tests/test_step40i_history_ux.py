from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "views" / "design_change_history_page.py").read_text(encoding="utf-8")


def test_history_search_fields_are_separated():
    assert '"Request ID"' in SOURCE
    assert 'key="phase3_history_request_id_filter"' in SOURCE
    assert '"제품"' in SOURCE
    assert 'key="phase3_history_version_filter"' in SOURCE
    assert '"PLANT"' in SOURCE
    assert 'key="phase3_history_plant_filter"' in SOURCE
    assert '"업무 상태"' in SOURCE
    assert 'key="phase3_history_status_filter"' in SOURCE


def test_history_is_paginated_by_fifteen_rows():
    assert "def _paginate_history_pairs(" in SOURCE
    assert "page_size: int = 15" in SOURCE
    assert "page_size=15" in SOURCE
    assert '"← 이전"' in SOURCE
    assert '"다음 →"' in SOURCE


def test_request_id_is_blue_bold_in_app_button():
    assert 'phase3_history_req_' in SOURCE
    assert 'type="tertiary"' in SOURCE
    assert 'color: #1565C0' in SOURCE
    assert 'font-weight: 700' in SOURCE
    assert 'history_request_id=' not in SOURCE


def test_request_detail_selectbox_is_removed_and_click_drives_detail_without_url_reload():
    assert "상세 조회할 Request" not in SOURCE
    assert 'st.query_params.get("history_request_id"' not in SOURCE
    assert 'phase3_history_selected_request_id' in SOURCE
    assert "render_phase3_request_detail(client, selected)" in SOURCE
