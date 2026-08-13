from typing import Any

import pytest

from tools.product_tool import ProductTool


class FakeBomService:

    def search_product(
        self,
        keyword: str,
    ) -> list[dict[str, Any]]:

        products = [

            {
                "product_id": "OLED55-A100",
                "product_name": "OLED TV 55",
                "category": "TV",
            },

            {
                "product_id": "OLED65-A200",
                "product_name": "OLED TV 65",
                "category": "TV",
            },
        ]

        keyword = keyword.lower()

        return [

            product

            for product in products

            if keyword in product["product_id"].lower()

            or keyword in product["product_name"].lower()
        ]


def test_product_tool_definition() -> None:
    tool = ProductTool(FakeBomService())

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function_definition = definition["function"]

    assert function_definition["name"] == "search_product"
    assert "keyword" in (
        function_definition["parameters"]["properties"]
    )
    assert (
        function_definition["parameters"]["required"]
        == ["keyword"]
    )


def test_product_tool():

    tool = ProductTool(FakeBomService())

    result = tool.execute(keyword="OLED55")

    assert len(result) == 1

    assert result[0]["product_id"] == "OLED55-A100"


def test_product_tool_by_name():

    tool = ProductTool(FakeBomService())

    result = tool.execute(keyword="55")

    assert len(result) == 1


@pytest.mark.parametrize(
    "keyword",
    [
        "",
        "   ",
        None,
        123,
    ],
)
def test_invalid_keyword(keyword: Any):

    tool = ProductTool(FakeBomService())

    with pytest.raises(ValueError):

        tool.execute(keyword=keyword)