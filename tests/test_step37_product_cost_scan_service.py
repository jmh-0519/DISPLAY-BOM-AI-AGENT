from pathlib import Path
import shutil

from database import SQLiteDatabase
from services.phase3_workflow_service import Phase3WorkflowService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DB_PATH = PROJECT_ROOT / "data" / "display_bom.db"


def _temp_service(tmp_path) -> Phase3WorkflowService:
    db_path = tmp_path / "step37.db"
    shutil.copy2(BASE_DB_PATH, db_path)
    return Phase3WorkflowService(SQLiteDatabase(db_path))


def _find_scan_with_opportunities(service: Phase3WorkflowService) -> dict:
    with service.repository.database.connection() as connection:
        rows = connection.execute(
            """SELECT DISTINCT b.plant_code,b.parent_item_code AS version_code
               FROM bom_master b
               JOIN item_master i ON i.item_code=b.parent_item_code
               WHERE b.status='ACTIVE' AND i.item_type='VERSION' AND i.active_yn='Y'
               ORDER BY b.plant_code,b.parent_item_code"""
        ).fetchall()
    for row in rows:
        result = service.scan_product_cost_reduction_candidates(
            version_code=row["version_code"],
            plant_code=row["plant_code"],
            candidates_per_item=2,
        )
        if result["opportunity_source_count"] > 0:
            return result
    raise AssertionError("No active product BOM produced any replaceable opportunity")


def test_product_cost_scan_is_read_only_and_finds_eligible_opportunities(tmp_path):
    service = _temp_service(tmp_path)
    with service.repository.database.connection() as connection:
        before = connection.execute("SELECT COUNT(*) FROM change_requests").fetchone()[0]

    result = _find_scan_with_opportunities(service)

    with service.repository.database.connection() as connection:
        after = connection.execute("SELECT COUNT(*) FROM change_requests").fetchone()[0]

    assert after == before
    assert result["request_created"] is False
    assert result["production_bom_modified"] is False
    assert result["opportunity_source_count"] > 0
    assert result["technical_eligible_candidate_count"] > 0
    assert any(
        candidate["technical_status"] in {"PASS", "CONDITIONAL"}
        for row in result["opportunities"]
        for candidate in row["candidates"]
    )


def test_cost_scan_never_claims_savings_without_price_evidence(tmp_path):
    service = _temp_service(tmp_path)
    result = _find_scan_with_opportunities(service)
    unavailable = [
        candidate
        for row in result["opportunities"]
        for candidate in row["candidates"]
        if candidate["cost_reduction_status"] == "UNAVAILABLE"
    ]
    if not unavailable:
        # The test remains data-driven: if every discovered pair happens to gain
        # complete price evidence in a future seed, CONFIRMED rows must have real deltas.
        confirmed = [
            candidate
            for row in result["opportunities"]
            for candidate in row["candidates"]
            if candidate["cost_reduction_status"] == "CONFIRMED"
        ]
        assert confirmed
        assert all(c["unit_savings"] is not None and c["savings_pct"] is not None for c in confirmed)
        return
    for candidate in unavailable:
        assert candidate["unit_savings"] is None
        assert candidate["savings_pct"] is None
