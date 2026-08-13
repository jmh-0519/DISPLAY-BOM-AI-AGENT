# Change Log

## v5

### Added
- Azure OpenAI Gateway 연동
- AzureOpenAIClient
- LLM Tool Calling
- Tool 결과 재전달
- AzureBomAgent
- `BomService.search_product()`
- Streamlit Chat UI
- AzureBomAgent Test
- BomService Test

### Verified
- get_bom
- search_material
- search_product
- ToolExecutor
- Azure Tool Calling
- Final Answer Generation
- Streamlit Integration

### Fixed
- Streamlit 실행 시 `agents` 모듈 import 경로 문제
- ProductTool이 호출하던 `BomService.search_product()` 구현 누락 문제

### Architecture Change

Before:
```text
User
→ Rule-based BomAgent
→ ToolExecutor
```

After:
```text
User
→ Streamlit
→ AzureBomAgent
→ Azure OpenAI
→ ToolExecutor
→ Business Tool
→ BomService
→ Data
→ Azure OpenAI
→ Final Answer
```

### Remaining
- Memory
- Planning
- Multi-step Tool Calling
- Workflow State
- BOM Design Change
- Review / Validation
- Report Generation
