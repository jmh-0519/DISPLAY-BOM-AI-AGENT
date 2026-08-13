# 03. Design Decisions

## Single Agent
멀티 에이전트 대신 Single Agent를 사용한다.

## Tool Registry
Agent는 Tool 이름만 알고 Registry가 Tool 객체를 관리한다.

## Tool Executor
로그, 예외 처리, 입력 검증 등 공통 기능을 담당한다.

---
## 변경 이력
### 2026-07-31
- Registry Pattern 적용
- Executor Pattern 적용
