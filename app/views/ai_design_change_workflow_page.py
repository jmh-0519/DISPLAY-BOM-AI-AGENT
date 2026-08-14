from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.views.design_change_page import render_design_change_analysis_result
from app.views.bom_query_page import create_mcp_client


class _McpWorkflowAdapter:
    """Streamlit Workflow UI가 업무 Service를 우회하지 않도록 하는 MCP Adapter."""

    def __init__(self) -> None:
        self.client = create_mcp_client()

    def create_change_request(self, product_id, old_id, new_id, reason,
                              effective_date, requested_by, as_of_date):
        return self.client.call_tool("create_ai_change_request", {
            "product_id": product_id, "old_material_id": old_id,
            "new_material_id": new_id, "reason": reason,
            "effective_date": effective_date, "requested_by": requested_by,
            "as_of_date": as_of_date,
        })

    def create_review_bom(self, change_id, created_by, created_date):
        return self.client.call_tool("create_review_bom", {
            "change_id": change_id, "created_by": created_by, "created_date": created_date,
        })

    def run_ai_review(self, review_id, reviewed_by, checked_date):
        return self.client.call_tool("run_ai_bom_review", {
            "review_id": review_id, "reviewed_by": reviewed_by, "checked_date": checked_date,
        })

    def apply_to_production(self, review_id, applied_by, applied_date):
        return self.client.call_tool("apply_reviewed_bom", {
            "review_id": review_id, "applied_by": applied_by, "applied_date": applied_date,
        })


def _service() -> _McpWorkflowAdapter:
    return _McpWorkflowAdapter()


def _check_rows(ai_review: dict) -> list[dict]:
    rows = []
    for item in ai_review.get("rule_results", []):
        status = str(item.get("status", "PASS")).upper()
        rows.append({
            "구분": item.get("check_type") or item.get("category") or "Rule",
            "체크리스트": item.get("rule_name") or item.get("rule_id") or item.get("check") or "업무 규칙",
            "결과": "사용자 확인 필요" if status == "CONDITIONAL" else status,
            "실제값": item.get("actual_value", "-"),
            "기준값": item.get("expected_value", "-"),
            "검증 근거": item.get("message", ""),
            "_order": {"FAIL": 0, "CONDITIONAL": 1, "PASS": 2}.get(status, 3),
        })
    for item in ai_review.get("compatibility_results", []):
        status = str(item.get("status", "PASS")).upper()
        rows.append({
            "구분": "호환성",
            "체크리스트": f"신규 자재 {item.get('new_material_id', '')} 호환성",
            "결과": "사용자 확인 필요" if status == "CONDITIONAL" else status,
            "실제값": item.get("new_material_id", "-"),
            "기준값": "호환 가능",
            "검증 근거": item.get("message", ""),
            "_order": {"FAIL": 0, "CONDITIONAL": 1, "PASS": 2}.get(status, 3),
        })
    return sorted(rows, key=lambda row: row["_order"])


def _render_ai_review(ai_review: dict) -> None:
    result = str(ai_review.get("ai_review_result", "FAIL")).upper()
    label = {"PASS": "PASS", "CONDITIONAL": "사용자 확인 필요", "FAIL": "FAIL"}.get(result, result)
    rows = _check_rows(ai_review)
    counts = {"PASS": 0, "사용자 확인 필요": 0, "FAIL": 0}
    for row in rows:
        counts[row["결과"]] = counts.get(row["결과"], 0) + 1

    st.subheader("AI 품평 종합평가")
    if result == "PASS":
        st.success("AI 품평 결과: PASS")
        opinion = "모든 자동검증 항목이 기준을 충족했습니다."
    elif result == "CONDITIONAL":
        st.warning("AI 품평 결과: 사용자 확인 필요")
        opinion = "조건부 항목에 대한 업무 담당자 확인 전까지 양산 적용이 차단됩니다."
    else:
        st.error("AI 품평 결과: FAIL")
        opinion = "실패 항목이 있어 Workflow 진행과 양산 적용이 차단됩니다."
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("종합 판정", label)
    c2.metric("PASS", counts.get("PASS", 0))
    c3.metric("사용자 확인", counts.get("사용자 확인 필요", 0))
    c4.metric("FAIL", counts.get("FAIL", 0))
    st.info(opinion)

    st.subheader("품평 체크리스트 상세")
    if rows:
        display_rows = [{key: value for key, value in row.items() if key != "_order"} for row in rows]
        review_frame = pd.DataFrame(display_rows)

        def status_color(value: str) -> str:
            return {
                "PASS": "background-color: #d9ead3; color: #274e13; font-weight: bold",
                "사용자 확인 필요": "background-color: #fff2cc; color: #7f6000; font-weight: bold",
                "FAIL": "background-color: #f4cccc; color: #990000; font-weight: bold",
            }.get(str(value), "")

        st.dataframe(
            review_frame.style.map(status_color, subset=["결과"]),
            hide_index=True,
            width="stretch",
            column_config={
                "구분": st.column_config.TextColumn(width="small"),
                "체크리스트": st.column_config.TextColumn(width="medium"),
                "결과": st.column_config.TextColumn(width="small"),
                "검증 근거": st.column_config.TextColumn(width="large"),
            },
        )
    else:
        st.info("표시할 세부 체크리스트가 없습니다.")


def render_ai_design_change_workflow_page() -> None:
    st.header("AI 설계변경·품평 Workflow")
    st.caption(
        "AI가 변경안을 분석하고 품평회 BOM의 체크리스트를 자동 검증합니다. "
        "양산 E-BOM은 보고서 확인 후 마지막 적용 버튼에서만 변경됩니다."
    )
    with st.form("ai_change_request"):
        c1, c2 = st.columns(2)
        product_id = c1.text_input("모델 ID", "LTA400HR01-0")
        old_id = c1.text_input("기존 자재", "0001-200010")
        new_id = c2.text_input("신규 자재", "9000-290004")
        effective = c2.date_input("적용 예정일", date.today())
        reason = st.text_input("변경 사유", "대체 자재 적용 검토")
        requester = st.text_input("요청자", "USER01")
        submitted = st.form_submit_button("1. 분석 및 변경 요청 생성", type="primary")
    if submitted:
        result = _service().create_change_request(
            product_id, old_id, new_id, reason,
            effective.isoformat(), requester, date.today().isoformat(),
        )
        st.session_state.ai_dc = {"request": result}

    flow = st.session_state.get("ai_dc", {})
    request = flow.get("request")
    if not request:
        return
    if not request.get("success"):
        st.error(request.get("message", "설계변경 분석에 실패했습니다."))
        render_design_change_analysis_result(
            request.get("analysis", {}),
            title="설계변경 분석 결과",
        )
        return
    st.success(f"변경 요청이 생성되었습니다: {request['change_id']}")
    render_design_change_analysis_result(
        request.get("analysis", {}),
        title="설계변경 분석 결과",
    )

    if st.button("2. 품평회 BOM 생성", width="stretch"):
        flow["review_bom"] = _service().create_review_bom(
            request["change_id"], "BOM_AI_AGENT", date.today().isoformat()
        )
    review_bom = flow.get("review_bom")
    if not review_bom:
        return
    if not review_bom.get("success"):
        st.error(review_bom.get("message")); return
    st.info(f"Review BOM: {review_bom['review_id']} / Rev.{review_bom['current_revision']}")

    if st.button("3. AI 품평 체크리스트 검증", width="stretch"):
        flow["ai_review"] = _service().run_ai_review(
            review_bom["review_id"], "BOM_AI_AGENT", date.today().isoformat()
        )
    ai_review = flow.get("ai_review")
    if not ai_review:
        return
    _render_ai_review(ai_review)
    status = ai_review.get("workflow_result")
    if status != "AI_REVIEW_COMPLETED":
        return

    if st.button("4. 완료 보고서 생성", width="stretch"):
        try:
            with st.spinner("MCP를 통해 Word 완료 보고서를 생성하고 있습니다..."):
                flow["report"] = create_mcp_client().export_design_change_report(
                    request["change_id"]
                )
        except Exception as error:
            flow["report"] = {"success": False, "message": str(error)}
    report = flow.get("report")
    if not report:
        return
    if not report.get("success"):
        st.error(report.get("message", "완료 보고서 생성에 실패했습니다."))
        return
    st.success("Word 완료 보고서가 생성되었습니다. 다운로드 후 내용을 확인해 주세요.")
    st.download_button(
        "Word 완료 보고서 다운로드",
        report["file_bytes"],
        file_name=report["file_name"],
        mime=report["mime_type"],
        width="stretch",
    )
    confirmed = st.checkbox("보고서와 AI 품평 결과를 확인했으며 양산 E-BOM 반영을 승인합니다.")
    if st.button("5. 양산 E-BOM 변경 적용", type="primary", disabled=not confirmed):
        result = _service().apply_to_production(
            review_bom["review_id"], requester, date.today().isoformat()
        )
        flow["apply"] = result
    if flow.get("apply", {}).get("success"):
        st.success("양산 E-BOM 반영이 완료되었습니다.")
        applied = flow["apply"]
        c1, c2, c3 = st.columns(3)
        c1.metric("처리 결과", applied.get("result", "APPLIED"))
        c2.metric("Review BOM", applied.get("review_id", review_bom["review_id"]))
        c3.metric("무결성 검사", (applied.get("integrity_check") or {}).get("status", "PASS"))
