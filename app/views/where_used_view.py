from __future__ import annotations

import pandas as pd
import streamlit as st


def render_where_used_result(result: dict) -> None:
    """역방향 BOM(Where-used) 결과를 공통 UI로 표시합니다."""
    if not isinstance(result, dict):
        st.warning("역방향 BOM 조회 결과를 표시할 수 없습니다.")
        return

    item = result.get("item") or {}
    item_code = result.get("item_code") or item.get("item_code") or "-"
    plant_code = result.get("plant_code") or "-"
    plant_name = result.get("plant_name") or "-"
    rows = list(result.get("where_used") or [])

    st.subheader("역방향 BOM 조회")
    st.markdown(f"**PLANT:** `{plant_code}` · {plant_name}")
    st.markdown(
        f"**조회 자재:** `{item_code}` · {item.get('item_name') or '-'} "
        f"({item.get('item_type') or '-'})"
    )

    if not rows:
        st.info(result.get("message") or "해당 품목은 현재 BOM에 구성되어 있지 않습니다.")
        return

    direct = pd.DataFrame(result.get("direct_parents") or [])
    if not direct.empty:
        st.markdown("#### 직접 상위 품목")
        direct = direct.rename(columns={
            "item_code": "상위 코드",
            "item_name": "상위 품목명",
            "description": "DESCRIPTION",
            "item_type": "유형",
            "location": "LOCATION",
            "quantity": "BOM 수량",
        })
        st.dataframe(direct, use_container_width=True, hide_index=True)

    models = pd.DataFrame(result.get("top_models") or [])
    if not models.empty:
        st.markdown("#### 최상위 MODEL")
        models = models.rename(columns={
            "model_code": "MODEL 코드",
            "model_name": "MODEL 명",
            "description": "DESCRIPTION",
            "path": "BOM 경로",
        })
        st.dataframe(models, use_container_width=True, hide_index=True)

    st.markdown("#### 상위 BOM 경로")
    path_rows = []
    for row in rows:
        path_rows.append({
            "Level": row.get("level"),
            "하위 코드": row.get("child_item_code"),
            "하위 품목명": row.get("child_item_name"),
            "상위 코드": row.get("parent_item_code"),
            "상위 품목명": row.get("parent_item_name"),
            "상위 유형": row.get("parent_item_type"),
            "LOCATION": row.get("location_code"),
            "수량": row.get("quantity"),
            "경로": row.get("bom_path"),
        })
    st.dataframe(pd.DataFrame(path_rows), use_container_width=True, hide_index=True)
