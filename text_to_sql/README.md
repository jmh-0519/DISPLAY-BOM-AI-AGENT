# Text-to-SQL Foundation

This package is the safety boundary for future natural-language-to-SQL support.

## Authority model

- LLM: may generate a SQL candidate later.
- `SqlSchemaCatalog`: exposes only approved business-read schema.
- `validate_read_only_sql`: rejects non-query/multi-statement input early.
- `ReadOnlySqlExecutor`: final execution authority using SQLite `mode=ro`, `query_only`, authorizer, timeout and row cap.
- SQLite: remains the factual authority.

## Initial allowlist

The first release allows 15 business-read tables covering product/BOM, material,
supplier, inventory and production-plan analysis. Workflow, approval, apply,
rule-management, reason metadata and internal/system tables are intentionally
excluded.

No Agent, MCP or LLM integration is performed in this foundation step.
