# Lessons Learned

## 구현 순서는 계층별로 나눈다

```text
Data → Service → BaseTool → Registry → Request/Response → Executor → Business Tools → Agent
```

각 단계의 책임과 오류를 분리할 수 있다.

## Tool은 Service의 대체물이 아니다

Tool은 Agent와 Service 사이의 어댑터다. 업무 로직은 Service에 둔다.

## 테스트 수가 많다고 좋은 것은 아니다

같은 동작을 여러 계층에서 반복 검증하면 유지보수 비용이 증가한다. 현재는 개별 단위 테스트를 유지하고 Agent 구현 후 의미 있는 통합 테스트를 작성한다.

## Fake Service는 Tool 테스트에 효과적이다

실제 CSV 없이 Tool의 입력 검증과 위임만 확인할 수 있다.

## Registry에는 인스턴스를 저장한다

의존성 주입과 테스트 대역 사용이 쉬워진다.

## LLM은 마지막에 연결한다

전체 실행 구조를 먼저 검증하면 Azure OpenAI 연결 후 문제를 쉽게 분리할 수 있다.

## 문서는 작업 종료 시 전체 재생성한다

부분 수정 누적에 따른 문서 불일치를 방지한다.
