import json

import pytest

from database import SQLiteDatabase, SchemaManager
from repositories.design_change_apply_repository import SQLiteDesignChangeApplyRepository
from services.design_change_apply_service import AtomicDesignChangeApplyService
from services.design_change_workflow_service import DesignChangeWorkflowService
from repositories.design_change_repository import SQLiteDesignChangeRepository


def setup_request(
    tmp_path,
    *,
    status="PASS",
    action_type="REPLACE",
    old_item="OLD",
    new_item="NEW",
    new_quantity=1,
):
    database = SQLiteDatabase(tmp_path / "actions.db")
    SchemaManager(database).initialize()
    with database.transaction() as con:
        for code, item_type in (
            ("FA", "VERSION"), ("OLD", "MATERIAL"), ("NEW", "MATERIAL"),
            ("ADD", "MATERIAL"), ("QTY", "MATERIAL"),
        ):
            con.execute(
                "INSERT INTO item_master(item_code,item_type,item_name) VALUES(?,?,?)",
                (code, item_type, code),
            )
            if item_type == "VERSION":
                con.execute("INSERT INTO version_master(version_code) VALUES(?)", (code,))
            else:
                con.execute(
                    "INSERT INTO material_master(material_code,material_name) VALUES(?,?)",
                    (code, code),
                )
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

        selected_candidate_id = None
        if action_type in {"REPLACE", "ADD"}:
            selected_candidate_id = "C1"
        action_old = None if action_type == "ADD" else old_item
        action_new = new_item if action_type in {"REPLACE", "ADD"} else None
        old_quantity = None if action_type == "ADD" else 1
        action_new_quantity = new_quantity if action_type in {"ADD", "QUANTITY_CHANGE"} else 1
        con.execute(
            """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
               target_type,parent_item_code,old_item_code,new_item_code,location_code,
               old_quantity,new_quantity,evaluation_status,selected_candidate_id)
               VALUES('A1','REQ',1,?,'MATERIAL','FA',?,?,'N/A',?,?,?,?)""",
            (
                action_type,
                action_old,
                action_new,
                old_quantity,
                action_new_quantity,
                status,
                selected_candidate_id,
            ),
        )
        if selected_candidate_id:
            con.execute(
                """INSERT INTO candidate_evaluations(
                   candidate_id,action_id,candidate_item_code,final_status,total_score,grade)
                   VALUES('C1','A1',?,?,100,'S')""",
                (action_new, status if status in {"PASS", "CONDITIONAL", "FAIL"} else "PASS"),
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
        return {
            row["child_item_code"]: row["quantity"]
            for row in con.execute(
                "SELECT child_item_code,quantity FROM bom_master "
                "WHERE parent_item_code='FA' AND status='ACTIVE' AND valid_to IS NULL"
            )
        }


def test_apply_rejects_multiple_actions_per_request(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute(
            """INSERT INTO change_actions(action_id,request_id,action_seq,action_type,
               target_type,parent_item_code,old_item_code,location_code,old_quantity,
               new_quantity,evaluation_status)
               VALUES('A2','REQ',2,'QUANTITY_CHANGE','MATERIAL','FA','QTY','N/A',1,3,'PASS')"""
        )
    refresh_preview(database)

    with pytest.raises(ValueError, match="exactly one action"):
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_fail_action_blocks_apply(tmp_path):
    database = setup_request(tmp_path, status="FAIL")
    with pytest.raises(ValueError, match="FAIL action"):
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_conditional_requires_exception_reason(tmp_path):
    database = setup_request(tmp_path, status="CONDITIONAL")
    service = AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database))
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


def test_mid_apply_failure_rolls_back_transaction(tmp_path, monkeypatch):
    database = setup_request(tmp_path)
    repository = SQLiteDesignChangeApplyRepository(database)

    def fail_after_partial_write(connection, action, effective_date):
        connection.execute(
            "UPDATE bom_master SET quantity=99 WHERE parent_item_code='FA' AND child_item_code='OLD'"
        )
        raise RuntimeError("forced mid-apply failure")

    monkeypatch.setattr(repository, "apply_action", fail_after_partial_write)
    with pytest.raises(RuntimeError, match="forced mid-apply"):
        AtomicDesignChangeApplyService(repository).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_add_action_applies(tmp_path):
    database = setup_request(tmp_path, action_type="ADD", old_item=None, new_item="ADD", new_quantity=2)
    result = AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )
    assert result["result"] == "APPLIED"
    assert active_children(database) == {"OLD": 1, "QTY": 1, "ADD": 2}


def test_delete_action_applies(tmp_path):
    database = setup_request(tmp_path, action_type="DELETE", old_item="OLD", new_item=None)
    result = AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )
    assert result["result"] == "APPLIED"
    assert active_children(database) == {"QTY": 1}


def test_both_approval_gates_are_required(tmp_path):
    database = setup_request(tmp_path)
    with database.transaction() as con:
        con.execute("DELETE FROM change_approvals WHERE approval_stage='CANDIDATE'")
    service = AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database))
    with pytest.raises(ValueError, match="Candidate approval"):
        service.apply(request_id="REQ", final_approval_id="APP-F", applied_by="tester")


def test_pending_action_cannot_be_applied(tmp_path):
    database = setup_request(tmp_path, status="PENDING")
    with pytest.raises(ValueError, match="Every action"):
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
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
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
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
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )
    assert active_children(database) == {"OLD": 1, "QTY": 1}


def test_add_rejects_existing_active_relation(tmp_path):
    database = setup_request(tmp_path, action_type="ADD", old_item=None, new_item="QTY", new_quantity=2)
    with pytest.raises(ValueError, match="already active"):
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
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
        DesignChangeWorkflowService(database).select_and_approve_candidates(
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
        AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
            request_id="REQ", final_approval_id="APP-F", applied_by="tester",
        )


def test_delete_same_effective_day_relation_does_not_break_validity_constraint(tmp_path):
    database = setup_request(tmp_path, action_type="DELETE", old_item="OLD", new_item=None)
    with database.transaction() as con:
        con.execute(
            """UPDATE bom_master SET valid_from='2026-08-20',valid_to=NULL,status='ACTIVE'
               WHERE parent_item_code='FA' AND child_item_code='OLD'"""
        )
    refresh_preview(database)

    result = AtomicDesignChangeApplyService(SQLiteDesignChangeApplyRepository(database)).apply(
        request_id="REQ", final_approval_id="APP-F", applied_by="tester",
    )

    assert result["result"] == "APPLIED"
    with database.connection() as con:
        remaining = con.execute(
            """SELECT COUNT(*) FROM bom_master
               WHERE parent_item_code='FA' AND child_item_code='OLD'"""
        ).fetchone()[0]
    assert remaining == 0
