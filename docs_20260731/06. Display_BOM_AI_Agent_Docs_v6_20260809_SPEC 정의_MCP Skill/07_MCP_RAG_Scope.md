# MCP-RAG Scope

## 1. 현재 판단

v6에서는 MCP-RAG 또는 Tool Retrieval을 우선 적용하지 않는다.

현재 예상 Tool 수는 약 10개 내외이므로 모든 Tool Definition을 LLM에 제공하고 적절한 Tool을 선택하도록 하는 구조로 충분하다.

## 2. 현재 구조

```text
사용자 질문
↓
Agent / LLM
↓
전체 사용 가능 Tool Definition 확인
↓
적절한 Tool 선택
```

## 3. 향후 검토 시점

Tool이 수십~수백 개로 증가하거나 외부 시스템의 MCP Tool이 대규모로 연결되는 경우 다음 구조를 검토한다.

```text
사용자 질문
↓
Tool Metadata Retrieval
↓
관련 Tool 후보 검색
↓
LLM 최종 Tool 선택
↓
Tool 실행
```

즉 MCP-RAG는 현재 반드시 필요한 기능이 아니라 **Tool 규모가 커졌을 때 필요한 확장 전략**으로 관리한다.
