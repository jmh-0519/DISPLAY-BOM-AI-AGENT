from typing import Any

from services.bom_service import BomService
from tools.base_tool import BaseTool


class ProductTool(BaseTool):
    """
    제품 정보를 조회하는 Tool입니다.
    """

    name = "search_product"

    description = (
        "제품 ID 또는 제품명으로 제품 정보를 조회합니다."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "제품 ID 또는 제품명"
            }
        },
        "required": ["keyword"],
        "additionalProperties": False,
    }

    def __init__(self, bom_service: BomService):
        self.bom_service = bom_service

    def execute(self, **kwargs: Any):

        keyword = kwargs.get("keyword")

        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError(
                "keyword는 비어 있지 않은 문자열이어야 합니다."
            )

        return self.bom_service.search_product(
            keyword.strip()
        )