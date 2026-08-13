from __future__ import annotations

import pandas as pd
import streamlit as st

from mcp_client.client import DisplayBomMcpClient


@st.cache_resource
def _client() -> DisplayBomMcpClient:
    return DisplayBomMcpClient()


def _change_request_display(change: dict) -> pd.DataFrame:
    """설계변경 요청 정보를 JSON 대신 사용자용 표로 변환합니다."""
    return pd.DataFrame([{
        "변경 ID": change.get("change_id") or "-",
        "제품 ID": change.get("product_id") or "-",
        "변경 사유": change.get("reason") or "-",
        "적용 희망일": change.get("effective_date") or "-",
        "요청자": change.get("requested_by") or "-",
        "품평회 ID": change.get("review_id") or "-",
    }])


def _change_items_display(items: list[dict]) -> pd.DataFrame:
    """변경 자재 원본 필드를 업무 화면용 한글 컬럼으로 변환합니다."""
    return pd.DataFrame([{
        "순번": item.get("item_seq") or "-",
        "변경 유형": item.get("action") or "-",
        "상위 BOM": item.get("bom_parent") or "-",
        "기존 자재": item.get("old_bom_child") or "-",
        "신규 자재": item.get("new_bom_child") or "-",
        "위치": item.get("location") or "-",
        "전개 순서": item.get("sequence_no") or "-",
        "수량": item.get("quantity") or "-",
        "적용일": item.get("effective_date") or "-",
    } for item in items])


def render_design_change_history_page() -> None:
    st.subheader("설계변경 이력")
    st.caption("Agent 채팅과 AI 설계변경 Workflow에서 생성한 요청을 통합 조회합니다.")
    try:
        rows = _client().list_design_changes()
    except Exception as error:
        st.error(f"설계변경 이력 조회에 실패했습니다: {error}")
        return
    if not rows:
        st.info("등록된 설계변경 이력이 없습니다.")
        return

    c1, c2, c3 = st.columns(3)
    keyword = c1.text_input("변경 ID·제품·자재 검색")
    statuses = sorted({str(row.get("workflow_status", "")) for row in rows})
    status = c2.selectbox("진행상태", ["전체", *statuses])
    results = sorted({str(row.get("analysis_result", "")) for row in rows if row.get("analysis_result")})
    result = c3.selectbox("분석결과", ["전체", *results])
    filtered = []
    for row in rows:
        searchable = " ".join(str(row.get(k, "")) for k in (
            "change_id", "product_id", "old_material_id", "new_material_id", "requested_by"
        )).upper()
        if keyword and keyword.strip().upper() not in searchable:
            continue
        if status != "전체" and row.get("workflow_status") != status:
            continue
        if result != "전체" and row.get("analysis_result") != result:
            continue
        filtered.append(row)

    display = pd.DataFrame([{
        "변경 ID": x.get("change_id"), "제품 ID": x.get("product_id"),
        "기존 자재": x.get("old_material_id"), "신규 자재": x.get("new_material_id"),
        "분석": x.get("analysis_result"), "진행상태": x.get("workflow_status"),
        "요청일": x.get("requested_date"), "요청자": x.get("requested_by"),
    } for x in filtered])
    st.dataframe(display, hide_index=True, width="stretch")
    if not filtered:
        return
    selected = st.selectbox("상세 조회할 변경 ID", [x["change_id"] for x in filtered])
    detail = _client().get_design_change(selected)
    if not detail.get("success"):
        st.error(detail.get("message", "상세 조회에 실패했습니다."))
        return
    change = detail["change"]
    st.markdown("#### 설계변경 상세")
    a, b, c, d = st.columns(4)
    a.metric("진행상태", change.get("workflow_status", "-"))
    b.metric("분석결과", change.get("analysis_result", "-"))
    c.metric("품평결과", change.get("review_result") or "-")
    d.metric("양산 반영", "완료" if change.get("apply_status") == "APPLIED" else "미반영")
    st.markdown("#### 요청 정보")
    st.dataframe(_change_request_display(change), hide_index=True, width="stretch")
    if detail.get("items"):
        st.markdown("#### 변경 자재")
        st.dataframe(_change_items_display(detail["items"]), hide_index=True, width="stretch")
    if change.get("review_id"):
        try:
            report = _client().export_design_change_report(selected)
            if report.get("success"):
                st.download_button(
                    "Word 완료 보고서 다시 다운로드", report["file_bytes"],
                    file_name=report["file_name"], mime=report["mime_type"], width="stretch",
                )
        except Exception as error:
            st.warning(f"보고서를 다시 생성할 수 없습니다: {error}")
