from services.bom_service import BomService
from tools.material_list_tool import MaterialListTool


def test_material_list_tool_execute() -> None:
    service = BomService()
    tool = MaterialListTool(service)

    result = tool.execute()

    assert not result.empty
    assert "material_id" in result.columns


def test_material_list_tool_definition() -> None:
    service = BomService()
    tool = MaterialListTool(service)

    definition = tool.get_definition()

    assert definition["type"] == "function"

    function = definition["function"]

    assert function["name"] == "list_materials"
    assert (
        function["parameters"]["properties"]
        == {}
    )