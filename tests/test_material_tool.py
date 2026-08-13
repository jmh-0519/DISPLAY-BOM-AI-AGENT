from typing import Any

import pytest

from tools.material_tool import MaterialTool


class FakeBomService:
    """
    MaterialTool 테스트용 가짜 Service입니다.
    """

    def search_material(
        self,
        keyword: str,
    ) -> list[dict[str, Any]]:
        materials = [
            {
                "material_id": "MAT-001",
                "material_name": "OLED Panel",
                "material_type": "PANEL",
            },
            {
                "material_id": "MAT-002",
                "material_name": "Power Board",
                "material_type": "BOARD",
            },
        ]

        normalized_keyword = keyword.lower()

        return [
            material
            for material in materials
            if normalized_keyword
            in material["material_id"].lower()
            or normalized_keyword
            in material["material_name"].lower()
        ]


def test_material_tool_definition() -> None:
    tool = MaterialTool(FakeBomService())

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function_definition = definition["function"]

    assert function_definition["name"] == "search_material"
    assert "keyword" in (
        function_definition["parameters"]["properties"]
    )
    assert (
        function_definition["parameters"]["required"]
        == ["keyword"]
    )


def test_search_material_by_id() -> None:
    tool = MaterialTool(FakeBomService())

    result = tool.execute(keyword="MAT-001")

    assert len(result) == 1
    assert result[0]["material_id"] == "MAT-001"


def test_search_material_by_name() -> None:
    tool = MaterialTool(FakeBomService())

    result = tool.execute(keyword="panel")

    assert len(result) == 1
    assert result[0]["material_name"] == "OLED Panel"


def test_search_material_returns_empty_list() -> None:
    tool = MaterialTool(FakeBomService())

    result = tool.execute(keyword="UNKNOWN")

    assert result == []


@pytest.mark.parametrize(
    "keyword",
    [
        None,
        "",
        "   ",
        123,
    ],
)
def test_rejects_invalid_keyword(keyword: Any) -> None:
    tool = MaterialTool(FakeBomService())

    with pytest.raises(
        ValueError,
        match="keyword는 비어 있지 않은 문자열이어야 합니다.",
    ):
        tool.execute(keyword=keyword)


def test_rejects_missing_keyword() -> None:
    tool = MaterialTool(FakeBomService())

    with pytest.raises(ValueError):
        tool.execute()