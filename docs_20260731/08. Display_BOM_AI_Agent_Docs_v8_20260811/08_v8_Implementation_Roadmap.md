# v8 Implementation Roadmap

## Phase 0. Clean Baseline — 완료
- Single Agent / Azure OpenAI / Streamlit / pytest / CSV

## Phase 1. Domain Service — 완료/확장
- Query Service
- Design Change Analysis
- Preview/Apply 기반 Service
- Review/Revalidation

## Phase 2. MCP Foundation — 1차 완료
- Python MCP SDK
- MCP Server
- MCP Client
- stdio 호출
- Query Capability 노출
- MCP 호출 테스트

## Phase 3. Skill + Multi-step Tool Calling — 1차 완료
- SKILL.md
- Tool 사용 절차
- MCP Tool Definition 연결
- LLM → Tool → Observation → 재판단 Loop

## Phase 4. Query Normalization — 1차 완료
- Alias Dictionary
- Unit Normalization
- Token/Ranking
- 제품/자재 공통 적용
- 회귀 테스트 및 E2E

## Phase 5. Conversation Memory — 다음 작업
- conversation_history 전달
- 최근 User/Assistant Context
- Tool Observation 유지
- 지시어/후속질문 처리
- Memory 회귀 테스트

## Phase 6. Workflow State / Planning — 예정
- Design Change Workflow State
- 단계 진행/중단/재개
- Controlled Planning
- 승인 대기 상태

## Phase 7. Design Change MCP Integration — 예정
- analyze_design_change
- preview/apply
- evaluate_bom_review
- 기존 Service 재사용

## Phase 8. Human Approval — 예정
- Preview 확인
- 명시적 승인
- 승인 후 Apply

## Phase 9. Report — 예정
- generate_change_report

## Phase 10. Evaluation / Hardening — 예정
- test_questions 기반 평가
- 실패 유형 수집
- Skill/Alias/Rule 개선
- DB 전환 가능성 검토
