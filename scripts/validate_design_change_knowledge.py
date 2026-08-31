from __future__ import annotations

import argparse
from pathlib import Path

from rag.reason_catalog import ReasonCatalog
from rag.rule_catalog import RuleCatalog


DEFAULT_REASON_DIRECTORY = Path("knowledge/reasons")
DEFAULT_RULE_DIRECTORY = Path("knowledge/rules")


def validate(
    reason_path: Path = DEFAULT_REASON_DIRECTORY,
    rule_path: Path = DEFAULT_RULE_DIRECTORY,
) -> dict:
    reasons = ReasonCatalog.from_directory(reason_path)
    rules = RuleCatalog.from_directory(rule_path)

    active_reason_codes = {
        reason.reason_code for reason in reasons.reasons if reason.status == "ACTIVE"
    }
    violations: list[str] = []
    for rule in rules.rules:
        if rule.status != "ACTIVE":
            continue
        for reason_code in rule.reason_codes:
            if reason_code not in active_reason_codes:
                violations.append(
                    f"{rule.rule_id}: unknown/inactive reason_code {reason_code}"
                )
                continue
            for target_type in rule.target_types:
                if target_type == "ALL":
                    targets = ("MATERIAL", "ASSY")
                else:
                    targets = (target_type,)
                for target in targets:
                    for action in rule.action_types:
                        if not reasons.is_scope_allowed(
                            reason_code=reason_code,
                            target_type=target,
                            action_type=action,
                        ):
                            violations.append(
                                f"{rule.rule_id}: scope not allowed "
                                f"{reason_code}/{target}/{action}"
                            )
    if violations:
        raise ValueError("Knowledge catalog validation failed: " + "; ".join(violations))

    active_rules = [rule for rule in rules.rules if rule.status == "ACTIVE"]
    return {
        "reason_count": len(reasons.reasons),
        "active_reason_count": len(active_reason_codes),
        "alias_count": len(reasons.active_alias_records()),
        "scope_count": sum(len(reason.scopes) for reason in reasons.reasons),
        "rule_count": len(rules.rules),
        "active_rule_count": len(active_rules),
        "condition_count": sum(len(rule.conditions) for rule in active_rules),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate external design-change Reason/Rule knowledge catalogs."
    )
    parser.add_argument("--reasons", type=Path, default=DEFAULT_REASON_DIRECTORY)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULE_DIRECTORY)
    args = parser.parse_args()
    result = validate(args.reasons, args.rules)
    print("Design-change knowledge catalog validation passed")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
