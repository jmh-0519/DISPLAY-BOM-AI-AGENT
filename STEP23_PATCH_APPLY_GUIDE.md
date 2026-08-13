# Display BOM AI Agent STEP22 → STEP23 패치 적용 안내

## 적용 순서

1. 기존 STEP22 프로젝트 폴더를 백업합니다.
2. 패치 ZIP을 프로젝트 루트에 풉니다.
3. 같은 경로의 수정 파일은 덮어쓰고 신규 파일은 추가합니다.
4. 가상환경에서 `python -m pip install -r requirements.txt`를 실행합니다.
5. `python -m pytest -q`를 실행합니다. 정상 예상 결과는 `251 passed`입니다.
6. `python -m streamlit run app/streamlit_app.py`로 실행합니다.

## 수정 파일 7개

- `README.md`
- `docs/PROJECT_STATUS.md`
- `app/streamlit_app.py`
- `agents/bom_agent_graph.py`
- `mcp_client/client.py`
- `mcp_server/server.py`
- `skills/bom-design-change/SKILL.md`

## 신규 파일 6개

- `app/views/design_change_history_page.py`
- `app/views/bom_review_history_page.py`
- `services/workflow_history_repository.py`
- `mcp_server/capabilities/history.py`
- `tests/test_workflow_history.py`
- `tests/test_streamlit_download_rendering.py`

## 삭제 항목

업무 소스 삭제 대상은 없습니다. `.pytest_cache/`, 모든 `__pycache__/`, `*.pyc`, `qa/`, `qa_step22/`는 실행·검증 산출물이므로 프로젝트에 존재하면 삭제해도 됩니다.

## 기능 확인

- Agent 채팅에서 Word 보고서와 BOM Excel 요청 후 실제 다운로드 버튼 확인
- 설계변경 이력 메뉴에서 목록, 필터, 상세, 보고서 재다운로드 확인
- 품평회 이력 메뉴에서 종합판정과 체크리스트 상세 확인
- 조회·다운로드 전후 `data/bom.csv` 미변경 확인
