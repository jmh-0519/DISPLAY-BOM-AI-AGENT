# 테스트 전략

## 테스트 도구

```powershell
pytest -v
```

## 현재 권장 테스트 파일

```text
tests/
├── __init__.py
├── test_base_tool.py
├── test_bom_service.py
├── test_bom_tool.py
├── test_data.py
├── test_executor.py
├── test_material_tool.py
├── test_product_tool.py
└── test_registry.py
```

`__pycache__`는 Python이 자동 생성하는 캐시 폴더다.

## 제거 가능한 테스트

```text
test_bom_tool_integration.py
test_material_tool_integration.py
```

이 파일들은 Executor, Registry, Tool 조합을 반복 검증하므로 Agent 구현 후 통합 테스트로 대체한다.

## 테스트 계층

### 단위 테스트

- `BomService`
- `BaseTool`
- `ToolRegistry`
- `ToolExecutor`
- `BomTool`
- `MaterialTool`
- `ProductTool`

### 통합 테스트

다음 단계 예정 파일:

```text
tests/test_bom_agent.py
```

검증 범위:

```text
BomAgent → ToolExecutor → ToolRegistry → Tool
```

### E2E 테스트

Azure OpenAI 연결 후 예정:

```text
tests/test_ai_agent.py
```

## Fake Service 사용 이유

- 테스트 속도가 빠르다.
- CSV 경로와 무관하다.
- Tool 책임만 독립적으로 검증한다.
- 실패 원인을 쉽게 찾을 수 있다.

## 운영 원칙

- 한 테스트는 하나의 동작을 검증한다.
- 정상 입력과 오류 입력을 모두 검증한다.
- 테스트 간 실행 순서에 의존하지 않는다.
- 의미 있는 계층 경계에서만 통합 테스트를 작성한다.
