from __future__ import annotations

from pathlib import Path

from agents.design_change_workflow_state import apply_design_change_tool_result
from database import SQLiteDatabase
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService
from tests.design_change_test_support import iter_dynamic_replace_contexts


ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path):
    path = tmp_path / "completion.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    return DesignChangeWorkflowService(database), database


def _history(database: SQLiteDatabase) -> list[dict]:
    from repositories.design_change_repository import SQLiteDesignChangeRepository
    return SQLiteDesignChangeRepository(database).list_change_requests()


def _analysis(service: DesignChangeWorkflowService, database: SQLiteDatabase) -> dict:
    context = next(iter(iter_dynamic_replace_contexts(database)))
    reason = context["reasons"][0]
    return service.analyze_candidates(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": f"{reason['alias_text']} 때문에 변경 가능한 후보를 찾아줘",
            "reasons": [reason["reason_code"]],
            "requested_by": "pytest",
        },
        [{"action_type": "REPLACE", "old_item_code": context["source_item_code"]}],
    )


def _candidate(analysis: dict) -> dict:
    return next(row for row in analysis["candidates"] if row["status"] in {"PASS", "CONDITIONAL"})


def _selection(candidate: dict) -> list[dict]:
    return [{
        "action_id": candidate["action_id"],
        "candidate_item_code": candidate["candidate_item_code"],
        "supplier_item_id": candidate.get("recommended_supplier_item_id"),
    }]


def test_design_change_history_is_empty_of_new_analysis_until_explicit_request_commit(tmp_path):
    service, database = _service(tmp_path)
    before_ids = {row["request_id"] for row in _history(database)}

    analysis = _analysis(service, database)
    candidate = _candidate(analysis)
    selections = _selection(candidate)
    service.preview_analysis_impact(analysis, selections)

    after_analysis_ids = {row["request_id"] for row in _history(database)}
    assert after_analysis_ids == before_ids

    committed = service.commit_analysis_as_request(
        analysis=analysis,
        selections=selections,
        approved_by="pytest",
        exception_reason=(
            "조건부 분석안을 검토 후 진행"
            if candidate["status"] == "CONDITIONAL" else None
        ),
        impact_confirmed=True,
    )
    after_commit = _history(database)
    new_ids = {row["request_id"] for row in after_commit} - before_ids
    assert new_ids == {committed["request_id"]}
    row = next(value for value in after_commit if value["request_id"] == committed["request_id"])
    assert row["plant_code"] == analysis["request"]["plant_code"]
    assert row["version_code"] == analysis["request"]["version_code"]
    assert row["original_request"] == analysis["request"]["original_request"]


def test_report_generation_moves_ui_workflow_to_report_completed():
    state = {
        "request_id": "REQ-1",
        "current_step": "APPLIED",
        "report_status": "WAITING",
    }
    updated = apply_design_change_tool_result(
        "export_design_change_completion_report",
        state,
        {"success": True, "file_name": "REQ-1_design_change_completion_report.docx"},
    )
    assert updated["current_step"] == "REPORT_COMPLETED"
    assert updated["report_status"] == "COMPLETED"
    assert updated["report_result"]["success"] is True


def test_design_change_history_page_uses_current_request_history():
    source = (ROOT / "app" / "views" / "design_change_history_page.py").read_text(encoding="utf-8")
    assert "list_design_change_history" in source
    assert "get_change_request_result" in source
    assert "export_design_change_completion_report" in source
