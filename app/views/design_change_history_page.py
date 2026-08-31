from __future__ import annotations

import html
import json
import math

import pandas as pd
import streamlit as st

from core.datetime_display import format_utc_timestamp
from mcp_client.client import DisplayBomMcpClient


@st.cache_resource
def _client() -> DisplayBomMcpClient:
    return DisplayBomMcpClient()




_STATUS_LABELS = {
    # Workflow labels shown in the history UI.
    "NOT_STARTED": "미시작",
    "REQUESTED": "Request 생성",
    "CANDIDATES_EVALUATED": "후보 평가 완료",
    "WAITING_CANDIDATE_APPROVAL": "변경자재 확정 대기",
    "CONDITIONAL_REVIEW_REQUIRED": "조건부 검토 필요",
    "IMPACT_REVIEW_REQUIRED": "영향범위 확인 필요",
    "CANDIDATE_APPROVED": "변경자재 확정 완료",
    "WAITING_FINAL_APPROVAL": "설계변경 확정 대기",
    "FINAL_APPROVED": "설계변경 확정 완료",
    "APPLIED": "BOM 반영 완료",
    "REPORT_COMPLETED": "완료 보고서 생성 완료",
    "BLOCKED": "진행 차단",
    "PENDING": "대기",
    "REJECTED": "반려",
    "FAILED": "실패",
}


def _status_label(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return _STATUS_LABELS.get(text.upper(), text)


def _candidate_status_label(value) -> str:
    text = str(value or "").strip().upper()
    return {
        "PENDING": "대기",
        "APPROVED": "확정 완료",
        "REJECTED": "반려",
    }.get(text, _status_label(value))


def _final_status_label(value) -> str:
    text = str(value or "").strip().upper()
    return {
        "PENDING": "대기",
        "APPROVED": "확정 완료",
        "REJECTED": "반려",
    }.get(text, _status_label(value))


def _apply_status_label(value) -> str:
    text = str(value or "").strip().upper()
    return {
        "NOT_APPLIED": "미반영",
        "APPLIED": "반영 완료",
        "FAILED": "실패",
    }.get(text, _status_label(value))


def _reasons(value) -> str:
    if isinstance(value, list):
        return " · ".join(str(item) for item in value) or "-"
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    return " · ".join(str(item) for item in parsed) if isinstance(parsed, list) else str(parsed)


def _display_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if value != value:
            return "-"
        return f"{value:g}"
    return str(value)


def _display_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {key: _display_value(value) for key, value in row.items()}
        for row in rows
    ])


def _history_rows(requests: list[dict]) -> list[dict]:
    return [{
        "Request ID": row.get("request_id"),
        "PLANT": row.get("plant_code"),
        "제품": row.get("version_code"),
        "변경 사유": _reasons(row.get("reasons_json")),
        "변경자재 확정": _candidate_status_label(row.get("candidate_approval_status")),
        "설계변경 확정": _final_status_label(row.get("final_approval_status")),
        "BOM 반영": _apply_status_label(row.get("apply_status")),
        "업무 상태": _status_label(row.get("workflow_status")),
        "요청자": row.get("requested_by"),
        "생성시각(KST)": format_utc_timestamp(row.get("created_at")),
    } for row in requests]


def _action_rows(actions: list[dict]) -> list[dict]:
    return [{
        "Action": row.get("action_type"),
        "대상 유형": row.get("target_type"),
        "Parent": row.get("parent_item_code"),
        "변경 전": row.get("old_item_code"),
        "변경 후": row.get("new_item_code"),
        "변경 전 수량": row.get("old_quantity"),
        "변경 후 수량": row.get("new_quantity"),
        "Location": row.get("location_code"),
        "평가": row.get("evaluation_status"),
    } for row in actions]


def _style_action_frame(frame: pd.DataFrame):
    """Emphasize before/after values without changing persisted values."""
    styler = frame.style
    before_cols = [column for column in ("변경 전", "변경 전 수량") if column in frame.columns]
    after_cols = [column for column in ("변경 후", "변경 후 수량") if column in frame.columns]
    if before_cols:
        styler = styler.set_properties(subset=before_cols, **{
            "color": "#1565C0",
            "font-weight": "700",
        })
    if after_cols:
        styler = styler.set_properties(subset=after_cols, **{
            "color": "#D32F2F",
            "font-weight": "700",
        })
    return styler


def _lookup_item(client: DisplayBomMcpClient, item_code: str | None, cache: dict[str, dict]) -> dict:
    code = str(item_code or "").strip()
    if not code:
        return {}
    if code in cache:
        return cache[code]
    try:
        rows = client.search_material(code)
    except Exception:
        rows = []
    exact = next((row for row in rows if str(row.get("material_id") or "") == code), None)
    value = dict(exact or (rows[0] if rows else {}))
    cache[code] = value
    return value


def _action_item_detail_rows(client: DisplayBomMcpClient, actions: list[dict]) -> list[dict]:
    cache: dict[str, dict] = {}
    rows: list[dict] = []
    for index, action in enumerate(actions, start=1):
        old_code = action.get("old_item_code")
        new_code = action.get("new_item_code")
        old_item = _lookup_item(client, old_code, cache)
        new_item = _lookup_item(client, new_code, cache)
        rows.append({
            "Action": index,
            "유형": action.get("action_type"),
            "구분": "변경 전",
            "품목 코드": old_code,
            "품목명": old_item.get("material_name"),
            "DESCRIPTION": old_item.get("specification"),
            "품목 유형": old_item.get("material_type") or action.get("target_type"),
            "상태": old_item.get("lifecycle_status"),
            "BOM 수량": action.get("old_quantity"),
        })
        rows.append({
            "Action": index,
            "유형": action.get("action_type"),
            "구분": "변경 후",
            "품목 코드": new_code,
            "품목명": new_item.get("material_name"),
            "DESCRIPTION": new_item.get("specification"),
            "품목 유형": new_item.get("material_type") or action.get("target_type"),
            "상태": new_item.get("lifecycle_status"),
            "BOM 수량": action.get("new_quantity"),
        })
    return [row for row in rows if row.get("품목 코드") or row.get("BOM 수량") is not None]


def _render_action_item_detail_table(rows: list[dict]) -> None:
    """Render before/after rows with one vertically merged Action sequence cell."""
    if not rows:
        return

    columns = list(rows[0].keys())
    grouped: list[tuple[object, list[dict]]] = []
    for row in rows:
        action_no = row.get("Action")
        if grouped and grouped[-1][0] == action_no:
            grouped[-1][1].append(row)
        else:
            grouped.append((action_no, [row]))

    head = "".join(
        f"<th>{html.escape(str(column))}</th>" for column in columns
    )
    body_parts: list[str] = []
    for action_no, action_rows in grouped:
        span = len(action_rows)
        for row_index, row in enumerate(action_rows):
            cells: list[str] = []
            if row_index == 0:
                cells.append(
                    f'<td rowspan="{span}" class="action-seq">'
                    f'{html.escape(_display_value(action_no))}</td>'
                )
            for column in columns[1:]:
                value = _display_value(row.get(column))
                cls = ""
                if column in {"품목 코드", "BOM 수량"}:
                    cls = "before" if row.get("구분") == "변경 전" else "after"
                cells.append(
                    f'<td class="{cls}">{html.escape(value)}</td>'
                )
            body_parts.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        f"""
        <style>
        .design-change-item-detail-wrap {{
            overflow-x: auto;
            margin-bottom: 0.75rem;
        }}
        table.design-change-item-detail {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.90rem;
        }}
        table.design-change-item-detail th,
        table.design-change-item-detail td {{
            border: 1px solid #E5E7EB;
            padding: 0.52rem 0.58rem;
            text-align: left;
            vertical-align: middle;
            white-space: nowrap;
        }}
        table.design-change-item-detail th {{
            background: #F8FAFC;
            font-weight: 500;
        }}
        table.design-change-item-detail td.action-seq {{
            text-align: center;
            font-weight: 600;
            background: #FFFFFF;
        }}
        table.design-change-item-detail td.before {{
            color: #1565C0;
            font-weight: 700;
        }}
        table.design-change-item-detail td.after {{
            color: #D32F2F;
            font-weight: 700;
        }}
        </style>
        <div class="design-change-item-detail-wrap">
          <table class="design-change-item-detail">
            <thead><tr>{head}</tr></thead>
            <tbody>{''.join(body_parts)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_history_next_step(
    client: DisplayBomMcpClient,
    detail: dict,
    *,
    actor: str = "streamlit-user",
) -> None:
    """Allow a pending persisted Request to continue from the history detail."""
    request_id = str(detail.get("request_id") or "").strip()
    workflow_status = str(detail.get("workflow_status") or "").strip().upper()
    if not request_id:
        return

    try:
        if workflow_status == "CANDIDATE_APPROVED":
            st.info("변경자재 확정이 완료되었습니다. 적용 전 최종 확인 정보를 자동으로 준비합니다.")
            client.create_design_change_preview(request_id, actor)
            st.rerun()

        elif workflow_status == "WAITING_FINAL_APPROVAL":
            st.info("적용 전 최종 확인 정보가 준비되었습니다. 설계변경을 확정할 수 있습니다.")
            if st.button(
                "설계변경 확정",
                type="primary",
                key=f"history_next_confirm_{request_id}",
            ):
                client.record_final_apply_approval(request_id, actor)
                st.rerun()

        elif workflow_status == "FINAL_APPROVED":
            final_approval_id = str(detail.get("final_approval_id") or "").strip()
            if not final_approval_id:
                st.warning("설계변경 확정 정보는 있으나 최종 확정 ID를 확인할 수 없습니다.")
                return
            st.warning(
                "확정된 설계변경 내용을 Production E-BOM에 반영합니다. "
                "반영 후에는 BOM이 실제 변경되므로 변경 내용을 다시 확인해 주세요."
            )
            if st.button(
                "설계변경 BOM 반영",
                type="primary",
                key=f"history_next_apply_{request_id}",
            ):
                client.apply_approved_change_request(
                    request_id=request_id,
                    final_approval_id=final_approval_id,
                    applied_by=actor,
                )
                st.rerun()
    except Exception as error:
        st.error(f"다음 단계 진행에 실패했습니다: {error}")


def render_design_change_request_detail(
    client: DisplayBomMcpClient,
    request_id: str,
    *,
    heading: str = "설계변경 Request 상세",
    show_completion_report: bool = True,
) -> dict | None:
    """Render one Design Change Request using the same detail layout everywhere.

    This is shared by the history page and the Agent-chat workflow so a Request
    looks identical immediately after creation and when it is reviewed days later.
    """
    try:
        detail = client.get_change_request_result(request_id)
    except Exception as error:
        st.error(f"Request 상세 조회에 실패했습니다: {error}")
        return None

    st.markdown(f"#### {heading}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("업무 상태", _status_label(detail.get("workflow_status")))
    c2.metric("변경자재 확정", _candidate_status_label(detail.get("candidate_approval_status")))
    c3.metric("설계변경 확정", _final_status_label(detail.get("final_approval_status")))
    c4.metric("BOM 반영", _apply_status_label(detail.get("apply_status")))

    st.table(_display_df([
        {"항목": "Request ID", "값": detail.get("request_id")},
        {"항목": "PLANT", "값": detail.get("plant_code")},
        {"항목": "제품", "값": detail.get("version_code")},
        {"항목": "요청 원문", "값": detail.get("original_request")},
        {"항목": "변경 사유", "값": _reasons(detail.get("reasons") or detail.get("reasons_json"))},
        {"항목": "요청자", "값": detail.get("requested_by")},
        {"항목": "생성시각(KST)", "값": format_utc_timestamp(detail.get("created_at"))},
    ]))

    actions = detail.get("actions") or []
    if actions:
        st.markdown("#### 확정 변경 Action")
        action_frame = _display_df(_action_rows(actions))
        st.dataframe(_style_action_frame(action_frame), hide_index=True, width="stretch")

        item_rows = _action_item_detail_rows(client, actions)
        if item_rows:
            st.markdown("#### 변경 품목 상세")
            st.caption("확정한 변경 전/후 품목의 Master 정보를 함께 표시합니다.")
            _render_action_item_detail_table(item_rows)

    if show_completion_report:
        _render_history_next_step(client, detail)

    if show_completion_report and detail.get("apply_status") == "APPLIED":
        try:
            report = client.export_design_change_completion_report(request_id)
        except Exception as error:
            st.warning(f"완료 보고서를 다시 생성할 수 없습니다: {error}")
            return detail
        if report.get("success") and report.get("file_bytes"):
            st.download_button(
                "Word 완료 보고서 다시 다운로드",
                report["file_bytes"],
                file_name=report.get("file_name") or f"{request_id}_design_change_completion_report.docx",
                mime=report.get("mime_type") or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                width="stretch",
                key=f"history_report_{request_id}",
            )
    return detail


def _filter_history_pairs(
    rows: list[dict],
    display_rows: list[dict],
    *,
    request_id_query: str = "",
    version_query: str = "",
    plant_query: str = "",
    workflow_status: str = "전체",
) -> list[tuple[dict, dict]]:
    """Apply the history-page search conditions independently.

    Request ID / product / PLANT are deliberately separate filters because a
    real history list can become large and operators often know only one field.
    """
    request_id_query = str(request_id_query or "").strip().upper()
    version_query = str(version_query or "").strip().upper()
    plant_query = str(plant_query or "").strip().upper()
    pairs: list[tuple[dict, dict]] = []
    for source, display in zip(rows, display_rows):
        if request_id_query and request_id_query not in str(source.get("request_id") or "").upper():
            continue
        if version_query and version_query not in str(source.get("version_code") or "").upper():
            continue
        if plant_query and plant_query not in str(source.get("plant_code") or "").upper():
            continue
        if workflow_status != "전체" and source.get("workflow_status") != workflow_status:
            continue
        pairs.append((source, display))
    return pairs


def _paginate_history_pairs(
    pairs: list[tuple[dict, dict]],
    page: int,
    *,
    page_size: int = 15,
) -> tuple[list[tuple[dict, dict]], int, int]:
    total_pages = max(1, math.ceil(len(pairs) / page_size))
    safe_page = min(max(int(page or 1), 1), total_pages)
    start = (safe_page - 1) * page_size
    return pairs[start:start + page_size], safe_page, total_pages


def _render_history_list(page_pairs: list[tuple[dict, dict]]) -> None:
    """Render the paged Request list with an in-app clickable Request ID.

    We intentionally use Streamlit buttons rather than URL query parameters.
    Query-parameter links reload the whole application and can reset the main
    sidebar radio to Agent chat before the history page is rendered.
    """
    if not page_pairs:
        return

    st.markdown(
        """
        <style>
        div[class*="st-key-design_change_history_req_"] button {
            color: #1565C0 !important;
            font-weight: 700 !important;
            background: transparent !important;
            border: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            min-height: 1.6rem !important;
            text-decoration: underline;
        }
        div[class*="st-key-design_change_history_req_"] button:hover {
            color: #0D47A1 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    columns = list(page_pairs[0][1].keys())
    widths = [1.55, 0.65, 1.35, 1.25, 0.9, 0.9, 0.9, 1.05, 0.9, 1.5]
    header = st.columns(widths)
    for col, name in zip(header, columns):
        col.markdown(f"**{name}**")
    st.divider()

    for source, display in page_pairs:
        row_cols = st.columns(widths)
        request_id = _display_value(display.get("Request ID"))
        safe_key = "".join(ch if ch.isalnum() else "_" for ch in request_id)
        if row_cols[0].button(
            request_id,
            key=f"design_change_history_req_{safe_key}",
            type="tertiary",
            help=f"{request_id} 상세 조회",
        ):
            st.session_state["design_change_history_selected_request_id"] = request_id

        for col, name in zip(row_cols[1:], columns[1:]):
            col.write(_display_value(display.get(name)))


def render_design_change_history_page() -> None:
    """Active Design Change Request history with field filters and 15-row paging.

    Analysis Sessions are intentionally excluded. Request details are opened by
    clicking the blue Request ID button in the list; there is no second lookup control.
    """
    st.subheader("설계변경 이력")
    st.caption(
        "AI 분석 Session은 이 목록에 저장되지 않습니다. 후보·영향범위를 확인한 뒤 사용자가 "
        "'설계변경 진행'을 선택하여 실제 Request가 생성된 건만 표시합니다."
    )
    client = _client()
    try:
        rows = client.list_design_change_history()
    except Exception as error:
        st.error(f"설계변경 이력 조회에 실패했습니다: {error}")
        return
    if not rows:
        st.info("생성된 설계변경 Request가 없습니다.")
        return

    statuses = sorted({str(row.get("workflow_status") or "") for row in rows if row.get("workflow_status")})
    f1, f2, f3, f4 = st.columns([2.2, 2.0, 1.4, 1.8])
    with f1:
        request_id_query = st.text_input(
            "Request ID",
            key="design_change_history_request_id_filter",
            placeholder="예: REQ-7CF4...",
        )
    with f2:
        version_query = st.text_input(
            "제품",
            key="design_change_history_version_filter",
            placeholder="예: LTA650HR11-001",
        )
    with f3:
        plant_query = st.text_input(
            "PLANT",
            key="design_change_history_plant_filter",
            placeholder="예: P03",
        )
    with f4:
        status = st.selectbox(
            "업무 상태",
            ["전체", *statuses],
            key="design_change_history_status_filter",
            format_func=lambda value: "전체" if value == "전체" else _status_label(value),
        )

    display_rows = _history_rows(rows)
    filtered_pairs = _filter_history_pairs(
        rows,
        display_rows,
        request_id_query=request_id_query,
        version_query=version_query,
        plant_query=plant_query,
        workflow_status=status,
    )

    filter_signature = "|".join((
        request_id_query.strip().upper(),
        version_query.strip().upper(),
        plant_query.strip().upper(),
        status,
    ))
    previous_signature = st.session_state.get("design_change_history_filter_signature")
    if previous_signature != filter_signature:
        st.session_state["design_change_history_filter_signature"] = filter_signature
        st.session_state["design_change_history_page"] = 1

    current_page = int(st.session_state.get("design_change_history_page", 1))
    page_pairs, current_page, total_pages = _paginate_history_pairs(filtered_pairs, current_page, page_size=15)
    st.session_state["design_change_history_page"] = current_page

    if not filtered_pairs:
        st.info("검색 조건에 해당하는 설계변경 Request가 없습니다.")
        return

    total_count = len(filtered_pairs)
    start_no = (current_page - 1) * 15 + 1
    end_no = min(current_page * 15, total_count)
    st.caption(f"총 {total_count}건 · {start_no}-{end_no}건 표시 · 페이지 {current_page}/{total_pages}")
    _render_history_list(page_pairs)

    if total_pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        with p1:
            if st.button("← 이전", disabled=current_page <= 1, key="design_change_history_prev", width="stretch"):
                st.session_state["design_change_history_page"] = current_page - 1
                st.rerun()
        with p2:
            st.markdown(
                f"<div style='text-align:center; padding-top:0.45rem;'>"
                f"<strong>{current_page}</strong> / {total_pages}</div>",
                unsafe_allow_html=True,
            )
        with p3:
            if st.button("다음 →", disabled=current_page >= total_pages, key="design_change_history_next", width="stretch"):
                st.session_state["design_change_history_page"] = current_page + 1
                st.rerun()

    selected = str(st.session_state.get("design_change_history_selected_request_id", "") or "").strip()
    filtered_request_ids = {str(source.get("request_id") or "") for source, _ in filtered_pairs}
    if selected and selected in filtered_request_ids:
        st.divider()
        render_design_change_request_detail(client, selected)

