# Display BOM AI Agent

Display 제품의 BOM 조회부터 설계변경 분석, 대체 자재·ASSY 추천, 검증, 승인 및 Production E-BOM 반영까지 지원하는 **Single AI Agent** 프로젝트입니다.

현재 기준 버전은 Phase2 완료 상태인 `v2.0.0`이며, 다음 목표는 `STEP26`부터 시작하는 Phase3 `v3.0.0`입니다.

## 1. 현재 완료 상태 — Phase2 v2.0.0

Phase2에서는 CSV Runtime을 완전히 제거하고 모든 업무 데이터를 SQLite 단일 Runtime으로 전환했습니다.

```text
Streamlit
  → Single LangGraph Agent
  → MCP Client
  → Display BOM MCP Server
  → Domain Services
  → SQLite Repositories
  → data/display_bom.db
```

완료된 주요 기능:

- 제품·자재·BOM 조회 및 자연어 Query Normalization
- 설계변경 REPLACE 분석과 `PASS / CONDITIONAL / FAIL` 판정
- 변경 요청, 변경 예정 BOM, Review BOM 및 Revision 관리
- Rule·Compatibility 기반 AI 품평
- 사용자 승인 후 Production E-BOM Apply
- SQLite Transaction 기반 Atomic Apply와 실패 시 Rollback
- 설계변경·품평·적용 이력 저장 및 조회
- BOM Excel, 설계변경 Word 보고서 생성·다운로드
- Agent와 Streamlit의 MCP Tool 경유 통일
- CSV Runtime·Repository·파일·MCP 관련 코드 제거
- SQLite-only 검증 및 전체 회귀 테스트 정상 확인

Phase2 초기 방향에 포함됐던 RAG와 Text-to-SQL은 실제 적용 필요성이 낮아 구현하지 않았습니다. Phase3에서도 제외하고, Phase1~3 완료 결과를 재검증한 뒤 적용 가능한 영역을 다시 판단합니다.

## 2. Phase3 v3.0.0 목표

자연어 요청을 받은 Agent가 설계변경 사유를 파악하고, 대체 가능한 MATERIAL과 ASSY를 탐색하여 원가·납기·재고·품질·공급 안정성·규제 적합성 등을 분석합니다. 사용자가 후보와 주 공급사를 선택한 뒤 최종 Preview를 다시 승인하면 Production E-BOM까지 안전하게 반영합니다.

대표 요청:

> A모델의 C자재가 단종되어 변경해야 합니다. 변경 가능한 자재를 찾아주세요.

목표 Workflow:

```text
자연어 요청
  → 제품·BOM·변경 대상 식별
  → 변경 사유 및 복수 Action 분석
  → 대체 MATERIAL/ASSY 후보 탐색
  → Rule·속성·원가·납기·재고·품질·공급사 평가
  → 전체 적합 후보 순위와 근거 제시
  → 1차 승인: 자재 + 주 공급사 선택
  → 영향 모델·공용 ASSY·수량·비용 통합 Preview
  → 2차 승인: 최종 Apply
  → Atomic Production Apply 또는 전체 Rollback
  → 적용 이력·사후 성과·학습 데이터 저장
```

## 3. Phase3 지원 범위

### 설계변경 Action

- `REPLACE`
- `ADD`
- `DELETE`
- `QUANTITY_CHANGE`
- 공용 ASSY의 수량 변경과 ASSY 교체
- 한 요청 안의 복수 Action 조합

복수 변경은 하나의 트랜잭션으로 처리합니다. 하나의 Action이라도 `FAIL`이면 전체 Apply를 취소하며, 통과한 변경만 부분 적용하지 않습니다.

### 추천 대상과 결과

- MATERIAL과 ASSEMBLY 모두 지원
- 후보 자재별 순위와 전체 적합 후보 표시
- 자재 아래에 주 공급사와 대체 공급사 평가 표시
- 총점, `S/A/B/C` 등급, 상태, 적용 Rule과 세부 근거 제공
- `PASS`를 먼저 점수순으로 표시한 뒤 `CONDITIONAL`을 점수순으로 표시
- `FAIL`은 추천 순위에서 제외하되 실패 Rule과 제외 사유를 표시

등급 기준:

| 등급 | 점수 |
| --- | ---: |
| S | 90점 이상 |
| A | 80점 이상 |
| B | 70점 이상 |
| C | 70점 미만 |

상태와 점수는 분리합니다. `PASS / CONDITIONAL / FAIL`은 필수조건과 데이터 충족 여부이며, 점수와 등급은 후보 간 우선순위를 의미합니다.

## 4. 후보 탐색과 판정 원칙

후보 탐색 순서:

1. 등록된 대체관계
2. 동일 자재분류 및 핵심 속성 일치
3. 전체 자재의 속성 유사도

등록된 변경 사유 Rule이 있으면 Rule별 가중치를 적용합니다. Rule이 없으면 LLM이 요청 사유에 필요한 평가 항목을 선택하고, Service가 자재 속성과 업무 데이터로 단계별 검증 및 점수 계산을 수행합니다. 판단 기준이나 필수 데이터가 부족한 후보는 제거하지 않고 `CONDITIONAL`로 유지합니다.

Rule 충돌 우선순위:

```text
안전 필수조건
  → 변경 사유별 Rule
  → 공통 Rule
  → 최신 유효 Revision
```

`FAIL`은 예외승인할 수 없습니다. `CONDITIONAL`은 추가 데이터를 입력한 뒤 자동 재검증하며, 계속 조건부일 경우 사용자가 사유를 입력하여 예외승인할 수 있습니다.

## 5. Rule 관리 UI

Agent 채팅을 주 실행 화면으로 유지하고 다음 화면을 별도 메뉴로 제공합니다.

- Rule 조회·추가·Revision·비활성화
- 설계변경 및 승인·Apply 이력
- 적용 후 성과평가

Rule UI에는 사용자 권한 구분이나 관리자 비밀번호를 두지 않습니다. 모든 사용자가 Rule을 조회하고 추가할 수 있습니다.

Rule 입력 항목:

- Rule명과 설명
- 변경 사유
- 적용 대상 및 자재분류
- 필수조건 또는 평가항목
- 연산자와 기준값
- 가중치
- 유효 시작일
- Revision 및 활성 상태

기존 Rule을 물리적으로 수정·삭제하지 않습니다. 변경 시 새 Revision을 생성하거나 비활성화하며, 사용자가 명시적으로 활성화해야 적용됩니다. 활성화 시 유효 시작일은 필수입니다.

## 6. 원가·납기·재고·공급사

- Phase3 원가는 KRW 단일 통화를 사용하되 통화 필드는 확장 가능하게 설계
- 공급사별 원가, 납기, 품질등급, 공급 안정성을 평가하여 주 공급사 추천
- 자재와 주 공급사를 하나의 승인 단위로 선택
- 재고는 `공장 → 창고 → Location → 자재` 수준으로 관리
- 샘플 조직은 공장 2개, 공장별 창고 2개, 창고별 Location 2개로 구성
- 생산계획과 사용자 요청수량을 모두 지원
- 요청수량이 있으면 주 판단 기준으로 사용하고 생산계획 기준 결과도 비교 표시
- 요청에 적용일·필요수량이 없으면 현재 기준일과 최신 유효 생산계획을 자동 적용하고 가정값을 공개

## 7. 공용 ASSY와 영향 분석

동일 ASSY의 BOM은 모든 사용 모델에서 동일해야 합니다. 공용 ASSY 내부 자재 또는 구조가 변경되면 해당 ASSY를 사용하는 제품과 상위 ASSY를 재귀적으로 탐색합니다.

- 영향받는 전체 모델·ASSY와 변경 범위를 사용자에게 제공
- 모델별 ASSY 복제 방식은 사용하지 않음
- 영향 전체를 하나의 변경 묶음으로 구성
- 전체 승인 후 하나의 트랜잭션으로 Apply
- 일부 모델만 선택적으로 적용하지 않음

## 8. 10개 대표 설계변경 사례

| No. | 사례 | 주요 Action |
| ---: | --- | --- |
| 1 | 단종(EOL) 대응 | REPLACE |
| 2 | 공급사 공급중단 대응 | REPLACE |
| 3 | 납기 개선 | REPLACE |
| 4 | 원가 절감 | REPLACE |
| 5 | 재고 부족·긴급 대체 | REPLACE |
| 6 | 품질 불량 개선 | REPLACE |
| 7 | 고객 신규 사양 반영 | ADD |
| 8 | 환경·규제 대응 | REPLACE |
| 9 | 자재 공용화·공정 개선 | DELETE 또는 REPLACE |
| 10 | 공용 ASSY 핵심 변경 | QUANTITY_CHANGE 또는 ASSY REPLACE |

각 REPLACE·ADD 사례에는 5개 이상의 후보를 구성합니다. DELETE는 삭제 영향과 대안, QUANTITY_CHANGE는 수량별 원가·재고·생산 영향 대안을 제공합니다. 샘플 코드는 현재 제품·자재 코드 형식과 동일한 가상 코드로 작성합니다.

샘플데이터는 바로 DB에 넣지 않습니다. 사례별 데이터, 후보, Rule, 예상 판정과 순위를 표로 먼저 검토한 뒤 승인된 데이터만 기존 `display_bom.db`에 반영합니다.

## 9. LLM 역할과 학습 계획

### Phase3 역할 분리

Phase3의 LLM은 자연어 의도·대상·변경 사유 식별, 실행계획, 평가 항목 선택과 결과 설명을 담당합니다. 계산과 결정적 판정은 Service·Rule Engine이 수행합니다.

### Phase3에서 수집할 학습 데이터

- 사용자 자연어 원문과 정규화된 요청
- 제품·BOM·기존 자재·Action·변경 사유
- 탐색된 모든 후보와 자재·ASSY·공급사 속성
- 적용 Rule Revision, 필수조건, 세부 점수와 최종 상태
- Agent 설명과 실행계획
- 후보 선택·반려 및 예외승인 사유
- 최종 Preview와 Apply·Rollback 결과
- 적용 후 30·60·90일 원가·납기·재고·품질·불량·공급 안정성
- 사용자 사후평가

원본 이력은 SQLite에 누적하고 후속 학습용 JSONL 데이터셋 추출 기능을 제공합니다.

### Phase3 이후 추론학습

1. 데이터 정제와 개인정보·식별정보 처리
2. 요청·후보·판정·실제 성과를 연결한 학습 레코드 생성
3. Rule 판정, 사용자 선택·반려, 실제 적용 결과와 사후 성과를 결합한 정답 구성
4. 학습·검증·테스트 데이터 분리와 데이터 누수 방지
5. 적합한 학습 방식 검토 및 모델 학습
6. Rule Engine과 학습형 LLM의 Shadow 병행평가
7. 오류 유형과 잘못된 PASS를 중심으로 재학습·평가
8. 검증 데이터 정확도 90% 이상 및 안전 필수조건의 잘못된 PASS 0건 확인
9. 기준 충족 시 추천·적합성 판정을 단계적으로 LLM으로 대체

최종 학습형 LLM은 후보 탐색, 설계변경 분석, 적합성 판정, 검증 근거와 순위 생성을 수행하는 것을 목표로 합니다. 다만 후보 선택과 최종 Apply의 2회 사용자 승인은 유지합니다. BOM 무결성, 승인 확인, Atomic Transaction, Rollback과 감사이력은 LLM 학습과 무관하게 시스템에서 강제합니다.

## 10. Phase3 제외 범위

- RAG
- Text-to-SQL
- 실제 PLM·ERP·MES·SCM 연동
- 기업용 인증·RBAC·전자결재
- 학습형 LLM의 실제 운영 전환

RAG와 Text-to-SQL은 Phase1~3 결과를 재검증한 후 분명한 적용 사례가 확인될 때 별도 도입합니다.

## 11. STEP26 개발 순서

1. `STEP26-A` — Phase2 기준선·요구사항·10개 사례 확정
2. `STEP26-B` — SQLite 확장 Schema와 Repository 구현
3. `STEP26-C` — 후보 탐색·Rule Revision·점수·등급 Engine
4. `STEP26-D` — 공급사·원가·납기·재고·생산계획 평가
5. `STEP26-E` — REPLACE·ADD·DELETE·QUANTITY_CHANGE와 복수 Action Transaction
6. `STEP26-F` — 공용 ASSY 재귀 영향 분석과 통합 Preview
7. `STEP26-G` — MCP Tool 확장과 Single Agent Workflow
8. `STEP26-H` — Agent 채팅의 2회 승인과 재검증·예외승인
9. `STEP26-I` — Rule·이력·성과평가 UI와 학습 데이터·JSONL Export
10. `STEP26-J` — 10개 사례 E2E·회귀·Rollback·패키징 검증

## 12. 완료 기준

10개 대표 사례 모두 다음 전체 과정이 자동 테스트와 화면 검증을 통과해야 합니다.

```text
자연어 요청
→ 대상 식별
→ 후보 전체 탐색
→ 상태·점수·등급·Rule 근거 생성
→ 후보 및 주 공급사 선택 승인
→ 통합 영향 Preview
→ 최종 Apply 승인
→ Production E-BOM 반영
→ 실패 시 전체 Rollback
→ 변경·승인·판정·성과·학습 이력 확인
```

## 13. 실행

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Azure OpenAI 설정은 `.env.example`을 복사하여 `.env`에 입력합니다. `.env`, API Key, 가상환경, 캐시, 로컬 실행 산출물은 Git에 포함하지 않습니다.

## 14. 최종 지향점

> 축적된 설계변경 데이터로 추론학습한 Single AI Agent가 MATERIAL과 ASSY의 복합 설계변경을 분석·검증하고, 사용자 승인과 시스템 안전장치 아래 Production E-BOM에 원자적으로 반영하는 실무형 BOM AI Agent

