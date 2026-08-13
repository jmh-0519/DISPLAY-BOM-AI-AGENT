# Test Strategy

## 테스트 계층

### Service Test
실제 CSV 검색 로직 검증.
- `test_bom_service.py`

### Tool Test
각 Business Tool의 입력/출력 검증.
- `test_bom_tool.py`
- `test_material_tool.py`
- `test_product_tool.py`

### Agent Test
LLM Tool Calling Agent의 orchestration 검증.
- `test_azure_bom_agent.py`

실제 Azure API를 매번 호출하지 않도록 Mock Client를 사용한다.

### Integration Test
실제 Azure OpenAI와 ToolExecutor를 연결하여 검증한다.
- Tool 선택 확인
- ToolRequest 변환
- ToolExecutor 실행
- 실제 CSV 조회
- Tool 결과 LLM 재전달
- 최종 답변 확인

### UI Test
Streamlit에서 실제 자연어 질문으로 검증한다.

## 현재 검증된 대표 시나리오
1. `PRD-LED-43-A의 BOM을 보여줘.`
2. `Speaker 자재를 검색해줘.`
3. `LED 제품을 찾아줘.`
