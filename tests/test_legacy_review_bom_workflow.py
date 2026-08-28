from __future__ import annotations

import shutil

import pytest

from database import SQLiteDatabase
from mcp_server.capabilities.design_change import (
    apply_reviewed_bom_data,
    create_ai_change_request_data,
    create_review_bom_data,
    generate_design_change_report_data,
    run_ai_bom_review_data,
)
from mcp_server.capabilities.query import get_bom_data
from services.sqlite_production_bom_service import SQLiteProductionBomService


@pytest.fixture
def runtime_db(tmp_path, monkeypatch):
    source = "data/test_display_bom.db"
    target = tmp_path / "display_bom.db"
    shutil.copy2(source, target)
    monkeypatch.setenv("BOM_SQLITE_PATH", str(target))
    return SQLiteDatabase(target)


def _workflow(runtime_db):
    before = get_bom_data("LTA400HR01-001", "2026-08-13")
    assert before
    request = create_ai_change_request_data(
        product_id="LTA400HR01-001",
        old_material_id="0001-200004",
        new_material_id="9000-290002",
        reason="STEP25 SQLite E2E",
        effective_date="2026-08-20",
        requested_by="TESTER",
        as_of_date="2026-08-13",
    )
    assert request["success"] is True
    review = create_review_bom_data(
        change_id=request["change_id"], created_by="TESTER", created_date="2026-08-13"
    )
    assert review["result"] == "REVIEW_CREATED"
    evaluation = run_ai_bom_review_data(
        review_id=review["review_id"], reviewed_by="BOM_AI_AGENT", checked_date="2026-08-13"
    )
    assert evaluation["ai_review_result"] == "PASS"
    report = generate_design_change_report_data(change_id=request["change_id"])
    assert report["success"] is True
    assert report["review"]["approved_revision"] == 1
    return request, review


def test_all_workflow_mcp_capabilities_use_sqlite(runtime_db):
    request, review = _workflow(runtime_db)
    applied = apply_reviewed_bom_data(
        review_id=review["review_id"], applied_by="TESTER", applied_date="2026-08-20"
    )
    assert applied["result"] == "APPLIED"
    with runtime_db.connection() as con:
        assert con.execute(
            "SELECT apply_status FROM design_changes WHERE change_id=?", (request["change_id"],)
        ).fetchone()[0] == "APPLIED"
        assert con.execute(
            "SELECT COUNT(*) FROM production_apply_history WHERE change_id=? AND apply_result='SUCCEEDED'",
            (request["change_id"],),
        ).fetchone()[0] == 1


def test_sqlite_apply_rolls_back_bom_and_workflow(runtime_db, monkeypatch):
    request, review = _workflow(runtime_db)
    service = SQLiteProductionBomService(runtime_db)

    def fail(_connection):
        raise RuntimeError("forced rollback")

    monkeypatch.setattr(service, "_before_commit", fail)
    with pytest.raises(RuntimeError, match="forced rollback"):
        service.apply_approved_review(
            review_id=review["review_id"], applied_by="TESTER", applied_date="2026-08-20"
        )
    with runtime_db.connection() as con:
        assert con.execute(
            "SELECT apply_status FROM design_changes WHERE change_id=?", (request["change_id"],)
        ).fetchone()[0] == "APPROVED_TO_APPLY"
        assert con.execute(
            "SELECT COUNT(*) FROM production_apply_history WHERE change_id=?", (request["change_id"],)
        ).fetchone()[0] == 0


def test_unapproved_review_cannot_apply(runtime_db):
    request = create_ai_change_request_data(
        product_id="LTA400HR01-001", old_material_id="0001-200004",
        new_material_id="9000-290002", reason="approval guard",
        effective_date="2026-08-20", requested_by="TESTER", as_of_date="2026-08-13",
    )
    review = create_review_bom_data(
        change_id=request["change_id"], created_by="TESTER", created_date="2026-08-13"
    )
    with pytest.raises(ValueError, match="APPROVED"):
        apply_reviewed_bom_data(
            review_id=review["review_id"], applied_by="TESTER", applied_date="2026-08-20"
        )

