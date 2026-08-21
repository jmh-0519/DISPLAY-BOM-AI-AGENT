from __future__ import annotations

import json


class MultiActionApplyService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def apply(
        self,
        *,
        request_id: str,
        final_approval_id: str,
        applied_by: str,
    ) -> dict:
        context = self.repository.get_apply_context(request_id)
        if not context:
            raise ValueError("Change request not found")
        actions = context["actions"]
        if not actions:
            raise ValueError("Change request has no actions")
        if context["apply_status"] != "NOT_APPLIED":
            raise ValueError("Change request was already applied or blocked")
        if any(action["evaluation_status"] == "FAIL" for action in actions):
            raise ValueError("FAIL action blocks the entire apply")
        if any(action["evaluation_status"] not in {"PASS", "CONDITIONAL"} for action in actions):
            raise ValueError("Every action must be PASS or CONDITIONAL before apply")
        if any(action["action_type"] in {"REPLACE", "ADD"} and
               not action.get("selected_candidate_id") for action in actions):
            raise ValueError("Every REPLACE/ADD action requires a selected candidate")
        approvals = context["approvals"]
        candidate_approval = next((value for value in approvals if
            value["approval_stage"] == "CANDIDATE" and value["decision"] == "APPROVED"), None)
        final_approval = next((value for value in approvals if
            value["approval_id"] == final_approval_id and
            value["approval_stage"] == "FINAL_APPLY" and value["decision"] == "APPROVED"), None)
        if candidate_approval is None:
            raise ValueError("Candidate approval is required")
        if final_approval is None:
            raise ValueError("Matching final apply approval is required")
        if any(action["evaluation_status"] == "CONDITIONAL" for action in actions):
            exception = next((value for value in approvals if
                value["approval_stage"] == "CONDITIONAL_EXCEPTION" and
                value["decision"] == "APPROVED" and value.get("decision_reason")), None)
            if exception is None:
                raise ValueError("CONDITIONAL action requires an exception reason")
        preview = context.get("preview")
        if not preview or preview["validation_status"] == "FAIL":
            raise ValueError("A valid final preview is required")
        approved_selection = json.loads(final_approval.get("selection_json") or "{}")
        if approved_selection.get("preview_id") != preview["preview_id"]:
            raise ValueError("Final approval does not match the latest preview")
        snapshot = json.loads(preview.get("snapshot_json") or "{}")
        snapshot_actions = {
            value.get("action_id"): value for value in snapshot.get("actions", [])
        }
        snapshot_keys = (
            "action_type", "target_type", "parent_item_code", "old_item_code",
            "new_item_code", "old_quantity", "new_quantity", "location_code",
            "evaluation_status", "selected_candidate_id", "selected_supplier_item_id",
            "row_revision",
        )
        if set(snapshot_actions) != {action["action_id"] for action in actions}:
            raise ValueError("Preview action set is stale")
        for action in actions:
            if action.get("plant_code") != context.get("plant_code"):
                raise ValueError("Action PLANT does not match the request PLANT")
            approved_action = snapshot_actions[action["action_id"]]
            if any(approved_action.get(key) != action.get(key) for key in snapshot_keys):
                raise ValueError("Action changed after preview; create and approve a new preview")
            if action["action_type"] != "ADD":
                with self.repository.database.connection() as connection:
                    current = connection.execute(
                        """SELECT bom_id,row_revision,quantity FROM bom_master
                           WHERE bom_id=? AND status='ACTIVE'""",
                        (approved_action.get("source_bom_id"),),
                    ).fetchone()
                if (not current or
                        current["row_revision"] != approved_action.get("source_bom_row_revision") or
                        current["quantity"] != approved_action.get("source_bom_quantity")):
                    raise ValueError("Production BOM changed after preview")

        action_results = []
        with self.repository.transaction() as connection:
            for action in actions:
                self.repository.validate_action(connection, action, context["effective_date"])
                self.repository.validate_hierarchy(connection, action)
            for action in actions:
                action_results.append(self.repository.apply_action(
                    connection, action, context["effective_date"],
                ))
            apply_id = self.repository.finish_apply(
                connection, request_id=request_id, preview_id=preview["preview_id"],
                approval_id=final_approval_id, applied_by=applied_by,
                action_results=action_results,
            )
        return {
            "success": True, "result": "APPLIED", "apply_id": apply_id,
            "request_id": request_id, "action_results": action_results,
            "plant_code": context["plant_code"],
            "production_bom_modified": True,
        }
