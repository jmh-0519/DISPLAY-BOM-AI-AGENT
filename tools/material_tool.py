from typing import Any

from services.bom_service import BomService
from tools.base_tool import BaseTool


class MaterialTool(BaseTool):
    """
    자재 ID 또는 자재명으로 자재 정보를 검색하는 Tool입니다.
    """

    name = "search_material"
    description = (
        "자재 ID 또는 자재명에 포함된 키워드를 기준으로 "
        "자재 정보를 검색합니다."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "검색할 자재 ID 또는 자재명",
            }
        },
        "required": ["keyword"],
        "additionalProperties": False,
    }

    def __init__(self, bom_service: BomService) -> None:
        self.bom_service = bom_service

    def execute(self, **kwargs: Any) -> Any:
        keyword = kwargs.get("keyword")

        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError(
                "keyword는 비어 있지 않은 문자열이어야 합니다."
            )

        return self.bom_service.search_material(keyword.strip())