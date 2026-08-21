# STEP40-N3 – Phase3 UI / History UX 정리

## 반영 항목

1. Agent Tool 오류 표시
   - 사용자 화면에는 Tool 함수명 / `Error executing tool` / 내부 Error Code를 표시하지 않음.
   - 실제 업무 오류 메시지만 표시.
   - 원본 오류는 Graph state / observability 로그에는 그대로 유지.

2. 변경 품목 상세 Action 번호
   - 동일 Action의 변경 전/후 2개 행을 하나의 Action 셀로 세로 병합(rowspan) 표시.

3. Agent 버튼 문구
   - `Production Apply 2차 최종 승인` → `설계변경 확정`

4. Agent Apply 버튼 문구
   - `승인된 변경 전체 Apply` → `설계변경 BOM 반영`

5. 설계변경 이력 화면 용어 정리
   - 승인/적용 중심 표현을 확정/반영 중심 표현으로 변경.

6. 후보 승인 컬럼
   - `후보 승인` → `변경자재 확정`
   - `승인 완료` → `확정 완료`

7. 최종 승인 컬럼
   - `최종 승인` → `설계변경 확정`
   - `승인 완료` → `확정완료`

8. E-BOM 적용 컬럼
   - `E-BOM 적용` → `BOM 반영`
   - `적용 완료` → `반영 완료`
   - `미적용` → `미반영`

9. 설계변경 이력에서 진행 재개
   - Request 상세 조회 시 현재 상태에 따라 다음 단계 버튼 제공.
   - `CANDIDATE_APPROVED` → `통합 영향 Preview 생성`
   - `WAITING_FINAL_APPROVAL` → `설계변경 확정`
   - `FINAL_APPROVED` → `설계변경 BOM 반영`
   - UI에서 Repository/SQLite를 직접 접근하지 않고 기존 MCP Client를 통해 진행.
   - `get_change_request_result`에 재개에 필요한 `preview_id`, `final_approval_id`만 추가 노출.

## 수정 파일

- `agents/bom_agent_graph.py`
- `app/views/design_change_history_page.py`
- `app/views/phase3_agent_view.py`
- `services/phase3_workflow_service.py`
- `tests/test_bom_agent_graph.py`
- `tests/test_step40i_history_ux.py`

## 수정하지 않은 항목

- `app/streamlit_app.py`
- Production DB / Seed DB
- Design Change Request/Action 데이터
- Repository schema
- Apply transaction / rollback 로직

## 확인 결과

현재 패치 제작 환경에서:

- Python compile: PASS
- `verify_phase3_business_sample`: PASS (`business_bom_rows: 50`)
- `tests/test_step40i_history_ux.py`: 7 passed
- `tests/test_step40_action_coverage.py`: 5 passed
- History resume용 `final_approval_id` 조회: 별도 복사 DB에서 PASS

전체 pytest는 패치 제작 환경에 Streamlit/LangChain runtime dependency가 없어 실행할 수 없으므로,
프로젝트 `.venv`에서 아래 명령으로 최종 확인한다.

```powershell
python -m scripts.verify_phase3_business_sample --database data/display_bom.db
python -m scripts.run_tests -q
```
