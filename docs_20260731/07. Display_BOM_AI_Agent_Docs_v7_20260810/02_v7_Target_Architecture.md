# v7 Target Architecture

## 1. 목표 아키텍처

```text
┌─────────────────────────────────────────┐
│              Streamlit UI               │
│  Agent Chat / Design Change / Review    │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│         Display BOM AI Agent            │
│                                         │
│ Constitution                            │
│ Intent Analysis                         │
│ Skill                                   │
│ Planner                                 │
│ Workflow State / Memory                 │
│ MCP Client                              │
└────────────────────┬────────────────────┘
                     │ MCP
                     ▼
┌─────────────────────────────────────────┐
│         Display BOM MCP Server          │
│                                         │
│ Query Capability                        │
│ Design Change Analysis                  │
│ Design Change Apply                     │
│ BOM Review                              │
│ Report Generation                       │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│          Service / Business Logic       │
│                                         │
│ BomService                              │
│ DesignChangeService                     │
│ DesignChangeApplyService                │
│ ReviewService                           │
└────────────────────┬────────────────────┘
                     │
                     ▼
                  CSV / DB
```

## 2. 현재 구현 상태

### 구현됨
- Streamlit
- AzureBomAgent
- Azure OpenAI Client
- Tool Registry / Executor
- Query Service
- Design Change Analysis Business Logic
- Compatibility 검증
- Rule 검증
- Preview/Apply 기반 Logic
- Review/Revalidation Logic
- BOM Tree Viewer

### 미구현 또는 미완성
- MCP Server
- MCP Client
- Constitution
- 명시적 Skill
- Planner
- Workflow State
- Agent 기반 승인 제어
- Report Generation

## 3. 아키텍처 원칙
Service는 업무 규칙의 소유자이며 MCP는 Service를 표준 Capability로 노출한다.

MCP가 Planning을 수행하지 않으며 Agent가 업무 순서를 결정한다.

Single Agent 원칙은 유지한다.
