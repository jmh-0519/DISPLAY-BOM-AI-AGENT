from typing import Any

from tools.base_tool import BaseTool


class BomTool(BaseTool):
    """
    제품 ID를 이용하여 BOM 정보를 조회하는 Tool입니다.
    """

    name = "get_bom"
    description = "제품 ID를 기준으로 해당 제품의 BOM 구성 정보를 조회합니다."

    input_schema = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "BOM을 조회할 제품 ID",
            }
        },
        "required": ["product_id"],
        "additionalProperties": False,
    }

    def __init__(self, bom_service: Any) -> None:
        self.bom_service = bom_service

    def execute(self, **kwargs: Any) -> Any:
        product_id = kwargs.get("product_id")

        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("product_id는 비어 있지 않은 문자열이어야 합니다.")

        return self.bom_service.get_bom(product_id.strip())
