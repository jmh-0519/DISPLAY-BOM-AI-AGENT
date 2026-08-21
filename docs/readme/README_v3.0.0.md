# Display BOM AI Agent v3.0.0

> Azure OpenAI + LangGraph + MCP 기반의 Single AI Agent로 Display BOM 설계변경 업무를 분석하고, 근거를 제시하며, 사용자 승인 후 Production E-BOM까지 안전하게 적용하는 프로젝트입니다.

**v3.0.0은 2026-08-21 기준 Phase3 개발 기준선(Current Development Baseline)입니다.**  
현재 Single-Action Coverage는 마무리 단계이며, STEP40 Multi-Action + COMMON 최종 Acceptance와 STEP41~43 후속 개발은 계속 진행합니다.

---

## 1. 프로젝트 목표

이 프로젝트의 우선순위는 특정 BOM 업무 규칙을 하드코딩하는 것이 아니라, 실제 업무를 수행할 수 있는 **AI Agent Engineering 구조를 설계하고 단계적으로 고도화하는 것**입니다.

초기부터 다음 방향을 유지했습니다.

- **Single Agent** 구조 유지
- Azure OpenAI가 자연어 의도와 업무 대상을 이해
- LangGraph로 Agent 실행 흐름과 상태를 제어
- MCP를 Agent와 업무 기능 사이의 표준 Tool Interface로 사용
- 업무 검증과 계산은 LLM이 임의 생성하지 않고 Service / Rule Engine이 수행
- Repository를 통해 SQLite에 접근
- Analysis와 실제 Design Change Request를 분리
- Human-in-the-loop 승인 후에만 Production BOM 변경
- 복수 Action은 Atomic Transaction으로 Apply / Rollback
- Agent의 Tool Call과 실행 상태를 관찰하고 평가 가능한 구조로 발전

---

## 2. AI Agent 개발 단계

### Phase1 / v1.0.0 – Tool-Using Agent MVP

첫 단계의 목표는 **LLM이 단순 Q&A를 넘어 실제 업무 Tool을 선택하고 호출할 수 있는 Agent 구조**를 만드는 것이었습니다.

주요 구현:

- Azure OpenAI 기반 BOM Agent
- LangGraph 기반 Agent → Tool → Agent 흐름
- Display BOM MCP Server
- BOM / 자재 / 제품 조회 Tool
- 설계변경 후보 분석
- 사용자 승인 기반 적용
- Streamlit Agent Chat UI
- Word / Excel 결과물 생성
- 기본 Human-in-the-loop 구조

이 단계에서 자연어 요청을 Tool 실행으로 연결하는 **Agent MVP**를 확보했습니다.

---

### Phase2 / v2.0.0 – Reliable Agent Runtime

Phase2의 목표는 Agent 기능을 늘리는 것이 아니라 **Agent가 실제 업무 데이터를 안정적으로 읽고 변경할 수 있는 실행 기반**을 만드는 것이었습니다.

주요 구현:

- CSV Runtime 제거
- SQLite Only Runtime 전환
- Repository / Service 계층 정리
- Database Unification
- Unit of Work / Transaction 구조
- Production BOM Apply 안전성 강화
- Atomic Apply / Rollback 기반 마련
- PLANT / BOM / MATERIAL / PRODUCT 데이터 모델 확장
- 테스트 DB와 Runtime DB Lifecycle 분리
- 특정 테스트 코드나 Scenario에 의존하지 않는 일반화 원칙 강화

Phase2 이후 Runtime Architecture는 다음 구조를 기본으로 합니다.

```text
Streamlit
    ↓
Single LangGraph BOM Agent
    ↓
MCP Client
    ↓
Display BOM MCP Server
    ↓
Domain Services / Rule Engine
    ↓
Repository / Unit of Work
    ↓
SQLite
```

---

### Phase3 / v3.0.0 – Stateful / Evidence-Driven Agent

Phase3의 목표는 Tool을 한 번 호출하는 Agent에서 발전해, **업무 상태를 유지하고 근거를 제시하며 여러 단계의 설계변경을 끝까지 수행하는 Agent**를 만드는 것입니다.

현재까지 다음 Agent Engineering 요소를 개발했습니다.

#### Planning / Intent Resolution

- 자연어 요청에서 PLANT / Target / Action / Reason 식별
- PLANT가 없으면 실제 DB에서 대상이 존재하는 PLANT만 조회해 사용자가 선택
- 사용자가 코드를 다시 입력하지 않고 선택 후 원래 요청을 계속 수행
- 명시적인 EOL / COST / COMMONIZATION 등의 Reason을 해석
- 사유가 없으면 중립 Reason `USER_REQUEST`를 시스템적으로 사용

#### Persistent Analysis Session

설계변경 분석과 실제 Request를 분리했습니다.

```text
Natural Language Request
→ Analysis Session
→ Candidate / Validation / Revalidation
→ Candidate Confirmation
→ COMMON Impact Confirmation
→ User "설계변경 진행" Approval
→ Design Change Request 최초 생성
```

Analysis 도중에는 `change_requests`에 실제 설계변경 Request를 생성하지 않습니다.

#### Candidate / Evidence 기반 판단

- Rule 기반 후보 평가
- Attribute / Supplier / Inventory Evidence
- PASS / CONDITIONAL / FAIL 상태
- 후보 전체 비교와 Ranking
- 후보 선택 후 반복 재검증
- 재검증 Before / After Evidence 누적
- FAIL은 Apply 금지
- CONDITIONAL은 사유 기반 예외승인 가능

#### Explainability

Agent가 단순히 후보 코드만 보여주는 것이 아니라 다음 근거를 사용자에게 설명할 수 있도록 확장했습니다.

- 기술 Rule / Spec
- 공급사
- 원가
- 재고
- BOM Quantity
- COMMON 영향
- 후보 선정 근거
- Preview / Apply 결과

LLM은 Tool Result에 없는 값을 임의 생성하지 않습니다.

#### Action Coverage

Phase3 설계변경 Action은 다음 4종을 지원합니다.

| Action | 의미 |
|---|---|
| REPLACE | 기존 MATERIAL / ASSY 교체 |
| ADD | 신규 MATERIAL / ASSY 추가 |
| DELETE | 기존 MATERIAL / ASSY 삭제 |
| QUANTITY_CHANGE | BOM QUANTITY 변경 |

수량 검증은 생산계획 수요량이 아니라 **BOM의 QUANTITY 자체**를 사용합니다.

```text
REPLACE         → 현재 BOM QUANTITY
ADD             → 추가할 BOM QUANTITY
DELETE          → 기존 BOM QUANTITY
QUANTITY_CHANGE → 현재 BOM QUANTITY vs 변경 후 BOM QUANTITY
```

#### COMMON Impact

공용 MATERIAL / ASSY 변경은 하나의 모델만 보고 적용하지 않습니다.

- 실제 영향받는 상위 MODEL 조회
- COMMON 영향 목록 확인
- 영향 모델의 변경 전 / 후 Spec 확인
- 추가 사용자 승인 Gate
- 공용 ASSY BOM을 모델별로 복제하지 않음

#### Request Gate / Human Approval

활성 Workflow:

```text
자연어 요청
→ Analysis Session
→ 후보 탐색 / 평가
→ 필요 시 반복 재검증
→ 후보 확정
→ COMMON 영향 확인
→ 사용자 "설계변경 진행" 승인
→ Design Change Request 생성
→ Preview
→ 최종 Apply 승인
→ Production E-BOM Atomic Apply
→ Word 완료보고서
→ 종료
```

승인 전에는 Production BOM을 변경하지 않습니다.

#### Atomic Apply / Rollback

- 여러 Action은 하나의 Transaction으로 Apply
- 하나라도 FAIL이면 전체 Apply 차단
- Apply 중 한 Action이라도 실패하면 전체 Rollback
- Production BOM 변경 결과와 Request 이력을 연결

#### Tool Retry Loop Guard

STEP40-N에서 Agent가 동일 Tool 오류를 무한 재호출하는 문제를 방지했습니다.

- RuntimeError 발생 시 실제 오류를 `state.error`에 보존
- 동일 Agent Turn의 후속 Tool 실행 중단
- 동일 Tool + 동일 Arguments의 무의미한 반복 방지
- 업무 Validation Error를 사용자에게 즉시 표시
- 일시적 오류와 업무 오류를 구분할 수 있는 기반 마련

STEP40-N2에서는 실패한 Candidate Analysis Tool 결과가 Streamlit에서 빈 답변으로 숨겨지는 문제를 수정했습니다.

---

## 3. Master / History / Reporting

Agent Workflow를 지원하기 위해 다음 조회와 이력 기능을 함께 제공합니다.

### Master 조회

- 정방향 BOM 조회
- 자재 Where-used / 역방향 BOM
- 모델 상세조회
- 자재 상세조회
- MATERIAL → 상위 ASSY → 최상위 MODEL 추적

### 설계변경 이력

- Request ID / 제품 / PLANT 검색
- 업무상태 Filter
- Paging
- Request 상세조회
- 변경 전 / 후 비교
- Agent Chat과 History UI 분리

### Word 완료보고서

DB Evidence를 기반으로 완료보고서를 생성합니다.

- 완료 요약
- 설계변경 개요
- 변경 전 / 후
- Reason / Evidence
- 전체 후보 및 최종 후보 선정 근거
- 기술 Rule / Spec 검증
- 공급사 / 원가
- BOM Quantity / 재고
- COMMON 영향
- 승인 / Preview
- Production Apply 결과
- 최종 결론

보고서 DOCX 원본을 영구 보관하지 않고, 설계변경 이력의 DB Evidence를 이용해 필요할 때 다시 생성합니다.

---

## 4. Observability

Langfuse는 업무 DB가 아니라 **Agent 관찰 / 평가 계층**으로 사용합니다.

관찰 대상 예시:

```text
User Request
→ LangGraph Agent
→ Azure OpenAI
→ MCP Tool Call
→ Tool Result / Error
→ Agent Response
```

원칙:

- Langfuse 장애가 실제 업무 Workflow를 중단시키지 않음
- SQLite 업무 이력을 Langfuse로 대체하지 않음
- API Key / Secret Key를 Git에 포함하지 않음
- 민감한 실제 BOM / 원가 / 공급사 데이터의 Trace 저장 최소화

---

## 5. Runtime / Technology Stack

- Python 3.12
- Azure OpenAI
- LangGraph
- MCP
- Streamlit
- SQLite
- python-docx
- pytest
- Langfuse

Runtime DB:

```text
data/display_bom.db
```

Test / Baseline DB는 Runtime DB와 별도로 관리합니다.

> `*.db`, `.env`, API Key, `.venv`, cache, log 파일은 Git Commit 대상이 아닙니다.

---

## 6. 개발 원칙

### Agent Architecture

- Single Agent 유지
- Multi-Agent로 변경하지 않음
- Agent 업무 기능은 MCP Tool을 경유
- MCP Server에 Business Logic 중복 구현 금지
- Business Logic은 Domain Service
- SQLite 접근은 Repository를 통해 수행

### Generalization

- 특정 테스트 MATERIAL / MODEL / Scenario ID로 Runtime 분기 금지
- 테스트 데이터는 Runtime 로직 기준으로 사용하지 않음
- DB 데이터를 동적으로 판단
- 업무 Scenario는 Acceptance Coverage이지 Runtime 조건이 아님

### Production Safety

- Analysis와 실제 Request 분리
- 승인 전 Production BOM 변경 금지
- COMMON 영향 확인
- FAIL Apply 금지
- 최종 Apply 승인 분리
- Atomic Transaction
- 실패 시 Rollback
- 기존 설계변경 이력 DB를 임의 초기화하지 않음

---

## 7. 현재 STEP40 상태

STEP40의 목표는 Phase3 Action Coverage 완성입니다.

### Single Action

| Action | 현재 상태 |
|---|---|
| REPLACE | E2E 완료 |
| ADD | E2E 완료 |
| DELETE | E2E 완료 |
| QUANTITY_CHANGE | STEP40-N/N1/N2 적용 후 실제 Streamlit 최종 확인 단계 |

### STEP40 종료 전에 남은 Acceptance

- Multi-Action 자연어 분리
- 하나의 Analysis Session에 복수 Action 유지
- Action별 독립 PASS / CONDITIONAL / FAIL 평가
- COMMON 영향 분석
- 하나의 Request로 Commit
- 통합 Preview
- Atomic Apply
- 부분 실패 시 전체 Rollback
- Word 보고서에 전체 Action 기록

이 Acceptance까지 통과한 뒤 STEP40 전체 완료로 판단합니다.

---

## 8. v3.0.0 이후 계속 진행할 Phase3 작업

### STEP41 – Decision Trace / Learning JSONL

LLM의 숨겨진 Chain-of-Thought가 아니라 **업무적으로 관찰 가능한 Agent Decision Event**를 저장합니다.

대상:

- 사용자 원문
- Intent / Planning
- Tool Call / Result
- Candidate 전체
- Rule / Attribute / Supplier / Inventory Evidence
- 사용자 후보 선택 / 반려
- 재검증 Before / After
- COMMON 영향
- Request Commit
- Preview / Approval
- Apply / Rollback
- 완료 Outcome

목적:

- Agent Debugging
- Agent Evaluation
- Tool 선택 오류 분석
- Ranking 개선
- 향후 Learning Dataset 기반

### STEP42 – 10 Scenario Final Acceptance

대표 업무 10개를 Runtime 하드코딩 없이 실제 자연어 E2E로 검증합니다.

1. EOL
2. 공급중단
3. 납기
4. 원가절감
5. 재고
6. 품질
7. CUSTOMER_SPEC / ADD
8. 환경규제
9. COMMON + DELETE
10. ASSY + QUANTITY_CHANGE / Multi-Action

### STEP43 – Phase3 Final Release 정리

- 전체 pytest
- Business DB Verify
- 10 Scenario Acceptance
- Architecture / Workflow 최종 문서화
- Decision Trace 설명
- 알려진 제한사항
- Phase4 후보 기능 정리

---

## 9. Phase3 범위에서 제외한 기능

다음 기능은 현재 활성 Phase3 Workflow에 포함하지 않습니다.

- Multi-Agent
- RAG
- Text-to-SQL
- 품평회 단계

기존 품평 관련 Source / DB는 삭제하지 않고 호환성과 과거 이력용으로 보존합니다.

---

## 10. 실행

환경 설정 후:

```powershell
streamlit run app/streamlit_app.py
```

Runtime은 SQLite Only입니다.

필수 환경값은 `.env.example` 또는 프로젝트 설정을 기준으로 구성하고 실제 Secret은 Git에 Commit하지 않습니다.

---

## 11. 검증

Business DB 확인:

```powershell
python -m scripts.verify_phase3_business_sample --database data/display_bom.db
```

전체 Test:

```powershell
python -m scripts.run_tests -q
```

개별 Test도 직접 pytest를 호출하지 않고 공통 Runner를 사용합니다.

```powershell
python -m scripts.run_tests tests/test_file.py -q
```

---

## 12. Version History

| Version | 핵심 목표 |
|---|---|
| v1.0.0 | Tool-Using Agent MVP |
| v2.0.0 | SQLite 기반 Reliable Agent Runtime |
| v3.0.0 | Stateful / Evidence-Driven / Human-in-the-loop Agent 개발 기준선 |

---

## Current Architecture Summary

```text
User Natural Language
        ↓
Streamlit Agent Chat
        ↓
Single LangGraph BOM Agent
        ↓
Planning / Intent / State
        ↓
MCP Tool Call
        ↓
Display BOM MCP Server
        ↓
Domain Service / Rule Engine
        ↓
Repository / Unit of Work
        ↓
SQLite
        ↓
Evidence / Candidate / Impact
        ↓
Human Approval
        ↓
Atomic Production Apply / Rollback
        ↓
History / Word Report
```

Display BOM AI Agent는 현재 **Chatbot → Tool-Using Agent → Reliable Workflow Agent → Stateful / Evidence-Driven Agent → Multi-Action / Evaluable Agent** 순서로 발전시키고 있습니다.
