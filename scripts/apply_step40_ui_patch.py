from __future__ import annotations

from pathlib import Path


TARGET = Path("app/views/phase3_agent_view.py")

HELPER = r'''def _render_candidate_free_action_analysis(
    workflow: dict,
    client: DisplayBomMcpClient,
    on_workflow_update,
) -> None:
    """Render DELETE/QUANTITY_CHANGE Analysis that does not require candidate selection."""
    actions = [
        dict(action) for action in workflow.get("actions", [])
        if action.get("action_type") in {"DELETE", "QUANTITY_CHANGE"}
    ]
    if not actions:
        return

    rows = []
    for index, action in enumerate(actions, start=1):
        demand = action.get("demand") or {}
        inventory = action.get("inventory") or {}
        rows.append({
            "Action": index,
            "유형": action.get("action_type"),
            "대상 품목": action.get("old_item_code") or "-",
            "Parent": action.get("parent_item_code") or "-",
            "LOCATION": action.get("location_code") or "-",
            "변경 전 수량": action.get("old_quantity"),
            "변경 후 수량": action.get("new_quantity"),
            "평가": action.get("evaluation_status") or "-",
            "수요 기준": demand.get("source") or "-",
            "필요수량": demand.get("quantity"),
            "가용재고": inventory.get("available_quantity"),
            "부족수량": inventory.get("shortage_quantity"),
        })

    st.markdown("#### Action 검증")
    st.caption(
        "DELETE와 QUANTITY_CHANGE는 대체 후보를 선택하지 않습니다. "
        "현재 BOM 관계, 변경 수량, 생산계획/재고 및 공용 BOM 영향범위를 검증한 뒤 진행합니다."
    )
    st.dataframe(_display_df(rows), width="stretch", hide_index=True)

    statuses = {str(action.get("evaluation_status") or "PENDING") for action in actions}
    context_id = workflow.get("analysis_id") or workflow.get("request_id")
    if "FAIL" in statuses:
        st.error("FAIL Action이 있어 설계변경 진행 대상으로 확정할 수 없습니다.")
        return

    exception_reason = ""
    if "CONDITIONAL" in statuses:
        st.warning(
            "수요/재고 등 추가 확인이 필요한 CONDITIONAL Action이 있습니다. "
            "업무상 보완할 수 없는 경우에만 예외 검토 사유를 기록하세요."
        )
        exception_reason = st.text_area(
            "CONDITIONAL 예외 검토 사유",
            key=f"candidate_free_exception_{context_id}",
        )
        can_confirm = bool(exception_reason.strip())
        label = "예외조건 포함 Action 분석안 확정"
    else:
        st.success("후보 선택이 필요 없는 Action 검증이 완료되었습니다. 영향범위를 확인할 수 있습니다.")
        can_confirm = True
        label = "이 Action 분석안 확정"

    if st.button(label, type="primary", key=f"confirm_candidate_free_{context_id}", disabled=not can_confirm):
        workflow["analysis_selection"] = []
        workflow["analysis_exception_reason"] = exception_reason.strip() or None
        try:
            result = client.preview_design_change_analysis_impact(
                analysis=_analysis_payload(workflow), selections=[],
            )
        except Exception as error:
            st.error(f"영향범위 분석에 실패했습니다: {error}")
            return
        _complete_workflow_action(
            workflow,
            "preview_design_change_analysis_impact",
            result,
            "Action 분석안을 확정했습니다. 실제 Design Change Request는 아직 생성되지 않았습니다.",
            on_workflow_update,
        )


'''


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"STEP40 UI target not found: {TARGET}")
    text = TARGET.read_text(encoding="utf-8")
    changed = False

    if "def _render_candidate_free_action_analysis(" not in text:
        marker = "def _render_candidate_selection(workflow: dict, rows: list[dict], client: DisplayBomMcpClient, on_workflow_update) -> None:\n"
        if marker not in text:
            raise RuntimeError("STEP40 UI insertion marker was not found")
        text = text.replace(marker, HELPER + marker, 1)
        changed = True

    old_header = '''def _render_pre_workflow_analysis(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:\n    if not workflow.get("candidates"):\n        return\n'''
    new_header = '''def _render_pre_workflow_analysis(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:\n    if not workflow.get("candidates") and not workflow.get("actions"):\n        return\n'''
    if old_header in text:
        text = text.replace(old_header, new_header, 1)
        changed = True

    old_branch = '''    if step in {"ANALYSIS_READY", "ANALYSIS_REVALIDATED"}:\n        # 재검증이 특정 후보를 FAIL로 바꾸더라도 최초 분석 후보 Pool은 유지하여\n        # 다른 후보를 선택하거나 수량을 바꿔 반복 재검증할 수 있게 한다.\n        _render_candidate_selection(workflow, initial_rows, client, on_workflow_update)\n'''
    new_branch = '''    if step in {"ANALYSIS_READY", "ANALYSIS_REVALIDATED"}:\n        # 재검증이 특정 후보를 FAIL로 바꾸더라도 최초 분석 후보 Pool은 유지하여\n        # 다른 후보를 선택하거나 수량을 바꿔 반복 재검증할 수 있게 한다.\n        if _required_candidate_actions(workflow):\n            _render_candidate_selection(workflow, initial_rows, client, on_workflow_update)\n        else:\n            _render_candidate_free_action_analysis(workflow, client, on_workflow_update)\n'''
    if old_branch in text:
        text = text.replace(old_branch, new_branch, 1)
        changed = True

    if "def _render_candidate_free_action_analysis(" not in text or "and not workflow.get(\"actions\")" not in text:
        raise RuntimeError("STEP40 UI patch could not be verified")

    if changed:
        TARGET.write_text(text, encoding="utf-8")
        print("STEP40 UI patch applied: app/views/phase3_agent_view.py")
    else:
        print("STEP40 UI patch already applied; no changes needed")


if __name__ == "__main__":
    main()
