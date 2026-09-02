from __future__ import annotations

from datetime import date
from pathlib import Path

from database import SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService


def _service(tmp_path: Path, name: str) -> tuple[DesignChangeWorkflowService, SQLiteDatabase]:
    target = tmp_path / f"{name}.db"
    rebuild_latest_database(target)
    database = SQLiteDatabase(target)
    return DesignChangeWorkflowService(database), database


def _add_rule_context(database: SQLiteDatabase) -> dict:
    """Find an active ADD scope/rule and candidate product/plant contexts dynamically."""
    today = date.today().isoformat()
    with database.connection() as connection:
        scope = connection.execute(
            """
            SELECT DISTINCT s.reason_code,s.target_type,a.alias_text,r.evaluation_item
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            JOIN rule_revisions r
              ON r.change_reason=s.reason_code
             AND r.target_type=s.target_type
             AND r.active_yn='Y'
             AND r.valid_from<=?
             AND (r.valid_to IS NULL OR r.valid_to>=?)
            WHERE s.action_type='ADD' AND s.active_yn='Y'
            ORDER BY a.priority,s.reason_code,s.target_type
            LIMIT 1
            """,
            (today, today),
        ).fetchone()
        assert scope is not None
        products = [dict(row) for row in connection.execute(
            """
            SELECT p.version_code,p.plant_code
            FROM production_plans p
            JOIN item_master i ON i.item_code=p.version_code
            WHERE p.status='CONFIRMED' AND i.active_yn='Y' AND i.item_type='VERSION'
            GROUP BY p.version_code,p.plant_code
            ORDER BY p.version_code,p.plant_code
            """
        ).fetchall()]
        assert products
    return {**dict(scope), "products": products}


def _action_context(database: SQLiteDatabase, action_type: str, target_type: str = "MATERIAL") -> dict:
    """Find a reachable active BOM edge with production demand and allowed reason."""
    repository = SQLiteDesignChangeRepository(database)
    from scripts.seed_design_change_business_sample import AS_OF_DATE
    today = AS_OF_DATE
    item_type = "ASSEMBLY" if target_type == "ASSY" else "MATERIAL"
    with database.connection() as connection:
        reason = connection.execute(
            """
            SELECT s.reason_code,a.alias_text
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.action_type=? AND s.target_type=? AND s.active_yn='Y'
            ORDER BY a.priority,s.reason_code,a.alias_id
            LIMIT 1
            """,
            (action_type, target_type),
        ).fetchone()
        assert reason is not None
        relations = connection.execute(
            """
            SELECT b.*
            FROM bom_master b
            JOIN item_master i ON i.item_code=b.child_item_code
            WHERE b.status='ACTIVE' AND i.active_yn='Y' AND i.item_type=?
              AND b.valid_from<=? AND (b.valid_to IS NULL OR b.valid_to>=?)
            ORDER BY b.plant_code,b.parent_item_code,b.child_item_code,b.location_code
            """,
            (item_type, today, today),
        ).fetchall()

    for relation in relations:
        ancestors = repository.get_recursive_ancestors(
            relation["child_item_code"], relation["plant_code"], today
        )
        for ancestor in ancestors:
            if ancestor["item_type"] != "VERSION":
                continue
            demand = repository.get_production_demand(
                ancestor["item_code"], relation["plant_code"], today
            )
            if demand is None:
                continue
            reachable = repository.find_version_source_relations(
                version_code=ancestor["item_code"],
                child_item_code=relation["child_item_code"],
                plant_code=relation["plant_code"],
                as_of_date=today,
            )
            exact = [
                row for row in reachable
                if row["parent_item_code"] == relation["parent_item_code"]
                and row["location_code"] == relation["location_code"]
            ]
            if exact:
                return {
                    **dict(reason),
                    "version_code": ancestor["item_code"],
                    "plant_code": relation["plant_code"],
                    "relation": dict(relation),
                    "production_quantity": demand,
                }
    raise AssertionError(f"No dynamic {action_type}/{target_type} context with production demand")


def _ensure_large_inventory(database: SQLiteDatabase, plant_code: str, item_code: str) -> None:
    with database.transaction() as connection:
        location = connection.execute(
            """
            SELECT l.inventory_location_code
            FROM inventory_locations l
            JOIN warehouses w ON w.warehouse_code=l.warehouse_code
            WHERE w.plant_code=?
            ORDER BY l.inventory_location_code
            LIMIT 1
            """,
            (plant_code,),
        ).fetchone()
        assert location is not None
        connection.execute(
            """
            INSERT INTO inventory_balances(
                inventory_location_code,item_code,on_hand_quantity,reserved_quantity,
                safety_stock,hold_quantity,incoming_quantity,incoming_date
            ) VALUES(?,?,1000000,0,0,0,0,NULL)
            ON CONFLICT(inventory_location_code,item_code) DO UPDATE SET
                on_hand_quantity=excluded.on_hand_quantity,
                reserved_quantity=0,safety_stock=0,hold_quantity=0,
                incoming_quantity=0,incoming_date=NULL
            """,
            (location["inventory_location_code"], item_code),
        )


def _complete_from_analysis(
    service: DesignChangeWorkflowService,
    analysis: dict,
    selections: list[dict],
) -> dict:
    impact = service.preview_analysis_impact(analysis, selections)
    exception_reason = None
    if any(action.get("evaluation_status") == "CONDITIONAL" for action in analysis["actions"]):
        exception_reason = "pytest conditional evidence acceptance"
    created = service.commit_analysis_as_request(
        analysis,
        selections,
        approved_by="pytest",
        exception_reason=exception_reason,
        impact_confirmed=bool(impact.get("requires_impact_approval")),
    )
    preview = service.create_preview(created["request_id"], "pytest")
    assert preview["validation_status"] == "PASS"
    final = service.approve_final(created["request_id"], "pytest")
    applied = service.apply(created["request_id"], final["approval_id"], "pytest")
    assert applied["result"] == "APPLIED"
    return created


def test_add_without_new_item_discovers_ranked_candidates_and_applies_selected_one(tmp_path):
    service, database = _service(tmp_path, "design-change-add-discovery")
    context = _add_rule_context(database)

    analysis = None
    selected = None
    for product in context["products"]:
        candidate_analysis = service.analyze_candidates(
            {
                "plant_code": product["plant_code"],
                "version_code": product["version_code"],
                "original_request": f"{context['alias_text']} 조건으로 추가 가능한 자재 후보를 찾아줘",
                "reasons": [context["reason_code"]],
                "requested_by": "pytest",
            },
            [{
                "action_type": "ADD",
                "target_type": context["target_type"],
                "target_item_name": context["evaluation_item"],
            }],
        )
        pass_candidate = next(
            (row for row in candidate_analysis["candidates"] if row["status"] == "PASS"),
            None,
        )
        if pass_candidate is not None:
            analysis = candidate_analysis
            selected = pass_candidate
            break

    assert analysis is not None, "No dynamic ADD product/plant context yielded a PASS candidate"
    assert selected is not None
    assert analysis["request_created"] is False
    assert len(analysis["candidates"]) > 1
    assert {row["discovery_mode"] for row in analysis["candidates"]} == {"ADD_RULE_DISCOVERY"}
    selection = [{
        "action_id": analysis["actions"][0]["action_id"],
        "candidate_item_code": selected["candidate_item_code"],
        "supplier_item_id": selected.get("recommended_supplier_item_id"),
    }]
    created = _complete_from_analysis(service, analysis, selection)

    request = service.repository.get_request(created["request_id"])
    action = request["actions"][0]
    assert action["action_type"] == "ADD"
    assert action["new_item_code"] == selected["candidate_item_code"]


def test_delete_runs_without_candidate_selection_through_apply(tmp_path):
    service, database = _service(tmp_path, "design-change-delete")
    context = _action_context(database, "DELETE", "MATERIAL")
    relation = context["relation"]

    analysis = service.analyze_candidates(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "requested_by": "pytest",
        },
        [{
            "action_type": "DELETE",
            "old_item_code": relation["child_item_code"],
            "parent_item_code": relation["parent_item_code"],
            "location_code": relation["location_code"],
        }],
    )

    assert analysis["candidates"] == []
    assert analysis["actions"][0]["evaluation_status"] == "PASS"
    created = _complete_from_analysis(service, analysis, [])

    with database.connection() as connection:
        active = connection.execute(
            """
            SELECT 1 FROM bom_master
            WHERE plant_code=? AND parent_item_code=? AND child_item_code=?
              AND location_code=? AND status='ACTIVE' AND valid_to IS NULL
            """,
            (
                context["plant_code"], relation["parent_item_code"],
                relation["child_item_code"], relation["location_code"],
            ),
        ).fetchone()
    assert active is None
    assert service.repository.get_request(created["request_id"])["apply_status"] == "APPLIED"


def test_quantity_change_uses_new_bom_quantity_only_and_applies(tmp_path):
    service, database = _service(tmp_path, "design-change-quantity")
    context = _action_context(database, "QUANTITY_CHANGE", "MATERIAL")
    relation = context["relation"]
    _ensure_large_inventory(database, context["plant_code"], relation["child_item_code"])
    old_quantity = float(relation["quantity"])
    new_quantity = old_quantity + 1.0

    analysis = service.analyze_candidates(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": context["alias_text"],
            "reasons": [context["reason_code"]],
            "requested_by": "pytest",
        },
        [{
            "action_type": "QUANTITY_CHANGE",
            "old_item_code": relation["child_item_code"],
            "parent_item_code": relation["parent_item_code"],
            "location_code": relation["location_code"],
            "new_quantity": new_quantity,
        }],
    )

    action = analysis["actions"][0]
    assert action["demand"]["required_quantity_basis"] == "BOM_QUANTITY"
    assert action["demand"]["source"] == "BOM_QUANTITY"
    assert action["demand"]["quantity"] == new_quantity
    assert action["demand"]["production_plan_quantity"] is None
    assert action["inventory"]["status"] == "PASS"
    assert action["evaluation_status"] == "PASS"

    _complete_from_analysis(service, analysis, [])
    with database.connection() as connection:
        active = connection.execute(
            """
            SELECT quantity FROM bom_master
            WHERE plant_code=? AND parent_item_code=? AND child_item_code=?
              AND location_code=? AND status='ACTIVE' AND valid_to IS NULL
            ORDER BY valid_from DESC,bom_id DESC LIMIT 1
            """,
            (
                context["plant_code"], relation["parent_item_code"],
                relation["child_item_code"], relation["location_code"],
            ),
        ).fetchone()
    assert active is not None
    assert float(active["quantity"]) == new_quantity


def test_add_analysis_marks_already_active_same_bom_candidate_fail_before_preview(tmp_path):
    service, database = _service(tmp_path, "design-change-add-duplicate-filter")
    context = _add_rule_context(database)

    initial = None
    selected = None
    request_payload = None
    for product in context["products"]:
        payload = {
            "plant_code": product["plant_code"],
            "version_code": product["version_code"],
            "original_request": f"{context['alias_text']} 조건으로 추가 가능한 자재 후보를 찾아줘",
            "reasons": [context["reason_code"]],
            "requested_by": "pytest",
        }
        candidate_analysis = service.analyze_candidates(
            payload,
            [{
                "action_type": "ADD",
                "target_type": context["target_type"],
                "target_item_name": context["evaluation_item"],
            }],
        )
        pass_candidate = next(
            (row for row in candidate_analysis["candidates"] if row["status"] == "PASS"),
            None,
        )
        if pass_candidate is not None:
            initial = candidate_analysis
            selected = pass_candidate
            request_payload = payload
            break

    assert initial is not None and selected is not None and request_payload is not None
    action = initial["actions"][0]
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO bom_master(
                plant_code,parent_item_code,child_item_code,location_code,
                sequence_no,quantity,valid_from,valid_to,row_revision,status
            ) VALUES(?,?,?,?,999,1,?,NULL,1,'ACTIVE')
            """,
            (
                request_payload["plant_code"],
                action["parent_item_code"],
                selected["candidate_item_code"],
                action["location_code"],
                date.today().isoformat(),
            ),
        )

    reanalysis = service.analyze_candidates(
        request_payload,
        [{
                "action_type": "ADD",
                "target_type": context["target_type"],
                "target_item_name": context["evaluation_item"],
            }],
    )
    duplicate = next(
        row for row in reanalysis["candidates"]
        if row["candidate_item_code"] == selected["candidate_item_code"]
    )
    assert duplicate["status"] == "FAIL"
    assert duplicate["technical_status"] == "FAIL"
    assert duplicate["rank"] is None
    assert any("이미 활성 자재" in reason for reason in duplicate["decision_reasons"])


def test_quantity_change_without_explicit_reason_uses_user_request(tmp_path):
    service, database = _service(tmp_path, "design-change-quantity-default-reason")
    context = _action_context(database, "QUANTITY_CHANGE", "MATERIAL")
    relation = context["relation"]
    _ensure_large_inventory(database, context["plant_code"], relation["child_item_code"])
    new_quantity = float(relation["quantity"]) + 1.0

    analysis = service.analyze_candidates(
        {
            "plant_code": context["plant_code"],
            "version_code": context["version_code"],
            "original_request": (
                f"{context['version_code']} {context['plant_code']}에서 "
                f"{relation['child_item_code']} 수량을 {new_quantity:g}로 변경하자"
            ),
            "reasons": [],
            "requested_by": "pytest",
        },
        [{
            "action_type": "QUANTITY_CHANGE",
            "old_item_code": relation["child_item_code"],
            "parent_item_code": relation["parent_item_code"],
            "location_code": relation["location_code"],
            "new_quantity": new_quantity,
        }],
    )

    assert analysis["analysis_context"]["primary_reason_code"] == "USER_REQUEST"
    assert analysis["analysis_context"]["reason_codes"] == ["USER_REQUEST"]
    assert analysis["actions"][0]["evaluation_status"] == "PASS"
