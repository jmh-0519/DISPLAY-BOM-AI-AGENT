# STEP40-I — Design Change History Search / Paging / Click Detail UX

## Scope

This patch updates only the active Phase3 design-change history UI and its UI contract test.

### Changes

1. Search conditions are separated into four independent fields:
   - Request ID: text input
   - Product: text input
   - PLANT: text input
   - Workflow status: selectbox
2. The history list is paginated at 15 requests per page.
3. Request ID is rendered as a blue, bold clickable link.
4. The old `상세 조회할 Request` selectbox is removed.
5. Clicking a Request ID reloads the same history page with `history_request_id` and renders the shared Request detail below the list.
6. Existing Korean status labels, Action before/after styling, and completion-report regeneration remain unchanged.

## Files

- `app/views/design_change_history_page.py`
- `tests/test_step40i_history_ux.py`

## Validation

```powershell
python -m scripts.run_tests -q
```

No DB migration or seed command is required.
