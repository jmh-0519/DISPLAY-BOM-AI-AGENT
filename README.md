# Display BOM AI Agent

Azure OpenAI, LangGraph, MCP, Streamlit으로 구성한 **단일 BOM AI Agent 학습 프로젝트**입니다.

`v1.0.0`은 CSV 기반 샘플 데이터를 사용하여 제품·자재·BOM 조회부터 설계변경 분석, Review BOM, AI 품평, 사용자 승인과 Production E-BOM 반영까지 End-to-End로 구현한 1차 MVP입니다.

핵심 목표는 기존 BOM 시스템 전체를 재구현하는 것이 아니라, 설계변경 분석과 Rule 기반 품평 체크리스트를 AI Agent가 자동화하고 사용자가 보고서를 확인한 뒤 양산 E-BOM 반영을 최종 승인하도록 만드는 것입니다.

## 버전 정보

| 항목 | 내용 |
| --- | --- |
| 버전 | `v1.0.0` |
| 개발 단계 | `STEP23 - 1차 MVP 완료` |
| Runtime 저장소 | CSV |
| Agent 구조 | Single Agent |
| 주요 UI | Streamlit Agent 채팅·BOM 조회·AI 설계변경 Workflow |
| 회귀 테스트 | 251개 자동화 테스트 통과 |

## 실행

### 1. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. 패키지 설치

```powershell
pip install -r requirements.txt
```

### 3. Azure OpenAI 환경설정

`.env.example`을 복사하여 `.env` 파일을 생성한 뒤 Azure OpenAI 설정을 입력합니다.

```text
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
AZURE_OPENAI_API_VERSION=...
```

`.env`와 API Key는 배포물 및 Git에 포함하지 않습니다.

### 4. Streamlit 실행

```powershell
streamlit run app/streamlit_app.py
```

## 핵심 Workflow

```text
자연어 설계변경 요청
  → 제품·기존 자재·신규 자재 식별
  → 설계변경 분석 및 PASS/CONDITIONAL/FAIL 판정
  → 변경 요청과 변경 예정 BOM 생성
  → Review BOM 생성
  → Rule 기반 AI 품평 체크리스트 자동검증
  → 적용 전 Word 보고서 생성·다운로드
  → 사용자 최종 승인
  → Production E-BOM 반영
  → 설계변경·품평 이력 저장
```

AI 분석이 완료됐다는 이유만으로 Production BOM을 변경하지 않습니다. 반드시 Review BOM, AI 품평과 사용자의 명시적인 최종 승인을 거쳐야 합니다.

## 주요 기능

### 제품·자재·BOM 조회

- 제품 목록 및 제품 검색
- 자재 목록 및 자재 검색
- 계층형 BOM 조회
- 자연어 조회 Query Normalization
- BOM 조회 결과 Excel 다운로드

### AI 설계변경 Workflow

- REPLACE 설계변경 분석
- Compatibility와 Rule 기반 `PASS / CONDITIONAL / FAIL` 판정
- 변경 예정 BOM Preview와 Revision 생성
- 변경 요청 및 BOM Snapshot 저장
- Review BOM 생성과 Revision 관리
- Rule 기반 AI 품평 자동검증
- 품평 결과와 세부 근거 저장
- 적용 전 Word 보고서 생성·다운로드
- 사용자 승인 후 Production E-BOM 반영
- E-BOM Effective Date와 변경 이력 저장

### 이력과 산출물

- 설계변경 이력 목록·상세 조회
- 품평회 이력 목록·상세 체크리스트 조회
- Agent 채팅에서 Word·Excel 실제 다운로드
- CSV 기반 Workflow 공통 이력 Repository

## Architecture

```text
Streamlit
    ↓
Single LangGraph Agent
    ├─ BOM 업무 Skill
    ├─ Planning / Tool Calling
    ├─ Conversation Memory
    └─ Human-in-the-loop
    ↓
MCP Client
    ↓
Display BOM MCP Server
    ↓
Domain Services / Rule Engine
    ↓
CSV Sample Data / Workflow History Repository
```

### 구성요소별 역할

- **Single Azure BOM Agent**: 사용자 의도 해석, 실행계획, Tool 선택, Workflow Memory와 결과 설명
- **BOM 업무 Skill**: BOM 조회 및 설계변경 실행 순서와 안전 규칙
- **Display BOM MCP Server**: 조회·분석·Review·품평·보고서·최종 반영 Capability 제공
- **Service Layer**: BOM 조회, 변경 분석, Rule 검증, Review BOM, 보고서와 최종 Apply
- **CSV Sample Data**: 학습 프로젝트용 E-BOM, 기준정보 및 Workflow 이력
- **Streamlit**: Agent 채팅, BOM 조회, AI 설계변경 Workflow와 이력 화면

## MCP Capability

| 영역 | MCP Tool |
| --- | --- |
| 조회 | `get_bom`, `list_products`, `search_product`, `list_materials`, `search_material` |
| 분석 | `analyze_design_change`, `create_ai_change_request` |
| Review BOM | `create_review_bom` |
| AI 품평 | `run_ai_bom_review` |
| 보고서 | `generate_design_change_report` |
| 최종 반영 | `apply_reviewed_bom` |
| 다운로드 | `export_bom_excel`, `export_design_change_report` |

Agent와 Streamlit Workflow는 MCP Capability를 통해 동일한 업무 기능을 사용합니다.

## Production E-BOM 쓰기 경계

`apply_reviewed_bom`만 Production 데이터인 `data/bom.csv`를 변경합니다.

다른 Tool은 다음 데이터만 생성하거나 조회합니다.

- 설계변경 요청
- 변경 예정 BOM
- Review BOM
- AI 품평 결과
- 보고서 데이터
- Workflow 이력

사용자 승인 전에는 Production E-BOM을 변경하지 않습니다. `FAIL` 판정 이후 Apply를 진행하지 않으며, `CONDITIONAL`은 사용자 확인이 필요합니다.

## 주요 CSV 데이터

```text
data/
├─ products.csv
├─ materials.csv
├─ material_attributes.csv
├─ suppliers.csv
├─ bom.csv
├─ bom_hierarchy.csv
├─ compatibility.csv
├─ rules.csv
├─ change_bom.csv
├─ change_bom_item.csv
├─ change_bom_detail.csv
├─ review_bom.csv
├─ review_bom_detail.csv
├─ review_bom_check.csv
├─ review_checklist.csv
└─ change_history.csv
```

CSV는 `v1.0.0`의 Runtime 저장소입니다. 직접 파일을 수정하기보다 Service와 Repository 경로를 통해 조회·저장합니다.

## 테스트

전체 자동화 테스트를 실행합니다.

```powershell
python -m pytest tests -q
```

`v1.0.0` 완료 기준은 251개 자동화 회귀 테스트 통과입니다.

주요 검증 영역:

- 제품·자재·BOM 조회
- 자연어 Query Normalization
- Agent Tool 선택과 LangGraph 분기
- MCP 조회 및 설계변경 Capability
- 설계변경 상태와 Rule 판정
- Review BOM과 AI 품평
- 승인 없는 Apply 차단
- Production E-BOM 적용과 이력
- Word·Excel 산출물 생성과 Streamlit 다운로드

## 프로젝트 구조

```text
display-bom-ai-agent/
├─ agents/          # Single Agent와 LangGraph Workflow
├─ app/             # Streamlit UI
├─ core/            # Azure OpenAI 설정과 공통 구성
├─ data/            # CSV 기준정보·BOM·Workflow 데이터
├─ docs/            # 아키텍처·상태·목표 Workflow 문서
├─ mcp_client/      # Display BOM MCP Client
├─ mcp_server/      # MCP Server와 Capability
├─ models/          # Tool Request·Response 모델
├─ services/        # Domain Service와 Rule Engine
├─ skills/          # BOM 업무 Skill
├─ tests/           # 자동화 테스트
├─ tools/           # 초기 Tool 계층
├─ requirements.txt
└─ README.md
```

## v1.0.0 범위 제한

- 샘플 CSV 기반이며 실제 Windchill·PLM·ERP 연동은 구현하지 않음
- 설계변경은 REPLACE 중심
- 여러 자재·ASSY를 한 번에 변경하는 복합 트랜잭션은 미지원
- CSV 특성상 DB 수준의 FK, Transaction과 Atomic Rollback 미지원
- 비정형 고객 승인이나 공급사 협의 데이터가 없으면 자동 승인하지 않음
- 보고서는 DOCX와 Excel을 지원하며 PDF 변환은 미지원
- 사용자 인증, 권한, 전자결재와 운영 감사 기능은 미구현
- RAG와 Text-to-SQL은 미적용

## 다음 고도화 방향

v1.0.0 이후에는 기존 Agent·MCP·Service 계약을 유지하면서 저장소를 SQLite로 전환하는 것을 우선합니다.

```text
CSV 기반 MVP
  → SQLite Schema와 Repository
  → Workflow 데이터 전환
  → Transaction 기반 Production Apply
  → CSV Runtime 제거
```

SQLite 전환 이후에는 복수 자재와 Assembly 설계변경, 원가·납기·재고 영향 분석, 실제 BOM 시스템 Adapter와 LLM 학습 데이터 축적을 단계적으로 검토합니다.

## 관련 문서

- `docs/PROJECT_STATUS.md`
- `docs/TARGET_WORKFLOW.md`
- `docs/ARCHITECTURE.md`
- `data/README_DATASET.md`
- `data/README_DESIGN_CHANGE_DATA.md`

## v1.0.0 최종 정의

> CSV 기반 샘플 데이터에서 Single LangGraph Agent가 MCP Capability를 조합하여 BOM 조회와 REPLACE 설계변경 Workflow를 End-to-End로 수행하고, Rule 기반 AI 품평과 사용자 최종 승인을 거쳐 Production E-BOM을 반영하는 1차 MVP
