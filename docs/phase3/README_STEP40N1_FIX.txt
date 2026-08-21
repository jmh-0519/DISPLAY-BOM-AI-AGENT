STEP40-N1 QUANTITY_CHANGE language fix

Replace only:
  agents/bom_agent_node.py

Do NOT replace or delete data/display_bom.db.
Do NOT modify app/streamlit_app.py.

Root cause:
  Korean conjugation '바꿔/바꿔줘' does not contain the literal stem string '바꾸',
  so _is_quantity_change_instruction() returned False.

Fix:
  Add recognized write-intent variants: 바꿔, 늘려, 줄여.
  Read-only quantity questions remain non-write intent.

After copying the file, run:
  python -m scripts.verify_phase3_business_sample --database data/display_bom.db
  python -m scripts.run_tests -q

Expected based on the supplied failure:
  verify PASS
  pytest: 261 passed
