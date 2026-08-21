# Phase3 UI Workflow 상태 동기화 수정

## 확인된 원인

Streamlit의 승인 버튼은 MCP를 직접 호출하여 SQLite 상태를 정상 갱신했지만,
채팅 메시지에 저장된 Workflow Snapshot과 LangGraph Checkpoint는 갱신하지
않았습니다. 따라서 DB는 CANDIDATE_APPROVED인데 화면은 이전
WAITING_CANDIDATE_APPROVAL을 계속 표시했습니다.

## 변경 내용

- Agent와 UI가 같은 Phase3 Tool 결과 상태 전이 함수 사용
- UI Action 성공 후 채팅 Workflow Snapshot 즉시 갱신
- UI Action 성공 후 LangGraph Checkpoint 동기화
- Streamlit rerun 후 다음 단계 버튼 자동 표시
- CONDITIONAL 후보 승인 시 예외승인 Gate 표시
- Preview, 2차 승인, Apply에도 동일 동기화 적용

## 변경 파일

- `agents/design_change_workflow_state.py`
- `agents/bom_mcp_tool_node.py`
- `agents/bom_agent_graph.py`
- `app/streamlit_app.py`
- `app/views/phase3_agent_view.py`
- `tests/test_bom_agent_graph.py`
- `tests/test_phase3_agent_view.py`
- `tests/test_phase3_mcp_agent.py`

## 적용

```powershell
Expand-Archive `
  -Path ".\PHASE3_UI_WORKFLOW_SYNC_FIX.zip" `
  -DestinationPath "C:\workspace\display-bom-ai-agent" `
  -Force
```

## 테스트

```powershell
$env:LANGFUSE_TRACING_ENABLED = "false"

python -m scripts.run_tests `
  tests/test_phase3_agent_view.py `
  tests/test_phase3_mcp_agent.py `
  tests/test_bom_agent_graph.py `
  -q

python -m scripts.run_tests

Remove-Item Env:LANGFUSE_TRACING_ENABLED
```

개발 검증 결과는 관련 테스트 19개, 전체 테스트 189개 통과입니다.

## 기능 재검증

수정 전 생성된 Streamlit Snapshot과 승인 데이터를 제거하기 위해 테스트 DB를
기준 상태로 다시 생성한 후 시나리오를 처음부터 실행합니다. `--recreate`는
사용하지 않습니다.

```powershell
$env:BOM_SQLITE_PATH = "data/phase3_business_functional_test.db"

Copy-Item `
  "data/display_bom.before_step24_final.db" `
  $env:BOM_SQLITE_PATH `
  -Force

python -m scripts.init_database --database $env:BOM_SQLITE_PATH
python -m scripts.seed_phase3_business_sample --database $env:BOM_SQLITE_PATH
python -m scripts.verify_phase3_business_sample --database $env:BOM_SQLITE_PATH
streamlit run app/streamlit_app.py
```

1차 승인 직후 정상 상태:

```text
current_step=CANDIDATE_APPROVED
candidate_approval_status=APPROVED
requires_exception=true   # 선택 후보가 CONDITIONAL인 경우
apply_status=NOT_APPLIED
```

화면에는 1차 승인 버튼 대신 CONDITIONAL 예외승인 입력 영역이 표시되어야 합니다.
