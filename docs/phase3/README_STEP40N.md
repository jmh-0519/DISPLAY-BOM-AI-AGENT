# STEP40-N – Reason Policy Consistency & Tool Loop Guard

## 목적

1. REPLACE / ADD / DELETE / QUANTITY_CHANGE의 사유 처리 정책을 동일하게 맞춘다.
2. 사용자가 별도 업무 사유를 명시하지 않아도 설계변경 Analysis를 진행한다.
3. MCP Tool RuntimeError가 발생하면 동일 Tool을 반복 호출하지 않고 최초 오류에서 현재 Agent 턴을 종료한다.

## 변경사항

### 1. 기본 사유 `USER_REQUEST`

사용자 요청에 EOL/COST/COMMONIZATION 등 등록된 사유가 포함되어 있으면 기존 Reason Metadata Resolver가 그대로 우선 처리한다.

별도 사유가 전혀 없으면 등록된 중립 사유를 사용한다.

- reason_code: `USER_REQUEST`
- 한글명: `사용자 요청`
- source: `SYSTEM_DEFAULT`

적용 범위:

- MATERIAL: REPLACE / ADD / DELETE / QUANTITY_CHANGE
- ASSY: REPLACE / ADD / DELETE / QUANTITY_CHANGE

### 2. 별도 사유 질문 제거

다음 요청은 사유를 다시 질문하지 않고 바로 Analysis로 진행한다.

- `... 자재를 제거하자.`
- `... 자재 수량을 2로 바꾸자.`

명시적인 사유가 있으면 해당 사유가 USER_REQUEST보다 우선한다.

### 3. Tool Loop Guard

MCP Tool이 RuntimeError로 실패한 경우:

- 실제 오류 메시지를 `state.error`에 보존
- 동일 Agent 턴의 후속 Tool 실행 중지
- MCP Tool Node에서 Agent Node로 재진입하지 않음
- `MAX_TOOL_STEPS=5`까지 같은 Tool을 반복하지 않음
- 사용자 화면에는 최초 Tool 오류를 바로 반환

전이 상태 오류(INVALID_PHASE3_TRANSITION)는 기존처럼 Tool Observation으로 남겨 Agent가 정상 복구할 수 있다.

## 기존 DB 적용

```powershell
python -m scripts.apply_step40n_reason_policy_patch --database data/display_bom.db
python -m scripts.verify_phase3_business_sample --database data/display_bom.db
python -m scripts.run_tests -q
```

`apply_step40n_reason_policy_patch`는 idempotent이며 기존 Request/이력/BOM 데이터는 삭제하지 않는다.

## 검증

현재 실행 가능한 Service/DB 테스트:

- 32 passed
- Business Sample verify PASS
- 변경 Python 파일 compile PASS

현재 실행 환경에는 `langchain_core`가 없어 Agent/LangGraph pytest는 collection할 수 없었으며, 해당 테스트 파일의 Python compile은 PASS했다.
