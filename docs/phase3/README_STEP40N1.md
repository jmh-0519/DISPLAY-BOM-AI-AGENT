# STEP40-N1 – Runtime Verification / Quantity Language / Regression Alignment

## Why this patch exists

STEP40-N introduced the neutral `USER_REQUEST` reason and MCP Tool loop guard. The first local verification exposed three follow-up issues:

1. Runtime Production E-BOM history had already grown from the original seed count (48 -> 50), while the verifier still required an exact baseline count.
2. Korean quantity-change wording `바꿔/바꿔줘` was not recognized by `_is_quantity_change_instruction` even though `바꾸` was.
3. STEP40J/K UI contract tests still expected the removed Streamlit radio/nested-column Master menu implementation.

## Changes

- `agents/bom_agent_node.py`
  - recognizes `수량을 ... 바꿔/바꿔줘` as QUANTITY_CHANGE.
  - read-only `현재 수량이 얼마야?` remains non-write intent.
- `scripts/verify_phase3_business_sample.py`
  - immutable sample/master counts remain exact.
  - `business_bom_rows` now verifies `>= 48` because successful effective-dated BOM Apply legitimately appends BOM history.
- `tests/test_step40j_master_reverse_bom.py`
- `tests/test_step40k_history_master_navigation.py`
  - align assertions with the current HTML/query-parameter Master navigation.
- `tests/test_bom_agent_node.py`
  - retains the quantity read/write language regression test.

## Existing DB

Do NOT rerun or rebuild the DB just for N1. STEP40-N's reason policy patch has already been applied and is idempotent.

Run:

```powershell
python -m scripts.verify_phase3_business_sample --database data/display_bom.db
python -m scripts.run_tests -q
```

Expected result: Business Sample verify PASS and all pytest tests PASS.

## STEP40 completion

If QUANTITY_CHANGE E2E succeeds after N1, Single-Action coverage (REPLACE / ADD / DELETE / QUANTITY_CHANGE) is complete.
The STEP40 umbrella is completed only after Multi-Action + COMMON Agent/UI E2E acceptance is also passed.
