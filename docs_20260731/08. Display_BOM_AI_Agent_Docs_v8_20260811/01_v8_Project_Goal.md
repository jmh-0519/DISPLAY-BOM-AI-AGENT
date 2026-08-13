# v8 Project Goal

## 1. 프로젝트 최종 방향
Display BOM AI Agent의 목표는 단순 질의응답이 아니라 **실제 Display BOM 업무 Workflow를 수행하는 Single AI Agent**를 구현하는 것이다.

```text
사용자 자연어 요청
→ Agent가 의도와 업무 절차 판단
→ 필요한 Capability 선택
→ MCP를 통해 Tool 실행
→ Service의 Business Rule 수행
→ 결과를 관찰하고 다음 단계 판단
→ 필요 시 사용자 승인
→ 업무 완료 및 보고
```

## 2. 유지하는 핵심 원칙
- Multi-Agent가 아닌 Single Agent
- Agent가 판단/계획, MCP는 Capability Interface
- Service가 Business Logic 소유
- Skill은 업무 절차와 Tool 사용법 제공
- 실제 변경은 Human Approval 이후 수행
- 기존 검증된 Service/Test 자산 재사용
- 필요하지 않은 MCP-RAG/Vector Tool Retrieval은 조기 도입하지 않음

## 3. v8에서 달성한 목표
v7에서 계획했던 MCP Foundation을 실제 구현하고, 조회 Agent를 MCP 기반 Tool-Using Agent로 연결했다. 자연어 표현 차이로 검색이 실패하던 문제는 Query Normalization 계층으로 해결했다.

## 4. 다음 목표
대화의 지시어와 이전 Tool 결과를 이어서 이해하도록 Conversation Memory를 구현하고, 이후 Design Change Workflow State/Human Approval로 확장한다.
