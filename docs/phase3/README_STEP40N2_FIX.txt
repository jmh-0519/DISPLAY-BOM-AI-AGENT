Display BOM AI Agent - STEP40-N2 Tool Error Visibility Fix
Date: 2026-08-21

Purpose
- Fix blank assistant response when analyze_design_change_candidates fails.
- Preserve STEP40-N no-retry behavior.
- Do not modify DB, seed data, Streamlit menu, or production history.

Root cause
1. The requested item 0001-310701 is no longer active in LTA650HR11-001 / P03 as of 2026-08-21.
   It was previously applied as DELETE, so candidate analysis correctly raises a source-BOM validation error.
2. run_with_artifacts() treated the failed analyze_design_change_candidates ToolMessage as a successful
   candidate-panel trigger and set suppress_answer=True. The terminal error answer was therefore hidden.

Changed files
- agents/bom_agent_graph.py
  * A terminal Tool error always keeps the answer visible.
  * A failed candidate-analysis tool does not render an empty Phase3 panel.
- services/phase3_workflow_service.py
  * Distinguishes no active source BOM relation from ambiguous multiple relations.
- tests/test_bom_agent_graph.py
  * Adds regression coverage for visible terminal candidate-analysis errors.

Validation in packaging environment
- python -m py_compile: PASS
- python -m scripts.verify_phase3_business_sample --database data/display_bom.db: PASS
  business_bom_rows = 50 (preserved)
- python -m scripts.run_tests tests/test_step40_action_coverage.py -q: 5 passed
- test_bom_agent_graph.py could not be executed in the packaging container because langchain_core is not installed there.
  Run it in the project's .venv environment.

Recommended local verification
1) python -m scripts.run_tests tests/test_bom_agent_graph.py -q
2) python -m scripts.run_tests -q
3) Retry the same Streamlit question.

Expected behavior for the same question
- No blank assistant bubble.
- No repeated same-tool loop.
- A visible message explains that 0001-310701 is not in the current active P03 BOM.
- No Design Change Request is created and Production BOM is not modified.
