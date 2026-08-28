from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from mcp_client.client import DisplayBomMcpClient


def rule_rows(rules: list[dict]) -> list[dict]:
    fields = ("rule_id", "rule_name", "revision_no", "target_type", "change_reason",
              "evaluation_item", "required_yn", "weight", "valid_from", "valid_to", "active_yn")
    return [{key: rule.get(key) for key in fields} for rule in rules]


def history_rows(requests: list[dict]) -> list[dict]:
    fields = ("request_id", "version_code", "workflow_status", "candidate_approval_status",
              "final_approval_status", "apply_status", "created_at", "updated_at")
    return [{key: request.get(key) for key in fields} for request in requests]


def render_phase3_management(client: DisplayBomMcpClient | None = None) -> None:
    client = client or DisplayBomMcpClient()
    st.subheader("Design Change Rule / History / Learning Data")
    rules_tab, history_tab, export_tab = st.tabs(["Rules", "History & Performance", "Dataset"])
    with rules_tab:
        rules = client.list_rules()
        st.caption("모든 사용자가 Rule을 조회하고 새 Revision을 등록하거나 비활성화할 수 있습니다.")
        st.dataframe(pd.DataFrame(rule_rows(rules)), width="stretch")
        with st.form("phase3_rule_revision"):
            rule_json = st.text_area("Rule JSON")
            conditions_json = st.text_area("Conditions JSON array")
            create = st.form_submit_button("Create rule")
            update = st.form_submit_button("Update as new revision")
            if create:
                st.success(client.create_rule(json.loads(rule_json), json.loads(conditions_json)))
            if update:
                st.success(client.update_rule(json.loads(rule_json), json.loads(conditions_json)))
        active_revisions = [
            value for value in rules if value.get("active_yn") == "Y"
        ]
        if active_revisions:
            selected = st.selectbox(
                "Deactivate rule revision",
                [(value["rule_id"], value["revision_no"]) for value in active_revisions],
                format_func=lambda value: f"{value[0]} / revision {value[1]}",
            )
            if st.button("Deactivate selected revision"):
                st.success(client.deactivate_rule(selected[0], selected[1]))
    with history_tab:
        st.dataframe(pd.DataFrame(history_rows(client.list_design_change_history())), width="stretch")
        with st.form("phase3_performance"):
            request_id = st.text_input("Applied request ID")
            measurement_day = st.selectbox("Measurement day", [30, 60, 90])
            outcome_json = st.text_area("Outcome JSON", value="{}")
            measured_at = st.text_input("Measured at (ISO-8601)")
            rating = st.number_input("User rating", min_value=1, max_value=5, value=3)
            if st.form_submit_button("Record performance"):
                st.success(client.record_performance_outcome(
                    request_id=request_id, measurement_day=measurement_day,
                    outcome=json.loads(outcome_json), measured_at=measured_at, user_rating=rating))
    with export_tab:
        date_from = st.text_input("From date (optional)")
        date_to = st.text_input("To date (optional)")
        created_by = st.text_input("Requested by", value="phase3-ui")
        if st.button("Build anonymized JSONL"):
            result = client.export_training_dataset(
                date_from=date_from or None, date_to=date_to or None, created_by=created_by)
            st.caption(f"records={result['record_count']} checksum={result['checksum']}")
            st.download_button("Download JSONL", result["jsonl"],
                               file_name=f"{result['export_id']}.jsonl",
                               mime="application/x-ndjson")
