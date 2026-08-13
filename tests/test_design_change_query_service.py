import shutil
from pathlib import Path

import pandas as pd

from services.design_change_apply_service import (
    DesignChangeApplyService,
)

from services.bom_service import BomService
from services.design_change_query_service import (
    DesignChangeQueryService,
)


TEST_DATE = "2026-08-10"


def create_service() -> DesignChangeQueryService:
    bom_service = BomService()

    return DesignChangeQueryService(
        bom_service=bom_service,
    )


def test_get_change_result_returns_header() -> None:
    service = create_service()

    result = service.get_change_result(
        "CHG-20260810-001"
    )

    assert result["success"] is True

    assert (
        result["change_id"]
        == "CHG-20260810-001"
    )

    assert (
        result["product_id"]
        == "LTA400HR02-0"
    )

    assert (
        result["change_type"]
        == "REPLACE"
    )


def test_get_change_result_returns_items() -> None:
    service = create_service()

    result = service.get_change_result(
        "CHG-20260810-001"
    )

    assert result["success"] is True
    assert len(result["items"]) >= 1

    item = result["items"][0]

    assert (
        item["old_bom_child"]
        == "LJ94-110001"
    )

    assert (
        item["new_bom_child"]
        == "LJ94-190001"
    )


def test_get_change_result_returns_before_after_dates() -> None:
    service = create_service()

    result = service.get_change_result(
        "CHG-20260810-001"
    )

    assert (
        result["effective_date"]
        == "2026-08-15"
    )

    assert (
        result["before_date"]
        == "2026-08-14"
    )


def test_get_change_result_returns_bom() -> None:
    service = create_service()

    result = service.get_change_result(
        "CHG-20260810-001"
    )

    assert result["before_bom"].empty is False
    assert result["after_bom"].empty is False


def test_get_change_result_returns_failure_for_unknown_change() -> None:
    service = create_service()

    result = service.get_change_result(
        "CHG-NOT-FOUND"
    )

    assert result["success"] is False

def test_applied_change_query_returns_old_before_and_new_after(
    tmp_path: Path,
) -> None:
    # ------------------------------------------
    # 1. 테스트용 data 복사
    # ------------------------------------------

    source_data = Path("data")
    test_data = tmp_path / "data"

    shutil.copytree(
        source_data,
        test_data,
    )

    # ------------------------------------------
    # 2. 테스트 Design Change 생성
    # ------------------------------------------

    changes_path = (
        test_data / "change_bom.csv"
    )

    changes = pd.read_csv(
        changes_path,
        encoding="utf-8-sig",
    )

    changes.loc[len(changes)] = {
        "change_id": "CHG-QUERY-TEST-001",
        "product_id": "LTA400HR01-0",
        "change_type": "REPLACE",
        "requested_date": "2026-08-10",
        "effective_date": "2026-08-15",
        "reason": "Query Integration Test",
        "analysis_result": "PASS",
        "approval_status": "APPROVED",
        "apply_status": "APPROVED_TO_APPLY",
        "applied_date": "",
        "requested_by": "TEST_USER",
        "approved_by": "TEST_ENG",
        "applied_by": "",
    }

    changes.to_csv(
        changes_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------
    # 3. 변경 Detail 생성
    # ------------------------------------------

    items_path = (
        test_data
        / "change_bom_item.csv"
    )

    items = pd.read_csv(
        items_path,
        encoding="utf-8-sig",
    )

    items.loc[len(items)] = {
        "change_id": "CHG-QUERY-TEST-001",
        "item_seq": 1,
        "action": "REPLACE",
        "bom_parent": "LJ94-100004",
        "old_bom_child": "0001-200010",
        "new_bom_child": "9000-290004",
        "location": "LC_SEALANT",
        "sequence_no": 20,
        "quantity": 1,
        "effective_date": "2026-08-15",
    }

    items.to_csv(
        items_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------
    # 4. 실제 Design Change 적용
    # ------------------------------------------

    bom_service = BomService(
        data_dir=str(test_data)
    )

    apply_service = (
        DesignChangeApplyService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    apply_result = (
        apply_service.apply_replace(
            change_id="CHG-QUERY-TEST-001",
            applied_by="BOM_AGENT",
            applied_date="2026-08-10",
        )
    )

    assert apply_result["success"] is True
    assert apply_result["result"] == "APPLIED"

    # ------------------------------------------
    # 5. Query Service 생성
    # ------------------------------------------

    query_service = (
        DesignChangeQueryService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    result = (
        query_service.get_change_result(
            "CHG-QUERY-TEST-001"
        )
    )

    assert result["success"] is True
    assert result["apply_status"] == "APPLIED"

    # ------------------------------------------
    # 6. 변경 전 BOM 검증
    # ------------------------------------------

    before_ids = set(
        result["before_bom"]["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "0001-200010" in before_ids
    assert "9000-290004" not in before_ids

    # ------------------------------------------
    # 7. 변경 후 BOM 검증
    # ------------------------------------------

    after_ids = set(
        result["after_bom"]["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "0001-200010" not in after_ids
    assert "9000-290004" in after_ids    