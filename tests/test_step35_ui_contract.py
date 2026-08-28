from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_sidebar_has_no_fixed_plant_selector_or_review_history_menu():
    source = (ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
    assert '"Agent 작업 PLANT"' not in source
    assert '"품평회 이력"' not in source
    assert "PLANT는 좌측에서 고정하지 않습니다" not in source
    assert "plant_options" in source
    assert "pending_plant_selection" in source


def test_revalidation_history_is_rendered_after_candidate_interaction():
    source = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
    function = source.split("def _render_pre_workflow_analysis", 1)[1].split("def _render_workflow", 1)[0]
    assert function.index("_render_candidate_selection") < function.index("_render_revalidation_history")
    assert "_analysis_selection_rows(workflow)" in function


def test_revalidation_navigation_has_result_autoscroll_and_return_buttons():
    source = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
    assert '"후보 다시 선택"' in source
    assert '"이 후보 조건 다시 수정"' in source
    assert "design_change_scroll_target" in source
    assert "scrollIntoView" in source
    assert "_candidate_selection_anchor(workflow)" in source
    assert "_revalidation_input_anchor(workflow, action_id, candidate_code)" in source
    assert "_revalidation_result_anchor(workflow, next_history_index)" in source
    assert "scroll_target=_revalidation_result_anchor(workflow, next_history_index)" in source


def test_condition_navigation_restores_history_candidate_before_selectbox_creation():
    source = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
    assert 'st.session_state["design_change_pending_candidate_navigation"]' in source
    assert 'st.session_state[selectbox_key] = pending_navigation["candidate_item_code"]' in source
    assert source.index('st.session_state[selectbox_key] = pending_navigation["candidate_item_code"]') < source.index('selected_code = st.selectbox(')


def test_repeated_scroll_to_same_anchor_uses_unique_navigation_event_and_modern_iframe():
    source = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
    assert 'design_change_scroll_event_seq' in source
    assert '"event_id": event_id' in source
    assert 'const navigationEventId' in source
    assert 'st.iframe(' in source
    assert 'components.html(' not in source
    assert 'streamlit.components.v1' not in source


def test_business_tables_are_arrow_safe_display_strings():
    source = (ROOT / "app" / "views" / "design_change_workflow_view.py").read_text(encoding="utf-8")
    assert 'def _display_value' in source
    assert 'def _display_df' in source
    assert 'st.table(_display_df(rows)' in source
    assert 'st.table(_display_df([{' in source
