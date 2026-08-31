from __future__ import annotations

from database import SQLiteDatabase
from rag.reason_catalog import ReasonCatalog
from rag.rule_catalog import RuleCatalog
from repositories.knowledge_design_change_repository import KnowledgeDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database


def test_runtime_repository_reads_reason_and_rule_definitions_from_knowledge(tmp_path) -> None:
    db_path = tmp_path / "knowledge-runtime.db"
    rebuild_latest_database(db_path)
    repository = KnowledgeDesignChangeRepository(SQLiteDatabase(db_path))

    reason_codes = {row["reason_code"] for row in repository.list_active_reason_metadata()}
    add_rules = repository.get_active_rules(
        ["CUSTOMER_SPEC"], "MATERIAL", "2026-08-31", action_type="ADD"
    )
    replace_rules = repository.get_active_rules(
        ["CUSTOMER_SPEC"], "MATERIAL", "2026-08-31", action_type="REPLACE"
    )

    assert "USER_REQUEST" in reason_codes
    assert [row["rule_id"] for row in add_rules] == ["DC-R-007"]
    assert replace_rules == []


def test_new_reason_is_projected_only_when_request_persistence_needs_fk(tmp_path) -> None:
    db_path = tmp_path / "knowledge-runtime.db"
    rebuild_latest_database(db_path)
    reason_dir = tmp_path / "reasons"
    reason_dir.mkdir()
    (reason_dir / "DELIVERY_RISK.md").write_text(
        '''+++
reason_code = "DELIVERY_RISK"
reason_name_ko = "납품 위험 대응"
description = "납품 지연 위험 대응"
category = "SUPPLY"
valid_from = "2026-08-31"

[[aliases]]
text = "납품 위험"
priority = 10

[[scopes]]
target_type = "MATERIAL"
action_type = "REPLACE"
+++
# Delivery Risk
''',
        encoding="utf-8",
    )
    repository = KnowledgeDesignChangeRepository(
        SQLiteDatabase(db_path),
        reason_catalog=ReasonCatalog.from_directory(reason_dir),
        rule_catalog=RuleCatalog.from_directory("knowledge/rules"),
    )

    with repository.database.connection() as connection:
        before = connection.execute(
            "SELECT 1 FROM change_reason_master WHERE reason_code='DELIVERY_RISK'"
        ).fetchone()
    assert before is None

    repository._ensure_reason_master_projection(
        [[{"reason_code": "DELIVERY_RISK"}]]
    )

    with repository.database.connection() as connection:
        after = connection.execute(
            "SELECT reason_name_ko,category FROM change_reason_master "
            "WHERE reason_code='DELIVERY_RISK'"
        ).fetchone()
    assert after is not None
    assert after["reason_name_ko"] == "납품 위험 대응"
    assert after["category"] == "SUPPLY"
