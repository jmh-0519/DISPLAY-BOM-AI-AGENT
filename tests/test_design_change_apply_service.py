import shutil
from pathlib import Path

import pandas as pd
import pytest

from services.bom_service import BomService
from services.design_change_apply_service import (
    DesignChangeApplyService,
)
from services.review_service import (
    ReviewService,
)

TEST_DATE = "2026-08-10"


def create_service() -> DesignChangeApplyService:
    return DesignChangeApplyService(
        bom_service=BomService()
    )

def create_component_apply_service(
    tmp_path: Path,
) -> tuple[
    DesignChangeApplyService,
    Path,
]:
    """
    실제 data 폴더를 임시 위치로 복사하고
    Component REPLACE용 테스트 Change를 추가합니다.
    """

    source_data = Path(
        "data"
    )

    test_data = (
        tmp_path / "data"
    )

    shutil.copytree(
        source_data,
        test_data,
    )

    changes_path = (
        test_data
        / "change_bom.csv"
    )

    items_path = (
        test_data
        / "change_bom_item.csv"
    )

    changes = pd.read_csv(
        changes_path,
        encoding="utf-8-sig",
    )

    changes.loc[
        len(changes)
    ] = {
        "change_id": (
            "CHG-TEST-COMP-001"
        ),
        "product_id": (
            "LTA400HR01-0"
        ),
        "change_type": "REPLACE",
        "requested_date": (
            "2026-08-10"
        ),
        "effective_date": (
            "2026-08-15"
        ),
        "reason": (
            "Component Replace Test"
        ),
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

    items = pd.read_csv(
        items_path,
        encoding="utf-8-sig",
    )

    items.loc[
        len(items)
    ] = {
        "change_id": (
            "CHG-TEST-COMP-001"
        ),
        "item_seq": 1,
        "action": "REPLACE",
        "bom_parent": (
            "LJ94-100004"
        ),
        "old_bom_child": (
            "0001-200010"
        ),
        "new_bom_child": (
            "9000-290004"
        ),
        "location": "LC_SEALANT",
        "sequence_no": 20,
        "quantity": 1,
        "effective_date": (
            "2026-08-15"
        ),
    }

    items.to_csv(
        items_path,
        index=False,
        encoding="utf-8-sig",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    service = (
        DesignChangeApplyService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    return service, test_data

def create_assembly_apply_service(
    tmp_path: Path,
) -> tuple[
    DesignChangeApplyService,
    Path,
]:
    source_data = Path("data")
    test_data = tmp_path / "data"

    shutil.copytree(
        source_data,
        test_data,
    )

    changes_path = (
        test_data
        / "change_bom.csv"
    )

    items_path = (
        test_data
        / "change_bom_item.csv"
    )

    changes = pd.read_csv(
        changes_path,
        encoding="utf-8-sig",
    )

    changes.loc[len(changes)] = {
        "change_id": "CHG-TEST-ASM-001",
        "product_id": "LTA400HR01-0",
        "change_type": "REPLACE",
        "requested_date": "2026-08-10",
        "effective_date": "2026-08-20",
        "reason": "Assembly Replace Test",
        "analysis_result": "CONDITIONAL",
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

    items = pd.read_csv(
        items_path,
        encoding="utf-8-sig",
    )

    items.loc[len(items)] = {
        "change_id": "CHG-TEST-ASM-001",
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
        items_path,
        index=False,
        encoding="utf-8-sig",
    )

    bom_service = BomService(
        data_dir=str(test_data)
    )

    service = DesignChangeApplyService(
        bom_service=bom_service,
        data_dir=str(test_data),
    )

    return service, test_data

def test_preview_replace_replaces_component() -> None:
    service = create_service()

    virtual_bom = service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="0001-200003",
        new_material_id="9000-299902",
        as_of_date=TEST_DATE,
    )

    child_ids = set(
        virtual_bom["bom_child"].astype(str).tolist()
    )

    assert "9000-299902" in child_ids
    assert "0001-200003" not in child_ids


def test_preview_replace_does_not_modify_original_bom() -> None:
    service = create_service()

    service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="0001-200003",
        new_material_id="9000-299902",
        as_of_date=TEST_DATE,
    )

    original_bom = service.bom_service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    child_ids = set(
        original_bom["bom_child"].astype(str).tolist()
    )

    assert "0001-200003" in child_ids
    assert "9000-299902" not in child_ids


def test_preview_replace_replaces_assembly() -> None:
    service = create_service()

    virtual_bom = service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="LJ94-100004",
        new_material_id="LJ94-190004",
        as_of_date=TEST_DATE,
    )

    child_ids = set(
        virtual_bom["bom_child"].astype(str).tolist()
    )

    assert "LJ94-190004" in child_ids
    assert "LJ94-100004" not in child_ids


def test_preview_replace_removes_old_assembly_subtree() -> None:
    service = create_service()

    original_bom = service.bom_service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    old_lc_row = original_bom[
        original_bom["bom_child"] == "LJ94-100004"
    ].iloc[0]

    old_path = str(old_lc_row["bom_path"])

    virtual_bom = service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="LJ94-100004",
        new_material_id="LJ94-190004",
        as_of_date=TEST_DATE,
    )

    virtual_paths = (
        virtual_bom["bom_path"].astype(str).tolist()
    )

    assert old_path not in virtual_paths
    assert not any(
        path.startswith(old_path + "/")
        for path in virtual_paths
    )


def test_preview_replace_adds_new_assembly_subtree() -> None:
    service = create_service()

    virtual_bom = service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="LJ94-100004",
        new_material_id="LJ94-190004",
        as_of_date=TEST_DATE,
    )

    new_subtree = service.bom_service.get_bom(
        "LJ94-190004",
        as_of_date=TEST_DATE,
    )

    expected_child_ids = set(
        new_subtree["bom_child"].astype(str).tolist()
    )

    virtual_child_ids = set(
        virtual_bom["bom_child"].astype(str).tolist()
    )

    assert expected_child_ids.issubset(
        virtual_child_ids
    )


def test_preview_replace_keeps_assembly_position() -> None:
    service = create_service()

    original_bom = service.bom_service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    old_row = original_bom[
        original_bom["bom_child"] == "LJ94-100004"
    ].iloc[0]

    virtual_bom = service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="LJ94-100004",
        new_material_id="LJ94-190004",
        as_of_date=TEST_DATE,
    )

    new_row = virtual_bom[
        virtual_bom["bom_child"] == "LJ94-190004"
    ].iloc[0]

    assert new_row["bom_parent"] == old_row["bom_parent"]
    assert new_row["location"] == old_row["location"]
    assert new_row["sequence_no"] == old_row["sequence_no"]
    assert new_row["quantity"] == old_row["quantity"]
    assert new_row["level"] == old_row["level"]


def test_preview_replace_keeps_original_data_unchanged_after_assembly_replace() -> None:
    service = create_service()

    service.preview_replace(
        product_id="LTA400HR01-0",
        old_material_id="LJ94-100004",
        new_material_id="LJ94-190004",
        as_of_date=TEST_DATE,
    )

    original_bom = service.bom_service.get_bom_explosion(
        "LTA400HR01-0",
        as_of_date=TEST_DATE,
    )

    child_ids = set(
        original_bom["bom_child"].astype(str).tolist()
    )

    assert "LJ94-100004" in child_ids
    assert "LJ94-190004" not in child_ids


def test_apply_approved_preview_modifies_only_effective_bom(tmp_path: Path) -> None:
    source_data = Path("data")
    test_data = tmp_path / "data"
    shutil.copytree(source_data, test_data)
    service = DesignChangeApplyService(
        bom_service=BomService(data_dir=str(test_data)),
        data_dir=str(test_data),
    )
    preview = service.create_preview_revision(
        product_id="LTA400HR01-0",
        old_material_id="0001-200010",
        new_material_id="9000-290004",
        as_of_date="2026-08-10",
    )
    result = service.apply_approved_preview(
        preview_revision=preview["preview_revision"],
        product_id="LTA400HR01-0",
        old_material_id="0001-200010",
        new_material_id="9000-290004",
        preview_as_of_date="2026-08-10",
        effective_date="2026-08-15",
        applied_by="USER01",
    )
    assert result["result"] == "APPLIED"
    assert result["production_bom_modified"] is True
    after = service.bom_service.get_bom_explosion(
        "LTA400HR01-0", as_of_date="2026-08-15"
    )
    ids = set(after["bom_child"].astype(str))
    assert "0001-200010" not in ids
    assert "9000-290004" in ids


def test_apply_approved_preview_rejects_wrong_revision(tmp_path: Path) -> None:
    test_data = tmp_path / "data"
    shutil.copytree(Path("data"), test_data)
    service = DesignChangeApplyService(
        bom_service=BomService(data_dir=str(test_data)),
        data_dir=str(test_data),
    )
    with pytest.raises(ValueError, match="Revision"):
        service.apply_approved_preview(
            preview_revision="PREVIEW-WRONG",
            product_id="LTA400HR01-0",
            old_material_id="0001-200010",
            new_material_id="9000-290004",
            preview_as_of_date="2026-08-10",
            effective_date="2026-08-15",
            applied_by="USER01",
        )

def test_apply_replace_component_updates_effective_bom(
    tmp_path: Path,
) -> None:
    service, _ = (
        create_component_apply_service(
            tmp_path
        )
    )

    result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is True
    assert result["result"] == "APPLIED"

    # 변경 적용 이전
    before_bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-14",
        )
    )

    before_ids = set(
        before_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "0001-200010" in before_ids
    assert "9000-290004" not in before_ids

    # 변경 적용일 이후
    after_bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-15",
        )
    )

    after_ids = set(
        after_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "0001-200010" not in after_ids
    assert "9000-290004" in after_ids

def test_apply_replace_keeps_old_bom_history(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    old_row = bom[
        (
            bom["bom_parent"]
            == "LJ94-100004"
        )
        &
        (
            bom["bom_child"]
            == "0001-200010"
        )
    ].iloc[0]

    assert (
        old_row["end_date"]
        == "2026-08-14"
    )    

def test_apply_replace_creates_new_effective_bom_row(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    new_row = bom[
        (
            bom["bom_parent"]
            == "LJ94-100004"
        )
        &
        (
            bom["bom_child"]
            == "9000-290004"
        )
    ].iloc[-1]

    assert (
        new_row["start_date"]
        == "2026-08-15"
    )

    assert (
        new_row["end_date"]
        == "2099-12-31"
    )

    assert (
        new_row["location"]
        == "LC_SEALANT"
    )

    assert (
        int(new_row["sequence_no"])
        == 20
    )

    assert (
        float(new_row["quantity"])
        == 1
    )    

def test_apply_replace_updates_change_header_to_applied(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    changes = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    change = changes[
        changes["change_id"]
        == "CHG-TEST-COMP-001"
    ].iloc[0]

    assert (
        change["apply_status"]
        == "APPLIED"
    )

    assert (
        change["applied_date"]
        == "2026-08-10"
    )

    assert (
        change["applied_by"]
        == "BOM_AGENT"
    )    

def test_apply_replace_blocks_already_applied_change(
    tmp_path: Path,
) -> None:
    service, _ = (
        create_component_apply_service(
            tmp_path
        )
    )

    first_result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    second_result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert first_result["success"] is True

    assert second_result["success"] is False

    assert (
        second_result["result"]
        == "FAILED"
    )    

def test_apply_replace_assembly_updates_effective_bom(
    tmp_path: Path,
) -> None:
    service, _ = (
        create_assembly_apply_service(
            tmp_path
        )
    )

    result = service.apply_replace(
        change_id="CHG-TEST-ASM-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is True
    assert result["result"] == "APPLIED"
    assert result["material_type"] == "ASSEMBLY"

    before_bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-19",
        )
    )

    before_ids = set(
        before_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-100004" in before_ids
    assert "LJ94-190004" not in before_ids

    after_bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-20",
        )
    )

    after_ids = set(
        after_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "LJ94-100004" not in after_ids
    assert "LJ94-190004" in after_ids    

def test_apply_replace_assembly_uses_new_subtree_after_effective_date(
    tmp_path: Path,
) -> None:
    service, _ = create_assembly_apply_service(
        tmp_path
    )

    service.apply_replace(
        change_id="CHG-TEST-ASM-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    after_bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-20",
        )
    )

    child_ids = set(
        after_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    # 신규 LC Assembly
    assert "LJ94-190004" in child_ids

    # 신규 LC 아래에 정의된 기존 CF / TFT 구조도
    # 정상적으로 이어져야 함
    assert "LJ94-100005" in child_ids
    assert "LJ94-100006" in child_ids

    # 신규 LC 자체의 Component도 포함되어야 함
    new_lc_children = (
        service.bom_service
        .get_bom(
            "LJ94-190004",
            as_of_date="2026-08-20",
        )
    )

    expected_child_ids = set(
        new_lc_children["bom_child"]
        .astype(str)
        .tolist()
    )

    assert expected_child_ids.issubset(
        child_ids
    )    

def test_apply_replace_assembly_does_not_delete_old_subtree_definition(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_assembly_apply_service(
            tmp_path
        )
    )

    # 적용 전 old Assembly 자체의 하위 BOM 정의 저장
    before_bom_csv = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    old_subtree_before = (
        before_bom_csv[
            before_bom_csv["bom_parent"]
            == "LJ94-100004"
        ]
        .copy()
        .sort_values(
            by=[
                "sequence_no",
                "bom_child",
            ]
        )
        .reset_index(drop=True)
    )

    service.apply_replace(
        change_id="CHG-TEST-ASM-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    after_bom_csv = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    old_subtree_after = (
        after_bom_csv[
            after_bom_csv["bom_parent"]
            == "LJ94-100004"
        ]
        .copy()
        .sort_values(
            by=[
                "sequence_no",
                "bom_child",
            ]
        )
        .reset_index(drop=True)
    )

    # 기존 Assembly 자체의 하위 BOM 정의는
    # 삭제되거나 수정되면 안 됨
    pd.testing.assert_frame_equal(
        old_subtree_before,
        old_subtree_after,
        check_dtype=False,
    )    

def test_validate_applied_change_passes_after_component_replace(
    tmp_path: Path,
) -> None:
    service, _ = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    change = service.design_changes[
        service.design_changes["change_id"]
        == "CHG-TEST-COMP-001"
    ].iloc[0]

    item = service.design_change_items[
        service.design_change_items["change_id"]
        == "CHG-TEST-COMP-001"
    ].iloc[0]

    result = (
        service._validate_applied_change(
            change_id="CHG-TEST-COMP-001",
            change=change,
            item=item,
        )
    )

    assert result["success"] is True

    assert (
        result["check"]
        == "BOM_INTEGRITY"
    )    

def test_apply_replace_returns_integrity_check_result(
    tmp_path: Path,
) -> None:
    service, _ = (
        create_component_apply_service(
            tmp_path
        )
    )

    result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is True
    assert result["result"] == "APPLIED"

    assert (
        result["integrity_check"]["success"]
        is True
    )

    assert (
        result["integrity_check"]["check"]
        == "BOM_INTEGRITY"
    )    

def test_apply_replace_sets_failed_when_integrity_check_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    def fake_validate(
        change_id,
        change,
        item,
    ):
        return {
            "success": False,
            "check": "TEST_FAILURE",
            "message": (
                "Integrity Check Test Failure"
            ),
        }

    monkeypatch.setattr(
        service,
        "_validate_applied_change",
        fake_validate,
    )

    result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is False
    assert result["result"] == "FAILED"

    assert (
        result["integrity_check"]["check"]
        == "TEST_FAILURE"
    )

    changes = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    change = changes[
        changes["change_id"]
        == "CHG-TEST-COMP-001"
    ].iloc[0]

    assert (
        change["apply_status"]
        == "FAILED"
    )

    assert (
        change["applied_by"]
        == "BOM_AGENT"
    )    

def test_apply_replace_rolls_back_bom_when_integrity_check_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    before_bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    def fake_validate(
        change_id,
        change,
        item,
    ):
        return {
            "success": False,
            "check": "TEST_FAILURE",
            "message": (
                "Integrity Check Test Failure"
            ),
        }

    monkeypatch.setattr(
        service,
        "_validate_applied_change",
        fake_validate,
    )

    result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is False
    assert result["result"] == "FAILED"

    after_bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    pd.testing.assert_frame_equal(
        before_bom,
        after_bom,
        check_dtype=False,
    )    

def test_apply_replace_rollback_restores_effective_bom(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, _ = (
        create_component_apply_service(
            tmp_path
        )
    )

    def fake_validate(
        change_id,
        change,
        item,
    ):
        return {
            "success": False,
            "check": "TEST_FAILURE",
            "message": (
                "Integrity Check Test Failure"
            ),
        }

    monkeypatch.setattr(
        service,
        "_validate_applied_change",
        fake_validate,
    )

    service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    bom = (
        service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-15",
        )
    )

    child_ids = set(
        bom["bom_child"]
        .astype(str)
        .tolist()
    )

    # Rollback되었으므로 기존 자재 유지
    assert "0001-200010" in child_ids

    # 신규 자재는 없어야 함
    assert "9000-290004" not in child_ids    

def test_apply_replace_blocks_before_review_approval(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    change_mask = (
        service.design_changes["change_id"]
        == "CHG-TEST-COMP-001"
    )

    service.design_changes.loc[
        change_mask,
        "apply_status",
    ] = "REVIEW_READY"

    service._save_design_changes()

    result = service.apply_replace(
        change_id="CHG-TEST-COMP-001",
        applied_by="BOM_AGENT",
        applied_date="2026-08-10",
    )

    assert result["success"] is False
    assert result["result"] == "FAILED"

    bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    old_rows = bom[
        (
            bom["bom_parent"]
            == "LJ94-100004"
        )
        &
        (
            bom["bom_child"]
            == "0001-200010"
        )
    ]

    # 품평회 승인 전이므로 Production BOM은
    # 전혀 변경되지 않아야 함
    assert not old_rows.empty

    old_row = old_rows.iloc[-1]

    assert (
        old_row["end_date"]
        != "2026-08-14"
    )    

def test_create_design_change_bom_saves_snapshot(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    result = (
        service.create_design_change_bom(
            change_id="CHG-TEST-COMP-001",
            created_date="2026-08-10",
        )
    )

    assert result["success"] is True
    assert result["result"] == "REVIEW_READY"

    detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rows = detail[
        detail["change_id"]
        == "CHG-TEST-COMP-001"
    ]

    assert not rows.empty

    child_ids = set(
        rows["bom_child"]
        .astype(str)
        .tolist()
    )

    assert "9000-290004" in child_ids    

def test_create_design_change_bom_sets_review_ready(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.create_design_change_bom(
        change_id="CHG-TEST-COMP-001",
        created_date="2026-08-10",
    )

    changes = pd.read_csv(
        test_data / "change_bom.csv",
        encoding="utf-8-sig",
    )

    change = changes[
        changes["change_id"]
        == "CHG-TEST-COMP-001"
    ].iloc[0]

    assert (
        change["apply_status"]
        == "REVIEW_READY"
    )    

def test_create_design_change_bom_marks_component_replace(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.create_design_change_bom(
        change_id="CHG-TEST-COMP-001",
        created_date="2026-08-10",
    )

    detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rows = detail[
        detail["change_id"]
        == "CHG-TEST-COMP-001"
    ]

    new_row = rows[
        rows["bom_child"]
        == "9000-290004"
    ].iloc[0]

    assert (
        new_row["change_action"]
        == "REPLACE"
    )    

def test_create_design_change_bom_keeps_unchanged_rows_as_none(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    service.create_design_change_bom(
        change_id="CHG-TEST-COMP-001",
        created_date="2026-08-10",
    )

    detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rows = detail[
        detail["change_id"]
        == "CHG-TEST-COMP-001"
    ]

    none_rows = rows[
        detail.loc[
            rows.index,
            "change_action",
        ]
        == "NONE"
    ]

    assert not none_rows.empty    

def test_create_design_change_bom_marks_assembly_replace(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_assembly_apply_service(
            tmp_path
        )
    )

    service.create_design_change_bom(
        change_id="CHG-TEST-ASM-001",
        created_date="2026-08-10",
    )

    detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rows = detail[
        detail["change_id"]
        == "CHG-TEST-ASM-001"
    ]

    new_assembly_row = rows[
        rows["bom_child"]
        == "LJ94-190004"
    ].iloc[0]

    assert (
        new_assembly_row["change_action"]
        == "REPLACE"
    )    

def test_create_design_change_bom_marks_new_assembly_subtree_as_add(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_assembly_apply_service(
            tmp_path
        )
    )

    service.create_design_change_bom(
        change_id="CHG-TEST-ASM-001",
        created_date="2026-08-10",
    )

    detail = pd.read_csv(
        test_data / "change_bom_detail.csv",
        encoding="utf-8-sig",
    )

    rows = detail[
        detail["change_id"]
        == "CHG-TEST-ASM-001"
    ]

    add_rows = rows[
        rows["change_action"]
        == "ADD"
    ]

    assert not add_rows.empty

    assert (
        add_rows["bom_parent"]
        == "LJ94-190004"
    ).any()    

def test_apply_approved_review_uses_final_review_bom(
    tmp_path: Path,
) -> None:
    # ------------------------------------------
    # 1. 테스트 Data 준비
    # ------------------------------------------

    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    change_id = "CHG-TEST-COMP-001"

    # 최초 설계변경 BOM 생성
    service.create_design_change_bom(
        change_id=change_id,
        created_date="2026-08-10",
    )

    # ------------------------------------------
    # 2. Review 생성
    # ------------------------------------------

    review_service = ReviewService(
        data_dir=str(test_data)
    )

    create_result = (
        review_service.create_review(
            change_id=change_id,
            created_by="TEST_USER",
            created_date="2026-08-10",
        )
    )

    assert create_result["success"] is True

    review_id = create_result[
        "review_id"
    ]

    # ------------------------------------------
    # 3. 품평회에서 최초 제안과 다른 자재로 수정
    # ------------------------------------------

    revise_result = (
        review_service.revise_review_bom(
            review_id=review_id,
            old_material_id="9000-290004",
            new_material_id="9000-290006",
            modified_by="REVIEWER01",
            modified_date="2026-08-11",
            remark="품평회 최종 대체 자재",
        )
    )

    assert revise_result["success"] is True
    assert (
        revise_result["current_revision"]
        == 2
    )

    # ------------------------------------------
    # 4. 품평회 PASS 상태로 만든 후 승인
    # ------------------------------------------

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

    approve_result = (
        review_service.approve_review(
            review_id=review_id,
            reviewed_by="REVIEWER01",
            completed_date="2026-08-12",
            decision_reason="최종 적합",
        )
    )

    assert approve_result["success"] is True

    # ApplyService는 Header 상태를 다시 읽어야 하므로
    # 새 인스턴스 생성
    bom_service = BomService(
        data_dir=str(test_data)
    )

    apply_service = (
        DesignChangeApplyService(
            bom_service=bom_service,
            data_dir=str(test_data),
        )
    )

    # ------------------------------------------
    # 5. 최종 Review BOM 적용
    # ------------------------------------------

    apply_result = (
        apply_service
        .apply_approved_review(
            review_id=review_id,
            applied_by="BOM_AGENT",
            applied_date="2026-08-12",
        )
    )

    assert apply_result["success"] is True
    assert apply_result["result"] == "APPLIED"

    # ------------------------------------------
    # 6. 적용일 이후 Production BOM 확인
    # ------------------------------------------

    after_bom = (
        apply_service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-15",
        )
    )

    after_ids = set(
        after_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    # 최초 AI 제안
    assert "9000-290004" not in after_ids

    # 품평회 최종 확정 자재
    assert "9000-290006" in after_ids

    # 원래 Production 자재
    assert "0001-200010" not in after_ids    

def test_apply_approved_review_returns_integrity_pass(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    change_id = "CHG-TEST-COMP-001"

    service.create_design_change_bom(
        change_id=change_id,
        created_date="2026-08-10",
    )

    review_service = ReviewService(
        data_dir=str(test_data)
    )

    create_result = review_service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    review_mask = (
        review_service.review_bom["review_id"]
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

    review_service.approve_review(
        review_id=review_id,
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="적합",
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
        apply_service.apply_approved_review(
            review_id=review_id,
            applied_by="BOM_AGENT",
            applied_date="2026-08-12",
        )
    )

    assert result["success"] is True

    assert (
        result["integrity_check"]["success"]
        is True
    )

    assert (
        result["integrity_check"]["check"]
        == "REVIEW_BOM_INTEGRITY"
    )    

def test_apply_approved_review_rolls_back_when_integrity_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    change_id = "CHG-TEST-COMP-001"

    service.create_design_change_bom(
        change_id=change_id,
        created_date="2026-08-10",
    )

    review_service = ReviewService(
        data_dir=str(test_data)
    )

    create_result = review_service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    review_mask = (
        review_service.review_bom["review_id"]
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

    review_service.approve_review(
        review_id=review_id,
        reviewed_by="REVIEWER01",
        completed_date="2026-08-12",
        decision_reason="적합",
    )

    before_bom = pd.read_csv(
        test_data / "bom.csv",
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

    def fake_validate(
        review_id,
        change_id,
        effective_date,
        applied_items,
    ):
        return {
            "success": False,
            "check": "TEST_FAILURE",
            "message": (
                "Review Integrity Test Failure"
            ),
        }

    monkeypatch.setattr(
        apply_service,
        "_validate_applied_review",
        fake_validate,
    )

    result = (
        apply_service.apply_approved_review(
            review_id=review_id,
            applied_by="BOM_AGENT",
            applied_date="2026-08-12",
        )
    )

    assert result["success"] is False
    assert result["result"] == "FAILED"

    after_bom = pd.read_csv(
        test_data / "bom.csv",
        encoding="utf-8-sig",
    )

    pd.testing.assert_frame_equal(
        before_bom,
        after_bom,
        check_dtype=False,
    )

    assert (
        result["integrity_check"]["check"]
        == "TEST_FAILURE"
    )    

def test_apply_approved_review_uses_approved_revision(
    tmp_path: Path,
) -> None:
    service, test_data = (
        create_component_apply_service(
            tmp_path
        )
    )

    change_id = "CHG-TEST-COMP-001"

    # 1. 설계변경 BOM 생성
    service.create_design_change_bom(
        change_id=change_id,
        created_date="2026-08-10",
    )

    # 2. Review 생성
    review_service = ReviewService(
        data_dir=str(test_data)
    )

    create_result = review_service.create_review(
        change_id=change_id,
        created_by="TEST_USER",
        created_date="2026-08-10",
    )

    review_id = create_result["review_id"]

    # 3. Rev.2 생성
    revise_result = (
        review_service.revise_review_bom(
            review_id=review_id,
            old_material_id="9000-290004",
            new_material_id="9000-290006",
            modified_by="REVIEWER01",
            modified_date="2026-08-11",
            remark="Rev.2 최종 승인 대상",
        )
    )

    assert revise_result["current_revision"] == 2

    # 4. PASS 상태 설정 후 Rev.2 승인
    review_mask = (
        review_service.review_bom["review_id"]
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

    approve_result = (
        review_service.approve_review(
            review_id=review_id,
            reviewed_by="REVIEWER01",
            completed_date="2026-08-12",
            decision_reason="Rev.2 승인",
        )
    )

    assert approve_result["success"] is True

    # 승인된 Revision은 2여야 함
    review_header = pd.read_csv(
        test_data / "review_bom.csv",
        encoding="utf-8-sig",
    )

    approved_row = review_header[
        review_header["review_id"]
        == review_id
    ].iloc[0]

    assert int(
        approved_row["approved_revision"]
    ) == 2

    # 5. 승인 후 current_revision을 임의로 1로 변경
    # 실제 적용은 current_revision이 아니라
    # approved_revision=2를 사용해야 함
    review_header.loc[
        review_header["review_id"]
        == review_id,
        "current_revision",
    ] = 1

    review_header.to_csv(
        test_data / "review_bom.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # 6. ApplyService 재생성
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
        apply_service.apply_approved_review(
            review_id=review_id,
            applied_by="BOM_AGENT",
            applied_date="2026-08-12",
        )
    )

    assert result["success"] is True
    assert result["result"] == "APPLIED"

    # approved_revision=2를 사용했는지 확인
    assert result["review_revision"] == 2

    # 7. Production BOM 확인
    after_bom = (
        apply_service.bom_service
        .get_bom_explosion(
            "LTA400HR01-0",
            as_of_date="2026-08-15",
        )
    )

    after_ids = set(
        after_bom["bom_child"]
        .astype(str)
        .tolist()
    )

    # Rev.2에서 담당자가 결정한 자재
    assert "9000-290006" in after_ids

    # Rev.1의 자재는 적용되면 안 됨
    assert "9000-290004" not in after_ids    
