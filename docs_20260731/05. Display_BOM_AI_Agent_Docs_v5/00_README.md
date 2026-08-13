# Display BOM AI Agent - Documentation v5

## 버전 목표

v5에서는 기존 Rule-based Agent를 실제 Azure OpenAI 기반 LLM Tool Calling Agent로 확장하고, Streamlit UI까지 연결하였다.

주요 구현 범위:
- Azure OpenAI Gateway 연동
- LLM Tool Calling 구현
- Tool Call → ToolExecutor 연결
- Tool 실행 결과의 LLM 재전달
- AzureBomAgent 구현
- BOM / 자재 / 제품 기본 조회 기능 구현
- Streamlit 기반 Chat UI 구현

## 현재 Agent 수준

Single Agent + LLM Tool Calling + Business Tool + 실제 데이터 조회 + 자연어 응답 + Streamlit UI

Planning과 Memory는 아직 구현하지 않았다.
