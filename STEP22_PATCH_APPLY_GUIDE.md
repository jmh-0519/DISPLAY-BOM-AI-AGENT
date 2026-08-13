# Display BOM AI Agent STEP21 → STEP22 패치 적용 안내

## 반영 기능

1. AI 품평 체크리스트 화면에서 원시 JSON 출력을 제거했습니다.
2. 품평 종합평가와 항목별 `PASS / 사용자 확인 필요 / FAIL` 결과를 업무용 표로 표시합니다.
3. 좌측 `설계변경` 메뉴를 제거하고 관련 서비스와 공용 UI는 Workflow 내부에서 계속 사용합니다.
4. BOM 조회 결과를 Excel로 생성하는 MCP Tool `export_bom_excel`을 추가했습니다.
5. 설계변경 완료 Word 문서를 생성하는 MCP Tool `export_design_change_report`를 추가했습니다.
6. 두 다운로드 기능은 MCP를 통해 실행되며 Production BOM을 변경하지 않습니다.
7. BOM 조회조건이 바뀌면 이전 다운로드 데이터를 폐기하고, 화면 행 수와 Excel 행 수가 다르면 다운로드를 차단합니다.

## 수정 파일 12개

- `README.md`
- `app/streamlit_app.py`
- `app/views/ai_design_change_workflow_page.py`
- `app/views/bom_query_page.py`
- `docs/PROJECT_STATUS.md`
- `mcp_client/client.py`
- `mcp_server/server.py`
- `requirements.txt`
- `services/ai_design_change_workflow_service.py`
- `skills/bom-design-change/SKILL.md`
- `skills/bom-query/SKILL.md`
- `tests/test_ai_design_change_workflow.py`

## 신규 파일 3개

- `mcp_server/capabilities/download.py`
- `services/bom_excel_export_service.py`
- `tests/test_download_capability.py`

## 적용 방법

1. 기존 STEP21 프로젝트를 백업합니다.
2. 이 ZIP을 STEP21 프로젝트 루트에 압축 해제합니다.
3. 같은 경로의 기존 파일은 덮어씁니다.
4. 가상환경을 활성화한 뒤 의존성을 갱신합니다.

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app/streamlit_app.py
```

`requirements.txt`에는 Excel 생성을 위한 `openpyxl`이 추가됩니다. Word 생성을 위한 `python-docx`도 계속 필요합니다.

## 삭제 권장 파일과 폴더

다음은 소스가 아니라 Python/테스트/화면 검증 과정에서 생성된 임시 산출물입니다. 프로젝트에 존재하면 삭제해도 됩니다.

- `.pytest_cache/` 전체
- 모든 `__pycache__/` 폴더
- 모든 `*.pyc` 파일
- `qa/` 전체
- `qa_step22/` 전체

STEP21의 업무 소스 중 반드시 삭제해야 하는 파일은 없습니다. `app/views/design_change_page.py`도 메뉴에서는 제거됐지만 Workflow가 공용 결과 UI를 사용하므로 현재 단계에서는 삭제하지 마십시오.

## 패치 제외 파일

다음 파일은 로컬 환경·백업 데이터이며 STEP22 기능 변경과 무관하므로 패치에 포함하지 않았습니다.

- `.env`
- `data/*.zip`
- 생성된 `.xlsx`, `.docx`, `.png`, `.pdf` QA 파일

## 검증 결과

```text
246 passed
```
