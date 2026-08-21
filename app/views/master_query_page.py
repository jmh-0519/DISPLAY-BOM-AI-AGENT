from __future__ import annotations

from datetime import date
import json

import pandas as pd
import streamlit as st

from app.views.bom_query_page import render_bom_query_page
from mcp_client.client import DisplayBomMcpClient


@st.cache_resource
def _client() -> DisplayBomMcpClient:
    return DisplayBomMcpClient()


def _display_value(value) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _flatten_detail_attributes(detail: dict) -> list[dict]:
    """Build one de-duplicated detail list below the core item information."""
    skip_keys = {
        "item_code", "item_type", "item_name", "description", "status",
        "product_id", "product_name", "product_type", "version_code",
        "material_id", "material_name", "material_type", "lifecycle_status",
        "active_yn", "material_active_yn", "version_active_yn",
    }
    seen: set[str] = set()
    rows: list[dict] = []

    def append_value(name: str, value, unit=None, source=None) -> None:
        key = str(name or "").strip()
        if not key or key in skip_keys or key in seen:
            return
        shown = _display_value(value)
        if shown == "-":
            return
        seen.add(key)
        row = {"속성": key, "값": shown}
        if unit not in (None, ""):
            row["단위"] = _display_value(unit)
        if source not in (None, ""):
            row["출처"] = _display_value(source)
        rows.append(row)

    for key, value in (detail.get("master") or {}).items():
        append_value(key, value)
    for key, value in (detail.get("specification") or {}).items():
        append_value(key, value)
    for key, raw in (detail.get("attributes") or {}).items():
        if isinstance(raw, dict):
            append_value(key, raw.get("value"), raw.get("unit"), raw.get("source"))
        else:
            append_value(key, raw)
    return rows


def _render_detail(detail: dict, title: str) -> None:
    if not detail or detail.get("found") is False:
        st.warning(f"조회 조건에 해당하는 {title} 정보를 찾을 수 없습니다.")
        return

    st.subheader(f"{title} 상세")
    core = [
        {"항목": "코드", "값": detail.get("item_code")},
        {"항목": "품목명", "값": detail.get("item_name")},
        {"항목": "DESCRIPTION", "값": detail.get("description")},
        {"항목": "유형", "값": detail.get("item_type")},
        {"항목": "상태", "값": detail.get("status")},
    ]
    st.dataframe(
        pd.DataFrame(core).fillna("-").astype(str),
        use_container_width=True,
        hide_index=True,
    )

    detail_rows = _flatten_detail_attributes(detail)
    if detail_rows:
        st.markdown("#### 상세 속성")
        frame = pd.DataFrame(detail_rows).fillna("-").astype(str)
        st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_clickable_result_table(
    rows: list[dict],
    *,
    code_key: str,
    columns: list[tuple[str, str]],
    state_key: str,
    button_prefix: str,
) -> None:
    """Dense result list whose blue/bold code button opens detail in-place."""
    if not rows:
        return

    st.markdown(
        f"""
        <style>
        div[class*="st-key-{button_prefix}"] button {{
            color: #1565C0 !important;
            font-weight: 700 !important;
            background: transparent !important;
            border: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            min-height: 1.6rem !important;
            text-decoration: underline;
        }}
        div[class*="st-key-{button_prefix}"] button:hover {{ color: #0D47A1 !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    widths = [1.25] + [1.4 for _ in columns[1:]]
    header = st.columns(widths)
    for col, (_, label) in zip(header, columns):
        col.markdown(f"**{label}**")
    st.divider()

    for row in rows:
        line = st.columns(widths)
        code = _display_value(row.get(code_key))
        safe_key = "".join(ch if ch.isalnum() else "_" for ch in code)
        if line[0].button(
            code,
            key=f"{button_prefix}{safe_key}",
            type="tertiary",
            help=f"{code} 상세 조회",
        ):
            st.session_state[state_key] = code
        for col, (field, _) in zip(line[1:], columns[1:]):
            col.write(_display_value(row.get(field)))


def render_model_query_page() -> None:
    st.header("모델 조회")
    st.caption("모델코드/모델명으로 검색한 뒤 파란색 모델코드를 클릭해 상세 속성을 조회합니다.")
    keyword = st.text_input("모델 코드 또는 검색어", key="master_model_keyword")
    as_of = st.date_input("기준일", value=date.today(), key="master_model_as_of")

    if st.button("모델 조회", type="primary", use_container_width=True, key="master_model_search"):
        if not keyword.strip():
            st.warning("모델 코드 또는 검색어를 입력해 주세요.")
            st.session_state["master_model_results"] = []
            st.session_state.pop("master_model_selected_code", None)
        else:
            try:
                st.session_state["master_model_results"] = _client().search_product(keyword.strip()) or []
                st.session_state.pop("master_model_selected_code", None)
            except Exception as error:
                st.error(f"모델 조회 중 오류가 발생했습니다: {error}")
                st.session_state["master_model_results"] = []

    results = st.session_state.get("master_model_results", [])
    if not results:
        return

    _render_clickable_result_table(
        results,
        code_key="product_id",
        columns=[
            ("product_id", "모델 코드"),
            ("product_name", "모델명"),
            ("product_type", "유형"),
            ("version_code", "VERSION"),
            ("status", "상태"),
        ],
        state_key="master_model_selected_code",
        button_prefix="master_model_code_",
    )

    selected = str(st.session_state.get("master_model_selected_code", "") or "").strip()
    if not selected:
        return
    st.divider()
    try:
        detail = _client().get_product_detail(selected, as_of.strftime("%Y-%m-%d"))
    except Exception as error:
        st.error(f"모델 상세조회 중 오류가 발생했습니다: {error}")
        return
    _render_detail(detail, "모델")


def render_material_query_page() -> None:
    st.header("자재 조회")
    st.caption("자재/ASSY 코드 또는 품목명으로 검색한 뒤 파란색 자재코드를 클릭해 상세 속성을 조회합니다.")
    keyword = st.text_input("자재 코드 또는 검색어", key="master_material_keyword")
    as_of = st.date_input("기준일", value=date.today(), key="master_material_as_of")

    if st.button("자재 조회", type="primary", use_container_width=True, key="master_material_search"):
        if not keyword.strip():
            st.warning("자재 코드 또는 검색어를 입력해 주세요.")
            st.session_state["master_material_results"] = []
            st.session_state.pop("master_material_selected_code", None)
        else:
            try:
                st.session_state["master_material_results"] = _client().search_material(keyword.strip()) or []
                st.session_state.pop("master_material_selected_code", None)
            except Exception as error:
                st.error(f"자재 조회 중 오류가 발생했습니다: {error}")
                st.session_state["master_material_results"] = []

    results = st.session_state.get("master_material_results", [])
    if not results:
        return

    _render_clickable_result_table(
        results,
        code_key="material_id",
        columns=[
            ("material_id", "자재 코드"),
            ("material_name", "품목명"),
            ("material_type", "유형"),
            ("category", "Category"),
            ("specification", "DESCRIPTION"),
            ("lifecycle_status", "상태"),
        ],
        state_key="master_material_selected_code",
        button_prefix="master_material_code_",
    )

    selected = str(st.session_state.get("master_material_selected_code", "") or "").strip()
    if not selected:
        return
    st.divider()
    try:
        detail = _client().get_item_detail(selected, as_of.strftime("%Y-%m-%d"))
    except Exception as error:
        st.error(f"자재 상세조회 중 오류가 발생했습니다: {error}")
        return
    _render_detail(detail, "자재")


def render_master_query_page(view_type: str) -> None:
    if view_type == "BOM":
        render_bom_query_page()
    elif view_type == "모델":
        render_model_query_page()
    elif view_type == "자재":
        render_material_query_page()
    else:
        st.warning("지원하지 않는 Master 조회 유형입니다.")
