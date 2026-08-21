# STEP40-G — DELETE Intent / Session Routing / BOM-scoped Target Resolution

## Purpose
Fix DELETE requests that were incorrectly routed to a plain BOM query and then stopped.

## Behavior
- DELETE synonyms (`삭제`, `제거`, `없애`, `빼`, `제외`) enter Phase3 routing even without EOL/COST/etc.
- If product + PLANT + exact item code + registered business reason are present, force `analyze_design_change_candidates` directly.
- If DELETE target is expressed only by item name, force a product-scoped `get_bom` read first; after the BOM observation, force `analyze_design_change_candidates` instead of ending with the BOM view.
- If the DELETE action/target is clear but the business reason is missing, do not invent a reason and do not fall back to BOM display. Ask the user for the design-change reason.
- A new change instruction after `APPLIED`, `REPORT_COMPLETED`, or `BLOCKED` is routed as a fresh Analysis Session while keeping the old Request intact for history.
- Compound BOM questions containing DELETE synonyms are not normalized into a simple `BOM을 보여줘` query.

## No DB migration
This patch does not modify schema or business data.

## Verification
Run:

```powershell
python -m scripts.run_tests -q
```

Recommended UI checks:
1. `LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 제거하자.`
   - Expected: asks for change reason; must NOT render only the BOM and stop.
2. `LTA650HR11-001 모델 P03 PLANT BOM에서 0001-310701 자재를 공용화를 위해 제거하자.`
   - Expected: starts DELETE Analysis directly.
3. `LTA650HR11-001 모델 P03 PLANT BOM에서 공용화를 위해 브라켓 자재를 제거하자.`
   - Expected: BOM-scoped target resolution, then DELETE Analysis; must not stop at BOM display.
4. Repeat #2 immediately after a completed workflow.
   - Expected: starts a new Analysis Session; old Request stays only in history.
