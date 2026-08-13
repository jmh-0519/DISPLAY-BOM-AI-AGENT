from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    모든 Tool이 따라야 하는 공통 인터페이스입니다.

    Tool은 반드시 다음 정보를 제공해야 합니다.

    - name: Tool의 고유 이름
    - description: Tool의 기능 설명
    - input_schema: Tool 입력값 정의
    - execute(): 실제 기능 실행
    """

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """
        Tool의 실제 기능을 실행합니다.

        하위 Tool 클래스는 반드시 이 메서드를 구현해야 합니다.
        """
        raise NotImplementedError

    def get_definition(self) -> dict[str, Any]:
        """
        Agent 또는 LLM에 전달할 Tool 정의를 반환합니다.
        """

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
