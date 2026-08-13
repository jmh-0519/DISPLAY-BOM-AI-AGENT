# 현재 파일 구조

```text
project-root/
├── agents/
│   └── __init__.py
├── core/
│   ├── __init__.py
│   ├── settings.py
│   └── exceptions.py
├── data/
│   ├── products.csv
│   ├── materials.csv
│   └── bom.csv
├── models/
│   ├── __init__.py
│   ├── tool_request.py
│   └── tool_response.py
├── services/
│   ├── __init__.py
│   └── bom_service.py
├── tools/
│   ├── __init__.py
│   ├── base_tool.py
│   ├── registry.py
│   ├── executor.py
│   ├── bom_tool.py
│   ├── material_tool.py
│   └── product_tool.py
├── tests/
│   ├── __init__.py
│   ├── test_base_tool.py
│   ├── test_bom_service.py
│   ├── test_bom_tool.py
│   ├── test_data.py
│   ├── test_executor.py
│   ├── test_material_tool.py
│   ├── test_product_tool.py
│   └── test_registry.py
├── docs/
├── requirements.txt
└── README.md
```

## 정리 대상

```text
tests/test_bom_tool_integration.py
tests/test_material_tool_integration.py
```

## 향후 추가 파일

```text
agents/bom_agent.py
tests/test_bom_agent.py
```

Azure OpenAI 연결 시:

```text
core/azure_openai_client.py
agents/ai_bom_agent.py
tests/test_ai_agent.py
```
