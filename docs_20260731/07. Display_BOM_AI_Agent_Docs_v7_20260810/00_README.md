# Display BOM AI Agent Docs v7

## 문서 목적
본 문서는 v6에서 수립한 개발 방향을 기준으로 2026-08-10까지 실제 구현된 내용을 반영하여 v7 Baseline을 정의한다.

## v7 판단 요약
현재 개발 내용은 **v6의 핵심 설계 원칙에 전반적으로 부합한다.**

특히 다음 원칙은 실제 구현에 반영되었다.

- Multi-Agent가 아닌 Single Agent 유지
- 조회 기능과 업무 Service 재사용
- 설계변경 분석과 실제 변경 적용 분리
- Compatibility / Rule 기반 검증
- Preview와 Production 변경 분리
- Review 재검증 및 검증결과 저장
- pytest 기반 회귀 테스트
- Streamlit 업무 UI 확장

다만 v6 목표 아키텍처의 모든 구성요소가 구현된 것은 아니다.

아직 본격 구현 전인 영역:
- MCP Server / MCP Client
- Constitution
- Intent Analysis 고도화
- Skill
- Planner
- Workflow Memory / State
- Agent 주도 Human Approval Workflow
- Report Generation

즉 현재 상태는 **v6 방향을 유지하면서 Service/Domain 기능과 UI를 먼저 구체화한 중간 구현 단계**이다.

## v7 현재 구현 범위
1. 기존 조회 Agent
2. Design Change Analysis
3. Design Change Preview / Apply 기반 Service
4. BOM Review / Revalidation
5. 검증결과 저장
6. Streamlit 설계변경 UI
7. 계층형 BOM Tree Viewer
8. 회귀 테스트

## v7 다음 핵심 목표
현재 구현된 Service를 버리지 않고 MCP Capability로 노출하고, 그 위에 Skill / Planning / Workflow State를 결합하여 Agent가 전체 설계변경 Workflow를 수행하도록 확장한다.
