# Current Architecture

## 현재 구조

```text
┌─────────────────────┐
│      Streamlit      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    AzureBomAgent    │
└──────┬────────┬─────┘
       │        │
       ▼        ▼
AzureOpenAI   ToolRegistry
  Client          │
                  ▼
             ToolExecutor
                  │
         ┌────────┼────────┐
         ▼        ▼        ▼
      BomTool  Material  Product
                 Tool      Tool
         └────────┼────────┘
                  ▼
              BomService
                  │
                  ▼
                 CSV
                  │
                  └──────────────┐
                                 ▼
                           Azure OpenAI
                                 │
                                 ▼
                           Final Answer
```

## 설계 원칙
- Single Agent 구조를 유지한다.
- LLM과 Business Logic을 분리한다.
- 실제 데이터 접근은 Service 계층이 담당한다.
- ToolExecutor를 통해 Tool 실행 경로를 일관되게 유지한다.
- LLM은 Tool 선택과 결과 해석에 집중한다.
