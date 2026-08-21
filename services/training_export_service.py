from __future__ import annotations

import hashlib
import json
import uuid


class TrainingExportService:
    SAFE_REASONS = {"EOL", "SUPPLIER_STOP", "LEAD_TIME", "COST", "INVENTORY",
                    "QUALITY", "CUSTOMER_SPEC", "REGULATION", "COMMONIZATION"}
    def __init__(self, repository) -> None:
        self.repository = repository

    @staticmethod
    def _pseudonym(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def export_jsonl(self, *, date_from: str | None, date_to: str | None,
                     created_by: str) -> dict:
        lines = []
        for record in self.repository.get_training_records(date_from, date_to):
            lines.append(json.dumps({
                "input": {
                    "request_id": self._pseudonym(record["request_id"]),
                    "version": self._pseudonym(record["version_code"]),
                    "reasons": [reason if reason in self.SAFE_REASONS else "OTHER"
                                for reason in json.loads(record["reasons_json"])],
                    "demand_source": record["demand_source"],
                    "actions": [{
                        "action_type": action["action_type"],
                        "target_type": action["target_type"],
                        "parent": self._pseudonym(action["parent_item_code"]),
                        "old_item": self._pseudonym(action.get("old_item_code")),
                        "new_item": self._pseudonym(action.get("new_item_code")),
                    } for action in record["actions"]],
                },
                "expected": {
                    "workflow_status": record["workflow_status"],
                    "apply_status": record["apply_status"],
                },
                "feedback": {
                    "approvals": [{
                        "approval_stage": approval.get("approval_stage"),
                        "decision": approval.get("decision"),
                        "reason_present": bool(approval.get("decision_reason")),
                    } for approval in record["approvals"]],
                    "outcomes": [{**value, "outcome_json": self._safe_outcome(
                        json.loads(value["outcome_json"]))}
                                 for value in record["outcomes"]],
                },
            }, ensure_ascii=False, sort_keys=True))
        content = "\n".join(lines)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        export_id = f"EXP-{uuid.uuid4().hex[:12].upper()}"
        self.repository.save_dataset_export(
            export_id, date_from, date_to, len(lines), checksum, created_by,
        )
        return {"export_id": export_id, "record_count": len(lines),
                "checksum": checksum, "jsonl": content}

    @classmethod
    def _safe_outcome(cls, value):
        if isinstance(value, dict):
            return {key: cls._safe_outcome(item) for key, item in value.items()
                    if not any(token in key.lower() for token in
                               ("name", "supplier", "item", "code", "request", "secret", "key"))}
        if isinstance(value, list):
            return [cls._safe_outcome(item) for item in value]
        if isinstance(value, str):
            return cls._pseudonym(value)
        return value
