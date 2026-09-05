# Display BOM AI Agent v4.0.0

디스플레이 제조사의 **BOM 조회와 설계변경 업무를 자연어로 지원하는 업무형 Single AI Agent** 프로젝트입니다.

단순 Q&A가 아니라 BOM / 품목 / 공급사 / 재고 / 업무 Rule / 지식 문서를 근거로 조회와 분석을 수행하고, 사용자의 명시적 승인 이후에만 Production E-BOM을 변경하도록 설계했습니다.

> **Final Release:** `v4.0.0`
> **Status:** 개발 완료 / Release Freeze 완료

---

## 1. 프로젝트 목표와 달성 결과

### 목표

- 자연어로 제품 BOM, ASSY BOM, Where-used, 자재/제품 정보를 조회
- REPLACE / ADD / DELETE / QUANTITY_CHANGE 설계변경 후보를 자동 분석
- 기술 Rule, 공급사, 재고, 비용, 공용 영향 범위를 근거 기반으로 검증
- Analysis와 실제 변경 권한을 분리하고 Human-in-the-Loop 승인 후에만 Apply
- RAG와 Text-to-SQL을 결합해 문서 지식과 관계형 데이터를 함께 활용
- Context/Ontology를 이용해 현재 BOM과 설계변경 Workflow의 Scope를 안전하게 관리
- Accuracy / Safety / Performance / RAG / Text-to-SQL / Regression을 하나의 Release Gate로 검증

### 최종 달성

| 영역 | 최종 결과 |
|---|---|
| BOM / Master 조회 | 구현 완료 |
| 설계변경 4개 Action | 구현 완료 |
| Human-in-the-Loop 승인 / Atomic Apply | 구현 완료 |
| History / Word 완료보고서 | 구현 완료 |
| RAG Knowledge Evidence | 구현 완료 / Gate PASS |
| Read-only Text-to-SQL | 구현 완료 / Gate PASS |
| Context / Ontology | 구현 완료 |
| Agent Evaluation | 56 Cases / 69 Turns |
| Intent / Route / Tool / Arguments | 100% |
| Safety | 167 / 167 PASS |
| P95 Latency | 3314.59 ms |
| Full Regression | 743 / 743 PASS |
| UI Acceptance | PASS |

---

## 2. v3.0 → v4.0 주요 변경

`v3.0.0`에서 설계변경 End-to-End Core Workflow를 완성한 뒤, `v4.0.0`에서는 **근거성, 분석 범위, Context 이해, 평가 체계와 Release 안정성**을 강화했습니다.

| 구분 | v3.0 | v4.0 |
|---|---|---|
| Agent 구조 | LangGraph Single Agent + MCP | Hybrid Single Agent + deterministic execution paths |
| 업무 지식 | Rule / DB 중심 | Rule + RAG Knowledge Evidence |
| 관계형 분석 | 정해진 조회 Tool | Read-only Text-to-SQL 추가 |
| 복합 질의 | LLM/Tool 중심 | Knowledge + Analytics Composition |
| 설계변경 분석 | Target/Action 중심 | Evidence-driven Workflow Composition |
| Context | Active BOM / Workflow State | Ontology + BOM Edge + Scope Conflict Guard |
| 상대 표현 | 제한적 Context 재사용 | `이 모델/이 BOM/이 자재/기존 분석` 중앙화 의미 해석 |
| 평가 | pytest / E2E 중심 | Ground Truth Agent Evaluation + Safety + Performance |
| Release 품질 | 기능 회귀 중심 | RAG / T2SQL / Agent / Safety / P95 / Full Regression 통합 Gate |

### v4.0 핵심 구현 항목

1. **RAG Knowledge Layer**
   - 설계변경 Rule / Reason / Policy / Guide / FAQ / Material / Supplier 문서화
   - Azure OpenAI Embedding + Chroma 기반 검색
   - Metadata filtering과 Ground Truth Retrieval Evaluation 적용

2. **Read-only Text-to-SQL**
   - 자연어 기반 BOM / 공급사 / 생산계획 Analytics
   - 허용 Schema, SELECT-only, SQL validation, SQLite read-only executor 적용
   - Workflow / Approval / Apply 관련 Write Schema는 접근 불가

3. **Evidence-driven Composition**
   - Analytics + Knowledge 조합 요청을 Read-only Composition으로 처리
   - Scoped BOM Evidence + RAG + Design Change Analysis를 Workflow Composition으로 연결
   - 명확한 요청은 LLM 없이 deterministic SQL / Tool 순서로 실행

4. **Ontology / Context Understanding**
   - `MODEL → VERSION → PLANT → BOM → BOM_EDGE` 구조 정의
   - BOM target을 Parent + Child + LOCATION edge로 식별
   - Active BOM Context와 Design Change Workflow Context를 분리
   - 서로 다른 Scope에서 상대 표현이 들어오면 자동 선택하지 않고 Scope Conflict로 차단

5. **Agent Evaluation / Safety / Performance**
   - 56 Cases / 69 Turns Ground Truth Dataset
   - 현재 Runtime의 모든 execution path 평가
   - Accuracy / Safety / Performance가 동일 observation run을 사용하도록 검증
   - RAG / Text-to-SQL 별도 domain gate와 Full Regression을 Release Gate에 통합

---

## 3. 최종 아키텍처

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

### 계층별 책임

| 계층 | 역할 |
|---|---|
| LLM | 모호한 자연어 해석, Tool 선택, Evidence 설명 |
| Router / Planner / Macro | 명확한 요청의 deterministic 실행과 Capability 순서 결정 |
| RAG | 업무 문서 Evidence 검색 |
| Text-to-SQL | 허용된 관계형 데이터의 Read-only Analytics |
| MCP | Agent와 업무 Capability의 계약 경계 |
| Domain Service / Rule | 업무 검증, 후보 판정, Apply 가능 여부 결정 |
| Repository / SQLite | 업무 사실, 상태, 변경 Evidence의 Source of Truth |
| User Approval | Request 진행과 최종 Production Apply 승인 |

자세한 구조는 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)를 참고합니다.

---

## 4. 주요 기능

### BOM / Master 조회

- 제품 BOM / ASSY BOM 조회
- Where-used 역방향 조회
- 자재 / 제품 / 품목 상세 검색
- PLANT 조회 및 선택
- Active BOM Context 기반 후속 수량 / 품목 조회

### 설계변경 분석

지원 Action:

- `REPLACE`
- `ADD`
- `DELETE`
- `QUANTITY_CHANGE`

분석 시 다음 Evidence를 결합합니다.

- 현재 BOM 구조 / 수량 / Parent / LOCATION
- 기술 Rule
- 공급사 및 Lead Time
- 재고
- 비용
- 공용 ASSY / 자재 영향 범위
- Knowledge Evidence

대상이 모호한 경우 전체 후보를 임의 평가하거나 자동 선택하지 않고 사용자에게 재질문합니다.

### Human-in-the-Loop Workflow

```text
Analysis Session
   ↓ 후보 / 영향 검토
사용자 설계변경 진행 승인
   ↓
Design Change Request
   ↓
Preview
   ↓ 최종 승인
Production E-BOM Atomic Apply
   ↓
History / Word Completion Report
```

- Analysis 단계에서는 Request를 생성하지 않습니다.
- Preview와 최종 승인 없이는 Production E-BOM을 변경하지 않습니다.
- `FAIL` Action은 Apply할 수 없습니다.
- Apply는 하나의 Transaction으로 처리하고 실패 시 Rollback합니다.

---

## 5. RAG

RAG는 **업무 판단 Authority가 아니라 Knowledge Evidence 계층**입니다.

Knowledge source:

```text
knowledge/
├─ rules/
├─ reasons/
└─ documents/
```

최종 Retrieval Evaluation:

| Metric | Result |
|---|---:|
| Cases | 56 |
| Hit Rate@1 | 94.64% |
| Hit Rate@3 | 100.00% |
| Hit Rate@5 | 100.00% |
| Mean Recall@5 | 100.00% |
| MRR | 0.9702 |
| Metadata Filter Accuracy | 100.00% |
| P95 Retrieval Latency | 176.83 ms |
| Gate | PASS |

상세 내용은 [`rag/README.md`](rag/README.md)를 참고합니다.

---

## 6. Text-to-SQL

Text-to-SQL은 **Read-only Analytics 전용**입니다.

- 허용 Schema만 LLM에 제공
- SELECT-only
- Multi-statement / DDL / DML 차단
- SQL Guard 검증 후 실행
- SQLite read-only / query_only / authorizer 적용
- row cap / timeout 적용
- Design Change Workflow write table은 접근 대상에서 제외

최종 Generation Evaluation:

| Metric | Result |
|---|---:|
| Cases | 23 |
| SQL Cases | 15 |
| UNSUPPORTED Cases | 8 |
| Overall Accuracy | 100.00% |
| SQL Execution Success | 100.00% |
| Semantic Result Match | 100.00% |
| UNSUPPORTED Accuracy | 100.00% |
| P95 Generation Latency | 1720.17 ms |
| Gate | PASS |

상세 내용은 [`text_to_sql/README.md`](text_to_sql/README.md)를 참고합니다.

---

## 7. Context / Ontology

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

Context는 다음을 별도 관리합니다.

- Active BOM Context
- Analysis Session
- Design Change Request
- Workflow Target BOM Edge provenance

현재 턴에 명시된 MODEL / PLANT / 품목이 이전 Context보다 우선합니다.

`이 모델`, `이 BOM`, `이 자재`, `이 ASSY`, `기존 분석`과 같은 상대 표현은 중앙화된 Context Semantics를 사용하며, Active BOM과 Workflow Scope가 충돌하면 자동 추론 대신 명시적 Scope 선택을 요구합니다.

---

## 8. Agent Evaluation / Safety / Performance

현재 Release Dataset:

```text
56 Cases / 69 Turns
```

포함 execution path:

- FAST_PATH
- DETERMINISTIC_MACRO
- AGENT_PATH
- KNOWLEDGE_PATH
- TEXT_TO_SQL_PATH
- READ_ONLY_COMPOSITION
- WORKFLOW_COMPOSITION
- SCOPE_CONFLICT

최종 품질 결과:

| Metric | Result |
|---|---:|
| Intent Accuracy | 100.00% (69/69) |
| Route Accuracy | 100.00% (69/69) |
| Tool Selection Accuracy | 100.00% (69/69) |
| Tool Argument Accuracy | 100.00% (48/48) |
| Planner Accuracy | 100.00% (6/6) |
| Context Gate | 13/13 PASS |
| Safety | 167/167 PASS |
| Average Latency | 808.02 ms |
| P95 Latency | 3314.59 ms |
| <=5s Turns | 95.65% (diagnostic) |
| LLM-free Turns | 85.51% (diagnostic) |
| Full Regression | 743/743 PASS |

Accuracy 100%는 정의된 Ground Truth Dataset에 대한 conformance이며 모든 실세계 질문에서의 절대 정확도를 의미하지 않습니다.

---

## 9. 평가 및 Release Gate 실행

### Evaluation Foundation

```powershell
python -m scripts.validate_evaluation_foundation
```

### RAG

```powershell
python -m scripts.run_rag_retrieval_evaluation `
  --rebuild-index `
  --strict `
  --output .perf/evaluation/rag_report.json
```

### Text-to-SQL

```powershell
python -m scripts.run_text_to_sql_generation_evaluation `
  --strict `
  --output .perf/evaluation/text_to_sql_report.json
```

### Agent Runtime Observation

```powershell
python -m scripts.collect_agent_evaluation_observations --all
```

### Accuracy / Performance / Safety

```powershell
python -m scripts.evaluate_agent_accuracy --require-complete
python -m scripts.evaluate_agent_performance --require-complete
python -m scripts.evaluate_agent_safety --require-complete
```

### Integrated Evaluation Gate

```powershell
python -m scripts.finalize_evaluation --run-tests --require-tests
```

### Release Freeze

```powershell
python -m scripts.validate_release_freeze
python -m scripts.finalize_release --run-tests --require-tests
```

---

## 10. 실행

```powershell
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

대표 환경 변수:

```text
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_VERSION=...
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=...
BOM_SQLITE_PATH=data/display_bom.db
```

Secret / API Key는 Git에 commit하지 않습니다.

---

## 11. Repository 구조

```text
display-bom-ai-agent/
├─ agents/          # LangGraph Agent / Router / Planner / Context orchestration
├─ app/             # Streamlit UI
├─ core/            # Settings / Azure client / observability / profiler
├─ data/            # Canonical Seed / Runtime DB
├─ database/        # Schema / migration
├─ docs/            # Architecture / DB / Release 문서
├─ evaluation/      # Ground Truth / Observation / Quality Gate
├─ knowledge/       # Rule / Reason / RAG documents
├─ mcp_client/      # MCP Client
├─ mcp_server/      # MCP Capability boundary
├─ models/          # Domain models
├─ ontology/        # Context / Domain Ontology
├─ rag/             # RAG Runtime
├─ repositories/    # Data access
├─ scripts/         # DB / validation / evaluation / release utilities
├─ services/        # Business logic / Rule / Workflow
├─ skills/          # Agent skill contracts
├─ tests/           # Regression / integration / evaluation tests
└─ text_to_sql/     # Read-only Text-to-SQL
```

Database 구조는 [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md)를 참고합니다.

---

## 12. 프로젝트 시사점

### 1. 제조업 Agent는 LLM 단독 구조보다 역할 분리가 중요하다

BOM과 설계변경은 실제 데이터와 승인 상태가 중요하므로 LLM이 모든 판단을 수행하도록 하지 않고, Router / Rule / Service / Repository / DB에 Authority를 분리했습니다.

### 2. RAG와 Text-to-SQL은 서로 다른 Evidence 문제를 해결한다

- RAG: 정책, Rule, Guide 등 비정형 지식
- Text-to-SQL: BOM, 공급사, 원가, 생산계획 등 구조화 데이터

두 기능을 Composition으로 결합하되 실제 설계변경 실행 권한과는 분리했습니다.

### 3. Context 이해는 대화 기억보다 업무 Scope가 핵심이다

단순 대화 History를 많이 전달하는 것보다 Active BOM과 Design Change Workflow의 Scope를 분리하고, Parent / Child / LOCATION 수준까지 Target provenance를 관리하는 것이 업무 안정성에 더 중요했습니다.

### 4. Agent 품질은 답변 예시가 아니라 Evaluation Gate로 관리해야 한다

Intent, Route, Tool, Arguments, Safety, P95, RAG, Text-to-SQL, Full Regression을 함께 검증하여 기능 추가가 기존 업무 안전성을 깨뜨리지 않는지 확인했습니다.

---

## 13. 범위와 향후 확장

`v4.0.0`은 현재 프로젝트의 **최종 개발 완료 버전**입니다.

현재 범위 밖:

- 실제 PLM / ERP / MES 연계
- Enterprise Oracle/PostgreSQL 전환
- 사내 SSO / RBAC / 조직 승인권한
- Multi-Action Request
- 별도 품평회 Workflow
- 운영 인프라 / Kubernetes 배포

실제 기업 적용 시에는 현재의 MCP / Service / Repository / Safety boundary를 유지한 채 외부 시스템과 Enterprise 권한체계를 연결하는 방식으로 확장할 수 있습니다.

---

## 14. Release

유지할 Major Release tag:

- `v1.0.0`
- `v2.0.0`
- `v3.0.0`
- `v4.0.0` — **Final**

Release 상세는 [`docs/RELEASE_V4_0_0.md`](docs/RELEASE_V4_0_0.md)를 참고합니다.
