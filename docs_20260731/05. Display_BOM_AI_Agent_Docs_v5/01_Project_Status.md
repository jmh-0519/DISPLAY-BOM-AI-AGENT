# Project Status

## 완료

### 기반 구조
- ToolRequest / ToolResponse
- BaseTool
- ToolRegistry
- ToolExecutor
- BomService
- CSV 기반 테스트 데이터

### Business Tool
- get_bom
- search_material
- search_product

### AI
- Azure OpenAI 연결
- Tool Definition 전달
- LLM Tool 선택
- Tool arguments 생성
- Tool 실행
- Tool 결과 재전달
- 최종 자연어 답변 생성

### Agent
- Rule-based BomAgent
- AzureBomAgent

### UI
- Streamlit Chat UI
- 대화 화면 표시
- Agent 호출
- 자연어 결과 표시
- 대화 초기화

## 미구현
- Conversation Memory
- Planning
- Multi-step Tool Calling
- Workflow State
- BOM 설계변경
- 품평회 검증
- 변경 승인
- 완료 보고서 생성
