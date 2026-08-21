from __future__ import annotations

import pandas as pd
import streamlit as st


def _display(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _flatten(scan: dict) -> list[dict]:
    rows: list[dict] = []
    for opportunity in scan.get("opportunities") or []:
        for candidate in opportunity.get("candidates") or []:
            rows.append({
                "현재 품목": opportunity.get("source_item_code"),
                "품목명": opportunity.get("source_item_name"),
                "유형": opportunity.get("target_type"),
                "Parent": opportunity.get("parent_item_code"),
                "후보 품목": candidate.get("candidate_item_code"),
                "후보명": candidate.get("candidate_item_name"),
                "기술 평가": candidate.get("technical_status"),
                "기술 점수": candidate.get("technical_score"),
                "현재 단가": opportunity.get("current_unit_price"),
                "후보 단가": candidate.get("candidate_unit_price"),
                "원가절감 확인": candidate.get("cost_reduction_status"),
                "단위 절감액": candidate.get("unit_savings"),
                "절감률(%)": candidate.get("savings_pct"),
                "공급 평가": candidate.get("supplier_status"),
            })
    return rows


def render_product_cost_scan(scan: dict) -> None:
    if not scan:
        return
    st.markdown("### 제품 BOM 원가절감 후보 탐색")
    st.caption(
        f"제품: {scan.get('version_code')} · PLANT: {scan.get('plant_code')} · "
        f"기준일: {scan.get('as_of_date')} · Request 미생성"
    )

    cols = st.columns(4)
    cols[0].metric("탐색 BOM 품목", int(scan.get("scanned_source_count") or 0))
    cols[1].metric("대체 후보 존재 품목", int(scan.get("opportunity_source_count") or 0))
    cols[2].metric("기술 대체 가능 후보", int(scan.get("technical_eligible_candidate_count") or 0))
    cols[3].metric("원가절감 확인 후보", int(scan.get("confirmed_cost_reduction_candidate_count") or 0))

    confirmed = int(scan.get("confirmed_cost_reduction_candidate_count") or 0)
    unverified = int(scan.get("cost_unverified_candidate_count") or 0)
    if confirmed == 0 and unverified:
        st.warning(
            "기술적으로 대체 가능한 후보는 존재하지만 현재품 또는 후보의 비교 가능한 단가 근거가 부족하여 "
            "실제 원가절감 여부는 아직 확정할 수 없습니다. 후보를 임의로 '저원가'라고 판단하지 않습니다."
        )
    elif confirmed:
        st.success(f"현재 등록된 단가 근거로 원가절감이 확인된 후보가 {confirmed}건 있습니다.")

    excluded_names = scan.get("excluded_item_names") or []
    excluded_codes = scan.get("excluded_item_codes") or []
    if excluded_names or excluded_codes:
        values = [*excluded_names, *excluded_codes]
        st.caption("탐색 제외: " + ", ".join(str(value) for value in values))

    rows = _flatten(scan)
    if not rows:
        st.info("기술적으로 PASS 또는 CONDITIONAL인 대체 후보를 찾지 못했습니다.")
        return

    frame = pd.DataFrame([
        {key: _display(value) for key, value in row.items()}
        for row in rows
    ])
    st.dataframe(frame, width="stretch", hide_index=True)
    st.caption(
        "`CONFIRMED`는 현재품과 후보의 단가 근거가 모두 있어 절감이 계산된 경우입니다. "
        "`UNAVAILABLE`은 기술 대체 후보이지만 원가 비교 근거가 부족한 상태입니다. "
        "원하는 현재 품목/후보 코드를 지정하면 해당 조합으로 정식 Analysis Session을 시작할 수 있습니다."
    )
