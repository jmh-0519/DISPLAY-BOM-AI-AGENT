# v7 Implementation Roadmap

## Phase 0. Clean Baseline — 완료
- v5 조회 기능 정리
- Single Agent
- Tool Registry / Executor
- Streamlit
- pytest
- CSV 데이터

## Phase 1. Architecture — 완료
- Single Agent 원칙
- Agent / MCP / Service 책임 정의
- Capability 분리
- Design Change Workflow 정의

## Phase 2. Design Change Analysis Contract — 완료 수준
- 입력/출력 구조
- 검증 항목
- PASS / CONDITIONAL / FAIL
- Blocking Reason
- 테스트 Case

## Phase 3. MCP Foundation — 미진행
- MCP Server
- MCP Client
- 기존 Tool MCP 노출

## Phase 4. Design Change Analysis — 구현
- 제품 검증
- 기존/신규 자재 검증
- Approval
- Lifecycle
- Compatibility
- Rule Validation
- 테스트

## Phase 5. Skill + Planning — 미진행
- BOM Design Change Skill
- Planner
- 단계별 Capability 호출

## Phase 6. Memory / Workflow State — 미진행
- Conversation Context
- Workflow State
- 승인 대기
- 중단/재개

## Phase 7. Design Change Apply — 기반 구현
- Preview/Apply Service
- Before/After 기반 구조
- Production BOM과 Preview 분리
- 테스트
- Agent Human Approval 연결은 미완성

## Phase 8. BOM Review — 상당 부분 구현
- Review 생성
- Review BOM Revision
- 재검증
- Compatibility
- Rule
- Check Result 저장/교체
- Check Type 분류
- 테스트

## Phase 9. Report — 미진행
- generate_change_report

## Phase 10. Streamlit Workflow UI — 부분 구현
완료/진행:
- 설계변경 화면
- 검증 상세
- Preview BOM
- BOM Tree Viewer

미완성:
- Planner 진행상태
- 승인 UI
- Review 전체 Workflow UI
- 최종 보고서
- Workflow 재개

## Phase 11. Final Validation — 진행 중
개발 과정에서 다수의 pytest 회귀 테스트를 통과했다.
최종 End-to-End Agent Scenario 검증은 아직 남아 있다.

## 다음 권장 순서
```text
1. 현재 Source/Test Baseline 고정
2. MCP Foundation
3. 기존 Query/Design Change/Review Service를 MCP로 노출
4. Skill
5. Planner
6. Workflow State
7. Human Approval
8. Report
9. End-to-End Streamlit Workflow
10. Final Validation
```
