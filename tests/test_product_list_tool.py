from services.bom_service import BomService
from tools.product_list_tool import ProductListTool


def test_product_list_tool_execute() -> None:
    service = BomService()
    tool = ProductListTool(service)

    result = tool.execute()

    assert not result.empty
    assert "product_id" in result.columns


def test_product_list_tool_definition() -> None:
    service = BomService()
    tool = ProductListTool(service)

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function = definition["function"]

    assert function["name"] == "list_products"
    assert (
        function["parameters"]["properties"]
        == {}
    )