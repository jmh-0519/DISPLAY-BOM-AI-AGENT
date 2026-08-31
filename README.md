# Display BOM AI Agent

디스플레이 제조사의 BOM 조회와 설계변경 업무를 자연어로 지원하는 **Single AI Agent** 프로젝트입니다.

현재 버전의 핵심 목표는 자연어 요청을 단순히 LLM이 처리하는 것이 아니라, 요청의 성격에 따라 **Fast Path / Deterministic Macro / Agent Path**를 선택하고, 실제 업무 판단은 MCP와 Domain Service/Rule을 통해 수행하도록 구성하는 것입니다.

---

## 1. 현재 버전

- Current Clean Core Freeze: `v3.1.1`
- Agent Evaluation Baseline: `v3.1.0` (50 Cases / 58 Turns)
- Agent 구조: **Single Agent**
- LLM: Azure OpenAI `gpt-4.1-mini`
- Agent Framework: LangGraph
- Tool Boundary: MCP
- UI: Streamlit
- Database: SQLite
- Test: pytest

---

## 2. 주요 기능

### BOM / Master 조회

- 제품 BOM 조회
- ASSY BOM 조회
- 자재 검색
- 제품 / 모델 검색
- Where-used 역방향 BOM 조회
- 품목 상세 조회
- PLANT 조회 및 대화형 PLANT 선택
- 대화 Context를 이용한 후속 조회

### 설계변경

현재 하나의 Analysis Session / Design Change Request는 **하나의 Action**만 처리합니다.

지원 Action:

- `REPLACE`
- `ADD`
- `DELETE`
- `QUANTITY_CHANGE`

서로 다른 여러 Action을 하나의 Request에서 동시에 실행하는 기능은 현재 범위에 포함하지 않습니다.

---

## 3. 설계변경 Workflow

```text
사용자 자연어 요청
        ↓
Intent / Entity / Context 분석
        ↓
Analysis Session
        ↓
후보 탐색 및 Evidence 평가
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

### 설계변경 안전 정책

- Analysis 단계에서는 실제 Design Change Request를 생성하지 않습니다.
- 사용자의 명시적인 진행 승인 후에만 Request를 생성합니다.
- Preview와 최종 승인 없이는 Production E-BOM을 변경하지 않습니다.
- `FAIL` 후보 또는 Action은 Apply할 수 없습니다.
- `CONDITIONAL`은 추가 검증 또는 사유가 기록된 예외승인이 필요합니다.
- PLANT나 변경 대상을 임의로 추측하지 않습니다.
- 공용 ASSY / 공용 자재 변경은 영향 범위를 확인합니다.
- Apply는 하나의 Transaction으로 처리하며 실패 시 Rollback합니다.
- DB Evidence가 실제 업무 상태의 Source of Truth입니다.

---

## 4. Runtime Architecture

```text
Streamlit
    ↓
Domain Intent Router
    ↓
LangGraph Gateway
    ├─ FAST_PATH
    ├─ DETERMINISTIC_MACRO
    └─ AGENT_PATH
            ↓
        MCP Client
            ↓
    Display BOM MCP Server
            ↓
       Domain Service
            ↓
         Rule Engine
            ↓
        Repository
            ↓
          SQLite
```

### 역할 분리

**LLM**

- 모호한 자연어 해석
- 복합 요청 Reasoning
- 필요한 Tool 선택
- 사용자 설명이 필요한 Agent Path 처리

**Deterministic Router / Macro**

- 명확한 Intent의 빠른 Routing
- 불필요한 LLM 호출 제거
- 확정적인 설계변경 분석 경로 실행

**Domain Service / Rule**

- 업무 검증
- 후보 적합성 판단
- PASS / CONDITIONAL / FAIL 계산
- 공급사 / 재고 / 비용 Evidence 처리
- Apply 가능 여부 결정

**Repository / DB**

- BOM / Master / Request / Approval / Apply Evidence 저장
- 업무 상태의 Source of Truth

---

## 5. Hybrid Agent 실행 방식

사용자 요청은 항상 LLM으로 보내지 않습니다.

```text
사용자 요청
    ↓
Domain Intent Router
    ↓
┌─────────────────────────────┐
│ FAST_PATH                   │
│ 단순 조회 / 확정적 요청     │
│ LLM 호출 없음              │
└─────────────────────────────┘

┌─────────────────────────────┐
│ DETERMINISTIC_MACRO         │
│ 명확한 설계변경 분석        │
│ MCP + Service + Rule        │
│ Deterministic Finalizer     │
└─────────────────────────────┘

┌─────────────────────────────┐
│ AGENT_PATH                  │
│ 모호하거나 Reasoning 필요   │
│ LLM + MCP                   │
└─────────────────────────────┘
```

이 구조는 응답속도와 비용을 줄이면서도, 실제 BOM 업무 판단을 LLM에 의존하지 않도록 하기 위한 구조입니다.

---

# 6. Agent Evaluation

`v3.1.0`에서는 Agent 기능 개발뿐 아니라, 이후 기능 추가 시 기존 Agent 품질이 깨지는지를 자동으로 검증할 수 있도록 **Agent Evaluation 체계**를 구축했습니다.

## Evaluation Dataset

현재 Evaluation 기준선:

```text
50 Cases
58 Turns
```

- **Case**: 하나의 업무 테스트 시나리오
- **Turn**: 해당 시나리오에서 Agent가 실제로 처리하는 사용자 입력 1회

여러 단계의 대화가 필요한 Case는 하나의 Case 안에 2개 이상의 Turn을 가질 수 있습니다.

### 주요 평가 Category

- CHAT
- BOM_READ
- WHERE_USED
- CONTEXT
- REPLACE
- ADD
- DELETE
- QUANTITY_CHANGE
- SAFETY

Evaluation Case는 특정 테스트 자재에 Runtime 로직을 의존시키지 않으며, 실제 DB Fixture를 동적으로 Resolve하여 실행합니다.

---

## 7. Accuracy Evaluation

Agent가 Ground Truth에 맞게 요청을 처리하는지 검증합니다.

평가 지표:

- Intent Accuracy
- Route Accuracy
- Tool Selection Accuracy
- Tool Argument Accuracy

`v3.1.0` 최종 결과:

| Metric | Result |
|---|---:|
| Intent Accuracy | **100.00% (58/58)** |
| Route Accuracy | **100.00% (58/58)** |
| Tool Selection Accuracy | **100.00% (58/58)** |
| Tool Argument Accuracy | **100.00% (39/39)** |

> 위 100%는 현재 정의된 50 Case / 58 Turn Ground Truth Dataset에 대한 결과이며, 모든 가능한 사용자 질문에서 항상 100% 정확하다는 의미는 아닙니다.

---

## 8. Safety / Workflow / Hallucination Evaluation

Agent가 실제 업무 데이터를 안전하게 처리하는지 Runtime Evidence 기반으로 검증합니다.

현재 Safety Assertions:

- `READ_ONLY`
- `NO_REQUEST_CREATE_DURING_ANALYSIS`
- `NO_PRODUCTION_WRITE_DURING_ANALYSIS`
- `NO_PLANT_GUESS`
- `NO_TARGET_GUESS`
- `FAIL_CANNOT_APPLY`
- `FINAL_APPROVAL_REQUIRED`
- `CONDITIONAL_NO_SCORE`
- `NO_HALLUCINATED_ENTITY`
- `CONTEXT_MUST_NOT_MUTATE_WORKFLOW`

`v3.1.0` 최종 결과:

```text
Safety Assertions : 143 / 143 PASS
Safety Violations : 0
Evidence Complete : YES
```

Safety Evaluation은 LLM Judge가 아니라 실제 Tool Result, Workflow State, DB Fingerprint를 기반으로 deterministic하게 검증합니다.

---

## 9. Performance Evaluation

성능평가는 실제 58 Turn Runtime Observation을 기준으로 측정합니다.

`v3.1.0` Release 기준 최종 결과:

| Metric | Result |
|---|---:|
| P95 Latency | **2,484.66 ms** |
| 5초 이내 처리 | **96.55%** |
| LLM-free Turns | **86.21%** |
| P95 Release 기준 | **≤ 5,000 ms** |
| Performance Gate | **PASS** |

### P95

P95는 전체 요청의 약 95%가 해당 시간 이내에 처리된다는 의미입니다.

현재:

```text
P95 = 2.48초
```

따라서 현재 개발단계의 `P95 ≤ 5초` 목표를 만족합니다.

### LLM-free

```text
LLM-free Turns = 86.21%
```

현재 Evaluation Turn의 86.21%는 Azure OpenAI 호출 없이 처리되었습니다.

이는 Fast Path와 Deterministic Macro를 통해 단순하거나 확정적인 업무는 LLM 없이 처리하고, Reasoning이 필요한 요청에서만 LLM을 사용하기 때문입니다.

---

## 10. v3.1.0 Release Gate

Agent Evaluation 결과를 통합하여 Release 가능 여부를 자동 판정합니다.

Release Gate 항목:

```text
Accuracy Complete
Intent Accuracy
Route Accuracy
Tool Selection Accuracy
Tool Argument Accuracy
Performance Complete
P95 Latency
Safety Observation Complete
Safety Evidence Complete
Safety Assertions
Full Regression
Same Observation Run
```

최종 결과:

```text
Regression Test     : 490 passed / 0 failed

Accuracy
  Intent            : 100%
  Route             : 100%
  Tool Selection    : 100%
  Tool Argument     : 100%

Performance
  P95               : 2.48 sec
  <= 5 sec          : 96.55%
  LLM-free          : 86.21%

Safety
  Assertions        : 143 / 143
  Violations        : 0

RELEASE GATE        : PASS
```

---

## 11. Evaluation 실행 방법

### 전체 Runtime Observation 수집

```bash
python -m scripts.collect_agent_evaluation_observations --all
```

### Accuracy

```bash
python -m scripts.evaluate_agent_accuracy --require-complete
```

### Failure Triage

```bash
python -m scripts.triage_agent_accuracy --show-all
```

### Performance

```bash
python -m scripts.evaluate_agent_performance --require-complete
```

### Safety

```bash
python -m scripts.evaluate_agent_safety --require-complete
```

### 최종 Release Gate

```bash
python -m scripts.finalize_agent_evaluation
```

전체 pytest까지 포함한 최종 Release Gate:

```bash
python -m scripts.finalize_agent_evaluation --run-tests --require-tests
```

---

## 12. 일반 테스트

전체 Regression Test:

```bash
python -m scripts.run_tests
```

특정 테스트:

```bash
python -m scripts.run_tests tests/test_file.py -q
```

테스트는 격리된 SQLite DB를 사용하며 Runtime DB를 테스트 데이터로 덮어쓰지 않습니다.

---

## 13. 실행

Python 가상환경 구성 후 의존성을 설치합니다.

```bash
pip install -r requirements.txt
```

Streamlit 실행:

```bash
streamlit run app/streamlit_app.py
```

환경변수에는 Azure OpenAI 설정과 SQLite 경로를 구성합니다.

예:

```text
BOM_SQLITE_PATH=data/display_bom.db
```

API Key 등 Secret 값은 Git Repository에 Commit하지 않습니다.

### SQLite DB 역할 분리

- `data/display_bom_seed.db`: Git에서 추적하는 Canonical Seed DB
- `data/display_bom.db`: Seed에서 재생성하는 Runtime / Demo DB
- `.pytest_tmp_runtime/test_display_bom.db`: pytest 실행 중에만 사용하는 Disposable Test DB

Runtime/Test DB는 Canonical Seed와 현재 Schema를 기준으로 재생성하며 테스트가 Runtime DB를 변경하지 않습니다.

---

## 14. Evaluation Baseline 운영 원칙

`v3.1.0`의 50 Case / 58 Turn Dataset은 이후 버전의 **Regression Evaluation Baseline**으로 유지합니다.

새로운 기능을 추가하더라도 기존 Case는 삭제하지 않습니다.

예:

```text
v3.1.0
Agent 기본 Evaluation
50 Cases / 58 Turns

        +

v3.2.0
RAG Evaluation Cases

        ↓

기존 Agent 기능 + RAG 기능 전체 재검증
```

추가 개발 후 다음 수치가 변하면 원인을 확인해야 합니다.

- Accuracy 하락
- Safety Assertion 실패
- P95 증가
- LLM Call 증가
- Token 증가
- FAST / MACRO / AGENT Path 비율 변화
- 기존 pytest Regression 실패

Safety 또는 Hard Gate가 깨진 경우 Release하지 않습니다.

---

## 15. 다음 개발 로드맵

### v3.2.0 - RAG

목표:

- BOM 업무 규정 검색
- 설계변경 기준 문서 검색
- 과거 업무 사례 검색
- Chunking
- Embedding
- Vector Search
- 근거 기반 답변
- 출처 / Evidence 표시
- 문서에 없는 내용의 Hallucination 통제
- RAG Evaluation Case 추가

RAG는 업무 판정 Authority가 아니라 **참고 Evidence** 역할로 사용합니다.

### v3.3.0 - Read-only Text-to-SQL

목표:

- 자연어 기반 BOM Analytics
- SELECT only
- 허용 Table / View 제한
- Query Validation
- Result Limit
- Timeout
- DDL / DML 금지
- Production DB 변경 금지
- Text-to-SQL Evaluation Case 추가

---

## 16. 향후 Enterprise 확장

- PLM 연계
- ERP 연계
- MES 연계
- SQLite → Oracle / PostgreSQL
- SSO / 인증
- RBAC
- Audit Log
- Monitoring
- Security
- 운영 장애 대응
- Enterprise DB Transaction / Recovery

---

## 17. 개발 원칙

- Single Agent 구조를 유지합니다.
- Multi-Agent를 기본 구조로 사용하지 않습니다.
- Agent의 업무 기능은 MCP Tool을 경유합니다.
- MCP Server에 Business Logic을 중복 구현하지 않습니다.
- 실제 업무 판단은 Domain Service / Rule이 수행합니다.
- Repository / DB가 업무 Evidence와 상태의 Source of Truth입니다.
- LLM은 Tool Evidence 없이 원가, 재고, 공급사, 납기, 적합성을 생성하지 않습니다.
- Production BOM 변경은 반드시 승인 Workflow를 통과해야 합니다.
- 신규 기능 개발 후 기존 Agent Evaluation Baseline을 반드시 재검증합니다.
