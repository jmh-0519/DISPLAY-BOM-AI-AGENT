# v7 MCP-RAG Scope

## 1. 현재 판단
v6의 판단을 그대로 유지한다.

현재 단계에서는 MCP-RAG / Tool Retrieval을 도입하지 않는다.

## 2. 이유
현재 필요한 Capability는 제한적이며 Tool 수가 아직 크지 않다.

예상 범위:
```text
Query 5종
analyze_design_change
apply_design_change
evaluate_bom_review
generate_change_report
```

따라서 모든 Tool Definition을 Agent에 제공하는 방식으로 충분하다.

## 3. 우선순위
현재 우선순위는 다음이다.

```text
Service 안정화
↓
MCP Foundation
↓
Skill / Planner
↓
Workflow State
↓
End-to-End Workflow
```

MCP-RAG는 Tool 수가 크게 증가할 때 재검토한다.
