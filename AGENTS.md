# Display BOM AI Agent Development Instructions

## Project

Display BOM AI Agent Phase3 v3.0.0 개발 프로젝트다.

현재 개발 브랜치:

- feature/phase3-agent

현재 Runtime Architecture:

Streamlit
→ Single LangGraph Agent
→ MCP Client
→ Display BOM MCP Server
→ Domain Services
→ SQLite Repositories
→ data/display_bom.db

## Architecture Rules

- Single Agent 구조를 유지한다.
- 멀티 Agent로 변경하지 않는다.
- Agent 업무 기능은 Display BOM MCP Tool을 경유한다.
- MCP Server에 Business Logic을 중복 구현하지 않는다.
- 업무 로직은 Domain Service에서 처리한다.
- Service는 Repository를 통해서만 SQLite에 접근한다.
- CSV Runtime, CSV Repository, CSV fallback을 추가하지 않는다.
- 기존 display_bom.db의 데이터 아키텍처 연속성을 유지한다.
- phase3_* 형태의 임시 테이블을 만들지 않는다.

## Production Safety

- 사용자 승인 전 Production BOM을 변경하지 않는다.
- 후보 분석과 설계변경 Workflow를 분리한다. 사용자가 후보를 선택하기 전에는 Workflow를 시작하지 않는다.
- 공용 ASSY 내부 BOM 변경은 영향 모델/Spec 추가 승인을 받은 뒤에만 Workflow를 시작한다.
- 최종 Apply 승인은 별도로 유지한다.
- 복수 Action Apply는 하나의 Transaction으로 처리한다.
- 하나의 Action이라도 FAIL이면 전체 Apply를 차단한다.
- Apply 실패 시 전체 변경을 Rollback한다.
- FAIL은 예외승인할 수 없다.
- CONDITIONAL만 사유를 기록하고 예외승인할 수 있다.
- 공용 ASSY의 BOM은 모델별로 복제하지 않는다.
- 공용 ASSY 변경 시 영향 모델 전체를 분석한다.

## LLM and Rule Responsibilities

Phase3에서는:

- LLM은 자연어 의도, 대상, 변경 사유, Action과 평가 항목을 식별한다.
- Service와 Rule Engine은 검증, 점수, 등급과 상태를 계산한다.
- LLM이 원가, 재고, 납기, 품질과 적합성을 임의로 생성하지 않는다.
- Tool 결과에 없는 데이터를 만들어내지 않는다.

## Langfuse

- Langfuse는 관찰·평가 계층으로만 사용한다.
- Langfuse 장애가 업무 Workflow를 중단시키면 안 된다.
- Langfuse가 SQLite 업무 이력을 대체하지 않는다.
- API Key와 Secret Key를 코드·테스트·Git에 포함하지 않는다.
- 실제 BOM, 원가, 공급사 등 민감정보는 Trace에 그대로 저장하지 않는다.
- 테스트에서는 Langfuse 네트워크 전송을 Mock 또는 비활성화한다.

## Development Workflow

작업 순서:

1. 관련 코드를 먼저 분석한다.
2. 구현 전 변경 계획과 영향 파일을 제시한다.
3. 승인된 범위만 수정한다.
4. 관련 단위 테스트를 추가한다.
5. 관련 테스트를 실행한다.
6. 전체 회귀 테스트를 실행한다.
7. git diff와 변경 파일을 요약한다.

## File Safety

- 사용자 변경사항을 임의로 삭제하지 않는다.
- 기존 테스트를 삭제하거나 통과 기준을 완화하지 않는다.
- .env, API Key, .venv, cache와 임시 파일을 Commit하지 않는다.
- data/display_bom.db를 테스트 데이터로 덮어쓰지 않는다.
- 테스트는 임시 SQLite DB를 사용한다.

## Completion Criteria

다음 조건을 모두 충족해야 완료로 판단한다.

- 요청한 기능 구현
- 관련 테스트 통과
- 전체 회귀 테스트 통과
- 승인 Gate와 Transaction 안전성 유지
- 변경 파일 및 테스트 결과 보고

## Test Execution

- 모든 pytest는 프로젝트 루트에서 실행한다.
- pytest를 직접 실행하지 않고 다음 공통 Runner를 사용한다.

  `python -m scripts.run_tests`

- 특정 테스트도 같은 Runner에 테스트 경로와 옵션을 전달한다.

  `python -m scripts.run_tests tests/test_file.py -v`

- 공통 Runner는 TEMP, TMP, TMPDIR와 pytest basetemp를
  프로젝트 내부 `.pytest_tmp`로 설정한다.
- 테스트를 위해 사용자 Temp 디렉터리나 프로젝트 외부 경로의
  접근 권한을 요청하지 않는다.
- 테스트 중 Langfuse 네트워크 전송은 비활성화한다.
- 권한 오류가 발생해도 Sandbox 권한 확대를 요청하지 말고
  공통 Runner 사용 여부를 먼저 확인한다.