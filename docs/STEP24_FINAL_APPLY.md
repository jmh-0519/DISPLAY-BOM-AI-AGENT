# STEP24-E2B + F 최종 적용

```powershell
Copy-Item data/display_bom.db data/display_bom.before_step24_final.db
python -m scripts.migrate_workflow_to_sqlite --data-dir data --database data/display_bom.db --report data/workflow_migration_report.json
python -m pytest -q
$env:BOM_STORAGE_MODE="SQLITE"
$env:BOM_SQLITE_PATH="data/display_bom.db"
streamlit run app/streamlit_app.py
```

Workflow 이관은 빈 업무 테이블에 한 번만 실행됩니다. 두 번째 실행은 중복을 차단합니다.

과거 `MOD → VERSION` 가상 관계 변경 2건은 현재 VERSION Root 구조로 임의 변환하지 않고
Item 미이관 경고로 남기며 Production Apply에서 차단합니다.
