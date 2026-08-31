from __future__ import annotations

from pathlib import Path

import pytest

from rag.reason_catalog import ReasonCatalog
from rag.rule_catalog import RuleCatalog
from scripts.validate_design_change_knowledge import validate


def test_reason_and_rule_catalogs_are_cross_valid() -> None:
    result = validate()

    assert result == {
        "reason_count": 10,
        "active_reason_count": 10,
        "alias_count": 18,
        "scope_count": 31,
        "rule_count": 10,
        "active_rule_count": 10,
        "condition_count": 30,
    }


def test_rule_action_scope_is_preserved_by_catalogs() -> None:
    reasons = ReasonCatalog.from_directory(Path("knowledge/reasons"))
    rules = RuleCatalog.from_directory(Path("knowledge/rules"))

    add_rules = rules.find_rule_engine_records(
        reason_codes=["CUSTOMER_SPEC"],
        target_type="MATERIAL",
        action_type="ADD",
        as_of_date="2026-08-31",
    )
    replace_rules = rules.find_rule_engine_records(
        reason_codes=["CUSTOMER_SPEC"],
        target_type="MATERIAL",
        action_type="REPLACE",
        as_of_date="2026-08-31",
    )

    assert reasons.is_scope_allowed(
        reason_code="CUSTOMER_SPEC", target_type="MATERIAL", action_type="ADD"
    )
    assert [row["rule_id"] for row in add_rules] == ["DC-R-007"]
    assert replace_rules == []


def test_cross_validation_rejects_rule_outside_reason_scope(tmp_path: Path) -> None:
    reason_dir = tmp_path / "reasons"
    rule_dir = tmp_path / "rules"
    reason_dir.mkdir()
    rule_dir.mkdir()
    (reason_dir / "EOL.md").write_text(
        '''+++
reason_code = "EOL"
reason_name_ko = "단종 대응"
description = "단종"
category = "LIFECYCLE"
valid_from = "2026-01-01"

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"
+++
# EOL
''',
        encoding="utf-8",
    )
    (rule_dir / "bad.md").write_text(
        '''+++
rule_id = "BAD-RULE"
revision_no = 1
rule_name = "Bad ADD Rule"
description = "scope mismatch"
status = "ACTIVE"
valid_from = "2026-08-31"
target_types = ["MATERIAL"]
action_types = ["ADD"]
reason_codes = ["EOL"]
evaluation_item = "FILM"
required = true
weight = 100

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "FILM"
+++
# bad
''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scope not allowed"):
        validate(reason_dir, rule_dir)
