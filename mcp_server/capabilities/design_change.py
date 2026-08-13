from datetime import date

from services.bom_service import BomService
from services.design_change_service import DesignChangeService
from services.design_change_apply_service import DesignChangeApplyService
from services.ai_design_change_workflow_service import AiDesignChangeWorkflowService


def create_ai_change_request_data(**kwargs) -> dict:
    return AiDesignChangeWorkflowService(
        data_dir=kwargs.pop("data_dir", "data")
    ).create_change_request(**kwargs)


def create_review_bom_data(**kwargs) -> dict:
    return AiDesignChangeWorkflowService(
        data_dir=kwargs.pop("data_dir", "data")
    ).create_review_bom(**kwargs)


def run_ai_bom_review_data(**kwargs) -> dict:
    return AiDesignChangeWorkflowService(
        data_dir=kwargs.pop("data_dir", "data")
    ).run_ai_review(**kwargs)


def generate_design_change_report_data(**kwargs) -> dict:
    return AiDesignChangeWorkflowService(
        data_dir=kwargs.pop("data_dir", "data")
    ).generate_report(**kwargs)


def apply_reviewed_bom_data(**kwargs) -> dict:
    return AiDesignChangeWorkflowService(
        data_dir=kwargs.pop("data_dir", "data")
    ).apply_to_production(**kwargs)


def analyze_design_change_data(
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    as_of_date: str | date | None = None,
) -> dict:
    """자재 교체 설계변경의 가능 여부와 영향을 분석합니다."""

    normalized_values = {
        "product_id": product_id,
        "old_material_id": old_material_id,
        "new_material_id": new_material_id,
    }

    for field_name, value in normalized_values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field_name}는 비어 있지 않은 문자열이어야 합니다."
            )

        normalized_values[field_name] = value.strip()

    bom_service = BomService()
    design_change_service = DesignChangeService(
        bom_service=bom_service,
    )

    return design_change_service.analyze_replace(
        product_id=normalized_values["product_id"],
        old_material_id=normalized_values["old_material_id"],
        new_material_id=normalized_values["new_material_id"],
        as_of_date=as_of_date,
    )


def create_design_change_preview_data(
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    as_of_date: str | date | None = None,
) -> dict:
    """분석을 재검증하고 Production BOM과 분리된 Preview를 생성합니다."""

    analysis = analyze_design_change_data(
        product_id=product_id,
        old_material_id=old_material_id,
        new_material_id=new_material_id,
        as_of_date=as_of_date,
    )
    if analysis.get("result") == "FAIL":
        raise ValueError(
            "설계변경 분석이 FAIL이므로 Preview를 생성할 수 없습니다."
        )

    bom_service = BomService()
    preview = DesignChangeApplyService(
        bom_service=bom_service,
    ).create_preview_revision(
        product_id=product_id.strip(),
        old_material_id=old_material_id.strip(),
        new_material_id=new_material_id.strip(),
        as_of_date=as_of_date,
    )
    preview["analysis_status"] = analysis["result"]
    return preview


def record_design_change_decision_data(
    preview_revision: str,
    decision: str,
    comment: str | None = None,
) -> dict:
    """품평 승인된 Preview에 대한 최종 적용 승인·반려를 기록합니다.

    이 함수는 결정 레코드만 반환하며 Production BOM을 변경하지 않습니다.
    Preview 존재 여부와 현재 Workflow 단계는 Agent State에서 검증합니다.
    """

    if not isinstance(preview_revision, str) or not preview_revision.strip():
        raise ValueError("preview_revision은 비어 있지 않은 문자열이어야 합니다.")

    if not isinstance(decision, str):
        raise ValueError("decision은 APPROVE 또는 REJECT여야 합니다.")

    normalized_decision = decision.strip().upper()
    if normalized_decision not in {"APPROVE", "REJECT"}:
        raise ValueError("decision은 APPROVE 또는 REJECT여야 합니다.")

    if comment is not None and not isinstance(comment, str):
        raise ValueError("comment는 문자열이어야 합니다.")

    normalized_comment = comment.strip() if comment else None
    return {
        "success": True,
        "preview_revision": preview_revision.strip(),
        "decision": normalized_decision,
        "comment": normalized_comment,
        "production_bom_modified": False,
        "next_step": (
            "READY_TO_APPLY"
            if normalized_decision == "APPROVE"
            else "CHANGE_REJECTED"
        ),
    }


def apply_approved_design_change_data(
    preview_revision: str,
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    preview_as_of_date: str,
    effective_date: str,
    applied_by: str,
    data_dir: str = "data",
) -> dict:
    """승인된 Preview와 동일한 설계변경을 Production BOM에 적용합니다."""

    bom_service = BomService(data_dir=data_dir)
    return DesignChangeApplyService(
        bom_service=bom_service,
        data_dir=data_dir,
    ).apply_approved_preview(
        preview_revision=preview_revision,
        product_id=product_id,
        old_material_id=old_material_id,
        new_material_id=new_material_id,
        preview_as_of_date=preview_as_of_date,
        effective_date=effective_date,
        applied_by=applied_by,
    )

