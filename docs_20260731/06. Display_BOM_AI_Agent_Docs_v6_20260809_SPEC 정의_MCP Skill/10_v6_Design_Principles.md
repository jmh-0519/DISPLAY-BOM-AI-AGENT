# v6 Design Principles

## 1. Single Agent
Agent는 하나를 유지한다.

## 2. Clear Responsibility
Agent, Skill, Planner, Memory, MCP, Service의 책임을 혼합하지 않는다.

## 3. Small and Explicit Tools
Tool은 한 가지 명확한 업무 Capability를 수행한다.

## 4. Read와 Write 분리
분석과 실제 BOM 변경을 분리한다.

```text
analyze_design_change ≠ apply_design_change
```

## 5. Human Approval
실제 데이터 변경 전 사용자 승인 절차를 고려한다.

## 6. Reuse v5
기존 조회 Tool, Service, Executor, 테스트 구조를 가능한 한 재사용한다.

## 7. Test First / Contract First
고수준 업무 기능은 Contract와 성공 기준을 먼저 정의하고 구현한다.

## 8. MCP is Capability Interface
MCP 자체가 Planning을 대신하지 않는다.

## 9. Skill is Procedure
Skill은 업무 수행 방법을 제공하고 실제 실행은 Planner와 Tool이 담당한다.

## 10. Memory is State
Memory는 단순 채팅 기록을 넘어 Workflow 진행 상태를 이어가기 위해 사용한다.

## 11. Avoid Premature Complexity
현재 필요하지 않은 Multi-Agent, MCP-RAG, Vector Tool Retrieval 등을 미리 도입하지 않는다.
