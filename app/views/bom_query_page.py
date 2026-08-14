from datetime import date

import pandas as pd
import streamlit as st

from app.views.bom_view import (
    render_bom_result_table,
)
from mcp_client.client import (
    DisplayBomMcpClient,
)


@st.cache_resource
def create_mcp_client() -> DisplayBomMcpClient:
    """
    BOM 조회 화면에서 사용할
    Display BOM MCP Client를 생성합니다.
    """

    return DisplayBomMcpClient()


def render_bom_query_page() -> None:
    """
    MCP를 이용한 BOM 조회 화면입니다.
    """

    st.header("BOM 조회")

    st.caption(
        "제품의 현재 BOM 구조를 조회합니다. "
        "조회 요청은 MCP를 통해 처리됩니다."
    )

    col1, col2 = st.columns(
        [2, 1]
    )

    with col1:
        product_id = st.text_input(
            "BOM 조회 대상 코드",
            value="LTA400HR01-001",
            key="bom_query_product_id",
        )

    with col2:
        as_of_date = st.date_input(
            "기준일",
            value=date.today(),
            key="bom_query_as_of_date",
        )

    query_clicked = st.button(
        "BOM 조회",
        type="primary",
        width="stretch",
        key="bom_query_button",
    )

    if query_clicked:
        normalized_product_id = (
            product_id.strip()
        )

        if not normalized_product_id:
            st.error(
                "VERSION 또는 ASSEMBLY 코드를 입력해 주세요."
            )
            return

        try:
            client = create_mcp_client()

            with st.spinner(
                "MCP를 통해 BOM을 조회하고 있습니다..."
            ):
                bom_data = client.get_bom(
                    product_id=(
                        normalized_product_id
                    ),
                    as_of_date=(
                        as_of_date.strftime(
                            "%Y-%m-%d"
                        )
                    ),
                )

        except Exception as error:
            st.error(
                "BOM 조회 중 오류가 발생했습니다."
            )

            st.exception(error)
            return

        st.session_state[
            "bom_query_result"
        ] = bom_data

        # 새 조회조건에는 이전에 생성한 다운로드 파일을 재사용하지 않습니다.
        st.session_state.pop(
            "bom_excel_download",
            None,
        )

        st.session_state[
            "bom_query_condition"
        ] = {
            "product_id": (
                normalized_product_id
            ),
            "as_of_date": (
                as_of_date.strftime(
                    "%Y-%m-%d"
                )
            ),
        }

    bom_data = st.session_state.get(
        "bom_query_result"
    )

    if bom_data is None:
        return

    if not bom_data:
        st.warning(
            "조회 조건에 해당하는 BOM이 없습니다."
        )
        return

    bom_df = pd.DataFrame(
        bom_data
    )

    st.divider()

    condition = st.session_state.get(
        "bom_query_condition",
        {},
    )

    info_col1, info_col2 = st.columns(2)
    info_col1.metric(
        "기준일",
        condition.get(
            "as_of_date",
            "",
        ),
    )

    info_col2.metric(
        "BOM 항목",
        len(bom_df),
    )

    render_bom_result_table(bom_df)

    st.subheader("조회 결과 다운로드")
    st.caption("화면과 동일한 조회조건으로 MCP가 BOM을 다시 확인한 뒤 Excel을 생성합니다.")
    if st.button("Excel 파일 생성", width="stretch", key="bom_excel_create"):
        try:
            with st.spinner("MCP를 통해 Excel 파일을 생성하고 있습니다..."):
                st.session_state["bom_excel_download"] = create_mcp_client().export_bom_excel(
                    product_id=condition.get("product_id", ""),
                    as_of_date=condition.get("as_of_date"),
                )
        except Exception as error:
            st.error("BOM Excel 생성 중 오류가 발생했습니다.")
            st.exception(error)

    export_result = st.session_state.get("bom_excel_download")
    if export_result:
        if export_result.get("success"):
            exported_count = export_result.get("row_count", 0)
            if exported_count != len(bom_df):
                st.error(
                    "화면 조회 결과와 Excel 생성 시점의 BOM 건수가 다릅니다. "
                    "BOM을 다시 조회한 뒤 파일을 생성해 주세요."
                )
            else:
                st.download_button(
                    "BOM 조회결과 Excel 다운로드",
                    data=export_result["file_bytes"],
                    file_name=export_result["file_name"],
                    mime=export_result["mime_type"],
                    width="stretch",
                )
                st.caption(f"조회 결과 {exported_count}건 · 읽기 전용 다운로드")
        else:
            st.warning(export_result.get("message", "Excel 파일을 생성하지 못했습니다."))
