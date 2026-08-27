from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, timedelta

from database import SQLiteDatabase


class SQLiteMultiActionRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_apply_context(self, request_id: str) -> dict | None:
        with self.database.connection() as connection:
            request = connection.execute(
                "SELECT * FROM change_requests WHERE request_id=?", (request_id,),
            ).fetchone()
            if not request:
                return None
            result = dict(request)
            result["actions"] = [dict(row) for row in connection.execute(
                "SELECT * FROM change_actions WHERE request_id=? ORDER BY action_seq",
                (request_id,),
            )]
            result["approvals"] = [dict(row) for row in connection.execute(
                "SELECT * FROM change_approvals WHERE request_id=? ORDER BY approved_at",
                (request_id,),
            )]
            preview = connection.execute(
                """SELECT * FROM change_previews WHERE request_id=?
                   ORDER BY preview_revision DESC LIMIT 1""",
                (request_id,),
            ).fetchone()
            result["preview"] = dict(preview) if preview else None
        return result

    @contextmanager
    def transaction(self):
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _active_relation(connection, action: dict, effective_date: str):
        old_code = action.get("old_item_code")
        if not old_code:
            return None
        rows = connection.execute(
            """SELECT * FROM bom_master WHERE plant_code=?
               AND parent_item_code=? AND child_item_code=?
               AND location_code=? AND status='ACTIVE' AND valid_from<=?
               AND (valid_to IS NULL OR valid_to>=?)""",
            (
                action["plant_code"], action["parent_item_code"], old_code,
                action["location_code"],
                effective_date, effective_date,
            ),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("Active BOM relation must exist exactly once")
        return rows[0]

    @staticmethod
    def validate_action(connection: sqlite3.Connection, action: dict, effective_date: str) -> None:
        expected_type = "ASSEMBLY" if action["target_type"] == "ASSY" else "MATERIAL"
        parent = connection.execute(
            "SELECT item_type,active_yn FROM item_master WHERE item_code=?",
            (action["parent_item_code"],),
        ).fetchone()
        if not parent or parent["item_type"] not in {"VERSION", "ASSEMBLY"} or parent["active_yn"] != "Y":
            raise ValueError("Action parent must be an active VERSION or ASSEMBLY")
        for field in ("old_item_code", "new_item_code"):
            item_code = action.get(field)
            if not item_code:
                continue
            item = connection.execute(
                "SELECT item_type,active_yn FROM item_master WHERE item_code=?", (item_code,),
            ).fetchone()
            if not item or item["item_type"] != expected_type or item["active_yn"] != "Y":
                raise ValueError(f"{field} does not match target_type or is inactive")
        if action["action_type"] == "REPLACE" and action["old_item_code"] == action["new_item_code"]:
            raise ValueError("Existing and replacement items must differ")
        if action["action_type"] in {"REPLACE", "ADD"}:
            candidate = connection.execute(
                """SELECT 1 FROM candidate_evaluations
                   WHERE candidate_id=? AND action_id=? AND candidate_item_code=?
                     AND final_status=?""",
                (
                    action.get("selected_candidate_id"), action["action_id"],
                    action.get("new_item_code"), action["evaluation_status"],
                ),
            ).fetchone()
            if not candidate:
                raise ValueError("Selected candidate no longer matches the approved action")
            supplier_item_id = action.get("selected_supplier_item_id")
            if supplier_item_id is not None:
                supplier = connection.execute(
                    "SELECT 1 FROM supplier_items WHERE supplier_item_id=? AND item_code=?",
                    (supplier_item_id, action["new_item_code"]),
                ).fetchone()
                if not supplier:
                    raise ValueError("Selected supplier no longer matches the approved candidate")
        child_code = action.get("new_item_code")
        if action["action_type"] in {"REPLACE", "ADD"}:
            duplicate = connection.execute(
                """SELECT 1 FROM bom_master
                   WHERE plant_code=? AND parent_item_code=?
                     AND child_item_code=? AND location_code=?
                     AND status='ACTIVE' AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?) LIMIT 1""",
                (
                    action["plant_code"], action["parent_item_code"], child_code,
                    action["location_code"],
                    effective_date, effective_date,
                ),
            ).fetchone()
            if duplicate:
                raise ValueError("Target item is already active at the same BOM location")
            if expected_type == "ASSEMBLY":
                cycle = connection.execute(
                    """WITH RECURSIVE descendants(item_code) AS (
                         SELECT child_item_code FROM bom_master
                         WHERE plant_code=? AND parent_item_code=? AND status='ACTIVE'
                           AND valid_from<=? AND (valid_to IS NULL OR valid_to>=?)
                         UNION
                         SELECT b.child_item_code FROM bom_master b
                         JOIN descendants d ON b.parent_item_code=d.item_code
                         WHERE b.plant_code=? AND b.status='ACTIVE' AND b.valid_from<=?
                           AND (b.valid_to IS NULL OR b.valid_to>=?)
                       ) SELECT 1 FROM descendants WHERE item_code=? LIMIT 1""",
                    (
                        action["plant_code"], child_code, effective_date, effective_date,
                        action["plant_code"],
                        effective_date, effective_date, action["parent_item_code"],
                    ),
                ).fetchone()
                if cycle:
                    raise ValueError("BOM cycle would be created")

    @staticmethod
    def validate_hierarchy(connection: sqlite3.Connection, action: dict) -> None:
        child_code = (
            action.get("new_item_code") if action["action_type"] in {"REPLACE", "ADD"}
            else action.get("old_item_code")
        )
        row = connection.execute(
            """SELECT p.item_type AS parent_type,
                      COALESCE(pa.process_name,'') AS parent_process,
                      c.item_type AS child_type,
                      COALESCE(ca.process_name,'') AS child_process
               FROM item_master p JOIN item_master c
               LEFT JOIN assembly_master pa ON pa.assembly_code=p.item_code
               LEFT JOIN assembly_master ca ON ca.assembly_code=c.item_code
               WHERE p.item_code=? AND c.item_code=?""",
            (action["parent_item_code"], child_code),
        ).fetchone()
        allowed = row and connection.execute(
            """SELECT 1 FROM bom_hierarchy_rules
               WHERE parent_type=? AND parent_process=? AND child_type=? AND child_process=?
                 AND active_yn='Y'""",
            (row["parent_type"], row["parent_process"], row["child_type"], row["child_process"]),
        ).fetchone()
        if not allowed:
            raise ValueError("Parent-child BOM hierarchy is not allowed")

    def apply_action(self, connection: sqlite3.Connection, action: dict, effective_date: str) -> dict:
        action_type = action["action_type"]
        effective = date.fromisoformat(effective_date)
        self.validate_action(connection, action, effective_date)
        self.validate_hierarchy(connection, action)
        old = None if action_type == "ADD" else self._active_relation(connection, action, effective_date)
        if action_type in {"REPLACE", "DELETE", "QUANTITY_CHANGE"}:
            assert old is not None
            old_valid_from = date.fromisoformat(str(old["valid_from"]))
            if effective <= old_valid_from:
                # The active relation may have been created earlier on the same
                # effective date (for example REPLACE followed by DELETE during
                # one day's UI acceptance). An inclusive valid_to cannot be set
                # to effective-1 without violating valid_to >= valid_from. There
                # is no historical day to preserve, so remove that zero-duration
                # production row. The approved Request/Preview/Apply evidence
                # remains persisted in the design-change audit tables.
                connection.execute(
                    "DELETE FROM bom_master WHERE bom_id=?",
                    (old["bom_id"],),
                )
            else:
                connection.execute(
                    """UPDATE bom_master SET valid_to=?,row_revision=row_revision+1,
                       updated_at=CURRENT_TIMESTAMP WHERE bom_id=?""",
                    ((effective - timedelta(days=1)).isoformat(), old["bom_id"]),
                )
        if action_type == "DELETE":
            return {"action_id": action["action_id"], "result": "DELETED"}

        child_code = (
            action["new_item_code"] if action_type in {"REPLACE", "ADD"}
            else action["old_item_code"]
        )
        if not child_code:
            raise ValueError("Action requires a target item")
        quantity = (
            action["new_quantity"] if action_type in {"ADD", "QUANTITY_CHANGE"}
            else old["quantity"]
        )
        if quantity is None or float(quantity) <= 0:
            raise ValueError("New quantity must be greater than zero")
        sequence = int(old["sequence_no"]) if old else connection.execute(
            """SELECT COALESCE(MAX(sequence_no),0)+1 FROM bom_master
               WHERE plant_code=? AND parent_item_code=?""",
            (action["plant_code"], action["parent_item_code"]),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO bom_master(plant_code,parent_item_code,child_item_code,location_code,
               sequence_no,quantity,valid_from,valid_to,row_revision,status)
               VALUES(?,?,?,?,?,?,?,NULL,1,'ACTIVE')""",
            (
                action["plant_code"], action["parent_item_code"], child_code,
                action["location_code"],
                sequence, quantity, effective_date,
            ),
        )
        return {"action_id": action["action_id"], "result": action_type}

    @staticmethod
    def finish_apply(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        preview_id: str,
        approval_id: str,
        applied_by: str,
        action_results: list[dict],
    ) -> str:
        apply_id = f"APPLY-{uuid.uuid4().hex[:12].upper()}"
        connection.execute(
            """INSERT INTO change_apply_results(apply_id,request_id,plant_code,preview_id,
               final_approval_id,result,applied_by,result_json)
               VALUES(?,?,?,?,?, 'APPLIED',?,?)""",
            (
                apply_id, request_id,
                connection.execute(
                    "SELECT plant_code FROM change_requests WHERE request_id=?",
                    (request_id,),
                ).fetchone()[0],
                preview_id, approval_id, applied_by, json.dumps(action_results),
            ),
        )
        connection.execute(
            """UPDATE change_requests SET workflow_status='APPLIED',apply_status='APPLIED',
               row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
            (request_id,),
        )
        return apply_id
