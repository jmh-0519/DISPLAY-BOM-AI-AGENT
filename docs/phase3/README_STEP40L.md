# STEP40-L — Nested Master Sidebar Navigation

## Goal
Render the sidebar as a tree-style navigation:

- Agent 채팅
- Master 조회
  - BOM
  - 모델
  - 자재
- 설계변경 이력
- Phase3 Rule / History

The Master parent remains selected while one child view is selected. The child menu is visually indented and does not repeat a second `Master 조회` section label.

## Changed files
- `app/streamlit_app.py`
- `tests/test_step40k_history_master_navigation.py`
- `tests/test_step40j_master_reverse_bom.py`

## Verification
```powershell
python -m scripts.run_tests -q
```
