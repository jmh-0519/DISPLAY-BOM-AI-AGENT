from __future__ import annotations

import argparse
from pathlib import Path

from rag.rule_catalog import RuleCatalog


DEFAULT_RULE_DIRECTORY = Path("knowledge/rules")


def validate(path: Path = DEFAULT_RULE_DIRECTORY) -> dict:
    catalog = RuleCatalog.from_directory(path)
    active = [rule for rule in catalog.rules if rule.status == "ACTIVE"]
    reason_codes = sorted({reason for rule in active for reason in rule.reason_codes})
    action_types = sorted({action for rule in active for action in rule.action_types})
    target_types = sorted({target for rule in active for target in rule.target_types})
    condition_count = sum(len(rule.conditions) for rule in active)
    return {
        "rule_count": len(catalog.rules),
        "active_rule_count": len(active),
        "condition_count": condition_count,
        "reason_codes": reason_codes,
        "action_types": action_types,
        "target_types": target_types,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate external design-change rule documents.")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULE_DIRECTORY)
    args = parser.parse_args()
    result = validate(args.rules)
    print("Rule knowledge catalog validation passed")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
