from pathlib import Path

import pytest

from database import SQLiteDatabase, SchemaManager
from services.design_change_workflow_service import DesignChangeWorkflowService


ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_SOURCE = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
AGENT_VIEW_SOURCE = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
HISTORY_SOURCE = (ROOT / "app" / "views" / "design_change_history_page.py").read_text(encoding="utf-8")


def _service_with_version(tmp_path):
    database = SQLiteDatabase(tmp_path / "v3-final-fix.db")
    SchemaManager(database).initialize()
    with database.transaction() as con:
        con.execute(
            "INSERT INTO item_master(item_code,item_type,item_name) VALUES('FA','VERSION','FA')"
        )
        con.execute("INSERT INTO version_master(version_code) VALUES('FA')")
    return DesignChangeWorkflowService(database)


def test_add_target_type_is_recovered_from_explicit_material_wording(tmp_path):
    service = _service_with_version(tmp_path)
    action = {"action_type": "ADD", "target_item_name": "SEALANT"}
    request = {
        "version_code": "FA",
        "original_request": "FA P01 모델에 자재를 추가하고 싶어",
    }

    service._normalize_and_validate_action(action, request)

    assert action["target_type"] == "MATERIAL"
    assert action["target_type_resolution_source"] == "EXPLICIT_REQUEST_TEXT"
    assert action["parent_item_code"] == "FA"
    assert action["new_quantity"] == 1.0


def test_add_ambiguous_target_type_returns_user_facing_korean_message(tmp_path):
    service = _service_with_version(tmp_path)
    with pytest.raises(ValueError, match="추가하려는 자재 또는 ASSY가 지정되지 않았습니다"):
        service._normalize_and_validate_action(
            {"action_type": "ADD"},
            {"version_code": "FA", "original_request": "FA P01 모델에 품목을 추가하고 싶어"},
        )



def test_add_without_specific_target_is_rejected_before_analysis(tmp_path):
    service = _service_with_version(tmp_path)
    with pytest.raises(ValueError, match="추가하려는 자재 또는 ASSY가 지정되지 않았습니다"):
        service._normalize_and_validate_action(
            {"action_type": "ADD", "target_type": "MATERIAL"},
            {
                "version_code": "FA",
                "original_request": "FA P01 모델에 자재를 추가하고 싶어",
            },
        )

def test_design_change_management_menu_is_not_exposed_in_main_navigation():
    assert '"phase3": "Design Change Rule / History"' not in STREAMLIT_SOURCE
    assert '_menu_link("Design Change Rule / History", "phase3")' not in STREAMLIT_SOURCE
    assert 'elif menu == "Design Change Rule / History"' not in STREAMLIT_SOURCE


def test_report_footer_phase3_caption_is_removed():
    assert "현재 Design Change 활성 프로세스" not in AGENT_VIEW_SOURCE


def test_request_proceed_prepares_preview_without_separate_preview_button():
    assert 'client.create_design_change_request_from_analysis(' in AGENT_VIEW_SOURCE
    assert 'preview_result = client.create_design_change_preview(request_id, "streamlit-user")' in AGENT_VIEW_SOURCE
    assert 'st.button("통합 영향 Preview 생성")' not in AGENT_VIEW_SOURCE
    assert 'st.markdown("#### 적용 전 최종 확인")' in AGENT_VIEW_SOURCE
    assert 'st.button("설계변경 확정", type="primary")' in AGENT_VIEW_SOURCE


def test_history_resume_does_not_expose_preview_generation_button():
    assert '"통합 영향 Preview 생성"' not in HISTORY_SOURCE
    assert 'client.create_design_change_preview(request_id, actor)' in HISTORY_SOURCE


def test_analysis_confirmation_and_proceed_are_one_user_action():
    assert 'label = "해당 분석안으로 설계변경 진행"' in AGENT_VIEW_SOURCE
    assert '_proceed_analysis_to_final_confirmation(' in AGENT_VIEW_SOURCE
    assert '"이 후보로 분석안 확정"' not in AGENT_VIEW_SOURCE
    assert '"이 Action 분석안 확정"' not in AGENT_VIEW_SOURCE
    assert 'st.button("영향범위를 확인했습니다"' not in AGENT_VIEW_SOURCE
    assert 'st.button("이 분석 결과로 설계변경 진행"' not in AGENT_VIEW_SOURCE


def test_final_confirmation_includes_common_impact_without_duplicate_step():
    assert 'analysis_models = impact_model_rows(workflow)' in AGENT_VIEW_SOURCE
    assert 'changed_specs = impact_spec_rows(workflow, changed_only=True)' in AGENT_VIEW_SOURCE
    assert 'st.markdown("**공용 영향 변경 Spec**")' in AGENT_VIEW_SOURCE
