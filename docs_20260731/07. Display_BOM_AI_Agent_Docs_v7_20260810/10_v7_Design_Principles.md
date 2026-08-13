# v7 Design Principles

## 1. Single Agent
Multi-Agent로 확장하지 않고 하나의 Azure BOM Agent를 유지한다.

## 2. Clear Responsibility
```text
Agent    = 판단 / 계획 / 결과 해석
Skill    = 표준 업무 절차
Planner  = 요청별 실행 순서
Memory   = Workflow 상태
MCP      = Capability Interface
Service  = Business Logic
UI       = 사용자 상호작용 / 표현
```

## 3. Small and Explicit Capability
조회, 분석, 적용, Review, Report를 하나의 거대한 Tool로 합치지 않는다.

## 4. Read / Analyze / Write 분리
```text
analyze_design_change
        ≠
apply_design_change
```

Preview도 Production Apply와 분리한다.

## 5. Human Approval
실제 BOM 변경은 Agent가 임의로 수행하지 않는다.
분석과 Preview를 제시한 후 사용자 승인을 거치는 구조를 목표로 한다.

## 6. Reuse
기존 Tool, Service, Test 자산을 최대한 재사용한다.

## 7. Contract First / Test First
업무 Capability의 입력/출력과 판정 기준을 먼저 명확히 하고 테스트로 고정한다.

## 8. MCP is Interface
Business Rule을 MCP Layer에 중복 구현하지 않는다.

## 9. Skill is Procedure
Skill은 Tool이 아니며 업무 수행 방법을 제공한다.

## 10. Memory is Workflow State
단순 채팅 기록을 넘어 현재 업무 단계, 승인 상태, Revision 등을 이어갈 수 있어야 한다.

## 11. UI Does Not Own Business Logic
Streamlit은 화면 표현과 사용자 Interaction을 담당한다.
검증/변경 Rule은 Service에 둔다.

## 12. Preserve BOM Hierarchy
BOM 정렬은 전체 전역 정렬을 하지 않는다.
각 Parent의 직속 Child 단위에서만 정렬한다.

## 13. Preview Before Production Change
설계변경 결과를 Preview로 확인할 수 있어야 하며 Preview는 Production BOM을 변경하지 않는다.

## 14. Avoid Premature Complexity
현재 필요하지 않은 Multi-Agent, MCP-RAG, Vector Tool Retrieval은 도입하지 않는다.
