from datetime import date

from database import SQLiteDatabase
from core.database_config import sqlite_database_path
from services.sqlite_design_change_workflow_service import SQLiteDesignChangeWorkflowService


def _workflow() -> SQLiteDesignChangeWorkflowService:
    return SQLiteDesignChangeWorkflowService(SQLiteDatabase(sqlite_database_path()))


def create_ai_change_request_data(**kwargs) -> dict:
    kwargs.pop("data_dir", None)
    return _workflow().create_change_request(**kwargs)


def create_review_bom_data(**kwargs) -> dict:
    kwargs.pop("data_dir", None)
    return _workflow().create_review_bom(**kwargs)


def run_ai_bom_review_data(**kwargs) -> dict:
    kwargs.pop("data_dir", None)
    return _workflow().run_ai_review(**kwargs)


def generate_design_change_report_data(**kwargs) -> dict:
    kwargs.pop("data_dir", None)
    return _workflow().generate_report(**kwargs)


def apply_reviewed_bom_data(**kwargs) -> dict:
    kwargs.pop("data_dir", None)
    return _workflow().apply_reviewed_bom(**kwargs)


def analyze_design_change_data(
    plant_code: str,
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    as_of_date: str | date | None = None,
) -> dict:
    """자재 교체 설계변경의 가능 여부와 영향을 분석합니다."""

    normalized_values = {
        "plant_code": plant_code,
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

    return _workflow().analyze_replace(
        plant_code=normalized_values["plant_code"],
        product_id=normalized_values["product_id"],
        old_material_id=normalized_values["old_material_id"],
        new_material_id=normalized_values["new_material_id"],
        as_of_date=as_of_date,
    )


def create_design_change_preview_data(
    plant_code: str,
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    as_of_date: str | date | None = None,
) -> dict:
    """분석을 재검증하고 Production BOM과 분리된 Preview를 생성합니다."""

    analysis = analyze_design_change_data(
        plant_code=plant_code,
        product_id=product_id,
        old_material_id=old_material_id,
        new_material_id=new_material_id,
        as_of_date=as_of_date,
    )
    if analysis.get("result") == "FAIL":
        raise ValueError(
            "설계변경 분석이 FAIL이므로 Preview를 생성할 수 없습니다."
        )

    return {"success": True, "result": "ANALYZED", "analysis_status": analysis["result"],
            "analysis": analysis, "production_bom_modified": False}


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

    raise RuntimeError(
        "구형 Preview Apply 경로는 STEP25에서 제거되었습니다. "
        "Review BOM을 승인한 뒤 apply_reviewed_bom Tool을 사용하세요."
    )
