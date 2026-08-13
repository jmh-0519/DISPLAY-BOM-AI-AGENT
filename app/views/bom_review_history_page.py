from __future__ import annotations

import pandas as pd
import streamlit as st

from mcp_client.client import DisplayBomMcpClient


@st.cache_resource
def _client() -> DisplayBomMcpClient:
    return DisplayBomMcpClient()


def _label(status: str) -> str:
    return "사용자 확인 필요" if str(status).upper() == "CONDITIONAL" else str(status)


def render_bom_review_history_page() -> None:
    st.subheader("품평회 이력")
    st.caption("Review BOM 품평회의 진행상태, 종합판정, 세부 체크리스트를 조회합니다.")
    try:
        rows = _client().list_bom_reviews()
    except Exception as error:
        st.error(f"품평회 이력 조회에 실패했습니다: {error}")
        return
    if not rows:
        st.info("등록된 품평회 이력이 없습니다.")
        return
    c1, c2 = st.columns(2)
    keyword = c1.text_input("품평회 ID·변경 ID·제품 검색")
    results = sorted({str(x.get("review_result", "")) for x in rows if x.get("review_result")})
    result = c2.selectbox("종합판정", ["전체", *results])
    filtered = [x for x in rows if (
        (not keyword or keyword.strip().upper() in " ".join(str(x.get(k, "")) for k in ("review_id", "change_id", "product_id")).upper())
        and (result == "전체" or x.get("review_result") == result)
    )]
    st.dataframe(pd.DataFrame([{
        "품평회 ID": x.get("review_id"), "변경 ID": x.get("change_id"),
        "제품 ID": x.get("product_id"), "Revision": x.get("current_revision"),
        "진행상태": x.get("review_status"), "종합판정": _label(x.get("review_result", "")),
        "PASS": x.get("pass_count", 0), "확인 필요": x.get("conditional_count", 0),
        "FAIL": x.get("fail_count", 0), "생성일": x.get("created_date"),
    } for x in filtered]), hide_index=True, width="stretch")
    if not filtered:
        return
    selected = st.selectbox("상세 조회할 품평회 ID", [x["review_id"] for x in filtered])
    detail = _client().get_bom_review(selected)
    if not detail.get("success"):
        st.error(detail.get("message", "상세 조회에 실패했습니다."))
        return
    review = detail["review"]
    st.markdown("#### 품평 종합평가")
    a, b, c, d = st.columns(4)
    a.metric("종합판정", _label(review.get("review_result", "-")))
    b.metric("PASS", review.get("pass_count", 0))
    c.metric("확인 필요", review.get("conditional_count", 0))
    d.metric("FAIL", review.get("fail_count", 0))
    checks = detail.get("checks", [])
    if checks:
        order = {"FAIL": 0, "CONDITIONAL": 1, "PASS": 2}
        checks = sorted(checks, key=lambda x: order.get(str(x.get("status", "")).upper(), 9))
        st.markdown("#### 품평 체크리스트")
        st.dataframe(pd.DataFrame([{
            "구분": x.get("check_type"), "대상": x.get("target_id"),
            "결과": _label(x.get("status", "")), "실제값": x.get("actual_value"),
            "기준값": x.get("expected_value"), "검증 근거": x.get("message"),
        } for x in checks]), hide_index=True, width="stretch")
    if detail.get("bom_items"):
        with st.expander("Review BOM 상세"):
            st.dataframe(pd.DataFrame(detail["bom_items"]), hide_index=True, width="stretch")
