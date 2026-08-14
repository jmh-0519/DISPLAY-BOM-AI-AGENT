# STEP25 SQLite-only 적용

이 패치는 기존 `data/display_bom.db`를 덮어쓰지 않습니다. STEP24 Workflow 이관과
303개 테스트를 완료한 프로젝트 루트에 적용합니다.

```powershell
python -m pytest tests -q
python -m scripts.verify_step25_sqlite_only
$env:BOM_SQLITE_PATH="data/display_bom.db"
streamlit run app/streamlit_app.py
```

정상 기준:

- 전체 테스트 통과
- CSV 파일과 CSV Runtime 참조 0건
- BOM 조회와 전체 설계변경 Workflow가 MCP → SQLite 경로 사용
- 미승인 Review Apply 차단
- Apply 실패 시 BOM·상태·이력 전체 Rollback
