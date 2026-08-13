# Current File Structure

현재 핵심 파일 구조는 다음과 같다.

```text
display-bom-ai-agent/
├─ agents/
│  ├─ bom_agent.py
│  └─ azure_bom_agent.py
├─ app/
│  └─ streamlit_app.py
├─ core/
│  ├─ settings.py
│  └─ azure_openai_client.py
├─ models/
│  ├─ tool_request.py
│  └─ tool_response.py
├─ services/
│  └─ bom_service.py
├─ tools/
│  ├─ base_tool.py
│  ├─ registry.py
│  ├─ executor.py
│  ├─ bom_tool.py
│  ├─ material_tool.py
│  └─ product_tool.py
├─ scripts/
│  ├─ test_azure_tool_selection.py
│  ├─ test_azure_tool_execution.py
│  └─ run_azure_bom_agent.py
└─ tests/
   ├─ test_bom_agent.py
   ├─ test_azure_bom_agent.py
   ├─ test_bom_service.py
   ├─ test_bom_tool.py
   ├─ test_material_tool.py
   ├─ test_product_tool.py
   ├─ test_executor.py
   └─ test_registry.py
```

실제 프로젝트에 존재하는 기타 테스트/데이터/문서 파일은 유지한다.
