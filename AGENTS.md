# Display BOM AI Agent Development Instructions

## Project

Display BOM AI Agent `v4.0.0` 최종 Release Core 프로젝트다.

Runtime Architecture:

User
→ Streamlit
→ Domain Intent Router
→ LangGraph Gateway
→ Fast Path / Deterministic Macro / Knowledge / Text-to-SQL / Composition / Scope Conflict / Single LLM Agent
→ MCP
→ Domain Service / Rule Engine
→ Repository
→ SQLite
→ Evidence / HITL
→ Atomic Apply / Rollback

## Architecture Rules

- Single Agent 구조를 유지하며 Multi-Agent로 변경하지 않는다.
- Agent 업무 기능은 Display BOM MCP Tool boundary를 유지한다.
- MCP Server에 Business Logic을 중복 구현하지 않는다.
- Service / Rule Engine이 업무 판단 Authority이며 LLM은 업무 Rule Authority가 아니다.
- RAG는 업무 지식 Evidence를 제공하지만 PASS / CONDITIONAL / FAIL 판정 Authority가 아니다.
- Text-to-SQL은 read-only Analytics에만 사용하며 DDL / DML / Production Write를 허용하지 않는다.
- Service는 Repository를 통해서만 SQLite에 접근한다.
- Runtime DB, Canonical Seed DB, Disposable Test DB의 역할을 분리한다.
- 개발 과정의 임시 Task 이름이나 호환 구조를 Release Core Naming에 추가하지 않는다.

## Context / Ontology Rules

- Active BOM Context와 Design Change Workflow Context를 분리한다.
- BOM target은 VERSION + PLANT + Parent + Child + LOCATION edge로 식별한다.
- Analysis Session과 Design Change Request를 같은 객체로 취급하지 않는다.
- Current-turn explicit MODEL / PLANT / target은 inherited context보다 우선한다.
- READ_ONLY 요청은 Active BOM semantics를 유지한다.
- Design Change follow-up은 Workflow scope semantics를 유지한다.
- Active BOM과 Workflow scope가 충돌한 상태에서 상대 표현만으로 변경 대상을 자동 선택하지 않는다.
- 모호한 target tie / commonality tie를 임의로 collapse하지 않는다.

## Design Change Policy

- 지원 Action은 REPLACE / ADD / DELETE / QUANTITY_CHANGE다.
- Single Request / Single Action 정책을 유지한다.
- Analysis Session과 Design Change Request를 분리한다.
- 분석 중 Request를 생성하지 않고 Production BOM을 변경하지 않는다.
- 사용자의 명시적 설계변경 진행 승인 후에만 Request를 생성한다.
- 공용 ASSY/자재 영향은 Request 생성 전에 확인한다.
- 최종 Apply 승인을 별도로 유지한다.
- FAIL은 Apply 및 예외승인을 허용하지 않는다.
- CONDITIONAL만 사유가 있는 예외승인을 허용한다.
- Apply는 하나의 Transaction으로 처리하고 실패 시 전체 Rollback한다.
- ADD / DELETE 등 target이 명확하지 않은 요청은 전체 후보를 임의 평가하지 않고 재질문한다.

## LLM / Rule Responsibility

- LLM은 모호한 자연어 해석, Tool 선택, Context 기반 추론과 Evidence 설명을 담당한다.
- 명확한 조회와 명확한 Design Change 요청은 deterministic path를 우선한다.
- Service와 Rule Engine은 BOM 사실, 검증, Candidate 평가, 상태와 Apply 가능 여부를 결정한다.
- LLM이 원가, 재고, 납기, 품질, 적합성이나 Tool 결과에 없는 데이터를 생성하지 않는다.
- 불필요한 LLM Call을 추가하지 않는다.

## Production Safety

- 사용자 승인 전 Production BOM을 변경하지 않는다.
- 테스트용 특정 자재/모델을 Runtime 분기 기준으로 사용하지 않는다.
- Atomic Transaction + Rollback을 유지한다.
- Runtime DB를 테스트가 변경하지 않는다.
- Request 생성, 승인, Production BOM write 권한을 Analysis / Context / Evaluation 계층에 추가하지 않는다.

## Development / Maintenance Workflow

1. 관련 코드를 먼저 분석한다.
2. 변경 목적과 영향 범위를 확인한다.
3. 기존 정상 기능을 유지하면서 필요한 범위만 수정한다.
4. 변경영역 Targeted Test와 QUICK/CORE 등 적절한 Suite를 실행한다.
5. Release 전 `validate_evaluation_foundation`, 통합 Evaluation Gate, Full Regression, Release Freeze Gate를 실행한다.
6. git diff / staged file / local artifact를 분리해서 확인한다.
7. Release commit 이후 tag와 remote branch/tag가 동일 commit인지 확인한다.

## File / Database Safety

- 사용자 변경사항을 임의로 삭제하지 않는다.
- 테스트 통과 기준을 완화하지 않는다.
- `.env`, API Key, `.venv`, cache, local backup, evaluation runtime artifact를 Commit하지 않는다.
- `data/display_bom_seed.db`는 Canonical Seed DB로 Git 추적한다.
- `data/display_bom.db`는 Runtime/Demo DB이며 테스트가 수정하지 않는다.
- Test DB는 disposable runtime path를 사용한다.

## Test Execution

- 공통 Runner는 `python -m scripts.run_tests`를 사용한다.
- Tier는 `quick`, `core`, `evaluation`, `full`을 사용한다.
- 특정 테스트도 `python -m scripts.run_tests tests/test_file.py -q` 형태로 실행할 수 있다.

## Release Quality Baseline

`v4.0.0` Release 기준:

- Agent Evaluation: 56 Cases / 69 Turns
- Intent / Route / Tool Selection / Tool Argument Accuracy: 100%
- Planner Accuracy: 100% (6/6)
- Context Gate: 13/13
- Safety: 167/167, failed assertion 0
- P95 latency: <= 5,000ms
- RAG Retrieval Gate: PASS
- Text-to-SQL Gate: PASS
- Full Regression: PASS

`<=5s turn rate`와 `LLM-free rate`는 diagnostic metric이며 별도 release threshold로 사용하지 않는다.

## Completion Criteria

- Single Agent / Single Request / Single Action 정책 유지
- Analysis-first + HITL + Final Approval 유지
- FAIL Apply 차단 및 Atomic Rollback 유지
- Runtime / Seed / Test DB 역할 분리 유지
- Context / Ontology scope semantics 유지
- RAG / Text-to-SQL authority boundary 유지
- 관련 테스트 및 Release Gate 통과
- 개발 Task 전용 Naming / 임시 호환 코드가 Release Core에 다시 유입되지 않음
