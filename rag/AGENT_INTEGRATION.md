# RAG Agent Integration

RAG is a read-only Knowledge Evidence layer.

- `FAST_KNOWLEDGE` is admitted only for high-confidence policy/criteria/guide/spec questions.
- Design-change action directives remain in the existing Agent/Workflow path.
- `search_knowledge` is an MCP capability but is hidden from the general LLM tool catalog; the Graph invokes it deterministically.
- BOM facts, inventory, supplier facts, PASS/CONDITIONAL/FAIL and Apply authority remain in SQLite/Service/RuleEngine.
- Optional Design Change follow-up enrichment is fail-open and disabled by default. Set `RAG_DESIGN_CHANGE_EVIDENCE_ENABLED=1` only after the RAG index is built and integration checks pass.
