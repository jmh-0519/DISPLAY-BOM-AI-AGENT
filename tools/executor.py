from time import perf_counter

from models.tool_request import ToolRequest
from models.tool_response import ToolResponse
from tools.registry import ToolRegistry


class ToolExecutor:
    """
    Tool 실행을 담당합니다.

    주요 책임:
    - Registry에서 Tool 조회
    - Tool 실행
    - 실행 시간 측정
    - 예외 처리
    - ToolResponse 생성
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_time = perf_counter()

        try:
            tool = self.registry.get(request.tool_name)

            result = tool.execute(**request.arguments)

            execution_time_ms = (perf_counter() - start_time) * 1000

            return ToolResponse(
                success=True,
                tool_name=request.tool_name,
                data=result,
                execution_time_ms=execution_time_ms,
            )

        except Exception as error:
            execution_time_ms = (perf_counter() - start_time) * 1000

            return ToolResponse(
                success=False,
                tool_name=request.tool_name,
                error=str(error),
                execution_time_ms=execution_time_ms,
            )