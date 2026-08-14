from typing import Any

import pandas as pd

from services.bom_service_factory import create_read_bom_service


def _to_records(
    data: Any,
) -> list[dict]:
    """
    Service 반환값을 MCP에서 전달 가능한
    list[dict] 형태로 변환합니다.
    """

    if data is None:
        return []

    if isinstance(
        data,
        pd.DataFrame,
    ):
        if data.empty:
            return []

        return data.to_dict(
            orient="records"
        )

    if isinstance(
        data,
        list,
    ):
        return data

    if isinstance(
        data,
        dict,
    ):
        return [data]

    raise TypeError(
        "지원하지 않는 Service 반환 형식입니다: "
        f"{type(data).__name__}"
    )


def get_bom_data(
    product_id: str,
    as_of_date: str | None = None,
) -> list[dict]:
    """
    제품의 Exploded BOM을 조회합니다.
    """

    bom_service = create_read_bom_service()

    result = (
        bom_service.get_bom_explosion(
            product_id,
            as_of_date=as_of_date,
        )
    )

    return _to_records(
        result
    )


def list_products_data() -> list[dict]:
    """
    등록된 전체 제품 목록을 조회합니다.
    """

    bom_service = create_read_bom_service()

    result = (
        bom_service.list_products()
    )

    return _to_records(
        result
    )


def search_product_data(
    keyword: str,
) -> list[dict]:
    """
    제품 ID 또는 제품명으로 제품을 검색합니다.
    """

    normalized_keyword = (
        keyword.strip()
        if isinstance(keyword, str)
        else ""
    )

    if not normalized_keyword:
        raise ValueError(
            "keyword는 비어 있지 않은 "
            "문자열이어야 합니다."
        )

    bom_service = create_read_bom_service()

    result = (
        bom_service.search_product(
            normalized_keyword
        )
    )

    return _to_records(
        result
    )


def list_materials_data() -> list[dict]:
    """
    등록된 전체 자재 목록을 조회합니다.
    """

    bom_service = create_read_bom_service()

    result = (
        bom_service.list_materials()
    )

    return _to_records(
        result
    )


def search_material_data(
    keyword: str,
) -> list[dict]:
    """
    자재 ID 또는 자재명으로 자재를 검색합니다.
    """

    normalized_keyword = (
        keyword.strip()
        if isinstance(keyword, str)
        else ""
    )

    if not normalized_keyword:
        raise ValueError(
            "keyword는 비어 있지 않은 "
            "문자열이어야 합니다."
        )

    bom_service = create_read_bom_service()

    result = (
        bom_service.search_material(
            normalized_keyword
        )
    )

    return _to_records(
        result
    )
