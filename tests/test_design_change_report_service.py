import shutil
from pathlib import Path

import pandas as pd

from services.bom_service import BomService
from services.design_change_apply_service import (
    DesignChangeApplyService,
)
from services.design_change_report_service import (
    DesignChangeReportService,
)
from services.review_service import (
    ReviewService,
)

def create_report_test_data(
    tmp_path: Path,
) -> tuple[
    DesignChangeReportService,
    Path,
    str,
]:
    source_data = Path("data")
    test_data = tmp_path / "data"

    shutil.copytree(
        source_data,
        test_data,
    )

    change_id = "CHG-REPORT-TEST-001"

    # --------------------------------------
    # Change Header
    # --------------------------------------

    change_path = (
        test_data / "change_bom.csv"
    )

    changes = pd.read_csv(
        change_path,
        encoding="utf-8-sig",
    )

    changes.loc[len(changes)] = {
        "change_id": change_id,
        "product_id": "LTA400HR01-0",
        "change_type": "REPLACE",
        "requested_date": "2026-08-10",
        "effective_date": "2026-08-20",
        "reason": "Report Service Test",
        "analysis_result": "PASS",
        "approval_status": "APPROVED",
        "apply_status": "VALIDATED",
        "applied_date": "",
        "requested_by": "TEST_USER",
        "approved_by": "TEST_ENG",
        "applied_by": "",
    }

    changes.to_csv(
        change_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------
    # Change Item
    # --------------------------------------

    item_path = (
        test_data / "change_bom_item.csv"
    )

    items = pd.read_csv(
        item_path,
        encoding="utf-8-sig",
    )

    items.loc[len(items)] = {
        "change_id": change_id,
        "item_seq": 1,
        "action": "REPLACE",
        "bom_parent": "LJ94-100004",
        "old_bom_child": "0001-200010",
        "new_bom_child": "9000-290004",
        "location": "LC_SEALANT",
        "sequence_no": 20,
        "quantity": 1,
        "effective_date": "2026-08-20",
    }

    items.to_csv(
        item_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------
    # Change BOM
    # --------------------------------------

    bom_service = BomService(
        data_dir=str(test_data)
    )

    apply_service = (
        DesignChangeApplyService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    result = (
        apply_service
        .create_design_change_bom(
            change_id=change_id,
            created_date="2026-08-10",
        )
    )

    assert result["success"] is True

    # --------------------------------------
    # Review Rev.1
    # --------------------------------------

    review_service = ReviewService(
        data_dir=str(test_data)
    )

    create_review_result = (
        review_service.create_review(
            change_id=change_id,
            created_by="TEST_USER",
            created_date="2026-08-10",
        )
    )

    assert (
        create_review_result["success"]
        is True
    )

    review_id = (
        create_review_result["review_id"]
    )

    # --------------------------------------
    # 담당자 수정 → Rev.2
    # --------------------------------------

    revise_result = (
        review_service.revise_review_bom(
            review_id=review_id,
            old_material_id=(
                "9000-290004"
            ),
            new_material_id=(
                "9000-290006"
            ),
            modified_by="REVIEWER01",
            modified_date="2026-08-11",
            remark="품평회 최종 수정",
        )
    )

    assert revise_result["success"] is True

    # --------------------------------------
    # 품평회 검증 결과 직접 PASS 처리
    # ReportService 테스트 목적
    # --------------------------------------

    review_mask = (
        review_service.review_bom[
            "review_id"
        ]
        == review_id
    )

    review_service.review_bom.loc[
        review_mask,
        "review_status",
    ] = "IN_REVIEW"

    review_service.review_bom.loc[
        review_mask,
        "review_result",
    ] = "PASS"

    review_service._save_review_bom()

    # --------------------------------------
    # Review Check sample
    # --------------------------------------

    check_rows = pd.DataFrame([
        {
            "review_id": review_id,
            "change_id": change_id,
            "review_revision": 2,
            "check_seq": 1,
            "check_type": "APPROVAL",
            "target_id": "RULE-009",
            "status": "PASS",
            "actual_value": "ALL_VALID",
            "expected_value": (
                "APPROVED|CONDITIONAL"
            ),
            "blocking_yn": "N",
            "message": "Approval PASS",
            "checked_date": "2026-08-12",
        },
        {
            "review_id": review_id,
            "change_id": change_id,
            "review_revision": 2,
            "check_seq": 2,
            "check_type": "COMPATIBILITY",
            "target_id": "9000-290006",
            "status": "PASS",
            "actual_value": "",
            "expected_value": "",
            "blocking_yn": "N",
            "message": "Compatibility PASS",
            "checked_date": "2026-08-12",
        },
    ])

    review_service.review_bom_check = (
        pd.concat(
            [
                review_service.review_bom_check,
                check_rows,
            ],
            ignore_index=True,
        )
    )

    review_service._save_review_bom_check()

    # --------------------------------------
    # 품평회 승인
    # --------------------------------------

    approve_result = (
        review_service.approve_review(
            review_id=review_id,
            reviewed_by="REVIEWER01",
            completed_date="2026-08-12",
            decision_reason="품평회 적합",
        )
    )

    assert approve_result["success"] is True

    # --------------------------------------
    # 최종 Production 적용
    # --------------------------------------

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
        apply_service
        .apply_approved_review(
            review_id=review_id,
            applied_by="BOM_AGENT",
            applied_date="2026-08-12",
        )
    )

    assert apply_result["success"] is True

    # --------------------------------------
    # Report Service
    # --------------------------------------

    report_bom_service = BomService(
        data_dir=str(test_data)
    )

    report_service = (
        DesignChangeReportService(
            data_dir=str(test_data),
            bom_service=report_bom_service,
        )
    )

    return (
        report_service,
        test_data,
        change_id,
    )

def test_get_report_data_returns_complete_report(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    assert result["success"] is True

    assert (
        result["change_id"]
        == change_id
    )

    assert (
        result["product_id"]
        == "LTA400HR01-0"
    )

    assert result["review"] is not None

    assert (
        result["report_revision"]
        == 2
    )

def test_get_report_data_returns_change_items(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    assert len(
        result["change_items"]
    ) == 1

    item = result[
        "change_items"
    ][0]

    assert (
        item["old_bom_child"]
        == "0001-200010"
    )

    assert (
        item["new_bom_child"]
        == "9000-290004"
    )    

def test_get_report_data_returns_revision_history(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    revisions = {
        row["revision"]
        for row in result[
            "review_revision_history"
        ]
    }

    assert revisions == {1, 2}

def test_get_report_data_returns_change_to_review_diff(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    differences = (
        result[
            "change_to_review_diff"
        ]
    )

    assert any(
        row["action"] == "REPLACE"
        and
        row["old_material_id"]
        == "9000-290004"
        and
        row["new_material_id"]
        == "9000-290006"
        for row in differences
    )

def test_get_report_data_returns_review_check_summary(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    summary = (
        result[
            "review_check_summary"
        ]
    )

    assert (
        summary["APPROVAL"]["status"]
        == "PASS"
    )

    assert (
        summary[
            "COMPATIBILITY"
        ]["status"]
        == "PASS"
    )

def test_get_report_data_returns_production_before_after(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    before_ids = {
        row["bom_child"]
        for row in result[
            "production_before_bom"
        ]
    }

    after_ids = {
        row["bom_child"]
        for row in result[
            "production_after_bom"
        ]
    }

    assert "0001-200010" in before_ids

    assert "0001-200010" not in after_ids

    assert "9000-290006" in after_ids

def test_get_report_data_returns_production_diff(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        change_id
    )

    differences = result[
        "production_diff"
    ]

    assert any(
        row["action"] == "REPLACE"
        and
        row["old_material_id"]
        == "0001-200010"
        and
        row["new_material_id"]
        == "9000-290006"
        for row in differences
    )

def test_get_report_data_returns_failure_for_unknown_change(
    tmp_path: Path,
) -> None:
    service, _, _ = (
        create_report_test_data(
            tmp_path
        )
    )

    result = service.get_report_data(
        "CHG-NOT-FOUND"
    )

    assert result["success"] is False

                            