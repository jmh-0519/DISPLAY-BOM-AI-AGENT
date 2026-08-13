from typing import Any

from services.bom_service import BomService
from tools.base_tool import BaseTool


class MaterialListTool(BaseTool):
    """
    등록된 전체 자재 목록을 조회하는 Tool입니다.
    """

    name = "list_materials"

    description = (
        "등록된 모든 자재 목록을 조회합니다. "
        "사용자가 전체 자재, 모든 자재, 자재 목록 등을 "
        "요청할 때 사용합니다."
    )

    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, bom_service: BomService) -> None:
        self.bom_service = bom_service

    def execute(self, **kwargs: Any) -> Any:
        return self.bom_service.list_materials()