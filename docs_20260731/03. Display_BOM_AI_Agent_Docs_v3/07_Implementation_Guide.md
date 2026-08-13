# 구현 가이드

## 새 Tool 추가 절차

1. `BaseTool` 상속
2. `name`, `description`, `input_schema` 정의
3. `execute()`에서 입력 검증 후 Service 호출
4. `tests/test_new_tool.py` 작성
5. Registry에 인스턴스 등록

```python
class NewTool(BaseTool):
    name = "new_tool"
    description = "새 업무 기능을 수행합니다."
    input_schema = {...}

    def __init__(self, service):
        self.service = service

    def execute(self, **kwargs):
        return self.service.run(...)
```

## Service 교체 방향

현재:

```text
Tool → BomService → CSV
```

향후:

```text
Tool → BomService → BomRepository
                       ├── CsvBomRepository
                       └── OracleBomRepository
```

## Azure OpenAI 연결 준비

Registry의 모든 Tool 정의를 수집할 수 있다.

```python
tool_definitions = [
    tool.get_definition()
    for tool in registry.get_all()
]
```

## 예외 처리

Tool은 잘못된 입력에 `ValueError`를 발생시키고, Executor는 이를 `ToolResponse` 실패 응답으로 변환한다.

## 코딩 기준

- PEP 8
- 타입 힌트
- 명확한 Docstring
- 의존성 주입
- pytest
- Tool과 Service 책임 분리
