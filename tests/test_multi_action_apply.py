import json

import pytest

from database import SQLiteDatabase, SchemaManager
from repositories.multi_action_repository import SQLiteMultiActionRepository
from services.multi_action_change_service import MultiActionApplyService
from services.phase3_workflow_service import Phase3WorkflowService
from repositories.design_change_repository import SQLiteDesignChangeRepository


def setup_request(tmp_path, statuses=("PASS", "PASS")):
    database = SQLiteDatabase(tmp_path / "actions.db")
    SchemaManager(database).initialize()
    with database.transaction() as con:
        for code, item_type in (
            ("FA", "VERSION"), ("OLD", "MATERIAL"), ("NEW", "MATERIAL"),
            ("ADD", "MATERIAL"), ("QTY", "MATERIAL"),
        ):
            con.execute("INSERT INTO item_master(item_code,item_type,item_name) VALUES(?,?,?)", (code, item_type, code))
            if item_type == "VERSION":
                con.execute("INSERT INTO version_master(version_code) VALUES(?)", (code,))
            else:
                con.execute("INSERT INTO material_master(material_code,material_name) VALUES(?,?)", (code, code))
        con.executemany(
            """INSERT INTO bom_master(parent_item_code,child_item_code,location_code,
               sequence_no,quantity,valid_from,status) VALUES('FA',?,'N/A',?,?,?, 'ACTIVE')""",
            [("OLD", 1, 1, "2026-01-01"), ("QTY", 2, 1, "2026-01-01")],
        )
        con.execute(
            """INSERT INTO change_requests(request_id,version_code,as_of_date,effective_date,
               demand_source,requested_by,workflow_status,candidate_approval_status,
               final_approval_status) VALUES('REQ','FA','2026-08-14','2026-08-20',
               'USER','tester','FINAL_APPROVED','APPROVED','APPROVED')"""
        )
        actions = [
            ("A1", 1, "REPLACE", "OLD", "NEW", 1, 1, statuses[0]),
            ("A2", 2, "QUANTITY_CHANGE", "QTY", None, 1, 3, statuses[1]),
        ]
        for action_id, seq, kind, old, new, old_qty, new_qty, status in actions:
            con.execute(
                """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
                   target_type,parent_item_code,old_item_code,new_item_code,location_code,
                   old_quantity,new_quantity,evaluation_status)
                   VALUES(?,'REQ',?,?,'MATERIAL','FA',?,?,'N/A',?,?,?)""",
                (action_id, seq, kind, old, new, old_qty, new_qty, status),
            )
        con.execute("UPDATE change_actions SET selected_candidate_id='C1' WHERE action_id='A1'")
        con.execute(
            """INSERT INTO candidate_evaluations(
               candidate_id,action_id,candidate_item_code,final_status,total_score,grade)
               VALUES('C1','A1','NEW',? ,100,'S')""",
            (statuses[0] if statuses[0] in {"PASS", "CONDITIONAL", "FAIL"} else "PASS",),
        )
        snapshot = _snapshot(con)
        con.execute(
            """INSERT INTO change_previews(preview_id,request_id,preview_revision,
               validation_status,snapshot_json,created_by)
               VALUES('PRE','REQ',1,'PASS',?,'tester')""",
            (json.dumps(snapshot),),
        )
        con.execute(
            """INSERT INTO change_approvals(approval_id,request_id,approval_stage,
               decision,selection_json,approved_by) VALUES('APP-C','REQ','CANDIDATE',
               'APPROVED','{}','tester')"""
        )
        con.execute(
            """INSERT INTO change_approvals(approval_id,request_id,approval_stage,
               decision,selection_json,approved_by) VALUES('APP-F','REQ','FINAL_APPLY',
               'APPROVED','{"preview_id":"PRE"}','tester')"""
        )
    return database


def _snapshot(connection):
    keys = (
        "action_id", "action_type", "target_type", "parent_item_code",
        "old_item_code", "new_item_code", "old_quantity", "new_quantity",
        "location_code", "evaluation_status", "selected_candidate_id",
        "selected_supplier_item_id", "row_revision",
    )
    actions = []
    for row in connection.execute(
        "SELECT * FROM change_actions WHERE request_id='REQ' ORDER BY action_seq"
    ):
        value = {key: row[key] for key in keys}
        if row["action_type"] != "ADD":
            relation = connection.execute(
                """SELECT bom_id,row_revision,quantity FROM bom_master
                   WHERE parent_item_code=? AND child_item_code=? AND location_code=?
                     AND status='ACTIVE' AND valid_to IS NULL""",
                (row["parent_item_code"], row["old_item_code"], row["location_code"]),
            ).fetchone()
            value.update({
                "source_bom_id": relation["bom_id"],
                "source_bom_row_revision": relation["row_revision"],
                "source_bom_quantity": relation["quantity"],
            })
        actions.append(value)
    return {"actions": actions}


def refresh_preview(database):
    with database.transaction() as con:
        con.execute(
            "UPDATE change_previews SET snapshot_json=? WHERE preview_id='PRE'",
            (json.dumps(_snapshot(con)),),
        )


def active_children(database):
    with database.connection() as con:
        return {row["child_item_code"]: row["quantity"] for row in con.execute(
            "SELECT child_item_code,quantity FROM bom_master WHERE parent_item_code='FA' AND status='ACTIVE' AND valid_to IS NULL"
        )}


def test_multiple_actions_apply_in_one_transaction(tmp_path):
    database = setup_request(tmp_path)
    result = MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )
    assert result["result"] == "APPLIED"
    assert active_children(database) == {"NEW": 1, "QTY": 3}
    with database.connection() as con:
        assert con.execute("SELECT COUNT(*) FROM change_apply_results").fetchone()[0] == 1


def test_fail_action_blocks_all_changes(tmp_path):
    database = setup_request(tmp_path, statuses=("PASS", "FAIL"))
    with pytest.raises(ValueError, match="FAIL action"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_conditional_requires_exception_reason(tmp_path):
    database = setup_request(tmp_path, statuses=("PASS", "CONDITIONAL"))
    service = MultiActionApplyService(SQLiteMultiActionRepository(database))
    with pytest.raises(ValueError, match="exception reason"):
        service.apply(request_id="REQ", final_approval_id="APP-F", applied_by="tester")
    with database.transaction() as con:
        con.execute(
            """INSERT INTO change_approvals(approval_id,request_id,approval_stage,decision,
               decision_reason,selection_json,approved_by) VALUES(
               'APP-E','REQ','CONDITIONAL_EXCEPTION','APPROVED','verified exception','{}','tester')"""
        )
    assert service.apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )["result"] == "APPLIED"


def test_mid_apply_failure_rolls_back_every_action(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("UPDATE change_actions SET new_quantity=0 WHERE action_id='A2'")
    refresh_preview(database)
    with pytest.raises(ValueError, match="quantity"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_add_and_delete_actions(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("DELETE FROM candidate_evaluations WHERE action_id IN ('A1','A2')")
        con.execute("DELETE FROM change_actions WHERE request_id='REQ'")
        con.execute(
            """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
               target_type,parent_item_code,old_item_code,location_code,evaluation_status)
               VALUES('D1','REQ',1,'DELETE','MATERIAL','FA','OLD','N/A','PASS')"""
        )
        con.execute(
            """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
               target_type,parent_item_code,new_item_code,location_code,new_quantity,evaluation_status)
               VALUES('N1','REQ',2,'ADD','MATERIAL','FA','ADD','N/A',2,'PASS')"""
        )
        con.execute("UPDATE change_actions SET selected_candidate_id='C-ADD' WHERE action_id='N1'")
        con.execute(
            """INSERT INTO candidate_evaluations(
               candidate_id,action_id,candidate_item_code,final_status,total_score,grade)
               VALUES('C-ADD','N1','ADD','PASS',100,'S')"""
        )
    refresh_preview(database)
    MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )
    assert active_children(database) == {"QTY": 1, "ADD": 2}


def test_both_approval_gates_are_required(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("DELETE FROM change_approvals WHERE approval_stage='CANDIDATE'")
    service = MultiActionApplyService(SQLiteMultiActionRepository(database))
    with pytest.raises(ValueError, match="Candidate approval"):
        service.apply(request_id="REQ", final_approval_id="APP-F", applied_by="tester")


def test_pending_action_cannot_be_applied(tmp_path):
    database = setup_request(tmp_path, statuses=("PENDING", "PASS"))
    with pytest.raises(ValueError, match="Every action"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_final_approval_must_match_latest_preview(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute(
            """INSERT INTO change_previews(preview_id,request_id,preview_revision,
               validation_status,snapshot_json,created_by)
               VALUES('PRE-2','REQ',2,'PASS',?,'tester')""",
            (json.dumps(_snapshot(con)),),
        )
    with pytest.raises(ValueError, match="latest preview"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_apply_rejects_target_type_mismatch(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("INSERT INTO item_master(item_code,item_type,item_name) VALUES('ASSY-X','ASSEMBLY','OLB')")
        con.execute("INSERT INTO assembly_master(assembly_code,process_name) VALUES('ASSY-X','OLB')")
        con.execute("UPDATE change_actions SET new_item_code='ASSY-X' WHERE action_id='A1'")
    refresh_preview(database)
    with pytest.raises(ValueError, match="target_type"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_add_rejects_existing_active_relation(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("DELETE FROM candidate_evaluations WHERE action_id IN ('A1','A2')")
        con.execute("DELETE FROM change_actions WHERE request_id='REQ'")
        con.execute(
            """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
               target_type,parent_item_code,new_item_code,location_code,new_quantity,
               evaluation_status,selected_candidate_id)
               VALUES('N1','REQ',1,'ADD','MATERIAL','FA','QTY','N/A',2,'PASS','C-QTY')"""
        )
        con.execute(
            """INSERT INTO candidate_evaluations(
               candidate_id,action_id,candidate_item_code,final_status,total_score,grade)
               VALUES('C-QTY','N1','QTY','PASS',100,'S')"""
        )
    refresh_preview(database)
    with pytest.raises(ValueError, match="already active"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_candidate_from_another_request_cannot_be_approved(tmp_path):
    database = SQLiteDatabase(tmp_path / "ownership.db")
    SchemaManager(database).initialize()
    with database.transaction() as con:
        for code, item_type in (("FA", "VERSION"), ("OLD", "MATERIAL"), ("NEW", "MATERIAL")):
            con.execute("INSERT INTO item_master(item_code,item_type,item_name) VALUES(?,?,?)", (code, item_type, code))
            if item_type == "VERSION":
                con.execute("INSERT INTO version_master(version_code) VALUES(?)", (code,))
            else:
                con.execute("INSERT INTO material_master(material_code,material_name) VALUES(?,?)", (code, code))
    repository = SQLiteDesignChangeRepository(database)
    base = {
        "version_code": "FA", "as_of_date": "2026-08-14",
        "effective_date": "2026-08-20", "demand_source": "UNAVAILABLE",
        "requested_by": "tester", "reasons": ["EOL"],
    }
    repository.create_request({**base, "request_id": "REQ-A"}, [{
        "action_id": "ACT-A", "action_type": "REPLACE", "target_type": "MATERIAL",
        "parent_item_code": "FA", "old_item_code": "OLD", "location_code": "N/A",
    }])
    repository.create_request({**base, "request_id": "REQ-B"}, [{
        "action_id": "ACT-B", "action_type": "REPLACE", "target_type": "MATERIAL",
        "parent_item_code": "FA", "old_item_code": "OLD", "location_code": "N/A",
    }])
    repository.save_candidate_evaluations("ACT-A", [{
        "candidate_item_code": "NEW", "status": "PASS", "total_score": 100,
        "grade": "S", "rank": 1,
    }])
    with pytest.raises(ValueError, match="every REPLACE/ADD"):
        Phase3WorkflowService(database).select_and_approve_candidates(
            "REQ-B", [{"action_id": "ACT-A", "candidate_id": "ACT-A-C1"}], "tester",
        )


def test_production_bom_change_after_preview_blocks_apply(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute(
            """UPDATE bom_master SET quantity=9,row_revision=row_revision+1
               WHERE parent_item_code='FA' AND child_item_code='OLD' AND valid_to IS NULL"""
        )
    with pytest.raises(ValueError, match="changed after preview"):
        MultiActionApplyService(SQLiteMultiActionRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
