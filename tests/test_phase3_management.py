import json

import pytest

from app.views.phase3_management_view import history_rows, rule_rows
from database import SchemaManager, SQLiteDatabase
from mcp_server import server
from repositories.design_change_repository import SQLiteDesignChangeRepository
from services.rule_management_service import RuleManagementService
from services.training_export_service import TrainingExportService


def make_repository(tmp_path):
    database = SQLiteDatabase(tmp_path / "management.db")
    SchemaManager(database).initialize()
    with database.transaction() as connection:
        connection.execute("INSERT INTO item_master(item_code,item_type,item_name) VALUES('V-S','VERSION','V')")
        connection.execute("INSERT INTO version_master(version_code) VALUES('V-S')")
        connection.execute("INSERT INTO item_master(item_code,item_type,item_name) VALUES('M-S','MATERIAL','M')")
        connection.execute("INSERT INTO material_master(material_code,material_name) VALUES('M-S','M')")
    return SQLiteDesignChangeRepository(database), database


def test_management_tools_are_registered():
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert {"list_rules", "create_rule", "update_rule", "deactivate_rule",
            "list_phase3_change_history", "record_performance_outcome",
            "export_training_dataset"} <= names


def test_rule_revisions_are_versioned_and_deactivated(tmp_path):
    repository, _ = make_repository(tmp_path)
    service = RuleManagementService(repository)
    rule = {"rule_id": "R-1", "rule_name": "Lifecycle", "target_type": "MATERIAL",
            "change_reason": "EOL", "evaluation_item": "lifecycle", "required_yn": "Y",
            "weight": 10, "valid_from": "2026-01-01", "active_yn": "Y"}
    condition = [{"attribute_name": "lifecycle", "operator": "EQ", "expected_value": "ACTIVE"}]
    assert service.create_revision(rule, condition)["revision_no"] == 1
    assert service.create_revision(rule, condition)["revision_no"] == 2
    assert service.deactivate("R-1", 1)["active_yn"] == "N"
    assert len(service.list_rules()) == 2


def test_rule_validation_rejects_invalid_inputs(tmp_path):
    repository, _ = make_repository(tmp_path)
    with pytest.raises(ValueError):
        RuleManagementService(repository).create_revision({"weight": -1}, [])


def test_performance_and_export_are_applied_only_and_anonymized(tmp_path):
    repository, database = make_repository(tmp_path)
    repository.create_request({
        "request_id": "REQ-SECRET", "version_code": "V-S",
        "original_request": "supplier ACME secret", "normalized_request": "private",
        "reasons": ["supplier ACME secret"], "as_of_date": "2026-08-14",
        "effective_date": "2026-08-15", "demand_source": "UNAVAILABLE",
        "requested_by": "person@example.com",
    }, [{"action_id": "A-S", "action_type": "DELETE", "target_type": "MATERIAL",
         "parent_item_code": "V-S", "old_item_code": "M-S"}])
    with pytest.raises(ValueError):
        repository.record_performance("REQ-SECRET", 30, {}, 5, "2026-09-13")
    with database.transaction() as connection:
        connection.execute("UPDATE change_requests SET apply_status='APPLIED' WHERE request_id='REQ-SECRET'")
        connection.execute(
            """INSERT INTO change_approvals(approval_id,request_id,approval_stage,
               decision,decision_reason,selection_json,approved_by)
               VALUES('APR-SECRET','REQ-SECRET','CANDIDATE','APPROVED',
                      'supplier ACME secret','{}','person@example.com')"""
        )
    repository.record_performance("REQ-SECRET", 30,
                                  {"cost_delta": -3, "supplier_name": "ACME"}, 5, "2026-09-13")
    result = TrainingExportService(repository).export_jsonl(
        date_from=None, date_to=None, created_by="auditor")
    payload = json.loads(result["jsonl"])
    assert result["record_count"] == 1
    assert "REQ-SECRET" not in result["jsonl"]
    assert "ACME" not in result["jsonl"]
    assert "person@example.com" not in result["jsonl"]
    assert payload["input"]["reasons"] == ["OTHER"]
    assert payload["feedback"]["approvals"] == [{
        "approval_stage": "CANDIDATE", "decision": "APPROVED", "reason_present": True,
    }]
    assert payload["feedback"]["outcomes"][0]["outcome_json"] == {"cost_delta": -3}


def test_management_view_rows_are_stable():
    assert rule_rows([{"rule_id": "R", "weight": 1}])[0]["rule_id"] == "R"
    assert history_rows([{"request_id": "Q", "apply_status": "APPLIED"}])[0]["apply_status"] == "APPLIED"
