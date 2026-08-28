from __future__ import annotations

from datetime import date

from database import SQLiteDatabase
from scripts.database_lifecycle import rebuild_latest_database
from services.design_change_workflow_service import DesignChangeWorkflowService
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


def _service(tmp_path):
    path = tmp_path / "macro-target-resolution.db"
    rebuild_latest_database(path)
    return DesignChangeWorkflowService(SQLiteDatabase(path))


def _unique_named_material(service: DesignChangeWorkflowService):
    today = date.today().isoformat()
    with service.repository.database.connection() as connection:
        row = connection.execute(
            """WITH RECURSIVE product_rows AS (
                 SELECT b.parent_item_code AS version_code,b.plant_code,
                        b.child_item_code,i.item_name,i.description
                 FROM bom_master b
                 JOIN item_master p
                   ON p.item_code=b.parent_item_code AND p.item_type='VERSION'
                 JOIN item_master i ON i.item_code=b.child_item_code
                 WHERE b.status='ACTIVE' AND i.item_type='MATERIAL'
               )
               SELECT version_code,plant_code,item_name,MIN(child_item_code) AS item_code,
                      COUNT(DISTINCT child_item_code) AS code_count
               FROM product_rows
               WHERE item_name IS NOT NULL AND TRIM(item_name)<>''
               GROUP BY version_code,plant_code,item_name
               HAVING COUNT(DISTINCT child_item_code)=1
               ORDER BY version_code,plant_code,item_name
               LIMIT 1"""
        ).fetchone()
    assert row is not None
    return dict(row), today


def test_service_resolves_name_only_target_inside_scoped_bom(tmp_path):
    service = _service(tmp_path)
    row, today = _unique_named_material(service)

    prepared = service._prepare_analysis(
        {
            "version_code": row["version_code"],
            "plant_code": row["plant_code"],
            "original_request": f"{row['item_name']} 자재를 변경하고싶어",
            "as_of_date": today,
            "effective_date": today,
        },
        [{
            "action_type": "REPLACE",
            "target_item_name": row["item_name"],
        }],
    )

    action = prepared["actions"][0]
    assert action["old_item_code"] == row["item_code"]
    assert action["target_resolution_source"] == "SCOPED_BOM_NAME_MATCH"


def test_router_extracts_named_target_for_macro_routing():
    router = DEFAULT_DOMAIN_INTENT_ROUTER

    assert router.extract_named_change_target(
        "LTA400HR01-001 P01 모델에서 SEALANT를 변경하고싶어"
    ) == "SEALANT"

    assert router.extract_named_change_target(
        "LTA400HR01-001 P01 모델에서 TFT 자재 수량을 2로 바꾸고싶어"
    ) == "TFT"

    assert router.extract_named_change_target(
        "LTA400HR01-001 P01 모델에서 자재를 변경하고싶어"
    ) is None


def test_name_resolution_never_searches_outside_selected_version(tmp_path):
    service = _service(tmp_path)
    row, today = _unique_named_material(service)

    code = service._resolve_source_item_code_by_name(
        request={
            "version_code": row["version_code"],
            "plant_code": row["plant_code"],
            "as_of_date": today,
        },
        target_item_name=row["item_name"],
    )
    assert code == row["item_code"]
