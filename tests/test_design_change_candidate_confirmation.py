from __future__ import annotations

import pytest

from database import SQLiteDatabase
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService
from tests.test_design_change_e2e import create_evaluated_replace_with_status, iter_dynamic_replace_contexts


def _service(tmp_path, name: str):
    path = tmp_path / f"{name}.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    return DesignChangeWorkflowService(database), database


def _selection(created: dict, candidate: dict) -> list[dict]:
    return [{
        "action_id": created["actions"][0]["action_id"],
        "candidate_id": candidate["candidate_id"],
        "supplier_item_id": candidate.get("recommended_supplier_item_id"),
    }]


def test_conditional_selection_is_not_saved_before_exception_confirmation(tmp_path):
    service, database = _service(tmp_path, "confirm-conditional")
    _context, created, candidate = create_evaluated_replace_with_status(
        service, database, "CONDITIONAL"
    )
    selections = _selection(created, candidate)

    with pytest.raises(ValueError, match="CONDITIONAL candidate requires"):
        service.confirm_candidate_selection(
            created["request_id"], selections, "pytest"
        )

    request = service.get_result(created["request_id"])
    assert request["actions"][0]["selected_candidate_id"] is None
    assert request["candidate_approval_status"] == "PENDING"

    confirmed = service.confirm_candidate_selection(
        created["request_id"], selections, "pytest",
        exception_reason="추가 기준정보 확보가 불가능하여 조건부 후보를 승인함",
    )
    assert confirmed["workflow_status"] in {"IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED"}
    request = service.get_result(created["request_id"])
    assert request["actions"][0]["selected_candidate_id"] is not None
    assert service.repository.has_approved_exception(created["request_id"]) is True


def test_pass_selection_is_saved_only_on_explicit_confirmation(tmp_path):
    service, database = _service(tmp_path, "confirm-pass")
    _context, created, candidate = create_evaluated_replace_with_status(
        service, database, "PASS"
    )
    before = service.get_result(created["request_id"])
    assert before["actions"][0]["selected_candidate_id"] is None

    confirmed = service.confirm_candidate_selection(
        created["request_id"], _selection(created, candidate), "pytest"
    )
    assert confirmed["workflow_status"] in {"IMPACT_REVIEW_REQUIRED", "CANDIDATE_APPROVED"}
    after = service.get_result(created["request_id"])
    assert after["actions"][0]["selected_candidate_id"] is not None


def test_duplicate_semantic_actions_from_llm_are_collapsed(tmp_path):
    service, database = _service(tmp_path, "dedupe-actions")
    context = next(iter(iter_dynamic_replace_contexts(database)))
    reason = context["reasons"][0]
    action = {"action_type": "REPLACE", "old_item_code": context["source_item_code"]}

    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": f"{reason['alias_text']} 때문에 변경",
            "reasons": [reason["reason_code"]],
            "demand_quantity": 1,
            "requested_by": "pytest",
        },
        [dict(action), dict(action)],
    )
    assert len(created["actions"]) == 1
    persisted = service.get_result(created["request_id"])
    assert len(persisted["actions"]) == 1


def test_additional_demand_can_revalidate_before_candidate_confirmation(tmp_path):
    service, database = _service(tmp_path, "revalidate-demand")
    context = next(iter(iter_dynamic_replace_contexts(database)))
    reason = context["reasons"][0]
    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": reason["alias_text"],
            "reasons": [reason["reason_code"]],
            "requested_by": "pytest",
        },
        [{"action_type": "REPLACE", "old_item_code": context["source_item_code"]}],
    )
    evaluated = service.evaluate_action(created["actions"][0]["action_id"])
    candidate = next(row for row in evaluated["candidates"] if row["status"] != "FAIL")

    result = service.submit_additional_data(
        action_id=created["actions"][0]["action_id"],
        candidate_item_code=candidate["candidate_item_code"],
        attributes={},
        demand_quantity=1,
    )
    assert result["revalidated"] is True
    request = service.get_result(created["request_id"])
    assert request["demand_source"] == "USER"
    assert float(request["demand_quantity"]) == 1.0
    assert request["actions"][0]["selected_candidate_id"] is None
