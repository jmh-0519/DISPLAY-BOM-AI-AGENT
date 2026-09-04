# Display BOM AI Agent

디스플레이 제조사의 BOM 조회, 분석, 설계변경 검토를 자연어로 지원하는 **Single AI Agent** 프로젝트입니다.

이 프로젝트의 핵심 원칙은 LLM이 업무 사실과 승인 권한을 직접 결정하지 않도록 하는 것입니다. 요청 유형에 따라 deterministic route, RAG, read-only Text-to-SQL, LangGraph Agent를 조합하고, BOM/설계변경의 최종 업무 판단은 MCP 뒤의 Domain Service / Rule / Repository / SQLite Evidence가 담당합니다.

---

## 1. Current Release

- Release target: `v4.0.0`
- Final pre-release baseline: `9f5a210` (`feat: harden agent evaluation safety and stability`)
- Architecture: **Single Agent + LangGraph + MCP**
- LLM: Azure OpenAI `gpt-4.1-mini`
- Retrieval: Azure OpenAI Embedding + local Chroma evaluation/runtime index
- Analytics: Read-only Text-to-SQL
- UI: Streamlit
- Database: SQLite
- Test: pytest

`v4.0.0`은 RAG, Text-to-SQL, workflow-aware composition, ontology/context hardening, Agent Evaluation / Safety / Performance gate까지 포함한 현재 완료 범위입니다.

자세한 구조는 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), Release 검증 결과는 [`docs/RELEASE_V4_0_0.md`](docs/RELEASE_V4_0_0.md)를 참고합니다.

---

## 2. 주요 기능

### BOM / Master 조회

- 제품 BOM / ASSY BOM 조회
- 자재 / 제품 검색
- Where-used 역방향 조회
- 품목 상세 조회
- PLANT 조회 및 사용자 선택
- Active BOM Context 기반 후속 조회

### Knowledge / RAG

- 설계변경 Rule / Reason / Policy / Guide 문서 검색
- 문서 Metadata 기반 Filtering
- 근거 기반 응답
- RAG는 **업무 판정 Authority가 아니라 Evidence 계층**으로 사용

### Read-only Text-to-SQL

- 자연어 기반 BOM / 공급사 / 생산계획 Analytics
- SELECT-only 실행
- 허용 Schema / Query validation
- DDL / DML / Production Write 차단
- 결과 Evidence와 Knowledge Evidence를 함께 사용하는 Read-only Composition 지원

### 설계변경 분석

현재 하나의 Analysis Session / Design Change Request는 **하나의 Action**만 처리합니다.

지원 Action:

- `REPLACE`
- `ADD`
- `DELETE`
- `QUANTITY_CHANGE`

분석 단계와 Request 단계는 분리하며, 사용자가 대상을 특정하지 않은 경우 Agent가 임의 품목을 선택하지 않고 재질문합니다.

---

## 3. 설계변경 Workflow

```text
사용자 자연어 요청
        ↓
Intent / Entity / Context 분석
        ↓
Analysis Session
        ↓
후보 탐색 + Rule / RAG / DB Evidence 평가
        ↓
PASS / CONDITIONAL / FAIL
        ↓
후보 비교 / 설명 / 재검증
        ↓
변경 후보 확정
        ↓
공용 BOM 영향 확인
        ↓
사용자 "설계변경 진행"
        ↓
Design Change Request 생성
        ↓
Preview
        ↓
설계변경 확정
        ↓
Production E-BOM Atomic Apply
        ↓
설계변경 이력 / 완료 보고서
```

### Safety Policy

- Analysis 단계에서는 Request를 생성하지 않습니다.
- 사용자의 명시적 진행 승인 후에만 Request를 생성합니다.
- Preview와 최종 승인 없이는 Production E-BOM을 변경하지 않습니다.
- `FAIL` 후보 / Action은 Apply할 수 없습니다.
- `CONDITIONAL`은 추가 검증 또는 사유가 기록된 예외승인이 필요합니다.
- PLANT / 자재 / ASSY / BOM scope를 임의로 추측하지 않습니다.
- Active BOM과 진행 중인 Analysis scope가 충돌하면 상대 표현으로 자동 선택하지 않습니다.
- 공용 ASSY / 자재는 영향 모델을 확인합니다.
- Apply는 하나의 Transaction으로 처리하고 실패 시 Rollback합니다.
- DB Evidence가 업무 상태의 Source of Truth입니다.

---

## 4. Runtime Architecture

```text
Streamlit
    ↓
Domain Intent Router
    ↓
LangGraph Gateway
    ├─ Fast Path
    ├─ Deterministic Macro
    ├─ Knowledge Path (RAG)
    ├─ Text-to-SQL Path
    ├─ Read-only Composition
    ├─ Workflow Composition
    ├─ Scope Conflict Guard
    └─ Agent Path
            ↓
         MCP Client
            ↓
     Display BOM MCP Server
            ↓
       Domain Service / Rule
            ↓
          Repository
            ↓
           SQLite
```

### Responsibility Boundary

**LLM**

- 모호한 자연어 해석
- 필요한 Tool 선택
- Context 기반 추론
- Evidence 설명

**Deterministic Router / Planner / Macro**

- 명확한 요청의 빠른 Routing
- 불필요한 LLM 호출 제거
- 정해진 Capability 순서와 권한 경계 적용

**RAG**

- 정책 / Rule / Guide Evidence 검색
- 설명 근거 제공
- PASS / CONDITIONAL / FAIL 최종 Authority 아님

**Text-to-SQL**

- 허용된 업무 데이터의 read-only Analytics
- SQL generation 결과는 validator와 read-only executor를 통과해야 함

**Domain Service / Rule**

- BOM 사실 및 업무 검증
- 후보 적합성 평가
- PASS / CONDITIONAL / FAIL
- 공급 / 재고 / 비용 Evidence
- Apply 가능 여부

**Repository / DB**

- BOM / Analysis / Request / Approval / Preview / Apply Evidence 저장
- Workflow state의 Source of Truth

---

## 5. Context / Ontology

현재 Context는 다음 의미를 분리합니다.

- Active BOM Context: 사용자가 현재 조회 중인 MODEL / PLANT
- Design Change Workflow Context: 진행 중인 Analysis Session / Request
- Workflow Target Edge: VERSION + PLANT + Parent + Child + LOCATION
- Analysis Session과 Change Request는 서로 다른 lifecycle

`이 모델`, `이 BOM`, `이 자재`, `이 ASSY`, `기존 분석` 같은 상대 표현은 중앙화된 Context Semantics를 사용합니다. Active BOM과 Workflow scope가 다를 때는 자동으로 한쪽을 선택하지 않고 Scope Conflict를 반환합니다.

---

## 6. Knowledge / Rule Catalog

Knowledge는 `knowledge/` 아래에서 관리합니다.

- `knowledge/rules/`: 구조화 Rule + 설명 문서
- `knowledge/reasons/`: 설계변경 Reason 정의
- `knowledge/documents/`: Policy / FAQ / Guide / Material / Supplier 기술 문서

Rule TOML front matter는 Runtime Rule Engine 입력으로 사용할 수 있고 Markdown 본문은 RAG Evidence로 사용합니다.

```powershell
python -m scripts.validate_design_change_knowledge
python -m scripts.validate_rule_catalog
python -m scripts.validate_knowledge_documents
```

---

## 7. Agent Evaluation

현재 Release Evaluation Dataset:

```text
56 Cases
69 Turns
```

기존 50 Case / 58 Turn dataset은 regression baseline으로 보존하고, `evaluation/datasets/agent_eval_v2.jsonl`이 현재 Runtime 경로를 추가 검증합니다.

포함 경로:

- FAST_PATH
- DETERMINISTIC_MACRO
- AGENT_PATH
- KNOWLEDGE_PATH
- TEXT_TO_SQL_PATH
- READ_ONLY_COMPOSITION
- WORKFLOW_COMPOSITION
- SCOPE_CONFLICT

### v4.0.0 Final Evaluation Result

| Metric | Result |
|---|---:|
| Intent Accuracy | **100.00% (69/69)** |
| Route Accuracy | **100.00% (69/69)** |
| Tool Selection Accuracy | **100.00% (69/69)** |
| Tool Argument Accuracy | **100.00% (48/48)** |
| Planner Accuracy | **100.00% (6/6)** |
| Context Gate | **13/13 PASS** |
| Safety | **167/167 PASS** |
| Average Latency | **808.02 ms** |
| P95 Latency | **3314.59 ms** |
| <=5s Turns | **95.65%** (diagnostic) |
| LLM-free Turns | **85.51%** (diagnostic) |
| RAG Gate | **PASS** |
| Text-to-SQL Gate | **PASS** |
| Full Regression | **737/737 PASS** |

Accuracy 100%는 현재 Ground Truth Dataset에 대한 conformance이며 모든 가능한 사용자 질문에서 항상 100% 정확하다는 의미는 아닙니다.

---

## 8. Evaluation 실행

### Foundation

```powershell
python -m scripts.validate_final_02_evaluation_foundation
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
python -m scripts.collect_agent_evaluation_observations `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --all
```

### Accuracy / Performance / Safety

```powershell
python -m scripts.evaluate_agent_accuracy `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete

python -m scripts.evaluate_agent_performance `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete

python -m scripts.evaluate_agent_safety `
  --dataset evaluation/datasets/agent_eval_v2.jsonl `
  --require-complete
```

### FINAL-02 Quality Gate

```powershell
python -m scripts.finalize_final_02_evaluation --run-tests --require-tests
```

### FINAL-03 Release Freeze Gate

```powershell
python -m scripts.finalize_final_03_release --run-tests --require-tests
```

---

## 9. 일반 테스트

전체 Regression:

```powershell
python -m scripts.run_tests
```

Quick:

```powershell
python -m scripts.run_tests --suite quick -q
```

특정 테스트:

```powershell
python -m scripts.run_tests tests/test_file.py -q
```

테스트는 격리된 SQLite DB를 사용하며 Runtime DB를 테스트 데이터로 덮어쓰지 않습니다.

---

## 10. 실행

```powershell
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

환경변수 예:

```text
BOM_SQLITE_PATH=data/display_bom.db
```

API Key / Secret은 Git에 Commit하지 않습니다.

### SQLite 역할

- `data/display_bom_seed.db`: Git 추적 Canonical Seed DB
- `data/display_bom.db`: Runtime / Demo DB
- `.pytest_tmp_runtime/test_display_bom.db`: Disposable pytest DB

---

## 11. Repository Hygiene

Git에 포함하지 않는 항목:

- `.env`, API Key, Secret
- `.perf/` evaluation runtime output
- `artifacts/` local audit / generated output
- `data/rag/` local vector index
- Runtime DB / DB backup
- `.final_*_backup_*`, `.plan_*_backup_*`, `.ctx_*_backup_*`, `.t2sql_*_backup_*` 등 patch backup workspace
- Python cache / pytest temp

Canonical Seed DB와 source / tests / public knowledge만 추적합니다.

---

## 12. 개발 원칙

- Single Agent 구조를 유지합니다.
- Multi-Agent를 기본 구조로 사용하지 않습니다.
- Agent 업무 기능은 MCP Tool boundary를 유지합니다.
- MCP Server에 Business Logic을 중복 구현하지 않습니다.
- Domain Service / Rule이 업무 판단 Authority입니다.
- Repository / DB가 업무 Evidence와 상태의 Source of Truth입니다.
- LLM은 Tool Evidence 없이 원가, 재고, 공급사, 납기, 적합성을 생성하지 않습니다.
- RAG는 Evidence이며 업무 판정 Authority가 아닙니다.
- Text-to-SQL은 read-only 범위를 벗어나지 않습니다.
- Production BOM 변경은 반드시 승인 Workflow를 통과합니다.
- 신규 변경은 기존 Agent Evaluation / Safety / Regression을 재검증합니다.
