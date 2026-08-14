from __future__ import annotations

import base64
from datetime import datetime

from mcp_server.capabilities.query import get_bom_data
from mcp_server.capabilities.design_change import generate_design_change_report_data
from services.bom_excel_export_service import BomExcelExportService
from services.design_change_word_report_service import DesignChangeWordReportService


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _file_result(file_name: str, mime_type: str, content: bytes, **metadata) -> dict:
    return {
        "success": True,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_data_base64": base64.b64encode(content).decode("ascii"),
        "file_size": len(content),
        "production_bom_modified": False,
        **metadata,
    }


def export_bom_excel_data(product_id: str, as_of_date: str | None = None) -> dict:
    """현재 조회조건으로 BOM을 재조회하고 Excel 파일을 생성합니다."""
    normalized_product_id = str(product_id).strip()
    if not normalized_product_id:
        raise ValueError("product_id는 비어 있지 않은 문자열이어야 합니다.")
    rows = get_bom_data(normalized_product_id, as_of_date)
    if not rows:
        return {
            "success": False,
            "message": "조회 조건에 해당하는 BOM이 없어 Excel을 생성하지 않았습니다.",
            "row_count": 0,
            "production_bom_modified": False,
        }
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    content = BomExcelExportService.build(
        rows, normalized_product_id, as_of_date, generated_at
    )
    safe_id = normalized_product_id.replace("/", "_").replace("\\", "_")
    date_token = (as_of_date or datetime.now().date().isoformat()).replace("-", "")
    return _file_result(
        f"BOM_{safe_id}_{date_token}.xlsx", XLSX_MIME, content,
        row_count=len(rows), generated_at=generated_at,
        query_conditions={"product_id": normalized_product_id, "as_of_date": as_of_date},
    )


def export_design_change_report_data(change_id: str) -> dict:
    """설계변경·AI 품평 데이터를 조회하고 Word 완료문서를 생성합니다."""
    normalized_change_id = str(change_id).strip().upper()
    if not normalized_change_id:
        raise ValueError("change_id는 비어 있지 않은 문자열이어야 합니다.")
    report = generate_design_change_report_data(change_id=normalized_change_id)
    if not report.get("success"):
        return report
    content = DesignChangeWordReportService().build(report)
    return _file_result(
        f"{normalized_change_id}_design_change_report.docx", DOCX_MIME, content,
        change_id=normalized_change_id, report_stage="PRE_APPLY",
    )
