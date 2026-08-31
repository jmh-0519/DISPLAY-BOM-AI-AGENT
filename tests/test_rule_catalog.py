from __future__ import annotations

from pathlib import Path

import pytest

from rag.rule_catalog import RuleCatalog, RuleCatalogError


RULES = Path("knowledge/rules")


def test_baseline_rule_catalog_loads_all_ten_rules() -> None:
    catalog = RuleCatalog.from_directory(RULES)

    assert len(catalog.rules) == 10
    assert len({rule.rule_id for rule in catalog.rules}) == 10
    assert all(rule.body for rule in catalog.rules)
    assert sum(len(rule.conditions) for rule in catalog.rules) == 30


def test_catalog_selects_eol_drive_ic_rule_deterministically() -> None:
    catalog = RuleCatalog.from_directory(RULES)

    rules = catalog.find_rule_engine_records(
        reason_codes=["EOL"],
        target_type="MATERIAL",
        action_type="REPLACE",
        evaluation_labels=["DRIVE-IC", "DRIVER_IC"],
        as_of_date="2026-08-31",
    )

    assert [rule["rule_id"] for rule in rules] == ["DC-R-001"]
    assert rules[0]["conditions"][2]["attribute_name"] == "operating_voltage"
    assert rules[0]["conditions"][2]["operator"] == "LE"
    assert rules[0]["conditions"][2]["expected_value"] == "3.3"


def test_catalog_separates_commonization_material_and_assy_rules() -> None:
    catalog = RuleCatalog.from_directory(RULES)

    material = catalog.find(
        reason_codes=["COMMONIZATION"],
        target_type="MATERIAL",
        action_type="REPLACE",
        evaluation_labels=["BRACKET"],
        as_of_date="2026-08-31",
    )
    assy = catalog.find(
        reason_codes=["COMMONIZATION"],
        target_type="ASSY",
        action_type="REPLACE",
        evaluation_labels=["OLB"],
        as_of_date="2026-08-31",
    )

    assert [rule.rule_id for rule in material] == ["DC-R-009"]
    assert [rule.rule_id for rule in assy] == ["DC-R-010"]


def test_catalog_keeps_add_action_scope_explicit() -> None:
    catalog = RuleCatalog.from_directory(RULES)

    matched = catalog.find(
        reason_codes=["CUSTOMER_SPEC"],
        target_type="MATERIAL",
        action_type="ADD",
        evaluation_labels=["EMI SHIELD TAPE"],
        as_of_date="2026-08-31",
    )
    wrong_action = catalog.find(
        reason_codes=["CUSTOMER_SPEC"],
        target_type="MATERIAL",
        action_type="REPLACE",
        evaluation_labels=["EMI SHIELD TAPE"],
        as_of_date="2026-08-31",
    )

    assert [rule.rule_id for rule in matched] == ["DC-R-007"]
    assert wrong_action == []


def test_new_rule_document_can_be_added_without_python_change(tmp_path: Path) -> None:
    extra = tmp_path / "DC-R-011_DELIVERY_RISK_FILM.md"
    extra.write_text(
        '''+++
rule_id = "DC-R-011"
revision_no = 1
rule_name = "DELIVERY_RISK MATERIAL suitability"
description = "납품 리스크 대응용 FILM Rule"
status = "ACTIVE"
valid_from = "2026-08-31"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["DELIVERY_RISK"]
evaluation_item = "FILM"
required = true
weight = 100

[[conditions]]
attribute_name = "material_family"
operator = "EQ"
expected_value = "FILM"
+++
# Delivery Risk FILM Rule

새로운 업무 Rule은 문서 추가만으로 Catalog에 등록된다.
''',
        encoding="utf-8",
    )

    catalog = RuleCatalog.from_directory(tmp_path)
    result = catalog.find(
        reason_codes=["DELIVERY_RISK"],
        target_type="MATERIAL",
        action_type="REPLACE",
        evaluation_labels=["FILM"],
        as_of_date="2026-08-31",
    )

    assert [rule.rule_id for rule in result] == ["DC-R-011"]


def test_invalid_rule_document_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.md"
    invalid.write_text(
        '''+++
rule_id = "BAD-001"
rule_name = "Bad Rule"
description = "invalid operator"
valid_from = "2026-08-31"
target_types = ["MATERIAL"]
action_types = ["REPLACE"]
reason_codes = ["EOL"]
evaluation_item = "FILM"

[[conditions]]
attribute_name = "material_family"
operator = "UNKNOWN"
expected_value = "FILM"
+++
# Invalid
''',
        encoding="utf-8",
    )

    with pytest.raises(RuleCatalogError, match="unsupported rule operator"):
        RuleCatalog.from_directory(tmp_path)


def test_rag_text_contains_structured_scope_and_human_policy() -> None:
    catalog = RuleCatalog.from_directory(RULES)
    rule = next(value for value in catalog.rules if value.rule_id == "DC-R-008")

    text = rule.rag_text()

    assert "Rule ID: DC-R-008" in text
    assert "Reason: REGULATION" in text
    assert "OPTICAL ADHESIVE" in text
    assert "rohs_status EQ COMPLIANT" in text
    assert "규제 대응" in text
