# T2SQL-02A — LLM SQL Generation

Scope:
- Full trusted Schema Context from T2SQL-01 allowlist
- Dedicated Azure OpenAI SQL-generation system prompt
- Structured JSON contract: SQL / UNSUPPORTED
- Deterministic SQL Guard before execution
- Existing SQLite read-only Authorizer/Executor remains final authority
- No Agent/Streamlit integration yet

Architecture:

Natural Language
  -> SqlSchemaCatalog
  -> AzureSqlGenerationModel
  -> SqlGenerator
  -> validate_read_only_sql
  -> ReadOnlySqlExecutor
  -> Result rows

The LLM never receives write authority.
