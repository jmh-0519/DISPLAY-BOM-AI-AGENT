# STEP24-D MCP 환경변수 전달 보정

## 원인

Streamlit/PowerShell Process에는 SQLite 환경변수가 설정됐지만,
MCP Client가 생성한 별도 MCP Server Process에는 해당 값이 전달되지 않았습니다.
그 결과 MCP Server가 기본 CSV Mode로 실행됐습니다.

## 변경

`mcp_client/client.py`의 `StdioServerParameters`에 현재 환경을 명시적으로
전달합니다.

```python
env=os.environ.copy()
```

## 적용 및 확인

ZIP을 프로젝트 루트에 압축 해제한 뒤 Streamlit이 실행 중이면 `Ctrl+C`로
완전히 종료합니다.

같은 PowerShell에서:

```powershell
$env:BOM_STORAGE_MODE="SQLITE"
$env:BOM_SQLITE_PATH="data/display_bom.db"
```

MCP 직접 확인:

```powershell
python -c "from mcp_client.client import DisplayBomMcpClient; r=DisplayBomMcpClient().get_bom('LTA400HR01-001','2026-08-10'); print('rows=',len(r)); print(r[0] if r else 'EMPTY')"
```

예상 결과:

```text
rows= 20
```

테스트:

```powershell
python -m pytest tests/test_repository_bom_service.py -q
python -m pytest -q
```

예상 결과는 전용 `9 passed`, 전체 `293 passed`입니다.

그 후 동일 PowerShell에서:

```powershell
streamlit run app/streamlit_app.py
```

대화를 초기화하고 `LTA400HR01-001의 BOM을 보여줘`를 다시 확인합니다.
