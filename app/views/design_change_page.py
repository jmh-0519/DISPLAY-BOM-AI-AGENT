from datetime import date

import pandas as pd
import streamlit as st

from app.views.bom_view import (
    render_bom_expandable_tree,
)
from app.views.bom_query_page import create_mcp_client


def get_status_label(
    status: str,
) -> str:
    status_map = {
        "PASS": "적합",
        "CONDITIONAL": "조건부 적합",
        "FAIL": "부적합",
        "UNKNOWN": "미확인",
    }

    normalized = str(
        status
    ).strip().upper()

    return status_map.get(
        normalized,
        str(status),
    )


def get_action_label(
    action: str,
) -> str:
    action_map = {
        "READY_FOR_NEXT_CHECK": "다음 검토 단계 진행 가능",
        "REVIEW_REQUIRED": "담당자 검토 필요",
        "CHANGE_BLOCKED": "설계변경 진행 불가",
        "PROCEED": "설계변경 진행 가능",
        "BLOCKED": "설계변경 진행 불가",
        "STOP": "설계변경 진행 불가",
    }

    normalized = str(
        action
    ).strip().upper()

    return action_map.get(
        normalized,
        str(action),
    )


def get_check_label(
    check: str,
) -> str:
    check_map = {
        "PRODUCT_EXISTS": "대상 모델 확인",
        "OLD_MATERIAL_IN_BOM": "기존 자재 BOM 확인",
        "NEW_MATERIAL_EXISTS": "신규 자재 확인",
        "NEW_MATERIAL_APPROVAL": "신규 자재 승인 상태",
        "NEW_MATERIAL_LIFECYCLE": "신규 자재 Lifecycle",
        "COMPATIBILITY": "자재 호환성",
        "RULE_VALIDATION": "BOM Rule 검증",
    }

    normalized = str(
        check
    ).strip().upper()

    return check_map.get(
        normalized,
        str(check),
    )


def render_design_change_analysis_result(
    result: dict,
    *,
    title: str = "분석 결과",
) -> str:
    """설계변경 메뉴와 AI Workflow가 공유하는 분석 결과 UI입니다."""
    st.subheader(title)
    result_status = str(result.get("result", "UNKNOWN")).strip().upper()

    if result_status == "PASS":
        st.success("설계변경 분석 결과가 적합합니다.")
    elif result_status == "CONDITIONAL":
        st.warning("조건부 적합입니다. 담당자 검토가 필요합니다.")
    else:
        st.error("부적합입니다. 설계변경을 진행할 수 없습니다.")

    summary_col1, summary_col2, summary_col3 = st.columns(3)
    summary_col1.metric(
        "변경 가능 여부",
        "가능" if result.get("changeable") else "불가",
    )
    summary_col2.metric("종합 판정", get_status_label(result_status))
    summary_col3.metric(
        "후속 조치",
        get_action_label(result.get("recommended_action", "")),
    )

    checks = result.get("checks", [])
    if checks:
        st.subheader("검증 상세")
        rows = [
            {
                "검증 항목": get_check_label(check.get("check", "")),
                "판정": get_status_label(check.get("status", "")),
                "검증 내용": check.get("message", ""),
            }
            for check in checks
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    warnings = result.get("warnings", [])
    if warnings:
        with st.expander("추가 검토 사항", expanded=False):
            for warning in warnings:
                st.warning(warning)

    blocking_reasons = result.get("blocking_reasons", [])
    if blocking_reasons:
        with st.expander("변경 차단 사유", expanded=True):
            for reason in blocking_reasons:
                st.error(reason)

    return result_status


@st.cache_resource
def create_design_change_services():
    """구형 별도 화면은 MCP Workflow 화면으로 통합되었습니다."""
    raise RuntimeError("AI 설계변경 Workflow 메뉴에서 MCP Tool을 사용하세요.")


def _reset_preview_if_input_changed(
    current_input: dict,
) -> None:
    """분석 입력이 변경되면 이전 Preview를 초기화합니다."""

    previous_input = (
        st.session_state.get(
            "dc_analysis_input"
        )
    )

    if (
        previous_input is not None
        and previous_input != current_input
    ):
        st.session_state.pop(
            "dc_preview_bom",
            None,
        )


def render_design_change_page() -> None:
    st.header("설계변경 분석")

    st.caption(
        "대상 모델의 자재 변경 가능 여부를 "
        "BOM 규칙, 자재 상태 및 호환성 기준으로 검증합니다."
    )

    (
        apply_service,
        design_change_service,
    ) = create_design_change_services()

    col1, col2 = st.columns(2)

    with col1:
        product_id = st.text_input(
            "모델 ID",
            value="LTA400HR01-0",
            key="dc_product_id",
        )

        old_material_id = st.text_input(
            "기존 자재",
            value="0001-200010",
            key="dc_old_material_id",
        )

    with col2:
        new_material_id = st.text_input(
            "신규 자재",
            value="9000-290004",
            key="dc_new_material_id",
        )

        as_of_date = st.date_input(
            "기준일",
            value=date.today(),
            key="dc_as_of_date",
        )

    current_input = {
        "product_id": product_id.strip(),
        "old_material_id": (
            old_material_id.strip()
        ),
        "new_material_id": (
            new_material_id.strip()
        ),
        "as_of_date": (
            as_of_date.strftime(
                "%Y-%m-%d"
            )
        ),
    }

    _reset_preview_if_input_changed(
        current_input
    )

    if st.button(
        "설계변경 분석",
        type="primary",
        width="stretch",
        key="dc_analyze",
    ):
        if not current_input["product_id"]:
            st.error(
                "모델 ID를 입력해 주세요."
            )
            return

        if not current_input[
            "old_material_id"
        ]:
            st.error(
                "기존 자재를 입력해 주세요."
            )
            return

        if not current_input[
            "new_material_id"
        ]:
            st.error(
                "신규 자재를 입력해 주세요."
            )
            return

        result = (
            design_change_service
            .analyze_replace(
                product_id=(
                    current_input[
                        "product_id"
                    ]
                ),
                old_material_id=(
                    current_input[
                        "old_material_id"
                    ]
                ),
                new_material_id=(
                    current_input[
                        "new_material_id"
                    ]
                ),
                as_of_date=(
                    current_input[
                        "as_of_date"
                    ]
                ),
            )
        )

        st.session_state[
            "dc_analysis_result"
        ] = result

        st.session_state[
            "dc_analysis_input"
        ] = current_input

        st.session_state.pop(
            "dc_preview_bom",
            None,
        )

    result = st.session_state.get(
        "dc_analysis_result"
    )

    if result is None:
        return

    st.divider()
    result_status = render_design_change_analysis_result(result)

    if result_status not in {
        "PASS",
        "CONDITIONAL",
    }:
        return

    st.divider()
    st.subheader(
        "설계변경 BOM 미리보기"
    )

    if st.button(
        "변경 BOM 미리보기",
        width="stretch",
        key="dc_preview",
    ):
        input_data = (
            st.session_state.get(
                "dc_analysis_input"
            )
        )

        if input_data is None:
            st.error(
                "먼저 설계변경 분석을 실행해 주세요."
            )
            return

        preview_bom = (
            apply_service
            .preview_replace(
                product_id=(
                    input_data[
                        "product_id"
                    ]
                ),
                old_material_id=(
                    input_data[
                        "old_material_id"
                    ]
                ),
                new_material_id=(
                    input_data[
                        "new_material_id"
                    ]
                ),
                as_of_date=(
                    input_data[
                        "as_of_date"
                    ]
                ),
            )
        )

        st.session_state[
            "dc_preview_bom"
        ] = preview_bom

    preview_bom = (
        st.session_state.get(
            "dc_preview_bom"
        )
    )

    if (
        preview_bom is not None
        and not preview_bom.empty
    ):
        render_bom_expandable_tree(
            preview_bom
        )

        st.info(
            "현재 BOM은 설계변경 검토를 위한 "
            "미리보기입니다. 실제 Production BOM에는 "
            "아직 반영되지 않았습니다."
        )
