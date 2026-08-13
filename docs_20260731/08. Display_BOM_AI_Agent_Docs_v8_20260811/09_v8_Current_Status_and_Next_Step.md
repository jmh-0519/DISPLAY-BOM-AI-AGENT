# v8 Current Status and Next Step

## 1. 현재 위치
v7에서는 MCP/Skill/Planner/Memory가 목표 아키텍처에만 존재했다. v8에서는 **MCP와 Skill-guided Multi-step Tool Calling이 실제 구현되었고 자연어 검색까지 E2E 검증**되었다.

## 2. 현재 가능한 것
- 제품/자재 목록 및 검색
- 제품 ID/자연어 제품명 기반 BOM 조회
- 자연어 Alias 기반 자재 검색
- Agent가 MCP Tool을 선택하고 결과에 따라 다음 Tool 호출
- Skill을 참고한 조회 절차
- 기존 Domain Service 재사용

## 3. 현재 부족한 것
- Conversation Memory
- Tool Observation의 턴 간 유지
- 구조화된 Workflow State
- Design Change 전체를 Agent가 주도하는 Planning
- Human Approval 연결
- Report Generation

## 4. 다음 작업 1순위
**Conversation Memory 구현**

완료 조건:
1. 이전 User/Assistant 대화를 Agent에 전달
2. 직전 Tool 결과를 후속 질문에서 참조
3. `그 중`, `그 자재`, `그 제품` 처리
4. 대화 초기화 시 Context 초기화
5. Memory 관련 pytest 추가
6. Streamlit 다중 턴 E2E 통과

## 5. 그 다음
Conversation Memory 안정화 후 Design Change Workflow State로 확장한다.
