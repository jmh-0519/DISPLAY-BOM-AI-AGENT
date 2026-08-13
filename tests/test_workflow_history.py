import base64
import json

import pandas as pd
from langchain_core.messages import ToolMessage

from agents.bom_agent_graph import BomAgentGraph
from services.workflow_history_repository import WorkflowHistoryRepository


def _write(path, name, rows, columns):
    pd.DataFrame(rows, columns=columns).to_csv(path / name, index=False, encoding="utf-8-sig")


def test_history_repository_links_change_review_and_checks(tmp_path):
    _write(tmp_path, "change_bom.csv", [["CHG-1", "P1", "REPLACE", "2026-08-13", "2026-08-20", "교체", "PASS", "APPROVED", "REVIEW_READY", "", "U1", "", ""]],
           ["change_id", "product_id", "change_type", "requested_date", "effective_date", "reason", "analysis_result", "approval_status", "apply_status", "applied_date", "requested_by", "approved_by", "applied_by"])
    _write(tmp_path, "change_bom_item.csv", [["CHG-1", "1", "REPLACE", "PA", "OLD", "NEW"]],
           ["change_id", "item_seq", "action", "bom_parent", "old_bom_child", "new_bom_child"])
    _write(tmp_path, "review_bom.csv", [["REV-1", "CHG-1", "P1", "APPROVED", "1", "1", "PASS", "2026-08-13", "", "", "U1", "AI", "PASS"]],
           ["review_id", "change_id", "product_id", "review_status", "current_revision", "approved_revision", "review_result", "created_date", "started_date", "completed_date", "created_by", "reviewed_by", "decision_reason"])
    _write(tmp_path, "review_bom_check.csv", [["REV-1", "CHG-1", "1", "1", "RULE", "NEW", "PASS", "A", "B", "N", "통과", "2026-08-13"]],
           ["review_id", "change_id", "review_revision", "check_seq", "check_type", "target_id", "status", "actual_value", "expected_value", "blocking_yn", "message", "checked_date"])
    _write(tmp_path, "change_bom_detail.csv", [], ["change_id"])
    _write(tmp_path, "review_bom_detail.csv", [], ["review_id"])
    repo = WorkflowHistoryRepository(tmp_path)
    change = repo.list_design_changes()[0]
    review = repo.list_bom_reviews()[0]
    assert change["review_id"] == "REV-1"
    assert change["workflow_status"] == "보고서/적용 대기"
    assert review["pass_count"] == 1
    assert repo.get_design_change("chg-1")["success"] is True
    assert repo.get_bom_review("rev-1")["checks"][0]["message"] == "통과"


def test_agent_extracts_real_download_bytes_from_mcp_tool_message():
    payload = {"success": True, "file_name": "report.docx", "mime_type": "application/test",
               "file_data_base64": base64.b64encode(b"document-bytes").decode("ascii")}
    message = ToolMessage(content=json.dumps(payload), tool_call_id="1", name="export_design_change_report")
    artifacts = BomAgentGraph._extract_download_artifacts([message])
    assert artifacts[0]["file_name"] == "report.docx"
    assert artifacts[0]["file_bytes"] == b"document-bytes"


def test_agent_ignores_non_download_tools():
    message = ToolMessage(content='{"success": true}', tool_call_id="1", name="get_bom")
    assert BomAgentGraph._extract_download_artifacts([message]) == []
