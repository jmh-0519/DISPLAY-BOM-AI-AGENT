# Display BOM AI Agent Docs v8

## 문서 목적
본 문서는 v7 Baseline 이후 2026-08-11까지 실제 구현·검증한 내용을 반영하여 v8 Baseline을 정의한다.

## v8 핵심 변화
v7에서 미구현이었던 **MCP Foundation과 Agent Skill 계층이 실제 구현 단계로 진입**했다. 또한 자연어 제품/자재 검색 품질을 높이기 위해 Query Normalization을 도입하고 Streamlit E2E까지 검증했다.

### 이번 버전에서 확인된 성과
- Single Agent 원칙 유지
- Python MCP SDK 설치 및 MCP Server/Client 구성
- Node.js/Inspector 없이 stdio 기반 MCP 실행 경로 채택
- BOM 조회 및 제품/자재 검색 Capability를 MCP Tool로 호출
- MCP Tool Definition을 Agent가 동적으로 사용할 수 있는 구조 구성
- `SKILL.md` 기반 업무 절차/Tool 사용 지침 적용
- Multi-step Tool Calling Agent Loop 구현
- 제품/자재 자연어 Query Normalization 도입
- Alias + Unit Normalization + Token/Ranking 검색 적용
- 기존 ID 부분검색 회귀 기능 보존
- pytest 전체 **222 passed** 확인
- Streamlit E2E에서 자연어 제품명 → 제품 검색 → BOM 조회 성공
- 후속 대화 테스트를 통해 Conversation Memory 필요성 확인

## 현재 판단
현재 프로젝트는 단순 조회 챗봇이 아니라 다음 구조로 발전하고 있다.

```text
Single Agent
 + Skill-guided Procedure
 + Tool-Using / Multi-step Agent Loop
 + MCP Capability Interface
 + Domain Service
 + Query Normalization
```

다음 핵심 개발 단계는 **Conversation Memory / Workflow State**이다.
