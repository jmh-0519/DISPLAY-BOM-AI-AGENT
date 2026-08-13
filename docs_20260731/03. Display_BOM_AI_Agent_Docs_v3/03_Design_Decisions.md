# 주요 설계 결정

## 단일 Agent 채택

멀티 Agent 대신 단일 Agent 구조를 채택한다.

- 관리 복잡도가 낮다.
- Agent 간 메시지 전달 비용이 없다.
- 디버깅이 쉽다.
- Tool 확장 방식으로 충분한 기능 확장이 가능하다.

## Agent와 Service 직접 연결 금지

```text
Agent → Tool → Service
```

Agent가 개별 Service를 직접 알게 되면 Tool이 늘어날수록 결합도가 높아진다. Tool 계층을 두면 Agent는 Tool 이름, 설명, 입력 스키마와 결과만 알면 된다.

## Registry에는 인스턴스 저장

```python
registry.register(BomTool(bom_service))
```

의존성 주입, Service 공유, 테스트 대역 사용 및 향후 DB 연결 객체 주입이 쉬워진다.

## Tool 결과 표준화

`ToolResponse` 필드:

- `success`
- `tool_name`
- `data`
- `error`
- `execution_time_ms`

## Rule-based Agent 선행 구현

Azure OpenAI 연결 전에 규칙 기반 Agent를 구현해 Tool 흐름을 검증하고 문제 원인을 분리한다.

## 중복 통합 테스트 최소화

현재 단계에서는 아래 파일을 제거할 수 있다.

- `test_bom_tool_integration.py`
- `test_material_tool_integration.py`

각 구성 요소가 이미 단위 테스트되고 있으며, Agent 구현 후 더 의미 있는 통합 테스트로 대체한다.
