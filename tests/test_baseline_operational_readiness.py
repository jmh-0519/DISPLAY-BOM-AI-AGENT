from __future__ import annotations

import shutil
from pathlib import Path

from database import SQLiteDatabase
from scripts.seed_design_change_business_sample import seed_design_change_business_sample
from services.design_change_workflow_service import DesignChangeWorkflowService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_DB = PROJECT_ROOT / "data" / "display_bom_seed.db"


def _seeded_service(tmp_path) -> DesignChangeWorkflowService:
    target = tmp_path / "baseline-operational.db"
    shutil.copy2(SEED_DB, target)
    database = SQLiteDatabase(target)
    seed_design_change_business_sample(database)
    return DesignChangeWorkflowService(database)


def test_baseline_product_plant_pairs_receive_default_production_plan(tmp_path):
    service = _seeded_service(tmp_path)
    with service.repository.database.connection() as connection:
        missing = connection.execute(
            """SELECT DISTINCT b.plant_code,b.parent_item_code AS version_code
               FROM bom_master b
               JOIN version_master v ON v.version_code=b.parent_item_code
               WHERE b.status='ACTIVE'
                 AND COALESCE(v.specification,'') NOT LIKE '%DESIGN_CHANGE_BUSINESS_SAMPLE%'
                 AND NOT EXISTS (
                   SELECT 1 FROM production_plans p
                   WHERE p.version_code=b.parent_item_code
                     AND p.plant_code=b.plant_code
                     AND p.plan_date>='2026-08-19'
                     AND p.status='CONFIRMED'
                 )"""
        ).fetchall()
    assert missing == []


def test_baseline_cost_candidate_uses_bom_quantity_even_when_production_plan_exists(tmp_path):
    service = _seeded_service(tmp_path)
    with service.repository.database.connection() as connection:
        roots = connection.execute(
            """SELECT DISTINCT b.plant_code,b.parent_item_code AS version_code
               FROM bom_master b
               JOIN version_master v ON v.version_code=b.parent_item_code
               WHERE b.status='ACTIVE'
                 AND COALESCE(v.specification,'') NOT LIKE '%DESIGN_CHANGE_BUSINESS_SAMPLE%'
               ORDER BY b.plant_code,b.parent_item_code"""
        ).fetchall()

    chosen = None
    for root in roots:
        scan = service.scan_product_cost_reduction_candidates(
            version_code=root["version_code"],
            plant_code=root["plant_code"],
            as_of_date="2026-08-19",
            include_target_types=["MATERIAL"],
            candidates_per_item=5,
        )
        for opportunity in scan["opportunities"]:
            confirmed = [
                row for row in opportunity["candidates"]
                if row["cost_reduction_status"] == "CONFIRMED"
                and row["technical_status"] == "PASS"
            ]
            if confirmed and float(opportunity.get("bom_quantity") or 0) > 1:
                chosen = (root, opportunity, confirmed[0])
                break
        if chosen:
            break

    assert chosen is not None, "Seeded baseline must contain a technically valid cost-saving material path"
    root, opportunity, scan_candidate = chosen
    result = service.analyze_candidates(
        {
            "version_code": root["version_code"],
            "plant_code": root["plant_code"],
            "reasons": ["COST"],
            "as_of_date": "2026-08-19",
            "effective_date": "2026-09-01",
            "original_request": "제품 BOM에서 원가절감 가능한 자재를 상세 분석",
            "normalized_request": "COST REPLACE",
            "requested_by": "tester",
        },
        [{
            "action_type": "REPLACE",
            "old_item_code": opportunity["source_item_code"],
            "parent_item_code": opportunity["parent_item_code"],
            "location_code": opportunity["location_code"],
        }],
    )
    candidate = next(
        row for row in result["candidates"]
        if row["candidate_item_code"] == scan_candidate["candidate_item_code"]
    )

    demand = candidate["demand"]
    assert demand["source"] == "BOM_QUANTITY"
    assert demand["required_quantity_basis"] == "BOM_QUANTITY"
    assert demand["production_plan_quantity"] is None
    assert demand["quantity"] == float(opportunity["bom_quantity"])
    assert candidate["supplier_status"] == "PASS"
    assert candidate["inventory_status"] == "PASS"
    assert candidate["status"] == "PASS"
