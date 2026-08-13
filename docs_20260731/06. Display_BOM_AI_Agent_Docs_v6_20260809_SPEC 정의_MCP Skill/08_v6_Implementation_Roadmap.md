# v6 Implementation Roadmap

## Phase 0. Clean Baseline - 완료

- v5 불필요 소스 정리
- 조회 기능 5종 정리
- `requirements.txt` 생성
- 루트 `README.md` 생성
- pytest 회귀 테스트
- Streamlit 동작 확인

## Phase 1. v6 Architecture - 현재 단계

- 목표 아키텍처 정의
- Agent / Skill / Planning / Memory / MCP 책임 분리
- MCP Capability 정의
- 설계변경 Workflow 정의

## Phase 2. Design Change Analysis Contract

다음 작업이다.

`analyze_design_change`에 대해 아래 내용을 먼저 설계한다.

- 업무 목적
- 입력값
- 출력값
- 사용 데이터
- 검증 Rule
- 판정 기준
- 오류 조건
- 테스트 Case

## Phase 3. MCP Foundation

- MCP Server 기본 구조
- MCP Client 연동
- 기존 조회 Tool의 MCP 노출 방식 결정/구현
- MCP 연결 테스트

## Phase 4. Design Change Analysis

- `analyze_design_change`
- compatibility / rules 활용
- Service 구현
- 테스트
- Agent 연동

## Phase 5. Skill + Planning

- BOM Design Change Skill
- 실행계획 생성
- 단계별 Tool 호출
- 실행 결과에 따른 다음 단계 결정

## Phase 6. Memory / Workflow State

- Conversation Memory
- Workflow State
- 중단/재개 처리
- 승인 대기 상태

## Phase 7. Design Change Apply

- `apply_design_change`
- 변경 이력
- Human Approval
- Before / After
- 테스트

## Phase 8. BOM Review

- `evaluate_bom_review`
- PASS / CONDITIONAL / FAIL
- 품평회 규칙
- 경고 및 검토 결과

## Phase 9. Report

- `generate_change_report`
- 분석/적용/품평회 결과 통합
- 완료 보고서

## Phase 10. Streamlit Workflow UI

- Planning 진행상태
- 승인 UI
- 품평회 결과
- 최종 보고서
- Workflow 재개

## Phase 11. Final Validation

- End-to-End Scenario
- 회귀 테스트
- 예외 시나리오
- Agent 평가
- v6 문서 업데이트
