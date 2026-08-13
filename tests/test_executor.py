from typing import Any

from models.tool_request import ToolRequest
from tools.base_tool import BaseTool
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


class SuccessTool(BaseTool):
    name = "success_tool"
    description = "정상 실행 테스트용 Tool"
    input_schema = {}

    def execute(self, **kwargs: Any) -> str:
        return "실행 성공"


class ErrorTool(BaseTool):
    name = "error_tool"
    description = "오류 테스트용 Tool"
    input_schema = {}

    def execute(self, **kwargs: Any) -> str:
        raise ValueError("Tool 실행 중 오류 발생")


def test_execute_success() -> None:
    registry = ToolRegistry()
    registry.register(SuccessTool())

    executor = ToolExecutor(registry)

    request = ToolRequest(
        tool_name="success_tool",
        arguments={},
    )

    response = executor.execute(request)

    assert response.success is True
    assert response.tool_name == "success_tool"
    assert response.data == "실행 성공"
    assert response.error is None
    assert response.execution_time_ms is not None


def test_execute_tool_error() -> None:
    registry = ToolRegistry()
    registry.register(ErrorTool())

    executor = ToolExecutor(registry)

    request = ToolRequest(
        tool_name="error_tool",
        arguments={},
    )

    response = executor.execute(request)

    assert response.success is False
    assert response.tool_name == "error_tool"
    assert response.data is None
    assert response.error == "Tool 실행 중 오류 발생"
    assert response.execution_time_ms is not None


def test_execute_unknown_tool() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    request = ToolRequest(
        tool_name="unknown_tool",
        arguments={},
    )

    response = executor.execute(request)

    assert response.success is False
    assert response.tool_name == "unknown_tool"
    assert response.error is not None