from __future__ import annotations

import json
import uuid
from datetime import date

from database import SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService


def _find_shared_parent_context(database: SQLiteDatabase) -> dict:
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()
    with database.connection() as connection:
        relations = connection.execute(
            """
            SELECT b.plant_code,b.parent_item_code,b.child_item_code,i.item_type
            FROM bom_master b
            JOIN assembly_master a ON a.assembly_code=b.parent_item_code
            JOIN item_master i ON i.item_code=b.child_item_code
            WHERE a.usage_type='COMMON'
              AND a.active_yn='Y'
              AND b.status='ACTIVE'
              AND b.valid_from<=?
              AND (b.valid_to IS NULL OR b.valid_to>=?)
              AND i.item_type IN ('MATERIAL','ASSEMBLY')
              AND i.active_yn='Y'
            ORDER BY b.plant_code,b.parent_item_code,b.child_item_code
            """,
            (today, today),
        ).fetchall()

        scopes = connection.execute(
            """
            SELECT s.reason_code,s.target_type,a.alias_text
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.active_yn='Y' AND s.action_type='REPLACE'
            ORDER BY a.priority,a.alias_id
            """
        ).fetchall()

    for relation in relations:
        target_type = "ASSY" if relation["item_type"] == "ASSEMBLY" else "MATERIAL"
        scope = next((row for row in scopes if row["target_type"] == target_type), None)
        if scope is None:
            continue
        models = [
            row for row in repository.get_recursive_ancestors(
                relation["parent_item_code"], relation["plant_code"], today
            )
            if row["item_type"] == "VERSION"
        ]
        if len(models) < 2:
            continue
        with database.connection() as connection:
            replacement = connection.execute(
                """
                SELECT item_code FROM item_master
                WHERE item_type=? AND active_yn='Y' AND item_code<>?
                ORDER BY item_code LIMIT 1
                """,
                (relation["item_type"], relation["child_item_code"]),
            ).fetchone()
        if replacement:
            return {
                "plant_code": relation["plant_code"],
                "parent_item_code": relation["parent_item_code"],
                "source_item_code": relation["child_item_code"],
                "candidate_item_code": replacement["item_code"],
                "version_code": models[0]["item_code"],
                "reason_code": scope["reason_code"],
                "alias_text": scope["alias_text"],
                "expected_models": {row["item_code"] for row in models},
            }
    raise AssertionError("No dynamically discovered COMMON parent with multiple models was found")


def test_common_parent_candidate_selection_requires_impact_approval_before_workflow(tmp_path):
    path = tmp_path / "impact-gate.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    service = DesignChangeWorkflowService(database)
    context = _find_shared_parent_context(database)

    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "demand_quantity": 1,
            "requested_by": "pytest",
        },
        [{
            "action_type": "REPLACE",
            "old_item_code": context["source_item_code"],
        }],
    )
    action_id = created["actions"][0]["action_id"]
    candidate_id = f"CAND-{uuid.uuid4().hex[:12].upper()}"

    # The gate test generates a PASS candidate dynamically; it does not depend on a
    # pre-defined scenario or item code.
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO candidate_evaluations(
                candidate_id,action_id,plant_code,candidate_item_code,final_status,
                total_score,grade,rank_no,missing_data_json,conditional_reasons_json,
                attribute_comparison_json,inventory_result_json,impact_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                candidate_id, action_id, context["plant_code"],
                context["candidate_item_code"], "PASS", 90, "S", 1,
                json.dumps([]), json.dumps([]), json.dumps({}), json.dumps({}), json.dumps({}),
            ),
        )

    prepared = service.prepare_candidate_selection(
        created["request_id"],
        [{"action_id": action_id, "candidate_id": candidate_id, "supplier_item_id": None}],
        "pytest",
    )

    assert prepared["workflow_status"] == "IMPACT_REVIEW_REQUIRED"
    assert prepared["workflow_started"] is False
    assert prepared["impact_review"]["requires_impact_approval"] is True
    assert context["expected_models"] <= {
        row["model_code"] for row in prepared["impact_review"]["impacted_models"]
    }
    assert prepared["impact_review"]["actions"][0]["spec_changes"]
    request = service.get_result(created["request_id"])
    assert request["candidate_approval_status"] == "PENDING"

    approved = service.approve_candidate_impact(created["request_id"], "pytest")
    assert approved["workflow_status"] == "CANDIDATE_APPROVED"
    assert approved["workflow_started"] is True
    assert approved["stage"] == "CANDIDATE"
    request = service.get_result(created["request_id"])
    assert request["candidate_approval_status"] == "APPROVED"


def test_common_impact_attaches_model_specific_before_after_specs(tmp_path):
    path = tmp_path / "impact-model-spec.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    service = DesignChangeWorkflowService(database)
    context = _find_shared_parent_context(database)

    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "demand_quantity": 1,
            "requested_by": "pytest",
        },
        [{"action_type": "REPLACE", "old_item_code": context["source_item_code"]}],
    )
    action_id = created["actions"][0]["action_id"]
    candidate_id = f"CAND-{uuid.uuid4().hex[:12].upper()}"
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO candidate_evaluations(
                candidate_id,action_id,plant_code,candidate_item_code,final_status,
                total_score,grade,rank_no,missing_data_json,conditional_reasons_json,
                attribute_comparison_json,inventory_result_json,impact_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                candidate_id, action_id, context["plant_code"],
                context["candidate_item_code"], "PASS", 90, "S", 1,
                json.dumps([]), json.dumps([]), json.dumps({}), json.dumps({}), json.dumps({}),
            ),
        )

    prepared = service.prepare_candidate_selection(
        created["request_id"],
        [{"action_id": action_id, "candidate_id": candidate_id, "supplier_item_id": None}],
        "pytest",
    )
    review = prepared["impact_review"]
    assert review["model_spec_impacts"]
    assert context["expected_models"] <= {
        row["model_code"] for row in review["model_spec_impacts"]
    }
    assert all("spec_changes" in row for row in review["model_spec_impacts"])
    assert all("changed_specs" in row for row in review["model_spec_impacts"])


def test_conditional_common_candidate_requires_exception_before_shared_impact_approval(tmp_path):
    path = tmp_path / "conditional-impact-gate.db"
    rebuild_latest_database(path)
    database = SQLiteDatabase(path)
    service = DesignChangeWorkflowService(database)
    context = _find_shared_parent_context(database)

    created = service.create_request(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "demand_quantity": 1,
            "requested_by": "pytest",
        },
        [{"action_type": "REPLACE", "old_item_code": context["source_item_code"]}],
    )
    action_id = created["actions"][0]["action_id"]
    candidate_id = f"CAND-{uuid.uuid4().hex[:12].upper()}"
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO candidate_evaluations(
                candidate_id,action_id,plant_code,candidate_item_code,final_status,
                total_score,grade,rank_no,missing_data_json,conditional_reasons_json,
                attribute_comparison_json,inventory_result_json,impact_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                candidate_id, action_id, context["plant_code"],
                context["candidate_item_code"], "CONDITIONAL", 75, "B", 1,
                json.dumps(["demand_quantity"]), json.dumps(["demand unavailable"]),
                json.dumps({}), json.dumps({}), json.dumps({}),
            ),
        )

    prepared = service.prepare_candidate_selection(
        created["request_id"],
        [{"action_id": action_id, "candidate_id": candidate_id, "supplier_item_id": None}],
        "pytest",
    )
    assert prepared["workflow_status"] == "CONDITIONAL_REVIEW_REQUIRED"
    assert service.get_result(created["request_id"])["candidate_approval_status"] == "PENDING"

    exception = service.approve_exception(
        created["request_id"], "업무상 조건부 후보 사용 필요", "pytest"
    )
    assert exception["workflow_status"] == "IMPACT_REVIEW_REQUIRED"
    assert exception["requires_exception"] is False
    assert service.get_result(created["request_id"])["candidate_approval_status"] == "PENDING"

    approved = service.approve_candidate_impact(created["request_id"], "pytest")
    assert approved["workflow_status"] == "CANDIDATE_APPROVED"
    assert approved["requires_exception"] is False
    assert service.get_result(created["request_id"])["candidate_approval_status"] == "APPROVED"
