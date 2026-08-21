# STEP40-M - QUANTITY_CHANGE Routing Completion

## Scope
- Keep the active Phase3 quantity policy as BOM `QUANTITY` only.
- Do not use production-plan demand calculations.
- Ask for a registered business reason before QUANTITY_CHANGE Analysis when the user omitted the reason.
- For name-based quantity changes, force a product BOM lookup to resolve the exact existing BOM child and continue into `analyze_design_change_candidates` in the same Agent flow.
- Do not classify read-only quantity questions such as `현재 수량이 얼마야?` as a design-change write intent.

## Files
- `agents/bom_agent_node.py`
- `tests/test_bom_agent_node.py`

## Verification in this environment
- `python -m py_compile agents/bom_agent_node.py tests/test_bom_agent_node.py` : PASS
- `python -m pytest -q tests/test_step40_action_coverage.py -k quantity` : 1 passed
- Full Agent-node pytest could not be collected here because `langchain_core` is not installed in this runtime.

## User environment
Run:

```powershell
python -m scripts.run_tests -q
```
