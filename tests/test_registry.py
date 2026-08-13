from typing import Any

import pytest

from tools.base_tool import BaseTool
from tools.registry import ToolRegistry


class SampleTool(BaseTool):
    name = "sample"
    description = "Registry 테스트용 Tool입니다."

    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def execute(self, **kwargs: Any) -> str:
        return "OK"


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())

    tool = registry.get("sample")

    assert tool.name == "sample"
    assert tool.execute() == "OK"


def test_get_all_tools() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())

    tools = registry.get_all()

    assert len(tools) == 1
    assert tools[0].name == "sample"


def test_duplicate_tool_registration() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())

    with pytest.raises(ValueError):
        registry.register(SampleTool())


def test_tool_not_found() -> None:
    registry = ToolRegistry()

    with pytest.raises(KeyError):
        registry.get("unknown_tool")


def test_contains_tool() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())

    assert registry.contains("sample") is True
    assert registry.contains("unknown_tool") is False