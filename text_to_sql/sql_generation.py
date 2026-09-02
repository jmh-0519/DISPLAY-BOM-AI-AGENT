from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from text_to_sql.schema_catalog import SqlSchemaCatalog
from text_to_sql.sql_guard import validate_read_only_sql


class SqlGenerationError(ValueError):
    """Raised when the LLM response cannot become a safe SQL generation result."""


class SqlGenerationModel(Protocol):
    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class SqlGenerationResult:
    status: str
    sql: str | None
    reason: str
    raw_response: str

    @property
    def is_sql(self) -> bool:
        return self.status == "SQL"


class AzureSqlGenerationModel:
    """Dedicated Azure OpenAI adapter for SQL generation.

    It intentionally uses the already-configured AzureOpenAIClient transport,
    but applies a SQL-specific system prompt instead of the general chat prompt.
    """

    SYSTEM_PROMPT = (
        "You are the read-only SQL generation component of Display BOM AI Agent. "
        "Generate SQL only from the trusted schema supplied by the caller. "
        "Never invent tables or columns. Never generate INSERT, UPDATE, DELETE, "
        "REPLACE, DROP, ALTER, CREATE, PRAGMA, ATTACH, transaction commands, or "
        "multiple statements. The only executable output is one SQLite SELECT "
        "statement or WITH ... SELECT statement. If the request is a write/change "
        "request, asks for workflow-managed request/approval/apply data outside "
        "the allowlisted analytics schema, or cannot be answered from the supplied "
        "schema, return UNSUPPORTED. Return JSON only and do not include markdown."
    )

    def __init__(self, azure_client) -> None:
        self.azure_client = azure_client

    def complete(self, prompt: str) -> str:
        response = self.azure_client.client.chat.completions.create(
            model=self.azure_client.settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise SqlGenerationError("Azure OpenAI returned an empty SQL generation response")
        return str(content)


def build_sql_generation_prompt(question: str, schema_context: str) -> str:
    normalized = " ".join(str(question or "").strip().split())
    if not normalized:
        raise ValueError("question must be a non-empty string")
    if not str(schema_context or "").strip():
        raise ValueError("schema_context must be non-empty")

    return f"""Convert the user's Korean or English analytics question into one read-only SQLite query.

Output contract:
{{
  "status": "SQL" | "UNSUPPORTED",
  "sql": "<single SELECT or WITH...SELECT statement>" | null,
  "reason": "<short user-safe reason, one sentence maximum>"
}}

Rules:
- Use only tables and columns listed in TRUSTED_SCHEMA.
- Never infer a hidden table or column.
- Do not modify data.
- Do not access design-change workflow/request/approval/apply/history internals.
- Do not emit more than one SQL statement.
- Prefer explicit JOIN conditions using listed foreign keys.
- Qualify selected, filtered, grouped, and ordered columns when a JOIN can make a name ambiguous.
- item_master is the global item identity/lifecycle authority for VERSION, ASSEMBLY and MATERIAL.
- item_master.item_type stored values are VERSION, ASSEMBLY and MATERIAL; the user term ASSY means ASSEMBLY, so never filter item_type='ASSY'.
- material_master.material_name is a compatibility mirror; item_master.item_name is the generic name authority.
- For questions that explicitly ask for active/current MATERIAL, ASSEMBLY or VERSION items, join the subtype master to item_master and filter item_master.active_yn='Y'.
- Do not silently add active/current filters when the user did not ask for active/current data.
- supplier_items is the only item-to-supplier relationship authority; do not infer supplier ownership from material_master.
- version_master exposes typed product attributes; use those typed columns instead of JSON extraction.
- Return the requested business dimensions and metrics. Avoid unrelated extra columns.
- Add ORDER BY when the user asks for ranking/top/bottom/high/low/many/few/short/long.
- Add LIMIT only when the user requests a limited number; runtime already caps rows.
- Use SQLite syntax.
- For a write/change request or unsupported scope, return status=UNSUPPORTED and sql=null.
- Do not answer the business question directly.
- Do not include markdown or code fences.

USER_QUESTION:
{normalized}

TRUSTED_SCHEMA:
{schema_context}
""".strip()


def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        raise SqlGenerationError("LLM response is empty")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    start = text.find("{")
    if start < 0:
        raise SqlGenerationError("LLM response does not contain a JSON object")

    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise SqlGenerationError("LLM response is not valid JSON") from exc

    if not isinstance(value, dict):
        raise SqlGenerationError("LLM response JSON must be an object")
    return value


class SqlGenerator:
    """Natural language -> structured SQL candidate.

    The LLM is only a candidate generator. validate_read_only_sql remains the
    deterministic gate before execution, and ReadOnlySqlExecutor remains the
    final SQLite authority.
    """

    def __init__(
        self,
        *,
        model: SqlGenerationModel,
        schema_catalog: SqlSchemaCatalog,
    ) -> None:
        self.model = model
        self.schema_catalog = schema_catalog

    def generate(self, question: str) -> SqlGenerationResult:
        schema_context = self.schema_catalog.to_prompt_context()
        prompt = build_sql_generation_prompt(question, schema_context)
        raw = self.model.complete(prompt)
        payload = _extract_json_object(raw)

        status = str(payload.get("status") or "").strip().upper()
        reason = " ".join(str(payload.get("reason") or "").strip().split())[:500]

        if status == "UNSUPPORTED":
            sql_value = payload.get("sql")
            if sql_value not in (None, "", "null"):
                raise SqlGenerationError("UNSUPPORTED response must not include executable SQL")
            return SqlGenerationResult(
                status="UNSUPPORTED",
                sql=None,
                reason=reason or "요청을 허용된 조회 스키마에서 안전하게 처리할 수 없습니다.",
                raw_response=raw,
            )

        if status != "SQL":
            raise SqlGenerationError("LLM response status must be SQL or UNSUPPORTED")

        sql = str(payload.get("sql") or "").strip()
        if not sql:
            raise SqlGenerationError("SQL response does not contain sql")

        validate_read_only_sql(sql)

        return SqlGenerationResult(
            status="SQL",
            sql=sql,
            reason=reason,
            raw_response=raw,
        )


__all__ = [
    "AzureSqlGenerationModel",
    "SqlGenerationError",
    "SqlGenerationModel",
    "SqlGenerationResult",
    "SqlGenerator",
    "build_sql_generation_prompt",
]
