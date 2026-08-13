from tools.base_tool import BaseTool


class ToolRegistry:
    """
    Tool 등록 및 조회를 담당하는 Registry 클래스입니다.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Tool 객체를 Registry에 등록합니다.
        """

        if not tool.name:
            raise ValueError("Tool 이름은 비어 있을 수 없습니다.")

        if tool.name in self._tools:
            raise ValueError(
                f"'{tool.name}' Tool이 이미 등록되어 있습니다."
            )

        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> BaseTool:
        """
        Tool 이름으로 등록된 Tool 객체를 조회합니다.
        """

        if tool_name not in self._tools:
            raise KeyError(
                f"'{tool_name}' Tool을 찾을 수 없습니다."
            )

        return self._tools[tool_name]

    def get_all(self) -> list[BaseTool]:
        """
        등록된 모든 Tool 객체를 반환합니다.
        """

        return list(self._tools.values())

    def contains(self, tool_name: str) -> bool:
        """
        Tool이 등록되어 있는지 확인합니다.
        """

        return tool_name in self._tools

    def get_tool_definitions(self) -> list[dict]:
        """
        등록된 모든 Tool을 Azure OpenAI Tool Calling 형식으로 반환합니다.
        """

        return [
            tool.get_definition()
            for tool in self.get_all()
        ]