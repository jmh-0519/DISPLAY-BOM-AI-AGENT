from __future__ import annotations


class RuleManagementService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def list_rules(self, as_of_date: str | None = None) -> list[dict]:
        return self.repository.list_rules(as_of_date)

    def create_revision(self, rule: dict, conditions: list[dict]) -> dict:
        if rule.get("active_yn") == "Y" and not rule.get("valid_from"):
            raise ValueError("Active rule requires valid_from")
        if float(rule.get("weight", -1)) < 0:
            raise ValueError("Rule weight must be non-negative")
        if not conditions:
            raise ValueError("At least one rule condition is required")
        return self.repository.create_rule_revision(rule, conditions)

    def deactivate(self, rule_id: str, revision_no: int) -> dict:
        self.repository.deactivate_rule(rule_id, revision_no)
        return {"rule_id": rule_id, "revision_no": revision_no, "active_yn": "N"}
