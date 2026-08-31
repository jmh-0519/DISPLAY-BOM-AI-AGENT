from __future__ import annotations

import pytest

from database import SQLiteDatabase
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService
from tests.design_change_test_support import iter_dynamic_replace_contexts


def _service(tmp_path, name: str):
    path = tmp_path / f"{name}.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    return DesignChangeWorkflowService(database), database


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


def test_distinct_actions_are_rejected_by_request_boundary(tmp_path):
    service, database = _service(tmp_path, "single-action-request")
    context = next(iter(iter_dynamic_replace_contexts(database)))
    reason = context["reasons"][0]
    request = {
        "plant_code": context["plant_code"],
        "version_code": context["version_code"],
        "original_request": reason["alias_text"],
        "reasons": [reason["reason_code"]],
        "requested_by": "pytest",
    }
    with pytest.raises(ValueError, match="exactly one Design Change action"):
        service.create_request(
            request,
            [
                {"action_type": "REPLACE", "old_item_code": context["source_item_code"]},
                {"action_type": "DELETE", "old_item_code": context["source_item_code"]},
            ],
        )


def test_distinct_actions_are_rejected_by_analysis_boundary(tmp_path):
    service, database = _service(tmp_path, "single-action-analysis")
    context = next(iter(iter_dynamic_replace_contexts(database)))
    reason = context["reasons"][0]
    request = {
        "plant_code": context["plant_code"],
        "version_code": context["version_code"],
        "original_request": reason["alias_text"],
        "reasons": [reason["reason_code"]],
        "requested_by": "pytest",
    }
    with pytest.raises(ValueError, match="exactly one Design Change action"):
        service.analyze_candidates(
            request,
            [
                {"action_type": "REPLACE", "old_item_code": context["source_item_code"]},
                {"action_type": "DELETE", "old_item_code": context["source_item_code"]},
            ],
        )
