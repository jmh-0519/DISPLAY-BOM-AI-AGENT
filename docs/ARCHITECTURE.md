# Display BOM AI Agent v4.0.0 Architecture

## 1. Architecture Goal

Display BOM AI Agent는 하나의 LLM Agent에 모든 요청을 맡기지 않습니다. 요청을 먼저 deterministic하게 분류하고, 필요한 경우에만 LLM / RAG / Text-to-SQL / MCP를 조합합니다.

```text
User
  ↓
Streamlit
  ↓
Domain Intent Router
  ↓
LangGraph Gateway
  ├─ FAST_PATH
  ├─ DETERMINISTIC_MACRO
  ├─ KNOWLEDGE_PATH
  ├─ TEXT_TO_SQL_PATH
  ├─ READ_ONLY_COMPOSITION
  ├─ WORKFLOW_COMPOSITION
  ├─ SCOPE_CONFLICT
  └─ AGENT_PATH
          ↓
       MCP Client
          ↓
   Display BOM MCP Server
          ↓
 Domain Service / Rule Engine
          ↓
      Repository
          ↓
       SQLite
```

## 2. Execution Paths

### FAST_PATH

명확한 BOM 조회, Where-used, 현재 BOM 수량 조회처럼 LLM이 필요하지 않은 요청을 처리합니다.

### DETERMINISTIC_MACRO

대상과 Action이 명확한 설계변경 후보 분석을 정해진 MCP / Service 순서로 실행합니다.

### KNOWLEDGE_PATH

설계변경 정책 / 기준 / Rule / FAQ 등의 Knowledge 문서를 RAG로 검색해 Evidence 기반 답변을 생성합니다.

### TEXT_TO_SQL_PATH

허용된 업무 데이터에 대한 read-only Analytics를 수행합니다. SQL 생성 결과는 validator와 read-only executor를 통과해야 하며 DDL / DML은 허용하지 않습니다.

### READ_ONLY_COMPOSITION

Analytics Evidence와 Knowledge Evidence를 함께 요구하는 read-only 요청을 조합합니다. Workflow나 Production BOM을 변경하지 않습니다.

### WORKFLOW_COMPOSITION

설계변경 분석에서 scoped BOM Evidence, RAG Evidence, Design Change Analysis를 capability dependency에 따라 조합합니다. Analysis Session까지만 생성하며 Request / Approval / Production Write 권한은 없습니다.

### SCOPE_CONFLICT

Active BOM과 진행 중인 Design Change Workflow scope가 다른 상태에서 `이 모델`, `이 자재`, `이 ASSY` 같은 상대 표현이 들어오면 자동 선택을 차단합니다.

### AGENT_PATH

모호한 자연어 해석, 대화형 재질문, 기존 Analysis 설명처럼 LLM reasoning이 필요한 요청을 처리합니다.

## 3. Authority Boundary

| Layer | Authority |
|---|---|
| LLM | 자연어 해석, Tool 선택, Evidence 설명 |
| RAG | 문서 Evidence 검색 |
| Text-to-SQL | Read-only Analytics Evidence |
| Planner / Router | Capability / 실행경로 선택 |
| Domain Service / Rule | 업무 검증과 후보 판정 |
| Repository / SQLite | 업무 상태와 Evidence 저장 |
| User Approval | Request 진행 / 최종 Apply 승인 |

LLM, RAG, Text-to-SQL, Context Resolver는 자체적으로 Production BOM write 권한을 갖지 않습니다.

## 4. Context / Ontology

핵심 Ontology:

```text
PRODUCT / MODEL
  ↓
VERSION
  ↓
PLANT
  ↓
BOM
  ↓
BOM_EDGE = Parent + Child + LOCATION
```

ITEM은 ASSY 또는 MATERIAL일 수 있습니다.

Context는 다음을 별도 관리합니다.

- Active BOM Context
- Design Change Analysis Session
- Design Change Request
- Workflow Target BOM Edge provenance

Current-turn explicit scope가 inherited context보다 우선하며, READ_ONLY와 Design Change follow-up의 precedence를 분리합니다.

## 5. Design Change Boundary

```text
Analysis Session
  ↓ user proceeds
Design Change Request
  ↓ approved candidate / impact
Preview
  ↓ final approval
Atomic Apply
```

Analysis Session은 Request가 아닙니다. 분석 중 Request 생성과 Production BOM write는 금지합니다.

## 6. Knowledge / RAG

- Rule Knowledge: `knowledge/rules/`
- Reason Knowledge: `knowledge/reasons/`
- Policy / Guide / FAQ / Material / Supplier: `knowledge/documents/`

Rule의 구조화 정의는 Runtime Rule Engine에 사용될 수 있으며, Markdown 본문은 RAG Evidence로 사용합니다. RAG 검색 결과만으로 PASS / CONDITIONAL / FAIL을 결정하지 않습니다.

## 7. Text-to-SQL

Text-to-SQL은 read-only source만 대상으로 합니다.

- 허용 schema 제한
- SELECT-only
- DDL / DML 차단
- 실행 전 validation
- 결과 제한 / timeout
- Workflow write authority 없음

설계변경 Composition에서 필요한 scoped cost evidence는 deterministic SQL 경로를 우선하며 SQL-generation LLM call 없이 실행할 수 있습니다.

## 8. Safety / Evaluation

Release 품질은 다음을 함께 검증합니다.

- Ground Truth Agent Accuracy
- Context / Planner / Composition validator
- RAG Retrieval gate
- Text-to-SQL generation gate
- Deterministic Safety assertion
- Runtime latency
- Full pytest regression

`v4.0.0` 기준은 [`RELEASE_V4_0_0.md`](RELEASE_V4_0_0.md)에 기록합니다.
