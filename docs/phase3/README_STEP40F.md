# STEP40-F - ADD Duplicate Candidate Guard / Preview Error UX

## Changes
- ADD candidate analysis checks the exact active BOM relation by PLANT + Parent + Child + Location + effective date.
- An already-active ADD candidate is marked FAIL during Analysis and cannot be ranked/selected as an addable candidate.
- Candidate decision reason explains that the item already exists in the target BOM relation.
- Preview errors no longer bubble to a Streamlit traceback. The current Request detail remains visible and a business error message is shown.
- User-confirmed Production E-BOM Apply warning text is preserved.

## Important
An already-created Request that selected an invalid duplicate ADD candidate is not rewritten automatically. Start a new Analysis after applying this patch; the duplicate candidate will then be excluded from selectable candidates.

## Validation
- `pytest -q tests/test_step40_action_coverage.py` -> 4 passed in the build environment.
- Python compile passed for changed files.
