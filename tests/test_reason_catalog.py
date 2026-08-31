from __future__ import annotations

from pathlib import Path

import pytest

from rag.reason_catalog import ReasonCatalog, ReasonCatalogError


REASONS = Path("knowledge/reasons")


def test_baseline_reason_catalog_loads_current_reason_contract() -> None:
    catalog = ReasonCatalog.from_directory(REASONS)

    assert len(catalog.reasons) == 10
    assert len(catalog.active_alias_records()) == 18
    assert sum(len(reason.scopes) for reason in catalog.reasons) == 31
    assert catalog.get("USER_REQUEST") is not None


def test_reason_aliases_and_scopes_match_current_behavior() -> None:
    catalog = ReasonCatalog.from_directory(REASONS)
    aliases = catalog.active_alias_records()

    assert any(
        row["normalized_alias"] == "단종" and row["reason_code"] == "EOL"
        for row in aliases
    )
    assert catalog.is_scope_allowed(
        reason_code="COMMONIZATION",
        target_type="MATERIAL",
        action_type="DELETE",
    )
    assert not catalog.is_scope_allowed(
        reason_code="EOL",
        target_type="MATERIAL",
        action_type="ADD",
    )


def test_new_reason_document_can_be_added_without_python_change(tmp_path: Path) -> None:
    (tmp_path / "DELIVERY_RISK.md").write_text(
        '''+++
reason_code = "DELIVERY_RISK"
reason_name_ko = "납품 위험 대응"
description = "납품 지연 위험에 대응"
category = "SUPPLY"
status = "ACTIVE"
valid_from = "2026-08-31"

[[aliases]]
text = "납품 위험"
language = "KO"
match_type = "KEYWORD"
priority = 10

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"
+++
# 납품 위험 대응

신규 사유는 문서 추가만으로 Catalog에 등록된다.
''',
        encoding="utf-8",
    )

    catalog = ReasonCatalog.from_directory(tmp_path)

    assert catalog.get("DELIVERY_RISK") is not None
    assert catalog.is_scope_allowed(
        reason_code="DELIVERY_RISK",
        target_type="MATERIAL",
        action_type="REPLACE",
    )
    assert catalog.active_alias_records()[0]["normalized_alias"] == "납품위험"


def test_invalid_reason_scope_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text(
        '''+++
reason_code = "BAD"
reason_name_ko = "잘못된 사유"
description = "invalid"
category = "TEST"
valid_from = "2026-08-31"

[[scopes]]
target_type = "MATERIAL"
action_type = "UNKNOWN"
+++
# invalid
''',
        encoding="utf-8",
    )

    with pytest.raises(ReasonCatalogError, match="invalid scope action_type"):
        ReasonCatalog.from_directory(tmp_path)


def test_reason_rag_text_contains_alias_scope_and_policy() -> None:
    catalog = ReasonCatalog.from_directory(REASONS)
    reason = catalog.get("EOL")
    assert reason is not None

    text = reason.rag_text()

    assert "Reason Code: EOL" in text
    assert "단종" in text
    assert "MATERIAL/REPLACE" in text
    assert "설계변경 사유" in text
