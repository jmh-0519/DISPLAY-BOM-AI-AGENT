from __future__ import annotations

import pandas as pd
import streamlit as st

from agents.design_change_workflow_state import apply_phase3_tool_result
from mcp_client.client import DisplayBomMcpClient
from app.views.design_change_history_page import render_phase3_request_detail


ANALYSIS_STEPS = {
    "ANALYSIS_READY",
    "ANALYSIS_REVALIDATED",
    "ANALYSIS_IMPACT_REVIEW",
    "ANALYSIS_CONFIRMED",
    # Backward-compatible pre-STEP34 request-first states:
    "REQUESTED", "CANDIDATES_EVALUATED", "WAITING_CANDIDATE_APPROVAL",
    "CONDITIONAL_REVIEW_REQUIRED", "IMPACT_REVIEW_REQUIRED",
}

WORKFLOW_STEPS = {
    "CANDIDATE_APPROVED",
    "WAITING_FINAL_APPROVAL",
    "FINAL_APPROVED",
    "APPLIED",
    "REPORT_COMPLETED",
    "BLOCKED",
}


def _dom_token(value) -> str:
    raw = str(value or "na")
    return "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-") or "na"


def _candidate_selection_anchor(workflow: dict) -> str:
    context_id = workflow.get("analysis_id") or workflow.get("request_id") or "analysis"
    return f"phase3-candidate-selection-{_dom_token(context_id)}"


def _revalidation_input_anchor(workflow: dict, action_id, candidate_code) -> str:
    context_id = workflow.get("analysis_id") or workflow.get("request_id") or "analysis"
    return (
        f"phase3-revalidation-input-{_dom_token(context_id)}-"
        f"{_dom_token(action_id)}-{_dom_token(candidate_code)}"
    )


def _revalidation_result_anchor(workflow: dict, index: int) -> str:
    context_id = workflow.get("analysis_id") or workflow.get("request_id") or "analysis"
    return f"phase3-revalidation-result-{_dom_token(context_id)}-{index}"


def _render_anchor(anchor_id: str) -> None:
    st.markdown(
        f'<div id="{anchor_id}" style="scroll-margin-top: 18px; height: 1px;"></div>',
        unsafe_allow_html=True,
    )


def _schedule_scroll(anchor_id: str) -> None:
    # The target can legitimately be the same on consecutive clicks.  Keep a
    # monotonically increasing event id so Streamlit receives a different iframe
    # payload every time and re-executes the scroll script.
    event_id = int(st.session_state.get("phase3_scroll_event_seq", 0)) + 1
    st.session_state["phase3_scroll_event_seq"] = event_id
    st.session_state["phase3_scroll_target"] = {
        "anchor_id": anchor_id,
        "event_id": event_id,
    }


def _render_pending_scroll() -> None:
    pending = st.session_state.pop("phase3_scroll_target", None)
    if not pending:
        return

    # Backward compatibility for sessions created by STEP35-B.
    if isinstance(pending, str):
        target = pending
        event_id = int(st.session_state.get("phase3_scroll_event_seq", 0)) + 1
        st.session_state["phase3_scroll_event_seq"] = event_id
    else:
        target = pending.get("anchor_id")
        event_id = pending.get("event_id")
    if not target:
        return

    # st.iframe accepts trusted raw HTML and allows same-origin JavaScript.  The
    # event id is embedded deliberately: even when targetId is unchanged, the
    # HTML payload changes and the script runs again on every click.
    st.iframe(
        f"""
        <script>
        const navigationEventId = {event_id!r};
        const targetId = {target!r};
        const scrollToTarget = () => {{
            const element = window.parent.document.getElementById(targetId);
            if (element) {{
                element.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                return true;
            }}
            return false;
        }};
        [0, 80, 180, 350, 700].forEach((delay) => {{
            setTimeout(scrollToTarget, delay);
        }});
        </script>
        """,
        height=1,
        width=1,
        tab_index=-1,
    )


def candidate_rows(workflow: dict) -> list[dict]:
    """Return comparison-friendly candidate rows without exposing internal JSON.

    Recommendation ranking is deliberately separated from evaluation status.
    A candidate receives a visible score/grade/rank only after its technical
    suitability is PASS. CONDITIONAL therefore means "evaluation pending",
    never a low-scoring recommendation.
    """
    rows = []
    reason_codes = _candidate_reason_codes(workflow)
    for candidate in workflow.get("candidates", []):
        supplier_eval = candidate.get("supplier_evaluation") or {}
        supplier = supplier_eval.get("recommended") or {}
        inventory = candidate.get("inventory") or {}
        reasons = candidate.get("decision_reasons") or []
        missing_data = list(candidate.get("missing_data", []))
        technical_status = str(candidate.get("technical_status") or candidate.get("status") or "").upper()
        ranking_score = candidate.get("ranking_score") if technical_status == "PASS" else None
        ranking_grade = candidate.get("ranking_grade") if technical_status == "PASS" else None
        ranking_rank = candidate.get("rank") if technical_status == "PASS" and ranking_score is not None else None
        rows.append({
            "action_id": candidate.get("action_id"),
            "candidate_id": candidate.get("candidate_id"),
            "supplier_item_id": supplier.get("supplier_item_id"),
            "rank": ranking_rank,
            "candidate_item_code": candidate.get("candidate_item_code"),
            "candidate_name": candidate.get("candidate_name"),
            "candidate_description": candidate.get("candidate_description"),
            "status": candidate.get("status"),
            "technical_status": candidate.get("technical_status"),
            "score": ranking_score,
            "grade": ranking_grade,
            "evaluation_mode": candidate.get("evaluation_mode"),
            "decision_reasons": " / ".join(str(value) for value in reasons),
            "evaluation_reasons": " · ".join(reason_codes) or "-",
            "supplier_code": supplier.get("supplier_code"),
            "supplier_name": supplier.get("supplier_name"),
            "supplier_status": candidate.get("supplier_status"),
            "unit_price": supplier.get("unit_price"),
            "lead_time_days": supplier.get("lead_time_days"),
            "quality_grade": supplier.get("quality_grade"),
            "inventory_status": candidate.get("inventory_status") or inventory.get("status"),
            "available_quantity": inventory.get("available_quantity"),
            "bom_quantity": (candidate.get("demand") or {}).get("bom_quantity")
                if (candidate.get("demand") or {}).get("bom_quantity") is not None
                else inventory.get("demand_quantity"),
            "shortage_quantity": inventory.get("shortage_quantity"),
            "quantity_basis": (candidate.get("demand") or {}).get("source") or "BOM_QUANTITY",
            "missing_data": ", ".join(str(value) for value in missing_data),
        })
    return rows


def candidate_missing_attributes(candidate: dict) -> list[str]:
    """Return only attributes that can be supplied to revalidate a candidate."""
    missing: list[str] = []
    for rule in candidate.get("rule_results") or []:
        evidence = rule.get("evidence") or {}
        for condition in evidence.get("conditions") or []:
            if (
                condition.get("status") == "CONDITIONAL"
                and condition.get("present") is False
                and condition.get("attribute")
            ):
                missing.append(str(condition["attribute"]))
    for result in candidate.get("attribute_results") or []:
        if result.get("status") == "CONDITIONAL" and result.get("attribute"):
            missing.append(str(result["attribute"]))
    return list(dict.fromkeys(missing))


def impact_rows(workflow: dict) -> list[dict]:
    return [{
        "plant_code": row.get("plant_code") or workflow.get("plant_code"),
        "item_code": row.get("impacted_item_code"),
        "impact_type": row.get("impact_type"),
        "impact_path": row.get("impact_path"),
    } for row in workflow.get("impacts", [])]


def _style_change_frame(frame: pd.DataFrame):
    """Highlight before/after values consistently across Analysis and Request UI."""
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


def preview_model_rows(workflow: dict, client: DisplayBomMcpClient | None = None) -> list[dict]:
    """Return only top-level impacted MODELs for the final Preview UI.

    Full TARGET/PARENT_ASSY hierarchy remains persisted in workflow["impacts"] for
    audit/reporting.  The interactive workflow deliberately shows only the final
    VERSION/MODEL scope so users do not need to inspect the entire ancestor path.
    """
    model_codes: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    default_plant = str(workflow.get("plant_code") or "").strip()
    for row in workflow.get("impacts", []) or []:
        impact_type = str(row.get("impact_type") or "").upper()
        if impact_type not in {"MODEL", "MODEL_CONNECTION"}:
            continue
        code = str(row.get("impacted_item_code") or "").strip()
        plant = str(row.get("plant_code") or default_plant).strip()
        if code and (plant, code) not in seen:
            seen.add((plant, code))
            model_codes.append((plant, code))

    # ADD or a direct VERSION-parent action can legitimately produce only a TARGET
    # impact.  In that case the request's version is already the top-level model.
    if not model_codes:
        version_code = str(
            workflow.get("version_code")
            or (workflow.get("analysis_context") or {}).get("version_code")
            or (workflow.get("request_context") or {}).get("version_code")
            or ""
        ).strip()
        if not version_code and client is not None and workflow.get("request_id"):
            try:
                request_detail = client.get_change_request_result(workflow["request_id"])
            except Exception:
                request_detail = {}
            version_code = str(request_detail.get("version_code") or "").strip()
            default_plant = str(request_detail.get("plant_code") or default_plant).strip()
        if version_code:
            model_codes.append((default_plant, version_code))

    rows: list[dict] = []
    product_cache: dict[str, dict] = {}
    for plant, code in model_codes:
        product: dict = {}
        if client is not None:
            if code not in product_cache:
                try:
                    matches = client.search_product(code)
                except Exception:
                    matches = []
                exact = next(
                    (item for item in matches if str(item.get("product_id") or "") == code),
                    None,
                )
                product_cache[code] = dict(exact or (matches[0] if matches else {}))
            product = product_cache[code]
        rows.append({
            "PLANT": plant or "-",
            "최상위 MODEL": code,
            "MODEL 정보": product.get("product_name") or "-",
            "상태": product.get("status") or "-",
        })
    return rows


def impact_model_rows(workflow: dict) -> list[dict]:
    review = workflow.get("impact_review") or {}
    return [{
        "PLANT": row.get("plant_code"),
        "영향 모델": row.get("model_code"),
        "모델명": row.get("model_name"),
        "DESCRIPTION": row.get("model_description"),
        "공용 ASSY": row.get("parent_item_code"),
        "ASSY명": row.get("parent_name"),
        "영향 경로": row.get("impact_path"),
        "변경 Spec 수": sum(
            len(value.get("changed_specs") or [])
            for value in row.get("action_impacts", [])
        ) if row.get("action_impacts") else row.get("changed_spec_count", 0),
    } for row in review.get("impacted_models", [])]


def impact_spec_rows(workflow: dict, changed_only: bool = False) -> list[dict]:
    review = workflow.get("impact_review") or {}
    rows = []
    model_impacts = review.get("model_spec_impacts") or []
    if model_impacts:
        for impact in model_impacts:
            specs = impact.get("spec_changes") or []
            for spec in specs:
                if changed_only and spec.get("change_status") == "SAME":
                    continue
                rows.append({
                    "영향 모델": impact.get("model_code"),
                    "PLANT": impact.get("plant_code"),
                    "공용 ASSY": impact.get("parent_item_code"),
                    "변경 대상": impact.get("old_item_code"),
                    "변경 후": impact.get("new_item_code"),
                    "Spec 항목": spec.get("attribute"),
                    "변경 전": spec.get("before"),
                    "변경 후 값": spec.get("after"),
                    "변경 여부": spec.get("change_status"),
                })
        return rows

    # Backward-compatible fallback for pre-STEP32 impact payloads.
    for action in review.get("actions", []):
        for spec in action.get("spec_changes", []):
            if changed_only and spec.get("change_status") == "SAME":
                continue
            rows.append({
                "영향 모델": None,
                "PLANT": review.get("plant_code") or workflow.get("plant_code"),
                "공용 ASSY": action.get("parent_item_code"),
                "변경 대상": action.get("old_item_code"),
                "변경 후": action.get("new_item_code"),
                "Spec 항목": spec.get("attribute"),
                "변경 전": spec.get("before"),
                "변경 후 값": spec.get("after"),
                "변경 여부": spec.get("change_status"),
            })
    return rows


def is_workflow_visible(workflow: dict) -> bool:
    return workflow.get("current_step") in WORKFLOW_STEPS


def available_action(workflow: dict) -> str | None:
    step = workflow.get("current_step")
    if step == "CANDIDATE_APPROVED" and workflow.get("requires_exception"):
        return "EXCEPTION_APPROVAL"
    return {
        "WAITING_CANDIDATE_APPROVAL": "CANDIDATE_SELECTION",
        "CONDITIONAL_REVIEW_REQUIRED": "CONDITIONAL_REVIEW",
        "IMPACT_REVIEW_REQUIRED": "IMPACT_APPROVAL",
        "CANDIDATE_APPROVED": "CREATE_PREVIEW",
        "WAITING_FINAL_APPROVAL": "FINAL_APPROVAL",
        "FINAL_APPROVED": "APPLY",
        "APPLIED": "REPORT",
    }.get(step)


def _complete_workflow_action(
    workflow: dict,
    tool_name: str,
    tool_result: dict,
    success_message: str,
    on_workflow_update=None,
    scroll_target: str | None = None,
) -> None:
    updated = apply_phase3_tool_result(
        tool_name,
        workflow,
        tool_result,
    )
    workflow.clear()
    workflow.update(updated)
    if on_workflow_update is not None:
        on_workflow_update(updated)
    st.session_state["phase3_workflow_notice"] = {
        "context_id": updated.get("request_id") or updated.get("analysis_id"),
        "message": success_message,
    }
    if scroll_target:
        _schedule_scroll(scroll_target)
    st.rerun()


def _current_status_label(target: dict) -> str:
    status_fields = target.get("status_fields") or {}
    for key in ("lifecycle_status", "supply_status", "quality_status"):
        if status_fields.get(key):
            return f"{key}={status_fields[key]}"
    return "ACTIVE" if target.get("active_yn") == "Y" else "INACTIVE"


def _reason_evidence_summary(context: dict, target: dict) -> str:
    """Summarize user-reason evidence without treating user language as DB fact."""
    reasons = list(dict.fromkeys(
        context.get("reason_codes")
        or ([context.get("reason_code")] if context.get("reason_code") else [])
    ))
    status_fields = target.get("status_fields") or {}
    messages: list[str] = []
    for reason in reasons:
        if reason == "EOL":
            lifecycle = status_fields.get("lifecycle_status")
            if lifecycle:
                suffix = "확인" if str(lifecycle).upper() == "EOL" else "불일치 · 확인 필요"
                messages.append(f"EOL: DB lifecycle_status={lifecycle} ({suffix})")
            else:
                current = "ACTIVE" if target.get("active_yn") == "Y" else "INACTIVE"
                messages.append(
                    f"EOL: 사용자 입력 / DB lifecycle_status 미등록 (현재 {current}) · 확인 필요"
                )
        elif reason == "COST":
            messages.append("COST: 후보별 공급사·단가 데이터로 평가")
        elif reason == "SUPPLIER_STOP":
            supply = status_fields.get("supply_status")
            messages.append(
                f"SUPPLIER_STOP: DB supply_status={supply}" if supply
                else "SUPPLIER_STOP: 사용자 입력 / DB supply_status 확인 필요"
            )
        elif reason == "QUALITY":
            quality = status_fields.get("quality_status")
            messages.append(
                f"QUALITY: DB quality_status={quality}" if quality
                else "QUALITY: 사용자 입력 / DB quality_status 확인 필요"
            )
    return " / ".join(messages) or "-"


def _display_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if value != value:  # NaN
            return "-"
        return f"{value:g}"
    return str(value)


def _display_df(rows: list[dict]) -> pd.DataFrame:
    """Return a presentation-only DataFrame with Arrow-safe string columns."""
    return pd.DataFrame([
        {key: _display_value(value) for key, value in row.items()}
        for row in rows
    ])


def _render_target_summary(workflow: dict, *, context_override: dict | None = None) -> None:
    context = context_override or workflow.get("analysis_context") or {}
    target = context.get("target_item") or {}
    parent = context.get("parent_item") or {}
    if not target:
        return

    st.markdown("#### 변경 대상 품목")
    rows = [
        {"항목": "PLANT", "값": context.get("plant_code")},
        {"항목": "제품", "값": context.get("version_code")},
        {"항목": "품목 유형", "값": context.get("target_type")},
        {"항목": "품목 코드", "값": target.get("item_code")},
        {"항목": "품목명", "값": target.get("item_name")},
        {"항목": "DESCRIPTION", "값": target.get("description")},
        {"항목": "현재 상태", "값": ("신규 추가 대상" if context.get("action_type") == "ADD" and not target.get("item_code") else _current_status_label(target))},
        {"항목": "공용/단독", "값": target.get("usage_type") or "미확인"},
        {"항목": "직접 Parent", "값": parent.get("item_code")},
        {"항목": "Parent DESCRIPTION", "값": parent.get("description")},
        {"항목": "Parent 공용/단독", "값": parent.get("usage_type") or "미확인"},
        {"항목": "LOCATION", "값": context.get("location_code")},
        {"항목": "현재 수량", "값": context.get("old_quantity")},
        {"항목": "변경 후 수량", "값": context.get("new_quantity")},
        {"항목": "변경 유형", "값": context.get("action_type")},
        {"항목": "Primary Reason", "값": context.get("primary_reason_code") or context.get("reason_code")},
        {"항목": "Secondary Reasons", "값": ", ".join(context.get("secondary_reason_codes") or []) or "-"},
        {"항목": "평가 사유 전체", "값": ", ".join(context.get("reason_codes") or ([context.get("reason_code")] if context.get("reason_code") else [])) or "-"},
        {"항목": "변경사유 Evidence", "값": _reason_evidence_summary(context, target)},
    ]
    # The target summary is intentionally rendered as a static table.
    # It is short business context and must be visible without an inner scrollbar.
    st.table(_display_df(rows).style.hide(axis="index"))


def _candidate_reason_codes(workflow: dict) -> list[str]:
    context = workflow.get("analysis_context") or {}
    return list(dict.fromkeys(
        context.get("reason_codes")
        or ([context.get("reason_code")] if context.get("reason_code") else [])
    ))


def _candidate_decision_summary(row: dict) -> str:
    """Return a short evidence-derived final-decision comment for the comparison table."""
    final_status = str(row.get("status") or "").upper()
    technical = str(row.get("technical_status") or "").upper()
    supplier = str(row.get("supplier_status") or "").upper()
    inventory = str(row.get("inventory_status") or "").upper()
    missing = [value.strip() for value in str(row.get("missing_data") or "").split(",") if value.strip()]

    if final_status == "FAIL":
        causes = []
        if technical == "FAIL":
            causes.append("필수 기술 사양 불일치")
        if supplier == "FAIL":
            causes.append("공급 조건 실패")
        if inventory == "FAIL":
            causes.append("BOM 수량 대비 가용재고 부족")
        return " · ".join(causes) + "로 대체 불가" if causes else "필수 평가조건 실패로 대체 불가"

    if final_status == "CONDITIONAL":
        needs = []
        if technical == "CONDITIONAL":
            needs.append("기술 데이터")
        if supplier == "CONDITIONAL":
            if any(value in {"supplier_options", "unit_price"} for value in missing):
                needs.append("공급사/원가 데이터")
            else:
                needs.append("공급 조건")
        if inventory == "CONDITIONAL":
            needs.append("재고 데이터")
        needs = list(dict.fromkeys(needs))
        prefix = "기술 사양은 적합하나 " if technical == "PASS" else ""
        return prefix + ("·".join(needs) + " 확인 필요" if needs else "추가 확인 데이터가 있어 조건부 적합")

    if final_status == "PASS":
        return "기술·공급·재고 필수조건 충족"
    return "평가 근거 확인 필요"


def _candidate_display_frame(rows: list[dict]) -> pd.DataFrame:
    display_rows = []
    for row in rows:
        display_rows.append({
            "순위": row.get("rank") if row.get("rank") is not None else "-",
            "후보 코드": row.get("candidate_item_code"),
            "품목명": row.get("candidate_name"),
            "DESCRIPTION": row.get("candidate_description"),
            "종합 적합성": row.get("status"),
            "종합 판단 요약": row.get("decision_summary") or _candidate_decision_summary(row),
            "평가 사유": row.get("evaluation_reasons") or "-",
            "기술 평가": row.get("technical_status"),
            "추천 점수": row.get("score") if row.get("score") is not None else "평가 보류",
            "추천등급": row.get("grade") or "-",
            "상세 판단 근거": row.get("decision_reasons"),
            "주 공급사": row.get("supplier_name") or row.get("supplier_code"),
            "공급 평가": row.get("supplier_status"),
            "단가(KRW)": row.get("unit_price"),
            "납기(일)": row.get("lead_time_days"),
            "공급사 품질등급": row.get("quality_grade"),
            "재고 평가": row.get("inventory_status"),
            "BOM 수량": row.get("bom_quantity"),
            "가용재고": row.get("available_quantity"),
            "부족수량": row.get("shortage_quantity"),
            "보완 필요 데이터": row.get("missing_data") or "-",
            "평가방식": row.get("evaluation_mode"),
        })
    return pd.DataFrame(display_rows)


def _render_candidate_tables(rows: list[dict]) -> None:
    if not rows:
        st.warning("검색된 대체 후보가 없습니다.")
        return
    passed = [row for row in rows if row.get("status") == "PASS"]
    conditional = [row for row in rows if row.get("status") == "CONDITIONAL"]
    failed = [row for row in rows if row.get("status") == "FAIL"]

    st.markdown("#### 후보 평가 결과")
    if passed:
        st.markdown(f"**추천 가능 후보 (PASS) · {len(passed)}건**")
        st.dataframe(_candidate_display_frame(passed), width="stretch", hide_index=True)
    else:
        st.info("현재 기술·업무 기준을 모두 통과하여 추천 순위를 산출할 수 있는 PASS 후보가 없습니다.")

    if conditional:
        st.markdown(f"**평가 보류 후보 (CONDITIONAL) · {len(conditional)}건**")
        st.caption("필수 기술 Evidence가 확인되기 전에는 추천 점수·추천등급·순위를 산출하지 않습니다. 기준정보 보완 후 재검증하세요.")
        st.dataframe(_candidate_display_frame(conditional), width="stretch", hide_index=True)

    if failed:
        with st.expander(f"검토 제외 후보 (FAIL) · {len(failed)}건", expanded=not passed and not conditional):
            st.dataframe(_candidate_display_frame(failed), width="stretch", hide_index=True)


def _render_analysis_metrics(workflow: dict, rows: list[dict], *, context_override: dict | None = None) -> None:
    if not rows:
        return
    counts = {
        status: sum(row.get("status") == status for row in rows)
        for status in ("PASS", "CONDITIONAL", "FAIL")
    }
    context = context_override or workflow.get("analysis_context") or {}
    cols = st.columns(5)
    cols[0].metric("검색 후보", len(rows))
    cols[1].metric("추천 가능", counts["PASS"])
    cols[2].metric("평가 보류", counts["CONDITIONAL"])
    cols[3].metric("검토 제외", counts["FAIL"])
    bom_quantity = context.get("new_quantity") if context.get("action_type") in {"ADD", "QUANTITY_CHANGE"} else context.get("old_quantity")
    cols[4].metric("BOM 수량", bom_quantity if bom_quantity is not None else "-")


def _required_candidate_actions(workflow: dict) -> list[dict]:
    return [
        action for action in workflow.get("actions", [])
        if action.get("action_type") in {"REPLACE", "ADD"}
    ]


def _selection_review_frame(workflow: dict, selected_rows: list[dict]) -> pd.DataFrame:
    context = workflow.get("analysis_context") or {}
    target = context.get("target_item") or {}
    rows = []
    for row in selected_rows:
        rows.append({
            "변경 대상": target.get("item_code") or context.get("old_item_code") or "-",
            "현재 DESCRIPTION": target.get("description") or target.get("specification") or "-",
            "선택 후보": row.get("candidate_item_code"),
            "후보 DESCRIPTION": row.get("candidate_description") or "-",
            "종합 적합성": row.get("status"),
            "종합 판단 요약": _candidate_decision_summary(row),
            "평가 사유": row.get("evaluation_reasons") or "-",
            "기술 평가": row.get("technical_status"),
            "추천 점수": row.get("score") if row.get("score") is not None else "평가 보류",
            "추천등급": row.get("grade") or "-",
            "주 공급사": row.get("supplier_name") or row.get("supplier_code") or "미등록",
            "단가(KRW)": row.get("unit_price"),
            "납기(일)": row.get("lead_time_days"),
            "재고 평가": row.get("inventory_status"),
            "BOM 수량": row.get("bom_quantity"),
            "가용재고": row.get("available_quantity"),
        })
    return pd.DataFrame(rows)


def _selected_candidate_missing_requirements(row: dict) -> list[str]:
    values = [
        value.strip() for value in str(row.get("missing_data") or "").split(",")
        if value.strip()
    ]
    return list(dict.fromkeys(values))


def _analysis_payload(workflow: dict) -> dict:
    return {
        "analysis_id": workflow.get("analysis_id"),
        "request": dict(workflow.get("analysis_request") or {}),
        "actions": [dict(value) for value in workflow.get("actions", [])],
        "candidates": [dict(value) for value in workflow.get("candidates", [])],
        "analysis_context": workflow.get("analysis_context"),
    }


def _render_selection_review_responsive(workflow: dict, selected_rows: list[dict]) -> None:
    context = workflow.get("analysis_context") or {}
    target = context.get("target_item") or {}
    for index, row in enumerate(selected_rows, start=1):
        st.markdown(f"##### 선택 후보 {index} 재확인")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**변경 대상**")
            st.table(_display_df([
                {"항목": "품목 코드", "값": target.get("item_code") or "-"},
                {"항목": "DESCRIPTION", "값": target.get("description") or target.get("specification") or "-"},
                {"항목": "평가 사유", "값": row.get("evaluation_reasons") or "-"},
            ]))
        with col2:
            st.markdown("**선택 후보**")
            st.table(_display_df([
                {"항목": "후보 코드", "값": row.get("candidate_item_code") or "-"},
                {"항목": "품목명", "값": row.get("candidate_name") or "-"},
                {"항목": "DESCRIPTION", "값": row.get("candidate_description") or "-"},
                {"항목": "종합 적합성", "값": row.get("status") or "-"},
                {"항목": "기술 평가", "값": row.get("technical_status") or "-"},
                {"항목": "공급 평가", "값": row.get("supplier_status") or "-"},
                {"항목": "재고 평가", "값": row.get("inventory_status") or "-"},
                {"항목": "BOM 수량", "값": row.get("bom_quantity")},
                {"항목": "가용재고", "값": row.get("available_quantity")},
                {
                    "항목": "추천 점수 / 추천등급",
                    "값": (
                        f"{row.get('score')} / {row.get('grade')}"
                        if row.get("score") is not None
                        else "평가 보류 / -"
                    ),
                },
            ]))
        st.markdown("**종합 판단 요약**")
        st.info(_candidate_decision_summary(row))
        st.table(_display_df([{
            "주 공급사": row.get("supplier_name") or row.get("supplier_code") or "미등록",
            "단가(KRW)": row.get("unit_price"),
            "납기(일)": row.get("lead_time_days"),
            "재고 평가": row.get("inventory_status"),
            "BOM 수량": row.get("bom_quantity"),
            "가용재고": row.get("available_quantity"),
        }]))
        raw_candidate = next((
            value for value in workflow.get("candidates", [])
            if value.get("action_id") == row.get("action_id")
            and value.get("candidate_item_code") == row.get("candidate_item_code")
        ), {})
        evidence_rows = []
        for rule_result in raw_candidate.get("rule_results") or []:
            evidence = rule_result.get("evidence") or {}
            for condition in evidence.get("conditions") or []:
                evidence_rows.append({
                    "구분": "RULE",
                    "평가 항목": condition.get("attribute"),
                    "후보 값": condition.get("actual"),
                    "기준": f"{condition.get('operator') or '-'} {condition.get('expected') if condition.get('expected') is not None else '-'}",
                    "결과": condition.get("status"),
                })
        for attr_result in raw_candidate.get("attribute_results") or []:
            evidence_rows.append({
                "구분": "ATTRIBUTE",
                "평가 항목": attr_result.get("attribute"),
                "후보 값": attr_result.get("candidate_value"),
                "기준": attr_result.get("source_value"),
                "결과": attr_result.get("status"),
            })
        if evidence_rows:
            with st.expander("선택 후보 기술/Rule 상세", expanded=False):
                st.dataframe(_display_df(evidence_rows), hide_index=True, width="stretch")


def _render_revalidation_history(workflow: dict) -> None:
    history = workflow.get("revalidation_history") or []
    if not history:
        return
    st.markdown("#### 재검증 결과")
    for index, item in enumerate(history, start=1):
        before = item.get("before") or {}
        after = item.get("after") or {}
        action_id = item.get("action_id")
        candidate_code = item.get("candidate_item_code")
        _render_anchor(_revalidation_result_anchor(workflow, index))
        st.markdown(f"**재검증 {index} · {candidate_code}**")
        rows = []
        for label, key in (
            ("종합 적합성", "status"), ("기술 평가", "technical_status"),
            ("공급 평가", "supplier_status"), ("재고 평가", "inventory_status"),
            ("추천 점수", "ranking_score"), ("추천등급", "ranking_grade"),
        ):
            before_value = before.get(key)
            after_value = after.get(key)
            if key == "ranking_score":
                before_value = before_value if before_value is not None else "평가 보류"
                after_value = after_value if after_value is not None else "평가 보류"
            elif key == "ranking_grade":
                before_value = before_value or "-"
                after_value = after_value or "-"
            rows.append({"항목": label, "재검증 전": before_value, "재검증 후": after_value})
        before_inv = before.get("inventory") or {}
        after_inv = after.get("inventory") or {}
        before_demand = before.get("demand") or {}
        after_demand = after.get("demand") or {}
        rows.append({
            "항목": "BOM 수량",
            "재검증 전": before_demand.get("bom_quantity", before_inv.get("demand_quantity")),
            "재검증 후": after_demand.get("bom_quantity", after_inv.get("demand_quantity")),
        })
        for label, key in (("가용재고", "available_quantity"), ("부족수량", "shortage_quantity")):
            rows.append({"항목": label, "재검증 전": before_inv.get(key), "재검증 후": after_inv.get(key)})
        st.table(_display_df(rows))
        if after.get("status") == "FAIL":
            st.error("재검증 결과 필수조건을 충족하지 못해 이 후보는 설계변경 진행 대상으로 선택할 수 없습니다.")
        elif after.get("status") == "CONDITIONAL":
            st.warning("재검증 후에도 추가 확인이 필요한 CONDITIONAL 상태입니다.")
        else:
            st.success("재검증 결과 PASS 상태입니다.")

        nav_col1, nav_col2 = st.columns(2)
        with nav_col1:
            if st.button(
                "후보 다시 선택",
                key=f"goto_candidate_selection_{(workflow.get('analysis_id') or workflow.get('request_id'))}_{index}",
                use_container_width=True,
            ):
                _schedule_scroll(_candidate_selection_anchor(workflow))
                st.rerun()
        with nav_col2:
            if st.button(
                "이 후보 조건 다시 수정",
                key=f"goto_revalidation_input_{(workflow.get('analysis_id') or workflow.get('request_id'))}_{index}",
                use_container_width=True,
            ):
                context_id = workflow.get("analysis_id") or workflow.get("request_id")
                if action_id and candidate_code:
                    # The selectbox was already instantiated earlier in this run, so do not
                    # mutate its widget key here. Store a pending navigation command and
                    # apply it before the selectbox is created on the next rerun.
                    st.session_state["phase3_pending_candidate_navigation"] = {
                        "context_id": context_id,
                        "action_id": action_id,
                        "candidate_item_code": candidate_code,
                    }
                    _schedule_scroll(_revalidation_input_anchor(workflow, action_id, candidate_code))
                else:
                    _schedule_scroll(_candidate_selection_anchor(workflow))
                st.rerun()

def _render_selected_candidate_revalidation(
    workflow: dict,
    selected_rows: list[dict],
    client: DisplayBomMcpClient,
    on_workflow_update,
) -> None:
    """Revalidate CONDITIONAL/FAIL candidates from persisted master/BOM data only.

    STEP40-C intentionally removes ad-hoc attribute and requested-demand inputs.
    Candidate suitability is re-read from Rule/Item/Supplier/Inventory master data,
    and quantity evaluation always uses the BOM QUANTITY already carried by the
    Analysis action.
    """
    revalidatable_rows = [
        row for row in selected_rows
        if row.get("status") in {"CONDITIONAL", "FAIL"}
    ]
    if not revalidatable_rows:
        return

    st.markdown("##### 기준정보 확인 및 재검증")
    st.caption(
        "수량은 BOM QUANTITY를 사용합니다. 이 화면에서 임시 속성이나 별도 요청수량을 입력하지 않습니다. "
        "부족한 기술/공급사/재고 기준정보를 등록한 뒤 다시 조회하여 재검증할 수 있습니다."
    )

    for row in revalidatable_rows:
        action_id = row.get("action_id")
        candidate_code = row.get("candidate_item_code")
        missing_requirements = _selected_candidate_missing_requirements(row)
        _render_anchor(_revalidation_input_anchor(workflow, action_id, candidate_code))
        st.markdown(f"**{candidate_code} · {row.get('candidate_description') or '-'}**")
        st.table(_display_df([{
            "BOM 수량": row.get("bom_quantity"),
            "재고 평가": row.get("inventory_status"),
            "가용재고": row.get("available_quantity"),
            "부족수량": row.get("shortage_quantity"),
        }]))
        if missing_requirements:
            st.info(
                "보완 필요 기준정보: " + ", ".join(missing_requirements) +
                "\n\n해당 값은 임시 입력하지 않고 Rule/Item/Supplier/Inventory 기준정보에 등록한 뒤 재검증합니다."
            )

        if st.button(
            f"{candidate_code} 기준정보 다시 조회 및 재검증",
            key=f"revalidate_selected_{(workflow.get('analysis_id') or workflow.get('request_id'))}_{action_id}_{candidate_code}",
        ):
            try:
                result = client.revalidate_design_change_analysis(
                    analysis=_analysis_payload(workflow),
                    action_id=action_id,
                    candidate_item_code=candidate_code,
                    attributes={},
                    demand_quantity=None,
                )
            except Exception as error:
                st.error(f"재검증에 실패했습니다: {error}")
                return
            next_history_index = len(workflow.get("revalidation_history", [])) + 1
            _complete_workflow_action(
                workflow,
                "revalidate_design_change_analysis",
                result,
                "현재 기준정보와 BOM QUANTITY를 다시 조회해 재검증했습니다. 기존 분석은 유지되고 하단에 결과가 추가됩니다.",
                on_workflow_update,
                scroll_target=_revalidation_result_anchor(workflow, next_history_index),
            )


def _analysis_selection_rows(workflow: dict) -> list[dict]:
    """Keep the original candidate pool selectable across repeated revalidation runs."""
    source = workflow.get("analysis_initial_candidates") or workflow.get("candidates") or []
    return candidate_rows({**workflow, "candidates": [dict(value) for value in source]})


def _latest_candidate_row(workflow: dict, base_row: dict) -> dict:
    """Return the latest evaluation for a selectable candidate without changing the original pool."""
    code = base_row.get("candidate_item_code")
    action_id = base_row.get("action_id")
    latest_rows = candidate_rows(workflow)
    for row in latest_rows:
        if row.get("candidate_item_code") == code and row.get("action_id") == action_id:
            return row
    return base_row


def _proceed_analysis_to_final_confirmation(
    workflow: dict,
    client: DisplayBomMcpClient,
    on_workflow_update,
    *,
    selections: list[dict],
    exception_reason: str | None = None,
) -> None:
    """Commit one confirmed Analysis and prepare the final Preview in one user action.

    The user-facing button is the explicit proceed approval. Internally we still
    preserve all safety gates: read-only shared-impact calculation, Request creation,
    and read-only Preview/Revision snapshot are executed in order. Production BOM is
    not modified until the later final approval + Apply actions.
    """
    workflow["analysis_selection"] = [dict(value) for value in selections]
    workflow["analysis_exception_reason"] = str(exception_reason or "").strip() or None

    try:
        impact_result = client.preview_design_change_analysis_impact(
            analysis=_analysis_payload(workflow),
            selections=selections,
        )
    except Exception as error:
        st.error(f"영향범위 분석에 실패했습니다: {error}")
        return

    impact_state = apply_phase3_tool_result(
        "preview_design_change_analysis_impact",
        workflow,
        impact_result,
    )
    impact_state["analysis_selection"] = [dict(value) for value in selections]
    impact_state["analysis_exception_reason"] = workflow.get("analysis_exception_reason")
    # This single button is the user's explicit approval to proceed with the selected
    # analysis. Common/shared impact is still displayed in the final confirmation
    # before the separate final approval and Production Apply.
    impact_state["analysis_impact_confirmed"] = True

    try:
        request_result = client.create_design_change_request_from_analysis(
            analysis=_analysis_payload(impact_state),
            selections=selections,
            approved_by="streamlit-user",
            exception_reason=impact_state.get("analysis_exception_reason"),
            impact_confirmed=True,
        )
    except Exception as error:
        st.error(f"설계변경 Request 생성에 실패했습니다: {error}")
        return

    request_state = apply_phase3_tool_result(
        "create_design_change_request_from_analysis",
        impact_state,
        request_result,
    )
    request_id = request_result.get("request_id")
    try:
        preview_result = client.create_multi_action_preview(
            request_id,
            "streamlit-user",
        )
    except Exception as error:
        # Keep the successfully created Request so the existing CANDIDATE_APPROVED
        # recovery path can recreate the read-only Preview without duplicate Request.
        workflow.clear()
        workflow.update(request_state)
        if on_workflow_update is not None:
            on_workflow_update(request_state)
        st.error(
            "설계변경 Request는 생성되었지만 적용 전 최종 확인 정보를 준비하지 못했습니다. "
            f"화면을 다시 갱신해 재시도해 주세요. 상세: {error}"
        )
        return

    updated = apply_phase3_tool_result(
        "create_multi_action_preview",
        request_state,
        preview_result,
    )
    workflow.clear()
    workflow.update(updated)
    if on_workflow_update is not None:
        on_workflow_update(updated)
    st.session_state["phase3_workflow_notice"] = {
        "context_id": updated.get("request_id"),
        "message": (
            f"설계변경 Request {request_id}가 생성되었고 적용 전 최종 확인 정보가 준비되었습니다. "
            "내용을 확인한 뒤 설계변경을 확정해 주세요."
        ),
    }
    st.rerun()


def _render_candidate_free_action_analysis(
    workflow: dict,
    client: DisplayBomMcpClient,
    on_workflow_update,
) -> None:
    """Render DELETE/QUANTITY_CHANGE Analysis that does not require candidate selection."""
    actions = [
        dict(action) for action in workflow.get("actions", [])
        if action.get("action_type") in {"DELETE", "QUANTITY_CHANGE"}
    ]
    if not actions:
        return

    rows = []
    for index, action in enumerate(actions, start=1):
        demand = action.get("demand") or {}
        inventory = action.get("inventory") or {}
        rows.append({
            "Action": index,
            "유형": action.get("action_type"),
            "대상 품목": action.get("old_item_code") or "-",
            "Parent": action.get("parent_item_code") or "-",
            "LOCATION": action.get("location_code") or "-",
            "변경 전 수량": action.get("old_quantity"),
            "변경 후 수량": action.get("new_quantity"),
            "평가": action.get("evaluation_status") or "-",
            "BOM 수량": demand.get("bom_quantity") if demand.get("bom_quantity") is not None else demand.get("quantity"),
            "가용재고": inventory.get("available_quantity"),
            "부족수량": inventory.get("shortage_quantity"),
        })

    st.markdown("#### Action 검증")
    st.caption(
        "DELETE와 QUANTITY_CHANGE는 대체 후보를 선택하지 않습니다. "
        "현재 BOM 관계, 변경 전/후 BOM QUANTITY, 재고 및 공용 BOM 영향범위를 검증한 뒤 진행합니다."
    )
    action_frame = _display_df(rows)
    st.dataframe(_style_change_frame(action_frame), width="stretch", hide_index=True)

    statuses = {str(action.get("evaluation_status") or "PENDING") for action in actions}
    context_id = workflow.get("analysis_id") or workflow.get("request_id")
    if "FAIL" in statuses:
        st.error("FAIL Action이 있어 설계변경 진행 대상으로 확정할 수 없습니다.")
        return

    exception_reason = ""
    if "CONDITIONAL" in statuses:
        st.warning(
            "BOM 수량/재고 등 추가 확인이 필요한 CONDITIONAL Action이 있습니다. "
            "업무상 보완할 수 없는 경우에만 예외 검토 사유를 기록하세요."
        )
        exception_reason = st.text_area(
            "CONDITIONAL 예외 검토 사유",
            key=f"candidate_free_exception_{context_id}",
        )
        can_confirm = bool(exception_reason.strip())
        label = "예외조건 포함 분석안으로 설계변경 진행"
    else:
        st.success(
            "Action 검증이 완료되었습니다. 아래 버튼을 누르면 이 분석안으로 Request를 생성하고 "
            "적용 전 최종 확인 정보까지 자동으로 준비합니다."
        )
        can_confirm = True
        label = "해당 분석안으로 설계변경 진행"

    if st.button(label, type="primary", key=f"confirm_candidate_free_{context_id}", disabled=not can_confirm):
        _proceed_analysis_to_final_confirmation(
            workflow,
            client,
            on_workflow_update,
            selections=[],
            exception_reason=exception_reason,
        )


def _render_candidate_selection(workflow: dict, rows: list[dict], client: DisplayBomMcpClient, on_workflow_update) -> None:
    if not any(row.get("status") in {"PASS", "CONDITIONAL"} for row in rows):
        return
    required_actions = _required_candidate_actions(workflow)
    if not required_actions:
        return
    context_id = workflow.get("analysis_id") or workflow.get("request_id")
    _render_anchor(_candidate_selection_anchor(workflow))
    st.markdown("#### 후보 선택")
    st.caption(
        "PASS 후보가 있으면 추천 가능한 PASS 후보만 선택합니다. PASS 후보가 하나도 없는 경우에만 "
        "CONDITIONAL 후보를 재검증/예외 검토 대상으로 선택할 수 있습니다."
    )
    selections: list[dict] = []
    selected_rows: list[dict] = []
    missing_actions: list[str] = []
    for action_index, action in enumerate(required_actions, start=1):
        action_id = action.get("action_id")
        all_action_rows = [row for row in rows if row.get("action_id") == action_id]
        pass_rows = [row for row in all_action_rows if row.get("status") == "PASS"]
        conditional_rows = [row for row in all_action_rows if row.get("status") == "CONDITIONAL"]
        action_rows = pass_rows if pass_rows else conditional_rows
        selection_mode = "PASS" if pass_rows else "CONDITIONAL"
        if not action_rows:
            missing_actions.append(f"Action {action_index}")
            continue
        codes = [row["candidate_item_code"] for row in action_rows]
        selectbox_key = f"analysis_candidate_{context_id}_{action_id}"
        pending_navigation = st.session_state.get("phase3_pending_candidate_navigation") or {}
        if (
            pending_navigation.get("context_id") == context_id
            and pending_navigation.get("action_id") == action_id
            and pending_navigation.get("candidate_item_code") in codes
        ):
            st.session_state[selectbox_key] = pending_navigation["candidate_item_code"]
            st.session_state.pop("phase3_pending_candidate_navigation", None)
        select_label = (
            f"추천 후보 선택 · Action {action_index}"
            if selection_mode == "PASS"
            else f"평가 보류 후보 선택(재검증/예외 검토) · Action {action_index}"
        )
        def _format_candidate(value, values=action_rows):
            row = next(row for row in values if row["candidate_item_code"] == value)
            score_label = f"{row['score']}점" if row.get("score") is not None else "평가 보류"
            return (
                f"{row['candidate_item_code']} · "
                f"{row.get('candidate_description') or row.get('candidate_name') or '-'} · "
                f"{row['status']} · {score_label}"
            )
        selected_code = st.selectbox(
            select_label, codes,
            key=selectbox_key,
            format_func=_format_candidate,
        )
        base_row = next(value for value in action_rows if value["candidate_item_code"] == selected_code)
        row = _latest_candidate_row(workflow, base_row)
        selected_rows.append(row)
        selections.append({
            "action_id": action_id, "candidate_item_code": selected_code,
            "supplier_item_id": row.get("supplier_item_id"),
        })
    if missing_actions:
        st.error("선택 가능한 후보가 없는 Action이 있어 분석안을 확정할 수 없습니다: " + ", ".join(missing_actions))
        return
    _render_selection_review_responsive(workflow, selected_rows)

    has_fail = any(row.get("status") == "FAIL" for row in selected_rows)
    has_conditional = any(row.get("status") == "CONDITIONAL" for row in selected_rows)
    if has_fail:
        st.error(
            "선택 후보의 최신 재검증 결과가 FAIL입니다. 이 상태에서는 분석안을 확정할 수 없습니다. "
            "후보를 바꾸거나 수량/추가정보를 수정해 다시 재검증하세요."
        )
        _render_selected_candidate_revalidation(workflow, selected_rows, client, on_workflow_update)
        reason = ""
        can_confirm = False
        label = "FAIL 후보는 분석안 확정 불가"
    elif has_conditional:
        st.warning("선택 후보에 CONDITIONAL이 있습니다. 가능한 추가정보를 입력해 재검증하거나, 보완할 수 없는 경우 예외 사유를 남겨 진행하세요.")
        _render_selected_candidate_revalidation(workflow, selected_rows, client, on_workflow_update)
        reason = st.text_area(
            "CONDITIONAL 예외 검토 사유",
            key=f"analysis_exception_{context_id}",
            placeholder="추가정보를 보완할 수 없는 업무 사유와 이 조건부 후보를 설계변경안으로 채택해야 하는 이유를 입력하세요.",
        )
        can_confirm = bool(reason.strip())
        label = "예외조건 포함 분석안으로 설계변경 진행"
    else:
        st.success(
            "선택한 후보의 최신 평가가 PASS입니다. 아래 버튼을 누르면 이 후보를 분석안으로 확정하고 "
            "공용 영향 확인, Request 생성, 적용 전 최종 확인 준비까지 연속 수행합니다."
        )
        reason = ""
        can_confirm = True
        label = "해당 분석안으로 설계변경 진행"

    if st.button(label, type="primary", key=f"confirm_analysis_selection_{context_id}", disabled=not can_confirm):
        _proceed_analysis_to_final_confirmation(
            workflow,
            client,
            on_workflow_update,
            selections=selections,
            exception_reason=reason,
        )

def _selected_conditional_rows(workflow: dict) -> list[dict]:
    selected = {
        value.get("candidate_id") for value in workflow.get("candidate_selection", [])
        if value.get("candidate_id")
    }
    return [
        row for row in candidate_rows(workflow)
        if row.get("candidate_id") in selected and row.get("status") == "CONDITIONAL"
    ]


def _render_conditional_review_gate(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:
    selected = _selected_conditional_rows(workflow)
    st.markdown("#### CONDITIONAL 후보 추가확인")
    st.warning(
        "후보 선택은 저장되었지만 아직 1차 후보 승인이 완료되지 않았습니다. "
        "아래 부족 데이터를 확인하고 가능한 항목은 보완·재검증하세요. "
        "계속 CONDITIONAL인 경우에만 예외승인 사유를 기록할 수 있습니다."
    )
    if selected:
        overview = []
        for row in selected:
            overview.append({
                "후보 코드": row.get("candidate_item_code"),
                "종합 적합성": row.get("status"),
                "종합 판단 요약": _candidate_decision_summary(row),
                "보완 필요 데이터": row.get("missing_data") or "평가 근거 상세 확인 필요",
                "공급 평가": row.get("supplier_status"),
                "재고 평가": row.get("inventory_status"),
                "BOM 수량": row.get("bom_quantity"),
            })
        st.table(_display_df(overview))

    # Reuse the existing deterministic attribute-data revalidation path when possible.
    _render_conditional_revalidation(workflow, client, on_workflow_update)

    st.markdown("**재검증 후에도 CONDITIONAL인 경우 예외승인**")
    reason = st.text_area(
        "CONDITIONAL 예외승인 사유",
        key=f"conditional_preworkflow_exception_{workflow.get('request_id')}",
        placeholder="부족 데이터를 보완할 수 없는 업무 사유와 조건부 후보를 사용해야 하는 이유를 입력하세요.",
    )
    if st.button("예외승인 후 다음 단계 진행", type="primary"):
        if not reason.strip():
            st.error("예외승인 사유를 입력해 주세요.")
            return
        result = client.record_exception_approval(
            request_id=workflow["request_id"],
            reason=reason.strip(),
            approved_by="streamlit-user",
        )
        status = result.get("workflow_status")
        message = (
            "예외승인이 기록되었습니다. 공용 BOM 영향범위를 확인해 주세요."
            if status == "IMPACT_REVIEW_REQUIRED"
            else "예외승인과 1차 후보 승인이 완료되어 설계변경 Workflow가 시작되었습니다."
        )
        _complete_workflow_action(
            workflow,
            "record_exception_approval",
            result,
            message,
            on_workflow_update,
        )


def _render_impact_review(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:
    """Render the read-only shared impact summary without a separate approval step."""
    review = workflow.get("impact_review") or {}
    st.markdown("#### 공용자재 영향 확인")
    st.info(
        "선택한 분석안의 공용 BOM 영향범위를 계산했습니다. 이 정보는 적용 전 최종 확인에도 함께 표시되며, "
        "Production BOM은 아직 변경되지 않습니다."
    )
    models = impact_model_rows(workflow)
    if models:
        st.markdown("**함께 변경되는 대상 모델**")
        st.dataframe(pd.DataFrame(models), width="stretch", hide_index=True)
    changed_specs = impact_spec_rows(workflow, changed_only=True)
    all_specs = impact_spec_rows(workflow, changed_only=False)
    st.markdown("**변경되는 Spec 정보**")
    if changed_specs:
        st.dataframe(pd.DataFrame(changed_specs), width="stretch", hide_index=True)
    else:
        st.info("비교 가능한 Spec 중 값이 변경되는 항목은 없습니다.")
    if len(all_specs) > len(changed_specs):
        with st.expander("동일 Spec까지 전체 비교"):
            st.dataframe(pd.DataFrame(all_specs), width="stretch", hide_index=True)
    st.caption(f"영향 모델 수: {review.get('impacted_model_count', len(models))}")


def _render_analysis_proceed_gate(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:
    st.markdown("#### 해당 분석안으로 설계변경 진행")
    st.success("후보 분석, 필요한 재검증 및 영향범위 확인이 완료되었습니다.")
    st.info(
        "아래 버튼은 현재 선택된 분석안을 실제 설계변경 대상으로 진행하겠다는 명시적 승인입니다. "
        "Request 생성과 적용 전 최종 확인 정보 준비까지 자동으로 수행하며 Production BOM은 아직 변경하지 않습니다."
    )
    if st.button("해당 분석안으로 설계변경 진행", type="primary", key=f"start_design_change_{workflow.get('analysis_id')}"):
        try:
            request_result = client.create_design_change_request_from_analysis(
                analysis=_analysis_payload(workflow),
                selections=workflow.get("analysis_selection") or [],
                approved_by="streamlit-user",
                exception_reason=workflow.get("analysis_exception_reason"),
                impact_confirmed=True,
            )
        except Exception as error:
            st.error(f"설계변경 Request 생성에 실패했습니다: {error}")
            return

        # Preserve the successfully created Request before attempting the read-only
        # final Preview. If Preview generation fails, the next render can recover
        # from CANDIDATE_APPROVED without creating a duplicate Request.
        request_state = apply_phase3_tool_result(
            "create_design_change_request_from_analysis", workflow, request_result
        )
        request_id = request_result.get("request_id")
        try:
            preview_result = client.create_multi_action_preview(request_id, "streamlit-user")
        except Exception as error:
            workflow.clear(); workflow.update(request_state)
            if on_workflow_update is not None:
                on_workflow_update(request_state)
            st.error(
                "설계변경 Request는 생성되었지만 적용 전 최종 확인 정보를 준비하지 못했습니다. "
                f"다시 화면을 갱신해 재시도해 주세요. 상세: {error}"
            )
            return

        updated = apply_phase3_tool_result(
            "create_multi_action_preview", request_state, preview_result
        )
        workflow.clear(); workflow.update(updated)
        if on_workflow_update is not None:
            on_workflow_update(updated)
        st.session_state["phase3_workflow_notice"] = {
            "context_id": updated.get("request_id"),
            "message": (
                f"설계변경 Request {request_id}가 생성되었고 적용 전 최종 확인 정보가 준비되었습니다. "
                "내용을 확인한 뒤 설계변경을 확정해 주세요."
            ),
        }
        st.rerun()

def _confirmed_selected_candidate_rows(workflow: dict) -> list[dict]:
    """Return only the candidate(s) the user confirmed for this Analysis Session."""
    selections = workflow.get("analysis_selection") or []
    if not selections:
        return []
    current_rows = candidate_rows(workflow)
    initial_rows = _analysis_selection_rows(workflow)
    selected_rows: list[dict] = []
    for selection in selections:
        action_id = selection.get("action_id")
        candidate_code = selection.get("candidate_item_code")
        row = next((
            value for value in current_rows
            if value.get("action_id") == action_id
            and value.get("candidate_item_code") == candidate_code
        ), None)
        if row is None:
            row = next((
                value for value in initial_rows
                if value.get("action_id") == action_id
                and value.get("candidate_item_code") == candidate_code
            ), None)
        if row is not None:
            selected_rows.append(row)
    return selected_rows


def _render_confirmed_analysis_summary(workflow: dict) -> None:
    """Render only the user's confirmed selection after candidate analysis is finalized."""
    context = workflow.get("analysis_context") or {}
    selected_rows = _confirmed_selected_candidate_rows(workflow)

    st.subheader("확정한 설계변경 분석")
    st.caption(
        f"Analysis ID: {workflow.get('analysis_id') or '-'} · "
        f"PLANT: {workflow.get('plant_code') or context.get('plant_code') or '-'} · Request: 미생성"
    )
    st.table(_display_df([
        {"항목": "제품", "값": context.get("version_code")},
        {"항목": "변경 유형", "값": context.get("action_type")},
        {"항목": "변경 사유", "값": " · ".join(context.get("reason_codes") or ([context.get("reason_code")] if context.get("reason_code") else [])) or "-"},
        {"항목": "Parent", "값": (context.get("parent_item") or {}).get("item_code") or context.get("parent_item_code")},
        {"항목": "LOCATION", "값": context.get("location_code")},
    ]))

    if selected_rows:
        for index, row in enumerate(selected_rows, start=1):
            title = "선택 자재" if len(selected_rows) == 1 else f"선택 자재 {index}"
            st.markdown(f"#### {title}")
            st.table(_display_df([
                {"항목": "품목 코드", "값": row.get("candidate_item_code")},
                {"항목": "품목명", "값": row.get("candidate_name")},
                {"항목": "DESCRIPTION", "값": row.get("candidate_description")},
                {"항목": "종합 적합성", "값": row.get("status")},
                {"항목": "기술 평가", "값": row.get("technical_status")},
                {"항목": "공급 평가", "값": row.get("supplier_status")},
                {"항목": "재고 평가", "값": row.get("inventory_status")},
                {
                    "항목": "추천 점수 / 추천등급",
                    "값": (
                        f"{row.get('score')} / {row.get('grade')}"
                        if row.get("score") is not None
                        else "평가 보류 / -"
                    ),
                },
                {"항목": "BOM 수량", "값": row.get("bom_quantity")},
                {"항목": "가용재고", "값": row.get("available_quantity")},
                {"항목": "주 공급사", "값": row.get("supplier_name") or row.get("supplier_code") or "미등록"},
                {"항목": "단가(KRW)", "값": row.get("unit_price")},
                {"항목": "납기(일)", "값": row.get("lead_time_days")},
            ]))
            st.markdown("**최종 판단**")
            st.info(_candidate_decision_summary(row))

            raw_candidate = next((
                value for value in workflow.get("candidates", [])
                if value.get("action_id") == row.get("action_id")
                and value.get("candidate_item_code") == row.get("candidate_item_code")
            ), {})
            evidence_rows = []
            for rule_result in raw_candidate.get("rule_results") or []:
                evidence = rule_result.get("evidence") or {}
                for condition in evidence.get("conditions") or []:
                    evidence_rows.append({
                        "구분": "RULE",
                        "평가 항목": condition.get("attribute"),
                        "후보 값": condition.get("actual"),
                        "기준": f"{condition.get('operator') or '-'} {condition.get('expected') if condition.get('expected') is not None else '-'}",
                        "결과": condition.get("status"),
                    })
            for attr_result in raw_candidate.get("attribute_results") or []:
                evidence_rows.append({
                    "구분": "ATTRIBUTE",
                    "평가 항목": attr_result.get("attribute"),
                    "후보 값": attr_result.get("candidate_value"),
                    "기준": attr_result.get("source_value"),
                    "결과": attr_result.get("status"),
                })
            if evidence_rows:
                with st.expander("선택 자재 기술/Rule 상세", expanded=False):
                    st.dataframe(_display_df(evidence_rows), hide_index=True, width="stretch")
        return

    # DELETE / QUANTITY_CHANGE do not have a replacement candidate. Show only the
    # confirmed Action analysis instead of returning to the full initial analysis.
    actions = workflow.get("actions") or []
    action_rows = []
    for index, action in enumerate(actions, start=1):
        inventory = action.get("inventory") or {}
        action_rows.append({
            "Action": index,
            "유형": action.get("action_type"),
            "대상 품목": action.get("old_item_code") or "-",
            "Parent": action.get("parent_item_code") or "-",
            "LOCATION": action.get("location_code") or "-",
            "변경 전 수량": action.get("old_quantity"),
            "변경 후 수량": action.get("new_quantity"),
            "평가": action.get("evaluation_status") or "-",
            "가용재고": inventory.get("available_quantity"),
            "부족수량": inventory.get("shortage_quantity"),
        })
    if action_rows:
        st.markdown("#### 확정 Action 분석")
        st.dataframe(_display_df(action_rows), hide_index=True, width="stretch")


def _render_pre_workflow_analysis(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:
    if not workflow.get("candidates") and not workflow.get("actions"):
        return

    step = workflow.get("current_step")

    # Once the user has confirmed the analysis selection, do not keep showing the
    # entire original candidate pool. From this point onward show only what the user
    # actually selected and its evaluation evidence.
    if step in {"ANALYSIS_IMPACT_REVIEW", "ANALYSIS_CONFIRMED"}:
        _render_confirmed_analysis_summary(workflow)
        if workflow.get("impact_review"):
            _render_impact_review(workflow, client, on_workflow_update)
        _render_analysis_proceed_gate(workflow, client, on_workflow_update)
        _render_pending_scroll()
        return

    st.subheader("설계변경 후보 분석")
    st.caption(f"Analysis ID: {workflow.get('analysis_id') or '-'} · PLANT: {workflow.get('plant_code')} · Request: 미생성")
    initial_context = workflow.get("analysis_initial_context") or workflow.get("analysis_context") or {}
    _render_target_summary(workflow, context_override=initial_context)
    initial_rows = _analysis_selection_rows(workflow)
    _render_analysis_metrics(workflow, initial_rows, context_override=initial_context)
    if _required_candidate_actions(workflow) or initial_rows:
        _render_candidate_tables(initial_rows)

    if step in {"ANALYSIS_READY", "ANALYSIS_REVALIDATED"}:
        # 재검증이 특정 후보를 FAIL로 바꾸더라도 최초 분석 후보 Pool은 유지하여
        # 다른 후보를 선택하거나 수량을 바꿔 반복 재검증할 수 있게 한다.
        if _required_candidate_actions(workflow):
            _render_candidate_selection(workflow, initial_rows, client, on_workflow_update)
        else:
            _render_candidate_free_action_analysis(workflow, client, on_workflow_update)
    elif step == "WAITING_CANDIDATE_APPROVAL":
        _render_candidate_selection(workflow, candidate_rows(workflow), client, on_workflow_update)
    elif step == "CONDITIONAL_REVIEW_REQUIRED":
        _render_conditional_review_gate(workflow, client, on_workflow_update)
    elif step == "IMPACT_REVIEW_REQUIRED":
        _render_impact_review(workflow, client, on_workflow_update)

    # Revalidation history is useful while the user is still comparing candidates.
    # After analysis confirmation the page switches to the confirmed-selection view above.
    _render_revalidation_history(workflow)
    _render_pending_scroll()

def _final_confirmation_action_rows(actions: list[dict]) -> list[dict]:
    """Return the minimal approved delta shown immediately before final approval."""
    return [{
        "Action": action.get("action_type"),
        "Parent": action.get("parent_item_code"),
        "LOCATION": action.get("location_code"),
        "변경 전": action.get("old_item_code"),
        "변경 후": action.get("new_item_code"),
        "변경 전 수량": action.get("old_quantity"),
        "변경 후 수량": action.get("new_quantity"),
        "종합 판정": action.get("evaluation_status"),
    } for action in actions]


def _render_final_confirmation(workflow: dict, client: DisplayBomMcpClient) -> None:
    """Render one de-duplicated Request + Preview confirmation surface."""
    request_id = workflow.get("request_id")
    try:
        detail = client.get_change_request_result(request_id) if request_id else {}
    except Exception:
        detail = {}

    context = workflow.get("analysis_context") or {}
    reason_codes = context.get("reason_codes") or (
        [context.get("reason_code")] if context.get("reason_code") else []
    )
    st.markdown("#### 적용 전 최종 확인")
    st.info(
        "설계변경 진행 승인으로 Request 생성과 적용 전 최종 확인 준비가 완료되었습니다. "
        "아래 내용은 실제 Production E-BOM에 반영될 변경사항만 중복 없이 요약한 것입니다."
    )
    st.table(_display_df([
        {"항목": "Request ID", "값": request_id or detail.get("request_id")},
        {"항목": "제품", "값": detail.get("version_code") or context.get("version_code")},
        {"항목": "PLANT", "값": detail.get("plant_code") or workflow.get("plant_code")},
        {"항목": "변경 사유", "값": " · ".join(reason_codes) or "-"},
    ]))

    actions = detail.get("actions") or workflow.get("actions") or []
    action_rows = _final_confirmation_action_rows(actions)
    if action_rows:
        st.markdown("**실제 적용 예정 변경사항**")
        st.dataframe(
            _style_change_frame(_display_df(action_rows)),
            hide_index=True,
            width="stretch",
        )

    analysis_models = impact_model_rows(workflow)
    models = analysis_models or preview_model_rows(workflow, client)
    if models:
        st.markdown("**영향 MODEL**")
        st.dataframe(_display_df(models), hide_index=True, width="stretch")

    changed_specs = impact_spec_rows(workflow, changed_only=True)
    if changed_specs:
        st.markdown("**공용 영향 변경 Spec**")
        st.dataframe(_display_df(changed_specs), hide_index=True, width="stretch")


def _render_workflow(workflow: dict, client: DisplayBomMcpClient, on_workflow_update) -> None:
    request_id = workflow.get("request_id")
    current_step = workflow.get("current_step")
    if request_id and current_step != "WAITING_FINAL_APPROVAL":
        render_phase3_request_detail(
            client,
            request_id,
            heading="현재 진행 중인 설계변경 Request 상세",
            show_completion_report=False,
        )

    review = workflow.get("impact_review") or {}
    if review:
        st.success("후보 선택 및 필요한 공용 BOM 영향 확인이 완료되었습니다.")

    actor = "streamlit-user"
    if workflow.get("current_step") == "REPORT_COMPLETED":
        st.success("설계변경 적용과 Word 완료 보고서 생성이 완료되었습니다. 업무가 종료되었습니다.")
        cache_key = f"phase3_completion_report_{workflow.get('request_id')}"
        report = st.session_state.get(cache_key)
        if report and report.get("success") and report.get("file_bytes"):
            st.download_button(
                "설계변경 완료 보고서 Word 다운로드",
                data=report["file_bytes"],
                file_name=report.get("file_name") or f"{workflow['request_id']}_design_change_completion_report.docx",
                mime=report.get("mime_type") or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                key=f"download_phase3_report_completed_{workflow.get('request_id')}",
            )
        return

    action = available_action(workflow)
    if action == "EXCEPTION_APPROVAL":
        st.warning("선택 후보가 CONDITIONAL입니다. 추가 데이터 재검증 또는 예외 사유 승인이 필요합니다.")
        reason = st.text_area("CONDITIONAL 예외승인 사유")
        if st.button("CONDITIONAL 예외승인 기록", type="primary"):
            result = client.record_exception_approval(
                request_id=workflow["request_id"], reason=reason, approved_by=actor,
            )
            _complete_workflow_action(
                workflow,
                "record_exception_approval",
                result,
                "예외승인이 기록되었습니다. Production BOM은 변경되지 않았습니다.",
                on_workflow_update,
            )
    elif action == "CREATE_PREVIEW":
        # Recovery path for a Request that was created successfully but whose
        # Preview preparation was interrupted. Preview is read-only, so retry it
        # automatically instead of exposing a separate Preview button.
        st.info("생성된 Request를 기준으로 적용 전 최종 확인 정보를 준비하고 있습니다.")
        try:
            result = client.create_multi_action_preview(workflow["request_id"], actor)
        except Exception as exc:
            message = str(exc)
            if "ADD target is already active at the effective date" in message:
                st.error(
                    "선택한 ADD 자재가 적용일 기준 동일한 PLANT/Parent/Location BOM에 "
                    "이미 존재합니다. 새 분석에서 다른 추가 후보를 선택해 주세요."
                )
            else:
                st.error(f"적용 전 최종 확인 정보를 준비하지 못했습니다: {message}")
            return
        _complete_workflow_action(
            workflow,
            "create_multi_action_preview",
            result,
            "적용 전 최종 확인 정보가 준비되었습니다. 내용을 확인한 뒤 설계변경을 확정해 주세요.",
            on_workflow_update,
        )
    elif action == "FINAL_APPROVAL":
        _render_final_confirmation(workflow, client)
        st.warning("실제 적용 예정 변경사항을 확인한 뒤 설계변경을 확정하세요.")
        if st.button("설계변경 확정", type="primary"):
            try:
                result = client.record_final_apply_approval(workflow["request_id"], actor)
            except Exception as error:
                st.error(f"설계변경 확정에 실패했습니다: {error}")
                return
            _complete_workflow_action(
                workflow,
                "record_final_apply_approval",
                result,
                "설계변경이 확정되었습니다. 아직 BOM에는 반영되지 않았습니다.",
                on_workflow_update,
            )
    elif action == "APPLY":
        st.error(
            "확정된 설계변경 내용을 Production E-BOM에 반영합니다. "
            "반영 후에는 BOM이 실제 변경되므로 변경 내용을 다시 확인해 주세요."
        )
        if st.button("설계변경 BOM 반영", type="primary"):
            try:
                result = client.apply_approved_change_request(
                    request_id=workflow["request_id"],
                    final_approval_id=workflow["final_approval_id"], applied_by=actor,
                )
            except Exception as error:
                st.error(
                    "BOM 반영 중 오류가 발생하여 변경을 완료하지 못했습니다. "
                    "Transaction은 Rollback되며 Production E-BOM을 다시 확인한 뒤 재시도해 주세요. "
                    f"상세: {error}"
                )
                return
            _complete_workflow_action(
                workflow,
                "apply_approved_change_request",
                result,
                "확정된 설계변경이 BOM에 반영되었습니다.",
                on_workflow_update,
            )
    elif action == "REPORT":
        st.success("설계변경이 Production E-BOM에 반영되었습니다. 품평회 단계 없이 완료 보고서를 생성하여 업무를 종료합니다.")
        cache_key = f"phase3_completion_report_{workflow.get('request_id')}"
        report = st.session_state.get(cache_key)
        if report is None:
            try:
                report = client.export_phase3_completion_report(workflow["request_id"])
                st.session_state[cache_key] = report
            except Exception as error:
                st.error(f"완료 보고서 생성에 실패했습니다: {error}")
                return
        if report.get("success") and report.get("file_bytes"):
            _complete_workflow_action(
                workflow,
                "export_phase3_completion_report",
                {"success": True, "file_name": report.get("file_name")},
                "Production E-BOM 반영과 Word 완료 보고서 생성이 완료되었습니다. 설계변경 업무를 종료합니다.",
                on_workflow_update,
            )
        else:
            st.error(report.get("message") or "완료 보고서를 생성할 수 없습니다.")


def render_phase3_workflow(
    workflow: dict,
    client: DisplayBomMcpClient | None = None,
    on_workflow_update=None,
) -> None:
    if not workflow or not (workflow.get("analysis_id") or workflow.get("request_id")):
        return
    client = client or DisplayBomMcpClient()

    notice = st.session_state.get("phase3_workflow_notice")
    if notice and notice.get("context_id") == (workflow.get("request_id") or workflow.get("analysis_id")):
        st.success(str(notice.get("message") or "상태가 갱신되었습니다."))
        st.session_state.pop("phase3_workflow_notice", None)

    if workflow.get("current_step") in ANALYSIS_STEPS:
        _render_pre_workflow_analysis(workflow, client, on_workflow_update)
        return

    if is_workflow_visible(workflow):
        _render_workflow(workflow, client, on_workflow_update)
