from __future__ import annotations

from datetime import date

import pytest

from database import SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService


def make_service(tmp_path, name: str) -> tuple[DesignChangeWorkflowService, SQLiteDatabase]:
    target = tmp_path / f"{name}.db"
    rebuild_latest_database(target)
    database = SQLiteDatabase(target)
    return DesignChangeWorkflowService(database), database


def iter_dynamic_replace_contexts(database: SQLiteDatabase):
    """Yield valid REPLACE contexts from current DB/metadata without fixture codes."""
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    with database.connection() as connection:
        sources = connection.execute(
            """
            SELECT DISTINCT r.source_item_code, i.item_type
            FROM substitution_relations r
            JOIN item_master i ON i.item_code=r.source_item_code
            WHERE r.active_yn='Y'
              AND i.active_yn='Y'
              AND r.valid_from<=?
              AND (r.valid_to IS NULL OR r.valid_to>=?)
            ORDER BY r.source_item_code
            """,
            (today, today),
        ).fetchall()
        reason_rows = connection.execute(
            """
            SELECT s.reason_code, s.target_type, a.alias_text, a.priority, a.alias_id
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.active_yn='Y' AND s.action_type='REPLACE'
            ORDER BY s.reason_code, a.priority, a.alias_id
            """
        ).fetchall()

    for source in sources:
        target_type = (
            "ASSY" if source["item_type"] == "ASSEMBLY"
            else "MATERIAL" if source["item_type"] == "MATERIAL"
            else None
        )
        if target_type is None:
            continue

        reasons = []
        seen_reasons = set()
        for row in reason_rows:
            if row["target_type"] != target_type or row["reason_code"] in seen_reasons:
                continue
            reasons.append({"reason_code": row["reason_code"], "alias_text": row["alias_text"]})
            seen_reasons.add(row["reason_code"])

        with database.connection() as connection:
            plants = [
                row["plant_code"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT plant_code
                    FROM bom_master
                    WHERE child_item_code=?
                      AND status='ACTIVE'
                      AND valid_from<=?
                      AND (valid_to IS NULL OR valid_to>=?)
                    ORDER BY plant_code
                    """,
                    (source["source_item_code"], today, today),
                ).fetchall()
            ]

        for plant_code in plants:
            ancestors = repository.get_recursive_ancestors(
                source["source_item_code"], plant_code, today
            )
            for ancestor in ancestors:
                if ancestor["item_type"] != "VERSION":
                    continue
                relations = repository.find_version_source_relations(
                    version_code=ancestor["item_code"],
                    child_item_code=source["source_item_code"],
                    plant_code=plant_code,
                    as_of_date=today,
                )
                if len(relations) != 1:
                    continue
                yield {
                    "plant_code": plant_code,
                    "version_code": ancestor["item_code"],
                    "source_item_code": source["source_item_code"],
                    "target_type": target_type,
                    "relation": relations[0],
                    "reasons": reasons,
                }


def create_evaluated_replace_with_status(
    service: DesignChangeWorkflowService,
    database: SQLiteDatabase,
    desired_status: str,
) -> tuple[dict, dict, dict]:
    """Create/evaluate requests until current data yields the requested status."""
    for context in iter_dynamic_replace_contexts(database):
        for reason in context["reasons"]:
            try:
                created = service.create_request(
                    {
                        "plant_code": context["plant_code"],
                        "version_code": context["version_code"],
                        "original_request": reason["alias_text"],
                        "reasons": [reason["reason_code"]],
                        # Keep the E2E approval test independent from production-plan size.
                        "demand_quantity": 1,
                        "requested_by": "pytest",
                    },
                    [
                        {
                            "action_type": "REPLACE",
                            "old_item_code": context["source_item_code"],
                        }
                    ],
                )
                evaluated = service.evaluate_action(created["actions"][0]["action_id"])
            except ValueError:
                continue

            selected = next(
                (row for row in evaluated["candidates"] if row["status"] == desired_status),
                None,
            )
            if selected is not None:
                return context, created, selected

    raise AssertionError(
        f"No dynamically discovered REPLACE candidate with status={desired_status} was found"
    )


def complete_candidate_selection(
    service: DesignChangeWorkflowService,
    request_id: str,
    selections: list[dict],
) -> dict:
    """Mirror STEP29 UI: shared BOM selection requires one extra impact approval."""
    result = service.prepare_candidate_selection(
        request_id, selections, "pytest"
    )
    if result.get("workflow_status") == "IMPACT_REVIEW_REQUIRED":
        assert result["impact_review"]["requires_impact_approval"] is True
        result = service.approve_candidate_impact(request_id, "pytest")
    assert result["workflow_status"] == "CANDIDATE_APPROVED"
    return result


def find_dynamic_add_context(database: SQLiteDatabase) -> dict:
    """Find an ADD-capable reason, product/plant, parent and target item dynamically."""
    with database.connection() as connection:
        scope = connection.execute(
            """
            SELECT s.reason_code, s.target_type, a.alias_text
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.active_yn='Y' AND s.action_type='ADD'
            ORDER BY a.priority, s.reason_code, a.alias_id
            LIMIT 1
            """
        ).fetchone()
        if scope is None:
            raise AssertionError("No active ADD reason metadata was found")

        item_type = "ASSEMBLY" if scope["target_type"] == "ASSY" else "MATERIAL"
        parent = connection.execute(
            """
            SELECT b.plant_code, b.parent_item_code, p.item_type,
                   v.version_code
            FROM bom_master b
            JOIN item_master p ON p.item_code=b.parent_item_code
            JOIN version_master v ON v.version_code=b.parent_item_code
            WHERE b.status='ACTIVE'
              AND p.active_yn='Y'
            GROUP BY b.plant_code, b.parent_item_code, p.item_type, v.version_code
            ORDER BY b.plant_code, b.parent_item_code
            LIMIT 1
            """
        ).fetchone()
        if parent is None:
            raise AssertionError("No active VERSION parent was found")

        target = connection.execute(
            """
            SELECT i.item_code
            FROM item_master i
            WHERE i.item_type=? AND i.active_yn='Y'
              AND NOT EXISTS (
                SELECT 1 FROM bom_master b
                WHERE b.plant_code=?
                  AND b.parent_item_code=?
                  AND b.child_item_code=i.item_code
                  AND b.status='ACTIVE'
              )
            ORDER BY i.item_code
            LIMIT 1
            """,
            (item_type, parent["plant_code"], parent["parent_item_code"]),
        ).fetchone()
        if target is None:
            raise AssertionError("No active item suitable for dynamic ADD test was found")

    return {
        "reason_code": scope["reason_code"],
        "alias_text": scope["alias_text"],
        "target_type": scope["target_type"],
        "plant_code": parent["plant_code"],
        "version_code": parent["version_code"],
        "parent_item_code": parent["parent_item_code"],
        "new_item_code": target["item_code"],
    }


def test_dynamic_replace_runs_through_candidate_approval_preview_final_approval_and_apply(tmp_path):
    service, database = make_service(tmp_path, "phase3-e2e-apply")
    context, created, selected = create_evaluated_replace_with_status(
        service, database, "PASS"
    )

    action = created["actions"][0]
    assert created["production_bom_modified"] is False

    candidate_approval = complete_candidate_selection(
        service,
        created["request_id"],
        [{
            "action_id": action["action_id"],
            "candidate_id": selected["candidate_id"],
            "supplier_item_id": selected.get("recommended_supplier_item_id"),
        }],
    )
    assert candidate_approval["stage"] == "CANDIDATE"
    assert candidate_approval["requires_exception"] is False

    preview = service.create_preview(created["request_id"], "pytest")
    assert preview["validation_status"] == "PASS"

    final = service.approve_final(created["request_id"], "pytest")
    assert final["stage"] == "FINAL_APPLY"

    applied = service.apply(created["request_id"], final["approval_id"], "pytest")
    assert applied["result"] == "APPLIED"

    # Verify the selected candidate is now the active child on the exact relation
    # that was discovered from the database at runtime.
    with database.connection() as connection:
        active = connection.execute(
            """
            SELECT child_item_code
            FROM bom_master
            WHERE plant_code=?
              AND parent_item_code=?
              AND location_code=?
              AND status='ACTIVE'
              AND valid_to IS NULL
            ORDER BY valid_from DESC, bom_id DESC
            """,
            (
                context["plant_code"],
                context["relation"]["parent_item_code"],
                context["relation"]["location_code"],
            ),
        ).fetchall()

    assert selected["candidate_item_code"] in {
        row["child_item_code"] for row in active
    }
    assert context["source_item_code"] not in {
        row["child_item_code"] for row in active
    }


def test_dynamic_add_action_is_evaluated_as_one_direct_candidate(tmp_path):
    service, database = make_service(tmp_path, "phase3-e2e-add")
    context = find_dynamic_add_context(database)

    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "requested_by": "pytest",
        },
        [
            {
                "action_type": "ADD",
                "parent_item_code": context["parent_item_code"],
                "new_item_code": context["new_item_code"],
                "new_quantity": 1,
            }
        ],
    )

    result = service.evaluate_action(created["actions"][0]["action_id"])

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["candidate_item_code"] == context["new_item_code"]
    assert result["candidates"][0]["discovery_mode"] == "DIRECT_ADD"


def test_dynamic_conditional_candidate_requires_exception_before_final_approval(tmp_path):
    service, database = make_service(tmp_path, "phase3-e2e-conditional")
    _context, created, selected = create_evaluated_replace_with_status(
        service, database, "CONDITIONAL"
    )

    action = created["actions"][0]
    prepared = service.prepare_candidate_selection(
        created["request_id"],
        [{
            "action_id": action["action_id"],
            "candidate_id": selected["candidate_id"],
            "supplier_item_id": selected.get("recommended_supplier_item_id"),
        }],
        "pytest",
    )
    assert prepared["workflow_status"] == "CONDITIONAL_REVIEW_REQUIRED"
    assert prepared["workflow_started"] is False
    assert prepared["requires_exception"] is True
    assert service.get_result(created["request_id"])["candidate_approval_status"] == "PENDING"

    with pytest.raises(ValueError, match="Candidate approval"):
        service.create_preview(created["request_id"], "pytest")

    exception = service.approve_exception(
        created["request_id"],
        "Dynamic CONDITIONAL acceptance test",
        "pytest",
    )
    if exception.get("workflow_status") == "IMPACT_REVIEW_REQUIRED":
        exception = service.approve_candidate_impact(created["request_id"], "pytest")
    assert exception["workflow_status"] == "CANDIDATE_APPROVED"
    assert exception["requires_exception"] is False

    preview = service.create_preview(created["request_id"], "pytest")
    assert preview["validation_status"] == "CONDITIONAL"
    final = service.approve_final(created["request_id"], "pytest")
    assert final["stage"] == "FINAL_APPLY"
