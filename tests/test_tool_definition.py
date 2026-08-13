from typing import Any

from tools.base_tool import BaseTool
from tools.registry import ToolRegistry


class SampleBomTool(BaseTool):
    name = "get_bom"
    description = "제품 ID를 기준으로 BOM을 조회합니다."

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

    def execute(self, **kwargs: Any) -> list:
        return []


class SampleMaterialTool(BaseTool):
    name = "search_material"
    description = "자재 ID 또는 자재명으로 자재를 검색합니다."

    input_schema = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "검색할 자재 키워드",
            }
        },
        "required": ["keyword"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> list:
        return []


def test_tool_definition_has_openai_format() -> None:
    tool = SampleBomTool()

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function = definition["function"]

    assert function["name"] == "get_bom"
    assert (
        function["description"]
        == "제품 ID를 기준으로 BOM을 조회합니다."
    )
    assert function["parameters"] == tool.input_schema


def test_registry_returns_all_tool_definitions() -> None:
    registry = ToolRegistry()

    registry.register(SampleBomTool())
    registry.register(SampleMaterialTool())

    definitions = registry.get_tool_definitions()

    assert len(definitions) == 2

    tool_names = {
        definition["function"]["name"]
        for definition in definitions
    }

    assert tool_names == {
        "get_bom",
        "search_material",
    }


def test_registry_returns_empty_definition_list() -> None:
    registry = ToolRegistry()

    definitions = registry.get_tool_definitions()

    assert definitions == []