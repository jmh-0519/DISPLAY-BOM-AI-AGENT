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


def test_history_uses_confirm_and_bom_reflect_business_labels():
    assert '"변경자재 확정"' in SOURCE
    assert '"설계변경 확정"' in SOURCE
    assert '"BOM 반영"' in SOURCE
    assert '"후보 승인"' not in SOURCE
    assert '"최종 승인"' not in SOURCE
    assert '"E-BOM 적용"' not in SOURCE
    assert '"APPROVED": "확정 완료"' in SOURCE
    assert '"APPROVED": "확정 완료"' in SOURCE
    assert '"APPLIED": "반영 완료"' in SOURCE


def test_request_detail_can_resume_pending_workflow_from_history():
    assert "def _render_history_next_step(" in SOURCE
    assert 'workflow_status == "CANDIDATE_APPROVED"' in SOURCE
    assert 'workflow_status == "WAITING_FINAL_APPROVAL"' in SOURCE
    assert 'workflow_status == "FINAL_APPROVED"' in SOURCE
    assert '"통합 영향 Preview 생성"' in SOURCE
    assert '"설계변경 확정"' in SOURCE
    assert '"설계변경 BOM 반영"' in SOURCE


def test_change_item_detail_merges_action_sequence_cell():
    assert "def _render_action_item_detail_table(" in SOURCE
    assert 'rowspan="{span}"' in SOURCE
    assert "action-seq" in SOURCE
