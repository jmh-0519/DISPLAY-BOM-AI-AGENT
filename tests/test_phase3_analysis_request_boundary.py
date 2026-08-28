from __future__ import annotations

from io import BytesIO

from docx import Document
from database import SQLiteDatabase
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_completion_report_service import DesignChangeCompletionReportService
from services.design_change_workflow_service import DesignChangeWorkflowService
from tests.test_phase3_e2e import iter_dynamic_replace_contexts


def _service(tmp_path, name: str):
    path = tmp_path / f"{name}.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    return DesignChangeWorkflowService(database), database


def _count(database: SQLiteDatabase, table: str) -> int:
    with database.connection() as connection:
        return int(connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])


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


def _selectable(analysis: dict) -> dict:
    return next(row for row in analysis["candidates"] if row["status"] in {"PASS", "CONDITIONAL"})


def _selection(analysis: dict, candidate: dict) -> list[dict]:
    return [{
        "action_id": candidate["action_id"],
        "candidate_item_code": candidate["candidate_item_code"],
        "supplier_item_id": candidate.get("recommended_supplier_item_id"),
    }]


def test_analysis_and_revalidation_do_not_create_design_change_request(tmp_path):
    service, database = _service(tmp_path, "analysis-no-request")
    before_requests = _count(database, "change_requests")
    before_actions = _count(database, "change_actions")

    analysis = _analysis(service, database)
    assert analysis["request_created"] is False
    assert analysis["request_id"] is None
    assert _count(database, "change_requests") == before_requests
    assert _count(database, "change_actions") == before_actions

    candidate = _selectable(analysis)
    revalidated = service.revalidate_analysis_candidate(
        analysis=analysis,
        action_id=candidate["action_id"],
        candidate_item_code=candidate["candidate_item_code"],
        demand_quantity=2,
    )
    assert revalidated["request_created"] is False
    assert revalidated["request_id"] is None
    assert revalidated["revalidation"]["before"]["candidate_item_code"] == candidate["candidate_item_code"]
    assert _count(database, "change_requests") == before_requests
    assert _count(database, "change_actions") == before_actions



def test_restart_analysis_creates_new_analysis_id_but_no_design_change_request(tmp_path):
    service, database = _service(tmp_path, "analysis-restart")
    first = _analysis(service, database)
    before = _count(database, "change_requests")
    restarted = service.analyze_candidates(
        dict(first["request"]),
        [{
            key: value
            for key, value in first["actions"][0].items()
            if key in {"action_type", "target_type", "parent_item_code", "reason_code", "old_item_code", "new_item_code", "location_code", "old_quantity", "new_quantity"}
            and value is not None
        }],
    )
    assert restarted["analysis_id"] != first["analysis_id"]
    assert restarted["request_id"] is None
    assert _count(database, "change_requests") == before

def test_read_only_impact_preview_does_not_create_request(tmp_path):
    service, database = _service(tmp_path, "analysis-impact")
    analysis = _analysis(service, database)
    candidate = _selectable(analysis)
    before = _count(database, "change_requests")

    impact = service.preview_analysis_impact(analysis, _selection(analysis, candidate))

    assert impact["production_bom_modified"] is False
    assert _count(database, "change_requests") == before


def test_explicit_proceed_is_the_first_point_that_creates_request(tmp_path):
    service, database = _service(tmp_path, "analysis-commit")
    analysis = _analysis(service, database)
    candidate = _selectable(analysis)
    selections = _selection(analysis, candidate)
    impact = service.preview_analysis_impact(analysis, selections)
    before = _count(database, "change_requests")

    result = service.commit_analysis_as_request(
        analysis=analysis,
        selections=selections,
        approved_by="pytest",
        exception_reason=(
            "분석 단계에서 보완 가능한 데이터가 없어 조건부 분석안을 승인함"
            if candidate["status"] == "CONDITIONAL" else None
        ),
        impact_confirmed=not impact.get("requires_impact_approval") or True,
    )

    assert result["request_created"] is True
    assert result["request_id"]
    assert _count(database, "change_requests") == before + 1
    persisted = service.get_result(result["request_id"])
    assert persisted["candidate_approval_status"] == "APPROVED"


def test_active_phase3_completes_with_word_report_without_review_stage(tmp_path):
    service, database = _service(tmp_path, "analysis-report")
    analysis = _analysis(service, database)
    candidate = _selectable(analysis)
    selections = _selection(analysis, candidate)
    impact = service.preview_analysis_impact(analysis, selections)
    review_bom_before = _count(database, "review_boms")
    bom_review_before = _count(database, "bom_reviews")

    committed = service.commit_analysis_as_request(
        analysis=analysis,
        selections=selections,
        approved_by="pytest",
        exception_reason=(
            "테스트 기준정보가 부족하여 조건부 분석안을 승인함"
            if candidate["status"] == "CONDITIONAL" else None
        ),
        impact_confirmed=True if impact.get("requires_impact_approval") else False,
    )
    preview = service.create_preview(committed["request_id"], "pytest")
    assert preview["validation_status"] in {"PASS", "CONDITIONAL"}
    final = service.approve_final(committed["request_id"], "pytest")
    applied = service.apply(committed["request_id"], final["approval_id"], "pytest")
    assert applied["result"] == "APPLIED"

    report_data = service.get_completion_report_data(committed["request_id"])
    assert report_data["production_bom_modified"] is True
    assert report_data["analysis_summary"]["candidate_count"] > 0
    assert report_data["candidate_evaluations"]
    assert report_data["selected_candidate_details"]
    assert "actions" in report_data["impact_review"]
    assert isinstance(report_data["preview"].get("snapshot"), dict)
    assert isinstance(report_data["apply_result"].get("action_results"), list)

    content = DesignChangeCompletionReportService().build(report_data)
    assert isinstance(content, bytes)
    assert len(content) > 3000
    document = Document(BytesIO(content))
    visible_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    for heading in (
        "1. 완료 요약",
        "3. 변경 전 / 후 확정 내용",
        "5. 후보 분석 및 최종 선정 근거",
        "6. 기술 적합성 검증",
        "7. 공급사 및 원가 평가",
        "8. BOM 수량 및 재고 검증",
        "9. BOM 영향 분석",
        "11. Production E-BOM 적용 결과",
        "12. 최종 결론",
    ):
        assert heading in visible_text
    assert _count(database, "review_boms") == review_bom_before
    assert _count(database, "bom_reviews") == bom_review_before
