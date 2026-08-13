# v8 Current Architecture

## 1. 현재 실행 구조

```text
┌──────────────────────────────────────┐
│            Streamlit UI              │
│     Agent Chat / BOM Query / DC      │
└──────────────────┬───────────────────┘
                   ▼
┌──────────────────────────────────────┐
│       Display BOM Single Agent       │
│                                      │
│ Azure OpenAI                         │
│ SKILL.md                             │
│ Multi-step Tool Calling Loop         │
│ Tool Definitions from MCP            │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│             MCP Client               │
│          stdio ClientSession         │
└──────────────────┬───────────────────┘
                   │ MCP
                   ▼
┌──────────────────────────────────────┐
│       Display BOM MCP Server         │
│ Query Capabilities                   │
│ - get_bom                            │
│ - search_product                     │
│ - search_material                    │
│ - list_products / list_materials     │
└──────────────────┬───────────────────┘
                   ▼
┌──────────────────────────────────────┐
│       Service / Business Logic       │
│ BomService / DesignChange / Review   │
│ QueryNormalizer                      │
└──────────────────┬───────────────────┘
                   ▼
            CSV Data / future DB
```

## 2. 책임 분리
| Layer | 책임 |
|---|---|
| UI | 입력/표현/사용자 상호작용 |
| Agent | 판단, Tool 선택, 결과 해석, 다음 Action 결정 |
| Skill | 업무 절차, 제약, Tool 사용 지침 |
| MCP Client/Server | 표준 Capability 연결/호출 |
| Service | 실제 Business Logic |
| QueryNormalizer | 사용자 검색 표현을 도메인 표준 표현으로 변환/Ranking |
| Data | BOM/제품/자재/Rule 등 원천 데이터 |

## 3. 아직 비어 있는 핵심 계층
현재 UI의 채팅 기록과 Agent Context가 완전히 연결되어 있지 않다. 따라서 다음 단계에서 Conversation Memory를 추가한다.
