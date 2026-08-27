# Display BOM AI Agent v3.0.0

> Azure OpenAI + LangGraph + MCP + SQLite 기반의 **Single AI Agent**로 Display BOM 조회와 자연어 설계변경 업무를 분석하고, 근거를 제시하며, 사용자 승인 후 Production E-BOM까지 안전하게 반영하는 PoC 프로젝트입니다.

`v3.0.0`은 단계적으로 확장해 온 Display BOM AI Agent의 **Core Agent 완료 버전**입니다. 현재 버전에서는 자연어 기반 BOM 조회, Context 유지, 설계변경 후보 분석, Human-in-the-Loop 승인, Preview, Atomic Apply, 이력 및 Word 완료보고서까지 End-to-End Workflow를 구현했습니다.

다음 개발은 Core 기능을 추가하는 것이 아니라, 먼저 **Agent Evaluation**으로 현재 Agent의 품질을 정량 검증한 뒤 **RAG → Text-to-SQL** 순서로 확장합니다.

---

## 1. Version Information

| 항목 | 내용 |
| --- | --- |
| Version | `v3.0.0` |
| 개발 상태 | Core BOM AI Agent 완료 |
| Agent 구조 | Single Agent |
| Runtime DB | SQLite |
| LLM | Azure OpenAI `gpt-4.1-mini` |
| Agent Framework | LangGraph |
| Tool Interface | MCP |
| UI | Streamlit |
| Test | pytest + Demo Acceptance + UI Acceptance |
| 다음 단계 | Agent Evaluation |

---

## 2. Project Goal

Display BOM AI Agent는 단순 Q&A Chatbot이 아니라 실제 BOM 업무 Workflow를 수행하는 **업무형 AI Agent**를 목표로 합니다.

핵심 원칙은 다음과 같습니다.

- 자연어 요청을 업무 Intent와 Context로 해석
- 명확한 조회는 LLM을 사용하지 않는 Fast Path로 처리
- 명확한 설계변경은 Deterministic Macro로 빠르게 실행
- 모호하거나 복잡한 요청만 LLM Agent가 Reasoning과 Tool Selection 수행
- 실제 계산과 PASS / CONDITIONAL / FAIL 판정은 Service / Rule Engine이 수행
- 모든 업무 데이터는 Repository를 통해 SQLite에서 조회
- Analysis와 실제 Design Change Request를 분리
- 사용자 명시적 승인 전에는 Production BOM을 변경하지 않음
- 최종 Apply는 SQLite Transaction 기반 Atomic Apply / Rollback으로 보호
- 모든 주요 판단과 변경 결과는 DB Evidence와 연결
- Multi-Agent가 아닌 Single Agent 구조 유지

---

## 3. Final Architecture

```text
User Natural Language
        ↓
Streamlit Agent Chat
        ↓
Domain Intent Router
        ↓
LangGraph Gateway
   ├─ Fast Path
   ├─ Deterministic Macro
   └─ Single LLM Agent
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
        ↓
Evidence / Candidate / Impact / History
        ↓
Human-in-the-Loop Approval
        ↓
Atomic Production E-BOM Apply / Rollback
```

### Hybrid Routing

#### Fast Path
단순 조회는 불필요한 LLM 호출 없이 즉시 처리합니다.

- 제품 BOM 조회
- ASSY BOM 조회
- Where-used
- 현재 BOM 수량 조회
- 명확한 Master 조회

#### Deterministic Macro
의도와 대상이 명확한 설계변경 요청은 Agent Tool Loop를 반복하지 않고 업무 Macro가 필요한 Service를 직접 실행합니다.

```text
Natural Language
→ Intent / Context Resolution
→ Deterministic Analysis Macro
→ MCP / Service
→ Compact Analysis Evidence
→ Dedicated Finalizer
```

#### Single LLM Agent
의도가 불명확하거나 추가 Reasoning이 필요한 요청만 Single Agent가 MCP Tool을 선택하여 처리합니다.

---

## 4. Core BOM Capability

### BOM / Master Query

- 제품 BOM 조회
- ASSY BOM 조회
- 제품 검색
- 자재 검색
- 자재 상세조회
- 모델 상세조회
- Where-used 역방향 BOM 조회
- PLANT 조회
- MATERIAL → ASSY → 상위 MODEL 영향 추적

BOM 주요 속성:

- PLANT
- VERSION
- PARENT
- CHILD
- LOCATION
- QUANTITY
- MATERIAL
- ASSY

Display BOM 계층은 다음 구조를 기본으로 합니다.

```text
VERSION
→ FA
→ OLB
→ CP
→ BIN
→ LC
→ CF / TFT
```

공용 MATERIAL과 공용 ASSY를 지원합니다.

---

## 5. Natural-Language Design Change

지원 Action:

| Action | 설명 |
| --- | --- |
| `REPLACE` | 기존 MATERIAL / ASSY 교체 |
| `ADD` | 신규 MATERIAL / ASSY 추가 |
| `DELETE` | 기존 MATERIAL / ASSY 삭제 |
| `QUANTITY_CHANGE` | BOM Quantity 변경 |

현재 `v3.0.0`은 **하나의 Request에서 하나의 Action을 처리하는 Single-Action Workflow**를 기준으로 합니다.

### Final Workflow

```text
자연어 설계변경 요청
→ Intent / Context 분석
→ 대상 MODEL / PLANT / MATERIAL / ASSY 식별
→ Analysis Session 생성
→ 후보 탐색
→ 기술 / 공급 / 재고 / Rule 평가
→ PASS / CONDITIONAL / FAIL
→ 필요 시 후보 재검증 / 비교 / 설명
→ 사용자 후보 선택
→ [해당 분석안으로 설계변경 진행]
   ├─ 선택 분석안 확정
   ├─ COMMON 영향 계산
   ├─ Design Change Request 생성
   └─ 적용 Preview 자동 생성
→ 적용 전 최종 확인
→ [설계변경 확정]
→ [설계변경 BOM 반영]
→ Production E-BOM Atomic Apply
→ BOM 재조회
→ 설계변경 이력
→ Word 완료보고서
```

### Request Boundary

Analysis 단계에서는 실제 `Design Change Request`를 생성하지 않습니다.

사용자가 **`해당 분석안으로 설계변경 진행`**을 명시적으로 승인한 시점에만 Request와 적용 Preview가 생성됩니다. 최종 승인 전에는 Production E-BOM이 변경되지 않습니다.

---

## 6. Candidate Evaluation Policy

후보 평가는 숫자 Ranking보다 **업무 적합성 Gate**를 먼저 적용합니다.

```text
Target Resolution
→ Technical Gate
→ Rule Gate
→ Supplier / Inventory / Cost Evaluation
→ Final Status
→ Ranking
```

- `PASS`
  - 필수 기술 / Rule 조건을 충족
  - 추천 Ranking 대상
- `CONDITIONAL`
  - 필수 Evidence가 부족하거나 추가 확인 필요
  - 추천 점수 / 추천등급 / 순위를 산출하지 않고 `평가 보류`
- `FAIL`
  - 필수조건 위반
  - 추천 Ranking에서 제외
  - Apply 불가

추천 Score와 Rank는 **기술 / Rule Gate를 통과한 PASS 후보끼리만 비교**합니다.

```text
PASS         → Score / Recommendation Grade / Rank
CONDITIONAL  → 평가 보류 / - / -
FAIL         → 검토 제외 / - / -
```

공급사 Master의 `품질등급`은 추천등급과 다른 데이터이므로 UI에서는 **공급사 품질등급**으로 구분합니다.

---

## 7. ADD Target Resolution

ADD는 추가할 대상이 명확해야 Analysis를 시작합니다.

예:

```text
"LTA400HR01-001 P01 모델에 자재를 추가하고 싶어"
```

위 요청처럼 자재가 특정되지 않으면 전체 MATERIAL을 임의 추천하지 않습니다.

```text
ADD 요청
→ 대상 특정 여부 확인
   ├─ 특정됨 → Analysis
   └─ 미특정 → 사용자 재질문
               → Analysis 미생성
               → Request 미생성
```

사용자는 자재코드, 자재명, 품목군, ASSY로 대상을 구체화할 수 있습니다.

예:

```text
"FILM을 추가하고 싶어"
"POLARIZER 자재를 추가해줘"
"0001-200007을 추가해줘"
```

품목군이 지정되면 해당 품목군과 관련된 후보만 탐색합니다.

---

## 8. Active Context / PLANT Resolution

대화 Context를 이용하여 자연스러운 후속질문을 지원합니다.

```text
"LTA400HR01-001 P01 모델의 BOM을 조회해줘"
→ "SEALANT 수량은 몇이야?"
```

직전 BOM Context가 유효한 경우 MODEL / PLANT를 다시 입력하지 않아도 조회할 수 있습니다.

단, 사용자가 새로운 MODEL을 명시하면 기존 PLANT를 임의로 승계하지 않습니다. DB에서 실제 대상이 존재하는 PLANT를 조회하여 버튼으로 제시하고, 사용자가 선택한 뒤 원래 요청을 계속 수행합니다.

---

## 9. COMMON Impact

공용 MATERIAL / ASSY의 변경은 단일 MODEL만 보고 적용하지 않습니다.

- 실제 영향받는 상위 MODEL 조회
- 공용 영향 범위 계산
- 변경 전 / 후 영향 정보 제공
- 최종 확인 화면에 COMMON 영향 통합
- Production Apply 전 영향 범위 재검증

공용 영향은 별도 Preview 버튼으로 분리하지 않고, `해당 분석안으로 설계변경 진행` 시 생성되는 **적용 전 최종 확인**에 포함합니다.

---

## 10. Human-in-the-Loop / Production Safety

### Safety Boundary

- Analysis 중 Request 생성 금지
- Analysis 중 Production BOM 변경 금지
- FAIL 후보 Apply 금지
- 대상 미해결 ADD Analysis 금지
- Request / Preview 생성 후 최종 승인 전 Apply 금지
- Apply 직전 현재 BOM 상태 / Revision 재검증
- SQLite Transaction 기반 Atomic Apply
- 오류 발생 시 전체 Rollback
- Backend RuntimeError를 그대로 사용자에게 노출하지 않도록 UI 오류 처리

### Apply Flow

```text
Analysis
→ User Proceed Approval
→ Request + Preview
→ Final Confirmation
→ Final Approval
→ Production Apply
```

Preview 생성 시점의 적용 대상과 현재 Production BOM 상태가 달라지면 Apply를 차단할 수 있도록 Revision / Snapshot 검증 구조를 유지합니다.

---

## 11. History / Completion Report

### Design Change History

주요 항목:

- Request ID
- PLANT
- 제품
- Action
- 변경 사유
- 변경 전 / 후
- 변경자재 확정
- 설계변경 확정
- BOM 반영
- 업무 상태
- 요청자
- 생성시각

SQLite `CURRENT_TIMESTAMP`는 UTC이므로 UI에서는 KST로 변환하여 표시합니다.

### Word Completion Report

Word 완료보고서는 설계변경 이력의 DB Evidence를 기준으로 재생성합니다.

- 설계변경 개요
- 대상 MODEL / PLANT
- 변경 전 / 후
- 후보 평가 결과
- 최종 후보 선정 근거
- 기술 / 공급 / 재고 / Rule Evidence
- COMMON 영향
- 승인 정보
- Production Apply 결과
- 최종 결론

DOCX 자체를 영구적인 Source of Truth로 사용하지 않고 DB Evidence를 기준으로 필요할 때 다시 생성합니다.

---

## 12. Performance Optimization

주요 최적화:

- Fast Path
- Domain Intent Router
- Deterministic Macro Dispatch
- Dedicated Analysis Finalizer
- Tool Catalog 재전달 최소화
- Compact Analysis Evidence
- Context Compaction
- 동일 Tool Retry Loop 방지
- Node / Tool / LLM Latency Profiling

대표 측정 사례:

```text
복잡한 분석 초기 응답
약 15초 수준
→ 최적화 후 약 4초대 수준

Azure LLM Input
약 11,290 tokens/call
→ 약 1,379 tokens/call
```

위 수치는 전체 요청의 고정 KPI가 아니라 **최적화 과정에서 확인한 대표 측정 사례**입니다. 정식 Average / P95 / Prompt Budget은 다음 단계의 Agent Evaluation에서 자동 측정합니다.

---

## 13. Verification

### Regression Test

```powershell
python -m scripts.run_tests
```

Release Gate:

```text
0 FAIL
```

Final Fix 적용 전 확인된 기준선에서는 `389 passed`를 확인했으며 이후 ADD Target Resolution / Candidate Ranking 관련 신규 테스트를 추가했습니다. 최종 `v3.0.0` Commit 직전 전체 Runner를 다시 실행하여 최종 Test Count를 확정합니다.

### Demo Acceptance

```powershell
python -m scripts.run_phase3_demo_acceptance
```

최근 확인 결과:

```text
TOTAL: 10/10 PASS
```

### UI Acceptance

실제 Streamlit UI에서 다음을 확인했습니다.

- BOM 조회
- Active Context 후속질문
- 새 MODEL + PLANT 누락 처리
- REPLACE E2E
- ADD 대상 재질문 / 품목군 필터링
- DELETE Apply
- QUANTITY_CHANGE Rule 판정
- Request + Preview 자동 생성
- 적용 전 최종 확인
- 설계변경 확정
- Production E-BOM 반영
- BOM 재조회
- 설계변경 이력
- Word 완료보고서
- Legacy Rule 관리 UI 제거

---

## 14. Runtime / Technology Stack

- Python 3.12
- Azure OpenAI
- LangGraph
- LangChain
- MCP
- Streamlit
- SQLite
- Pydantic
- python-docx
- pytest

Runtime DB:

```text
data/display_bom.db
```

Secret과 로컬 실행 산출물은 Git에 포함하지 않습니다.

```text
.env
API Key
.venv/
__pycache__/
*.db
.perf/
local log / cache
```

---

## 15. Project Structure

```text
display-bom-ai-agent/
├─ agents/          # Intent Router, Gateway, Fast Path, Macro, Single Agent
├─ app/             # Streamlit UI
├─ core/            # Azure OpenAI, Profiler, 공통 Utility
├─ data/            # SQLite Runtime / Sample Data
├─ mcp_client/      # Display BOM MCP Client
├─ mcp_server/      # MCP Server / Capability / Schema
├─ models/          # Request / Response Model
├─ repositories/    # SQLite Repository / Transaction
├─ scripts/         # Test / Demo Acceptance / Profiling
├─ services/        # Domain Service / Rule / Recommendation
├─ skills/          # BOM 업무 Skill
├─ tests/           # 자동화 회귀 테스트
├─ requirements.txt
└─ README.md
```

---

## 16. Development Principles

### Single Agent
- Multi-Agent로 확장하지 않음
- 하나의 BOM AI Agent를 중심으로 Workflow 관리
- Tool / Service / Repository 역할 분리

### Generalization
- 특정 MODEL / MATERIAL / Test Scenario ID 기반 Runtime 분기 금지
- 테스트 데이터는 Runtime 업무 기준으로 사용하지 않음
- DB 데이터와 Context를 동적으로 해석
- Scenario는 Acceptance Coverage로만 사용

### Evidence First
- LLM이 Tool Result에 없는 수치나 Spec을 임의 생성하지 않음
- 계산과 판정은 Service / Rule Engine
- LLM은 모호한 요청 해석, Reasoning, Tool Selection, 결과 설명 담당
- DB / Rule / Supplier / Inventory를 실제 Evidence로 사용

### Safe Production Apply
- Analysis / Request 분리
- Human-in-the-Loop
- Preview
- Revision 재검증
- Atomic Transaction
- Rollback
- History / Report Evidence 일치

---

## 17. v3.0.0 Scope Boundary

현재 Core Release에는 다음을 포함하지 않습니다.

- Multi-Agent
- Multi-Action Design Change
- RAG
- Text-to-SQL
- 실제 PLM / ERP / MES 연동
- Enterprise 인증 / SSO
- RBAC
- 전자결재
- 운영 Monitoring / Audit / Security 통합

현재 프로젝트의 설계변경 기준은 **Single Request / Single Action**입니다.

---

## 18. Next Development

### 18.1 Agent Evaluation

Core Agent 완료 후 가장 먼저 Agent 품질을 자동 평가합니다.

통합 대상:

- pytest
- Demo Acceptance
- Latency Profiling
- Prompt Budget Profiling
- Tool Call Validation
- UI Acceptance

목표 지표:

```text
Intent Routing Accuracy
Tool Selection Accuracy
Workflow Success Rate
Evidence / Hallucination
Average Response Time
Median Response Time
P95 Response Time
Prompt Token Budget
LLM Call Count
Safety Boundary
Regression Pass Rate
Demo Acceptance
UI Acceptance
```

추가로 Hybrid Architecture 효율을 확인합니다.

```text
Fast Path Rate
Deterministic Macro Rate
LLM Agent Rate
```

목표는 다음과 같이 설명할 수 있는 Evaluation Report를 만드는 것입니다.

> AI Agent의 Intent, Tool Selection, Workflow, Evidence Grounding, Latency, Prompt Budget과 Safety Boundary를 정량적으로 평가했다.

### 18.2 RAG

Agent Evaluation 완료 후 RAG를 추가합니다.

목표 예:

```text
"SEALANT 변경 관련 업무 규정을 알려줘"
"비슷한 과거 설계변경 사례가 있어?"
```

RAG는 실제 PASS / FAIL Authority가 아니라 규정 / 사례 참고 Evidence를 제공합니다.

```text
Rule / DB / Service = 실제 업무 판단
RAG                 = 규정 / 사례 참고 Evidence
```

### 18.3 Text-to-SQL

RAG 이후 Read-only Analytics 기능으로 추가합니다.

목표 예:

```text
"P01의 설계변경 완료 건수는?"
"FAIL 후보가 많이 발생한 자재는?"
"최근 설계변경 이력을 요약해줘"
```

안전 정책:

- SELECT Only
- 허용 Table / View 제한
- DDL / DML 금지
- Query Validation
- Result Limit
- Timeout
- Production DB 변경 금지

### 18.4 Enterprise Integration Roadmap

#### PLM
- Product
- Material
- BOM
- Design Change

#### ERP
- Supplier
- Purchase
- Cost
- Inventory

#### MES
- Production Apply
- Manufacturing Impact
- Production Status

#### Enterprise Platform
- SQLite → Oracle / PostgreSQL
- SSO
- Authentication
- RBAC
- Approval Authority
- Audit Log
- Tool / Data Access Control
- Monitoring
- 장애 대응
- Security

---

## 19. Version History

| Version | 핵심 내용 |
| --- | --- |
| `v1.0.0` | CSV 기반 Tool-Using Agent MVP |
| `v2.0.0` | SQLite 기반 Reliable Agent Runtime |
| `v3.0.0` | Hybrid Routing + Stateful / Evidence-Driven + Human-in-the-Loop E2E BOM Agent |

---

## 20. v3.0.0 Final Definition

> **Display BOM AI Agent v3.0.0**은 자연어 요청을 Domain Intent와 Context로 해석하고, Fast Path / Deterministic Macro / Single LLM Agent를 조합하여 BOM 조회와 Single-Action 설계변경을 수행하며, DB·Rule·Supplier·Inventory Evidence 기반 후보 평가, Human-in-the-Loop 승인, Preview, Revision 재검증, Atomic Production E-BOM Apply, History와 Word 완료보고서까지 End-to-End로 처리하는 Core AI Agent 완료 버전입니다.

다음 단계에서는 이 Core Agent를 정량 평가하는 **Agent Evaluation**을 수행한 뒤 RAG와 Read-only Text-to-SQL을 순차적으로 확장합니다.
