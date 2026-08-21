from datetime import date

import pandas as pd
import streamlit as st

from app.views.bom_view import render_bom_result_table
from app.views.where_used_view import render_where_used_result
from mcp_client.client import DisplayBomMcpClient


@st.cache_resource
def create_mcp_client() -> DisplayBomMcpClient:
    return DisplayBomMcpClient()


def _identify_code(client: DisplayBomMcpClient, code: str, as_of_date: str) -> dict:
    product = client.get_product_detail(code, as_of_date)
    if product and product.get("found") is not False and product.get("item_type") == "VERSION":
        return product
    item = client.get_item_detail(code, as_of_date)
    if item and item.get("found") is not False:
        return item
    return {"found": False, "item_code": code}


def render_bom_query_page() -> None:
    """정방향 BOM과 MATERIAL/ASSY where-used 조회를 지원하는 Master BOM 화면."""
    st.header("BOM 조회")
    st.caption(
        "VERSION/ASSY 코드는 하위 BOM을 조회하고, MATERIAL 코드는 해당 자재가 사용된 "
        "상위 ASSY와 최상위 MODEL을 역방향으로 조회합니다."
    )

    try:
        client = create_mcp_client()
        plants = client.list_plants()
    except Exception as error:
        st.error(f"활성 PLANT 목록을 조회하지 못했습니다: {error}")
        return

    plant_labels = {
        row["plant_code"]: f"{row['plant_code']} · {row['plant_name']}" for row in plants
    }
    col0, col1, col2 = st.columns([1.2, 2, 1])
    with col0:
        plant_code = st.selectbox(
            "PLANT", list(plant_labels), format_func=lambda value: plant_labels[value],
            key="bom_query_plant_code",
        )
    with col1:
        target_code = st.text_input(
            "BOM 조회 대상 코드", value="LTA400HR01-001", key="bom_query_product_id"
        )
    with col2:
        as_of_date = st.date_input("기준일", value=date.today(), key="bom_query_as_of_date")

    if st.button("BOM 조회", type="primary", use_container_width=True, key="bom_query_button"):
        normalized = target_code.strip().upper()
        if not normalized:
            st.warning("VERSION, ASSEMBLY 또는 MATERIAL 코드를 입력해 주세요.")
            return
        as_of_text = as_of_date.strftime("%Y-%m-%d")
        try:
            detail = _identify_code(client, normalized, as_of_text)
            if detail.get("found") is False:
                st.session_state["bom_query_result"] = None
                st.session_state["bom_where_used_result"] = None
                st.warning("등록된 VERSION/ASSEMBLY/MATERIAL 코드를 찾을 수 없습니다.")
                return

            item_type = detail.get("item_type")
            if item_type == "MATERIAL":
                with st.spinner("MCP를 통해 역방향 BOM을 조회하고 있습니다..."):
                    result = client.get_bom_where_used(normalized, plant_code, as_of_text)
                st.session_state["bom_query_result"] = None
                st.session_state["bom_where_used_result"] = result
                st.session_state.pop("bom_excel_download", None)
            else:
                with st.spinner("MCP를 통해 BOM을 조회하고 있습니다..."):
                    result = client.get_bom(
                        plant_code=plant_code, product_id=normalized, as_of_date=as_of_text
                    )
                st.session_state["bom_query_result"] = result
                st.session_state["bom_where_used_result"] = None
                st.session_state.pop("bom_excel_download", None)

            st.session_state["bom_query_condition"] = {
                "plant_code": plant_code,
                "plant_name": next(
                    row["plant_name"] for row in plants if row["plant_code"] == plant_code
                ),
                "product_id": normalized,
                "as_of_date": as_of_text,
                "item_type": item_type,
            }
        except Exception as error:
            # 조회 화면에서는 업무상 조회 실패를 Traceback으로 노출하지 않는다.
            st.error(f"BOM 조회 중 오류가 발생했습니다: {error}")
            return

    where_used = st.session_state.get("bom_where_used_result")
    if where_used is not None:
        st.divider()
        render_where_used_result(where_used)
        return

    bom_data = st.session_state.get("bom_query_result")
    if bom_data is None:
        return
    if not bom_data:
        st.info("조회 조건에 해당하는 활성 BOM이 없습니다.")
        return

    bom_df = pd.DataFrame(bom_data)
    st.divider()
    condition = st.session_state.get("bom_query_condition", {})
    info_col0, info_col1, info_col2 = st.columns(3)
    info_col0.metric(
        "PLANT", f"{condition.get('plant_code', '')} · {condition.get('plant_name', '')}"
    )
    info_col1.metric("기준일", condition.get("as_of_date", ""))
    info_col2.metric("BOM 항목", len(bom_df))
    render_bom_result_table(bom_df)

    st.subheader("조회 결과 다운로드")
    st.caption("화면과 동일한 조회조건으로 MCP가 BOM을 다시 확인한 뒤 Excel을 생성합니다.")
    if st.button("Excel 파일 생성", use_container_width=True, key="bom_excel_create"):
        try:
            with st.spinner("MCP를 통해 Excel 파일을 생성하고 있습니다..."):
                st.session_state["bom_excel_download"] = client.export_bom_excel(
                    plant_code=condition.get("plant_code", ""),
                    product_id=condition.get("product_id", ""),
                    as_of_date=condition.get("as_of_date"),
                )
        except Exception as error:
            st.error(f"BOM Excel 생성 중 오류가 발생했습니다: {error}")

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
                    use_container_width=True,
                )
                st.caption(f"조회 결과 {exported_count}건 · 읽기 전용 다운로드")
        else:
            st.warning(export_result.get("message", "Excel 파일을 생성하지 못했습니다."))
