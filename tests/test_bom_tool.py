from typing import Any

import pytest

from tools.bom_tool import BomTool


class FakeBomService:
    """
    BomTool 단위 테스트를 위한 가짜 Service입니다.
    """

    def get_bom(self, product_id: str) -> list[dict[str, Any]]:
        if product_id == "OLED55-A100":
            return [
                {
                    "product_id": "OLED55-A100",
                    "material_id": "MAT-001",
                    "quantity": 1,
                },
                {
                    "product_id": "OLED55-A100",
                    "material_id": "MAT-002",
                    "quantity": 2,
                },
            ]

        return []


def test_bom_tool_definition() -> None:
    tool = BomTool(FakeBomService())

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function_definition = definition["function"]

    assert function_definition["name"] == "get_bom"
    assert "product_id" in (
        function_definition["parameters"]["properties"]
    )
    assert (
        function_definition["parameters"]["required"]
        == ["product_id"]
    )


def test_execute_returns_bom() -> None:
    tool = BomTool(FakeBomService())

    result = tool.execute(product_id="OLED55-A100")

    assert len(result) == 2
    assert result[0]["product_id"] == "OLED55-A100"
    assert result[0]["material_id"] == "MAT-001"


def test_execute_returns_empty_list() -> None:
    tool = BomTool(FakeBomService())

    result = tool.execute(product_id="UNKNOWN")

    assert result == []


@pytest.mark.parametrize(
    "product_id",
    [
        None,
        "",
        "   ",
        123,
    ],
)
def test_execute_rejects_invalid_product_id(product_id: Any) -> None:
    tool = BomTool(FakeBomService())

    with pytest.raises(
        ValueError,
        match="product_id는 비어 있지 않은 문자열이어야 합니다.",
    ):
        tool.execute(product_id=product_id)


def test_execute_rejects_missing_product_id() -> None:
    tool = BomTool(FakeBomService())

    with pytest.raises(ValueError):
        tool.execute()