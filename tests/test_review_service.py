import shutil
from pathlib import Path

import pandas as pd

from services.bom_service import BomService
from services.design_change_service import (
    DesignChangeService,
)
from services.design_change_apply_service import (
    DesignChangeApplyService,
)
from services.review_service import ReviewService



class FakeDesignChangeService:

    def __init__(
        self,
        result: str,
    ) -> None:
        self.result = result

    def validate_bom_rules(
        self,
        product_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        return {
            "result": self.result,
            "rule_results": [
                {
                    "rule_id": "TEST-RULE",
                    "status": self.result,
                }
            ],
        }

    def validate_compatibility(
        self,
        product_id: str,
        new_material_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        return {
            "status": self.result,
            "message": (
                "Fake Compatibility Result"
            ),
            "blocking_reasons": (
                []
                if self.result != "FAIL"
                else [
                    "Fake Compatibility Failure"
                ]
            ),
        }    

class FakeMixedValidationService:

    def __init__(
        self,
        rule_result: str,
        compatibility_result: str,
    ) -> None:
        self.rule_result = rule_result
        self.compatibility_result = (
            compatibility_result
        )

    def validate_bom_rules(
        self,
        product_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        return {
            "result": self.rule_result,
            "rule_results": [
                {
                    "rule_id": "TEST-RULE",
                    "status": self.rule_result,
                }
            ],
        }

    def validate_compatibility(
        self,
        product_id: str,
        new_material_id: str,
        bom: pd.DataFrame,
    ) -> dict:
        return {
            "status": (
                self.compatibility_result
            ),
            "message": (
                "Fake Compatibility Result"
            ),
            "blocking_reasons": (
                []
                if self.compatibility_result
                != "FAIL"
                else [
                    "Fake Compatibility Failure"
                ]
            ),
        }
    
def create_review_test_data(
    tmp_path: Path,
) -> tuple[
    ReviewService,
    Path,
    str,
]:
    source_data = Path("data")
    test_data = tmp_path / "data"

    shutil.copytree(
        source_data,
        test_data,
    )

    change_id = "CHG-REVIEW-TEST-001"

    # ------------------------------------------
    # 1. Change Header 생성
    # ------------------------------------------

    change_bom_path = (
        test_data / "change_bom.csv"
    )

    change_bom = pd.read_csv(
        change_bom_path,
        encoding="utf-8-sig",
    )

    change_bom.loc[len(change_bom)] = {
        "change_id": change_id,
        "product_id": "LTA400HR01-0",
        "change_type": "REPLACE",
        "requested_date": "2026-08-10",
        "effective_date": "2026-08-20",
        "reason": "Review Service Test",
        "analysis_result": "PASS",
        "approval_status": "APPROVED",
        "apply_status": "VALIDATED",
        "applied_date": "",
        "requested_by": "TEST_USER",
        "approved_by": "TEST_ENG",
        "applied_by": "",
    }

    change_bom.to_csv(
        change_bom_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------
    # 2. Change Item 생성
    # ------------------------------------------

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
        "bom_parent": "LJ94-100003",
        "old_bom_child": "LJ94-100004",
        "new_bom_child": "LJ94-190004",
        "location": "LC",
        "sequence_no": 10,
        "quantity": 1,
        "effective_date": "2026-08-20",
    }

    items.to_csv(
        item_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------
    # 3. 설계변경 BOM Snapshot 생성
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

    result = (
        apply_service.create_design_change_bom(
            change_id=change_id,
            created_date="2026-08-10",
        )
    )

    assert result["success"] is True
    assert result["result"] == "REVIEW_READY"

    # ------------------------------------------
    # 4. ReviewService 생성
    # ------------------------------------------

    review_service = ReviewService(
        data_dir=str(test_data)
    )

    return (
        review_service,
        test_data,
        change_id,
    )

def test_create_review_creates_header_and_rev1(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    assert result["success"] is True
    assert result["review_status"] == "CREATED"
    assert result["review_result"] == "PENDING"
    assert result["current_revision"] == 1

def test_create_review_saves_review_header(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_bom = pd.read_csv(
        test_data / "review_bom.csv",
        encoding="utf-8-sig",
    )

    row = review_bom[
        review_bom["review_id"]
        == result["review_id"]
    ].iloc[0]

    assert row["change_id"] == change_id
    assert row["review_status"] == "CREATED"
    assert int(row["current_revision"]) == 1
    assert row["review_result"] == "PENDING"    

def test_create_review_copies_change_bom_to_rev1(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    change_detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    review_detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    change_rows = change_detail[
        change_detail["change_id"]
        == change_id
    ]

    review_rows = review_detail[
        review_detail["review_id"]
        == result["review_id"]
    ]

    assert len(review_rows) == len(
        change_rows
    )

    assert (
        review_rows["review_revision"]
        == 1
    ).all()

    assert (
        review_rows["source"]
        == "DESIGN_CHANGE"
    ).all()

    assert (
        review_rows["modified_yn"]
        == "N"
    ).all()    

def test_create_review_sets_change_to_in_review(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    change_bom = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    change = change_bom[
        change_bom["change_id"]
        == change_id
    ].iloc[0]

    assert (
        change["apply_status"]
        == "IN_REVIEW"
    )    

def test_create_review_blocks_duplicate_review(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    first_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    second_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    assert first_result["success"] is True

    assert second_result["success"] is False    

def test_create_review_blocks_change_not_review_ready(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    change_bom = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    mask = (
        change_bom["change_id"]
        == change_id
    )

    change_bom.loc[
        mask,
        "apply_status",
    ] = "VALIDATED"

    change_bom.to_csv(
        test_data / "change_bom.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # 메모리에 로딩된 Header도 동일하게 변경
    service.change_bom.loc[
        service.change_bom["change_id"]
        == change_id,
        "apply_status",
    ] = "VALIDATED"

    result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    assert result["success"] is False    

def test_revise_review_bom_creates_revision_2(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    result = service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        remark="품평회 대체 자재 검토",
    )

    assert result["success"] is True
    assert result["previous_revision"] == 1
    assert result["current_revision"] == 2
    assert (
        result["review_status"]
        == "RECHECK_REQUIRED"
    )    

def test_revise_review_bom_keeps_revision_1(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rev1 = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 1
        )
    ]

    rev2 = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 2
        )
    ]

    assert not rev1.empty
    assert not rev2.empty

    rev1_ids = set(
        rev1["bom_child"]
        .astype(str)
        .tolist()
    )

    rev2_ids = set(
        rev2["bom_child"]
        .astype(str)
        .tolist()
    )

    # Rev.1은 절대 변경되지 않음
    assert "9000-290004" in rev1_ids
    assert "9000-290006" not in rev1_ids

    # Rev.2에 담당자 수정 반영
    assert "9000-290004" not in rev2_ids
    assert "9000-290006" in rev2_ids    

def test_revise_review_bom_records_modifier(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        remark="품평회 대체 자재 검토",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    row = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 2
        )
        &
        (
            detail["bom_child"]
            == "9000-290006"
        )
    ].iloc[0]

    assert row["source"] == "REVIEW"
    assert row["modified_yn"] == "Y"
    assert row["modified_by"] == "REVIEWER01"

    assert (
        row["modified_date"]
        == "2026-08-11"
    )    

def test_revise_review_bom_updates_header(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.revise_review_bom(
        review_id=create_result["review_id"],
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    header = pd.read_csv(
        test_data / "review_bom.csv",
        encoding="utf-8-sig",
    )

    row = header[
        header["review_id"]
        == create_result["review_id"]
    ].iloc[0]

    assert int(row["current_revision"]) == 2

    assert (
        row["review_status"]
        == "RECHECK_REQUIRED"
    )

    assert (
        row["review_result"]
        == "PENDING"
    )    

def test_revalidate_review_pass(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService("PASS")
    )

    result = service.revalidate_review(
        review_id=create_result["review_id"],
    )

    assert result["success"] is True

    assert (
        result["review_result"]
        == "PASS"
    )

    assert (
        result["review_status"]
        == "IN_REVIEW"
    )    

def test_revalidate_review_conditional(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService(
            "CONDITIONAL"
        )
    )

    result = service.revalidate_review(
        review_id=create_result["review_id"],
    )

    assert result["success"] is True

    assert (
        result["review_result"]
        == "CONDITIONAL"
    )

    assert (
        result["review_status"]
        == "IN_REVIEW"
    )    

def test_revalidate_review_fail(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService("FAIL")
    )

    result = service.revalidate_review(
        review_id=create_result["review_id"],
    )

    assert result["success"] is True

    assert (
        result["review_result"]
        == "FAIL"
    )

    assert (
        result["review_status"]
        == "RECHECK_REQUIRED"
    )    

def test_revalidate_review_with_real_design_change_service(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    real_design_change_service = (
        DesignChangeService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    service.design_change_service = (
        real_design_change_service
    )

    result = service.revalidate_review(
        review_id=create_result["review_id"],
    )

    assert result["success"] is True

    assert result["review_result"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }

    assert len(
        result["rule_results"]
    ) > 0

    assert (
        result["review_status"]
        in {
            "IN_REVIEW",
            "RECHECK_REQUIRED",
        }
    )    

def test_approve_review_pass_sets_approved_to_apply(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService("PASS")
    )

    validation_result = (
        service.revalidate_review(
            review_id=create_result["review_id"],
        )
    )

    assert (
        validation_result["review_result"]
        == "PASS"
    )

    result = service.approve_review(
        review_id=create_result["review_id"],
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="품평회 검토 결과 적합",
    )

    assert result["success"] is True

    assert (
        result["review_status"]
        == "APPROVED"
    )

    assert (
        result["apply_status"]
        == "APPROVED_TO_APPLY"
    )

    review_bom = pd.read_csv(
        test_data / "review_bom.csv",
        encoding="utf-8-sig",
    )

    review = review_bom[
        review_bom["review_id"]
        == create_result["review_id"]
    ].iloc[0]

    assert (
        review["review_status"]
        == "APPROVED"
    )

    assert (
        review["reviewed_by"]
        == "REVIEWER01"
    )

    assert (
        review["completed_date"]
        == "2026-08-12"
    )

    change_bom = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    change = change_bom[
        change_bom["change_id"]
        == change_id
    ].iloc[0]

    assert (
        change["apply_status"]
        == "APPROVED_TO_APPLY"
    )    

def test_approve_review_blocks_conditional(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService(
            "CONDITIONAL"
        )
    )

    service.revalidate_review(
        review_id=create_result["review_id"],
    )

    result = service.approve_review(
        review_id=create_result["review_id"],
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="조건부 결과 승인 시도",
    )

    assert result["success"] is False
    assert result["review_result"] == "CONDITIONAL"    

def test_approve_review_blocks_fail(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService("FAIL")
    )

    service.revalidate_review(
        review_id=create_result["review_id"],
    )

    result = service.approve_review(
        review_id=create_result["review_id"],
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="FAIL 결과 승인 시도",
    )

    assert result["success"] is False    

def test_approve_review_sets_approved_revision(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    service.design_change_service = (
        FakeDesignChangeService("PASS")
    )

    service.revalidate_review(
        review_id=create_result["review_id"],
    )

    service.approve_review(
        review_id=create_result["review_id"],
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="적합",
    )

    review_bom = pd.read_csv(
        test_data / "review_bom.csv",
        encoding="utf-8-sig",
    )

    row = review_bom[
        review_bom["review_id"]
        == create_result["review_id"]
    ].iloc[0]

    assert int(
        row["approved_revision"]
    ) == int(
        row["current_revision"]
    )    

def create_assembly_review_test_data(
    tmp_path: Path,
) -> tuple[
    ReviewService,
    Path,
    str,
]:
    source_data = Path("data")
    test_data = tmp_path / "data"

    shutil.copytree(
        source_data,
        test_data,
    )

    change_id = "CHG-REVIEW-ASM-001"

    change_bom_path = (
        test_data / "change_bom.csv"
    )

    change_bom = pd.read_csv(
        change_bom_path,
        encoding="utf-8-sig",
    )

    change_bom.loc[len(change_bom)] = {
        "change_id": change_id,
        "product_id": "LTA400HR01-0",
        "change_type": "REPLACE",
        "requested_date": "2026-08-10",
        "effective_date": "2026-08-20",
        "reason": "Assembly Review Test",
        "analysis_result": "PASS",
        "approval_status": "APPROVED",
        "apply_status": "VALIDATED",
        "applied_date": "",
        "requested_by": "TEST_USER",
        "approved_by": "TEST_ENG",
        "applied_by": "",
    }

    change_bom.to_csv(
        change_bom_path,
        index=False,
        encoding="utf-8-sig",
    )

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
        "bom_parent": "LJ94-100003",
        "old_bom_child": "LJ94-100004",
        "new_bom_child": "LJ94-190004",
        "location": "LC",
        "sequence_no": 10,
        "quantity": 1,
        "effective_date": "2026-08-20",
    }

    items.to_csv(
        item_path,
        index=False,
        encoding="utf-8-sig",
    )

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

    review_service = ReviewService(
        data_dir=str(test_data),
        bom_service=bom_service,
    )

    return (
        review_service,
        test_data,
        change_id,
    )

def test_revise_review_assembly_creates_new_revision(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    result = (
        service.revise_review_assembly(
            review_id=create_result[
                "review_id"
            ],
            old_assembly_id=(
                "LJ94-190004"
            ),
            new_assembly_id=(
                "LJ94-100004"
            ),
            modified_by="REVIEWER01",
            modified_date="2026-08-11",
            as_of_date="2026-08-20",
            remark=(
                "품평회 Assembly 재검토"
            ),
        )
    )

    assert result["success"] is True

    assert (
        result["previous_revision"]
        == 1
    )

    assert (
        result["current_revision"]
        == 2
    )

    assert (
        result["review_status"]
        == "RECHECK_REQUIRED"
    )   

def test_revise_review_assembly_keeps_revision_1(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_assembly(
        review_id=review_id,
        old_assembly_id="LJ94-190004",
        new_assembly_id="LJ94-100004",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        as_of_date="2026-08-20",
        remark="품평회 Assembly 재검토",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rev1 = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 1
        )
    ]

    rev1_ids = set(
        rev1["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-190004" in rev1_ids
    assert "LJ94-100004" not in rev1_ids    

def test_revise_review_assembly_removes_old_subtree_from_revision_2(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_assembly(
        review_id=review_id,
        old_assembly_id="LJ94-190004",
        new_assembly_id="LJ94-100004",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        as_of_date="2026-08-20",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rev2 = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 2
        )
    ]

    rev2_ids = set(
        rev2["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-190004" not in rev2_ids
    assert "LJ94-100004" in rev2_ids    

def test_revise_review_assembly_adds_new_subtree_to_revision_2(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_assembly(
        review_id=review_id,
        old_assembly_id="LJ94-190004",
        new_assembly_id="LJ94-100004",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        as_of_date="2026-08-20",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rev2 = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 2
        )
    ]

    expected_subtree = (
        service.bom_service
        .get_bom_explosion(
            "LJ94-100004",
            as_of_date="2026-08-20",
        )
    )

    expected_ids = set(
        expected_subtree["bom_child"]
        .astype(str)
        .tolist()
    )

    rev2_ids = set(
        rev2["bom_child"]
        .astype(str)
        .tolist()
    )

    assert expected_ids.issubset(
        rev2_ids
    )    

def test_revise_review_assembly_sets_material_name(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_assembly(
        review_id=review_id,
        old_assembly_id="LJ94-190004",
        new_assembly_id="LJ94-100004",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        as_of_date="2026-08-20",
    )

    detail = pd.read_csv(
        test_data / "review_bom_detail.csv",
        encoding="utf-8-sig",
    )

    row = detail[
        (
            detail["review_id"]
            == review_id
        )
        &
        (
            detail["review_revision"]
            == 2
        )
        &
        (
            detail["bom_child"]
            == "LJ94-100004"
        )
    ].iloc[0]

    expected_name = (
        service.bom_service.materials[
            service.bom_service.materials[
                "material_id"
            ]
            == "LJ94-100004"
        ]
        .iloc[0]["material_name"]
    )

    assert (
        row["bom_child_name"]
        == expected_name
    )    

def test_get_review_revision_changes_finds_component_replace(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    changes = (
        service
        ._get_review_revision_changes(
            review_id=review_id,
            from_revision=1,
            to_revision=2,
        )
    )

    assert len(changes) == 1

    change = changes[0]

    assert change["action"] == "REPLACE"

    assert (
        change["old_material_id"]
        == "9000-290004"
    )

    assert (
        change["new_material_id"]
        == "9000-290006"
    )    

def test_get_review_revision_changes_finds_assembly_replace(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_assembly_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_assembly(
        review_id=review_id,
        old_assembly_id="LJ94-190004",
        new_assembly_id="LJ94-100004",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
        as_of_date="2026-08-20",
    )

    changes = (
        service
        ._get_review_revision_changes(
            review_id=review_id,
            from_revision=1,
            to_revision=2,
        )
    )

    assert any(
        change["old_material_id"]
        == "LJ94-190004"
        and
        change["new_material_id"]
        == "LJ94-100004"
        for change in changes
    )    

def test_revalidate_review_includes_compatibility_pass(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeDesignChangeService("PASS")
    )

    result = service.revalidate_review(
        review_id=review_id,
    )

    assert result["success"] is True

    assert (
        result["review_result"]
        == "PASS"
    )

    assert (
        result["rule_result"]
        == "PASS"
    )

    assert len(
        result["compatibility_results"]
    ) >= 1

    assert (
        result[
            "compatibility_results"
        ][0]["status"]
        == "PASS"
    )    

def test_revalidate_review_returns_conditional_when_compatibility_conditional(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeMixedValidationService(
            rule_result="PASS",
            compatibility_result="CONDITIONAL",
        )
    )

    result = service.revalidate_review(
        review_id=review_id,
    )

    assert result["rule_result"] == "PASS"

    assert (
        result["compatibility_results"][0][
            "status"
        ]
        == "CONDITIONAL"
    )

    assert (
        result["review_result"]
        == "CONDITIONAL"
    )

    assert (
        result["review_status"]
        == "IN_REVIEW"
    )    

def test_revalidate_review_returns_fail_when_compatibility_fails(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeMixedValidationService(
            rule_result="PASS",
            compatibility_result="FAIL",
        )
    )

    result = service.revalidate_review(
        review_id=review_id,
    )

    assert result["rule_result"] == "PASS"

    assert (
        result["compatibility_results"][0][
            "status"
        ]
        == "FAIL"
    )

    assert (
        result["review_result"]
        == "FAIL"
    )

    assert (
        result["review_status"]
        == "RECHECK_REQUIRED"
    )    

def test_revalidate_review_with_real_compatibility(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    # Rev.2 생성
    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    real_design_change_service = (
        DesignChangeService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    service.design_change_service = (
        real_design_change_service
    )

    result = service.revalidate_review(
        review_id=review_id,
    )

    assert result["success"] is True

    assert result["review_result"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }

    assert result["rule_result"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }

    assert len(
        result["compatibility_results"]
    ) >= 1

    compatibility = (
        result["compatibility_results"][0]
    )

    assert compatibility[
        "new_material_id"
    ] == "9000-290006"

    assert compatibility["status"] in {
        "PASS",
        "CONDITIONAL",
        "FAIL",
    }    

def test_revalidate_review_saves_check_results(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeMixedValidationService(
            rule_result="PASS",
            compatibility_result="PASS",
        )
    )

    result = service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-12",
    )

    assert result["success"] is True

    check_data = pd.read_csv(
        test_data
        / "review_bom_check.csv",
        encoding="utf-8-sig",
    )

    rows = check_data[
        (
            check_data["review_id"]
            == review_id
        )
        &
        (
            check_data[
                "review_revision"
            ]
            == 2
        )
    ]

    assert not rows.empty

    check_types = set(
        rows["check_type"]
    )

    assert "BOM_ATTRIBUTE" in check_types
    assert "COMPATIBILITY" in check_types

    assert set(
        rows["status"]
    ) == {"PASS"}

    assert set(
        rows["checked_date"]
    ) == {"2026-08-12"}    

def test_revalidate_review_replaces_previous_check_results(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    # Rev.2 생성
    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeMixedValidationService(
            rule_result="PASS",
            compatibility_result="PASS",
        )
    )

    # ------------------------------------------
    # 1차 검증
    # ------------------------------------------

    service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-12",
    )

    check_data = pd.read_csv(
        test_data / "review_bom_check.csv",
        encoding="utf-8-sig",
    )

    first_rows = check_data[
        (
            check_data["review_id"]
            == review_id
        )
        &
        (
            pd.to_numeric(
                check_data[
                    "review_revision"
                ],
                errors="coerce",
            )
            == 2
        )
    ]

    first_count = len(
        first_rows
    )

    assert first_count > 0

    assert set(
        first_rows["checked_date"]
    ) == {
        "2026-08-12"
    }

    # ------------------------------------------
    # 같은 Rev.2를 다시 검증
    # ------------------------------------------

    service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-13",
    )

    second_data = pd.read_csv(
        test_data / "review_bom_check.csv",
        encoding="utf-8-sig",
    )

    second_rows = second_data[
        (
            second_data["review_id"]
            == review_id
        )
        &
        (
            pd.to_numeric(
                second_data[
                    "review_revision"
                ],
                errors="coerce",
            )
            == 2
        )
    ]

    # ------------------------------------------
    # 동일 Revision 결과가 두 배로
    # 누적되면 안 됨
    # ------------------------------------------

    assert len(
        second_rows
    ) == first_count

    # 기존 8/12 결과가 삭제되고
    # 최신 8/13 결과만 남아야 함
    assert set(
        second_rows["checked_date"]
    ) == {
        "2026-08-13"
    }    

def test_get_review_check_type_classifies_rule_metrics(
    tmp_path: Path,
) -> None:
    service, _, _ = (
        create_review_test_data(
            tmp_path
        )
    )

    assert (
        service._get_review_check_type({
            "metric": "LIFECYCLE_STATUS",
        })
        == "LIFECYCLE"
    )

    assert (
        service._get_review_check_type({
            "metric": "APPROVAL_STATUS",
        })
        == "APPROVAL"
    )

    assert (
        service._get_review_check_type({
            "metric": "SUPPLIER_GRADE",
        })
        == "SUPPLIER"
    )

    assert (
        service._get_review_check_type({
            "metric": "LOCATION_EXISTS",
        })
        == "BOM_STRUCTURE"
    )

    assert (
        service._get_review_check_type({
            "metric": "REFRESH_HZ",
        })
        == "BOM_ATTRIBUTE"
    )    

def test_revalidate_review_saves_classified_real_rule_results(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    real_design_change_service = (
        DesignChangeService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    service.design_change_service = (
        real_design_change_service
    )

    result = service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-12",
    )

    assert result["success"] is True

    check_data = pd.read_csv(
        test_data / "review_bom_check.csv",
        encoding="utf-8-sig",
    )

    rows = check_data[
        (
            check_data["review_id"]
            == review_id
        )
        &
        (
            pd.to_numeric(
                check_data[
                    "review_revision"
                ],
                errors="coerce",
            )
            == 2
        )
    ]

    assert not rows.empty

    check_types = set(
        rows["check_type"]
        .astype(str)
        .tolist()
    )

    assert "BOM_STRUCTURE" in check_types
    assert "LIFECYCLE" in check_types
    assert "APPROVAL" in check_types
    assert "SUPPLIER" in check_types    

def test_revalidate_review_saves_rule_values_and_blocking_flag(
    tmp_path: Path,
) -> None:
    service, test_data, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    real_design_change_service = (
        DesignChangeService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    service.design_change_service = (
        real_design_change_service
    )

    result = service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-12",
    )

    assert result["success"] is True

    check_data = pd.read_csv(
        test_data / "review_bom_check.csv",
        encoding="utf-8-sig",
    )

    rows = check_data[
        (
            check_data["review_id"]
            == review_id
        )
        &
        (
            pd.to_numeric(
                check_data["review_revision"],
                errors="coerce",
            )
            == 2
        )
        &
        (
            check_data["check_type"].isin(
                [
                    "LIFECYCLE",
                    "APPROVAL",
                    "SUPPLIER",
                ]
            )
        )
    ]

    assert not rows.empty

    # expected_value는 Rule 기준값이므로
    # Rule 행에서는 값이 있어야 함
    assert (
        rows["expected_value"]
        .notna()
        .all()
    )

    # FAIL이면 blocking=Y,
    # 그 외에는 blocking=N
    for _, row in rows.iterrows():
        status = str(
            row["status"]
        ).strip().upper()

        blocking_yn = str(
            row["blocking_yn"]
        ).strip().upper()

        if status == "FAIL":
            assert blocking_yn == "Y"
        else:
            assert blocking_yn == "N"    

def test_get_review_summary_returns_check_type_summary(
    tmp_path: Path,
) -> None:
    service, _, change_id = (
        create_review_test_data(
            tmp_path
        )
    )

    create_result = service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    service.revise_review_bom(
        review_id=review_id,
        old_material_id="9000-290004",
        new_material_id="9000-290006",
        modified_by="REVIEWER01",
        modified_date="2026-08-11",
    )

    service.design_change_service = (
        FakeMixedValidationService(
            rule_result="PASS",
            compatibility_result="PASS",
        )
    )

    service.revalidate_review(
        review_id=review_id,
        checked_date="2026-08-12",
    )

    result = service.get_review_summary(
        review_id=review_id,
    )

    assert result["success"] is True
    assert result["review_revision"] == 2

    summary = result["summary"]

    assert (
        summary["BOM_ATTRIBUTE"]["status"]
        == "PASS"
    )

    assert (
        summary["COMPATIBILITY"]["status"]
        == "PASS"
    )

    assert (
        summary["COMPATIBILITY"]["count"]
        >= 1
    )            