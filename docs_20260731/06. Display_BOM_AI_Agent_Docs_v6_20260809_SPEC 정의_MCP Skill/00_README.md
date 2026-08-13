# Display BOM AI Agent Docs v6

## 문서 목적
본 문서는 Display BOM AI Agent의 v5 개발 완료 및 소스 정리 이후, v6에서 진행할 목표 아키텍처와 개발 방향을 기준선(Baseline)으로 정의한다.

## 현재 기준
v5까지 다음 기능이 구현되어 있다.

- Azure OpenAI 기반 Single Agent
- Tool Calling
- Streamlit UI
- BOM 조회
- 전체 제품 조회 / 제품 검색
- 전체 자재 조회 / 자재 검색
- Tool Registry / Executor 구조
- pytest 기반 회귀 테스트
- CSV 기반 업무 데이터

## v6 핵심 목표
단순 조회 Agent에서 실제 BOM 업무를 수행하는 Agent로 확장한다.

핵심 구성요소:
1. Constitution
2. Intent Analysis
3. Skill
4. Planning
5. Memory / Workflow State
6. MCP
7. Human-in-the-loop
8. 설계변경 / 품평회 / 보고서

## v6 개발 원칙
- Multi-Agent가 아닌 Single Agent를 유지한다.
- Agent는 판단, 계획, 실행 흐름을 담당한다.
- MCP는 실제 업무 Capability를 제공한다.
- Tool 하나에 지나치게 많은 업무를 넣지 않는다.
- 분석과 실제 데이터 변경을 분리한다.
- 데이터 변경 작업은 사용자 승인 절차를 고려한다.
- 기존 v5 조회 기능과 테스트 자산은 최대한 재사용한다.
- MCP-RAG는 현재 범위에 포함하지 않는다.

## 다음 작업
`analyze_design_change`의 업무 규칙, 입력/출력 Contract, 사용 데이터, 판정 기준을 상세 설계한다.
