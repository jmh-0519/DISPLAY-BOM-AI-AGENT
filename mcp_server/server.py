from pathlib import Path
import sys


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from mcp.server import MCPServer

from mcp_server.capabilities.query import (
    get_bom_data,
    list_materials_data,
    list_products_data,
    search_material_data,
    search_product_data,
)
from mcp_server.capabilities.design_change import (
    analyze_design_change_data,
    create_ai_change_request_data,
    create_review_bom_data,
    run_ai_bom_review_data,
    generate_design_change_report_data,
    apply_reviewed_bom_data,
)
from mcp_server.capabilities.download import (
    export_bom_excel_data,
    export_design_change_report_data,
)
from mcp_server.capabilities.history import (
    get_bom_review_data,
    get_design_change_data,
    list_bom_reviews_data,
    list_design_changes_data,
)


mcp = MCPServer(
    "Display BOM MCP Server"
)


@mcp.tool()
def get_bom(
    product_id: str,
    as_of_date: str | None = None,
) -> list[dict]:
    """
    제품 ID와 기준일을 이용하여
    계층형 BOM 데이터를 조회합니다.

    Args:
        product_id:
            조회할 제품 ID

        as_of_date:
            BOM 기준일.
            예: 2026-08-11

    Returns:
        BOM Row 목록
    """

    return get_bom_data(
        product_id=product_id,
        as_of_date=as_of_date,
    )

@mcp.tool()
def list_products() -> list[dict]:
    """
    등록된 전체 제품 목록을 조회합니다.
    """

    return list_products_data()


@mcp.tool()
def search_product(
    keyword: str,
) -> list[dict]:
    """
    제품 ID 또는 제품명에 포함된
    키워드로 제품을 검색합니다.
    """

    return search_product_data(
        keyword
    )


@mcp.tool()
def list_materials() -> list[dict]:
    """
    등록된 전체 자재 목록을 조회합니다.
    """

    return list_materials_data()


@mcp.tool()
def search_material(
    keyword: str,
) -> list[dict]:
    """
    자재 ID 또는 자재명에 포함된
    키워드로 자재를 검색합니다.
    """

    return search_material_data(
        keyword
    )


@mcp.tool()
def analyze_design_change(
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    as_of_date: str | None = None,
) -> dict:
    """
    제품 BOM의 기존 자재를 신규 자재로 교체할 수 있는지 분석합니다.

    실제 BOM 데이터는 변경하지 않으며 제품·자재 존재 여부,
    승인/Lifecycle, Compatibility, BOM 업무 Rule을 검증합니다.

    Args:
        product_id: 설계변경 대상 제품 ID
        old_material_id: 현재 BOM에 존재하는 기존 자재 ID
        new_material_id: 교체 후보 신규 자재 ID
        as_of_date: 분석 기준일. 예: 2026-08-11

    Returns:
        PASS / CONDITIONAL / FAIL 판정과 상세 검증 결과
    """

    return analyze_design_change_data(
        product_id=product_id,
        old_material_id=old_material_id,
        new_material_id=new_material_id,
        as_of_date=as_of_date,
    )


@mcp.tool()
def create_ai_change_request(
    product_id: str,
    old_material_id: str,
    new_material_id: str,
    reason: str,
    effective_date: str,
    requested_by: str,
    as_of_date: str | None = None,
) -> dict:
    """설계변경을 분석하고 적용 전 변경 요청을 등록합니다. E-BOM은 변경하지 않습니다."""
    return create_ai_change_request_data(
        product_id=product_id,
        old_material_id=old_material_id,
        new_material_id=new_material_id,
        reason=reason,
        effective_date=effective_date,
        requested_by=requested_by,
        as_of_date=as_of_date,
    )


@mcp.tool()
def create_review_bom(
    change_id: str,
    created_by: str,
    created_date: str,
) -> dict:
    """변경 예정 BOM Snapshot을 품평회 BOM Rev.1로 생성합니다."""
    return create_review_bom_data(
        change_id=change_id, created_by=created_by, created_date=created_date
    )


@mcp.tool()
def run_ai_bom_review(
    review_id: str,
    reviewed_by: str,
    checked_date: str,
) -> dict:
    """Review BOM의 Rule/Compatibility 체크리스트를 AI Agent가 자동 검증합니다."""
    return run_ai_bom_review_data(
        review_id=review_id, reviewed_by=reviewed_by, checked_date=checked_date
    )


@mcp.tool()
def generate_design_change_report(change_id: str) -> dict:
    """사용자 최종 승인 전에 설계변경·AI 품평 결과 보고서를 생성합니다."""
    return generate_design_change_report_data(change_id=change_id)


@mcp.tool()
def export_bom_excel(product_id: str, as_of_date: str | None = None) -> dict:
    """BOM 조회 결과를 읽기 전용 Excel 파일로 생성합니다."""
    return export_bom_excel_data(product_id=product_id, as_of_date=as_of_date)


@mcp.tool()
def export_design_change_report(change_id: str) -> dict:
    """설계변경·AI 품평 완료문서를 읽기 전용 Word 파일로 생성합니다."""
    return export_design_change_report_data(change_id=change_id)


@mcp.tool()
def list_design_changes() -> list[dict]:
    """설계변경 요청의 진행상태와 결과 목록을 읽기 전용으로 조회합니다."""
    return list_design_changes_data()


@mcp.tool()
def get_design_change(change_id: str) -> dict:
    """변경 ID로 설계변경, 변경 자재, Review BOM 상세를 조회합니다."""
    return get_design_change_data(change_id)


@mcp.tool()
def list_bom_reviews() -> list[dict]:
    """품평회 목록과 종합판정 및 체크 결과 건수를 조회합니다."""
    return list_bom_reviews_data()


@mcp.tool()
def get_bom_review(review_id: str) -> dict:
    """품평회 기본정보, 체크리스트, Review BOM 상세를 조회합니다."""
    return get_bom_review_data(review_id)


@mcp.tool()
def apply_reviewed_bom(
    review_id: str,
    applied_by: str,
    applied_date: str | None = None,
) -> dict:
    """보고서를 확인한 사용자의 명시적 요청으로만 Production E-BOM에 반영합니다."""
    return apply_reviewed_bom_data(
        review_id=review_id, applied_by=applied_by, applied_date=applied_date
    )


if __name__ == "__main__":
    mcp.run()
