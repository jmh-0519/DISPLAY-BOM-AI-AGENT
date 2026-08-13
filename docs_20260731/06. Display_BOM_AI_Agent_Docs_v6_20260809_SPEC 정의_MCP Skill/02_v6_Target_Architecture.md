# v6 Target Architecture

## 1. 목표 구조

```text
┌──────────────────────────────────────┐
│            Streamlit UI              │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│       Display BOM AI Agent           │
│                                      │
│  Constitution                        │
│       ↓                              │
│  Intent Analysis                     │
│       ↓                              │
│  Skill                               │
│       ↓                              │
│  Planner                             │
│       ↓                              │
│  Workflow State / Memory             │
│       ↓                              │
│  MCP Client                          │
└──────────────────┬───────────────────┘
                   │ MCP
                   ▼
┌──────────────────────────────────────┐
│       Display BOM MCP Server         │
│                                      │
│  Query Capability                    │
│  Design Change Analysis              │
│  Design Change Apply                 │
│  BOM Review                          │
│  Report Generation                   │
└──────────────────┬───────────────────┘
                   │
                   ▼
          Service / Business Logic
                   │
                   ▼
                CSV / DB
```

## 2. 역할 분리

### Agent
Agent는 다음을 담당한다.

- 사용자 Intent 이해
- Skill 참조
- 실행 계획 수립
- Tool 선택 및 호출 순서 결정
- Workflow 상태 관리
- Tool 실행 결과 해석
- 사용자 승인 요청
- 최종 응답 생성

### MCP Server
MCP Server는 Agent가 사용할 수 있는 실제 업무 Capability를 표준 인터페이스로 제공한다.

MCP Server 자체가 Agent의 Planning 역할을 수행하지 않는다.

### Service
Service 계층은 실제 BOM 업무 로직과 데이터 접근을 담당한다.

## 3. Single Agent 원칙

본 프로젝트는 Multi-Agent 구조로 확장하지 않고 Single Azure BOM Agent를 유지한다.

복잡한 업무는 Agent 수를 늘리는 방식이 아니라 다음 요소의 조합으로 해결한다.

```text
Single Agent
+ Skill
+ Planning
+ Memory
+ MCP Tools
```
