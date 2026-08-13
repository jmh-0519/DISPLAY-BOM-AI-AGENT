# v7 Project Goal

## 1. v7 Baseline

v7은 v6에서 정의한 다음 목표를 유지한다.

> 단순 조회 Agent에서 실제 BOM 업무 Workflow를 수행하는 Single Agent로 발전한다.

현재까지 조회 기능뿐 아니라 설계변경 분석, Preview, Review 관련 Business Logic과 Streamlit UI가 구현되었다.

## 2. 현재 실제 실행 구조

### Agent 조회 흐름
```text
사용자
  ↓
Streamlit
  ↓
AzureBomAgent
  ↓
Azure OpenAI
  ↓
Tool Registry / ToolExecutor
  ↓
Service / CSV
```

### 설계변경 화면 흐름
```text
사용자
  ↓
Streamlit 설계변경 화면
  ↓
Design Change Service
  ↓
Validation
  ├─ Product
  ├─ Existing Material
  ├─ New Material
  ├─ Approval
  ├─ Lifecycle
  ├─ Compatibility
  └─ BOM Rule
  ↓
Preview BOM
```

현재 설계변경 UI는 Agent Planner를 통하지 않고 Service를 직접 호출하는 구조도 사용한다.

## 3. v7 최종 목표

```text
사용자 요청
   ↓
Single Agent
   ↓
Intent Analysis
   ↓
Skill
   ↓
Planning
   ↓
Workflow State
   ↓
MCP Capability
   ↓
Service / Business Logic
   ↓
Human Approval
   ↓
Apply
   ↓
Review
   ↓
Report
```

## 4. v7의 핵심 과제

이미 구현된 설계변경/Review Service를 다시 만드는 것이 아니라 다음 계층을 추가한다.

- MCP Interface
- Agent Skill
- Planner
- Workflow State
- Human Approval
- Report Generation
- End-to-End Agent Workflow
