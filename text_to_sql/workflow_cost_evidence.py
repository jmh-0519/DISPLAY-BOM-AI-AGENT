"""Deterministic read-only BOM cost evidence for workflow target handoff.

General ad-hoc analytics continues to use the LLM Text-to-SQL generator.
This module is intentionally narrower: once an analytics result may become a
Design Change source target, BOM reachability and cost-basis selection must not
depend on free-form generated SQL.
"""

from __future__ import annotations

from datetime import date
import re

from text_to_sql.pipeline import TextToSqlPipelineResult
from text_to_sql.read_only_executor import ReadOnlySqlExecutor


class ScopedBomCostEvidenceQuery:
    """Return the highest-cost reachable MATERIAL from one VERSION/PLANT BOM.

    Cost basis is deterministic and current-date scoped:
    1. active primary supplier ``unit_price`` when available;
    2. active ``item_attribute_values.unit_cost`` fallback.

    The recursive CTE walks the full active product BOM, not only direct VERSION
    children.  The ReadOnlySqlExecutor remains the execution/safety authority.
    """

    VERSION_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
    PLANT_PATTERN = re.compile(r"^P\d{2,}$")

    def __init__(self, executor: ReadOnlySqlExecutor) -> None:
        if executor is None:
            raise ValueError("ReadOnlySqlExecutor is required")
        self.executor = executor

    def run(
        self,
        *,
        version_code: str,
        plant_code: str,
        question: str,
        as_of_date: str | None = None,
    ) -> TextToSqlPipelineResult:
        version = str(version_code or "").strip().upper()
        plant = str(plant_code or "").strip().upper()
        if self.VERSION_PATTERN.fullmatch(version) is None:
            raise ValueError("Invalid VERSION code for scoped BOM cost evidence")
        if self.PLANT_PATTERN.fullmatch(plant) is None:
            raise ValueError("Invalid PLANT code for scoped BOM cost evidence")

        effective_date = str(as_of_date or date.today().isoformat()).strip()
        try:
            date.fromisoformat(effective_date)
        except ValueError as error:
            raise ValueError("Invalid as_of_date") from error

        sql = self._sql(
            version_code=version,
            plant_code=plant,
            as_of_date=effective_date,
        )
        execution = self.executor.execute(sql)
        return TextToSqlPipelineResult(
            status="SQL",
            question=str(question or "").strip(),
            sql=sql,
            reason=(
                "Workflow target evidence uses deterministic recursive BOM SQL; "
                "no SQL-generation LLM was used."
            ),
            columns=execution.columns,
            rows=execution.rows,
            row_count=execution.row_count,
            truncated=execution.truncated,
            elapsed_ms=execution.elapsed_ms,
        )

    @classmethod
    def _sql(
        cls,
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str,
    ) -> str:
        # Inputs are strict regex/date validated above, so literal embedding is
        # deterministic and cannot introduce SQL syntax.
        return f"""
WITH RECURSIVE reachable(item_code) AS (
    SELECT '{version_code}'
    UNION
    SELECT b.child_item_code
    FROM reachable r
    JOIN bom_master b
      ON b.parent_item_code = r.item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
),
material_edges AS (
    SELECT DISTINCT
        b.parent_item_code,
        b.child_item_code,
        b.location_code
    FROM reachable r
    JOIN bom_master b
      ON b.parent_item_code = r.item_code
    JOIN item_master i
      ON i.item_code = b.child_item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND i.item_type = 'MATERIAL'
      AND i.active_yn = 'Y'
),
primary_price AS (
    SELECT
        si.item_code,
        MAX(si.unit_price) AS supplier_unit_price,
        MAX(si.currency_code) AS currency_code
    FROM supplier_items si
    JOIN supplier_master sm
      ON sm.supplier_code = si.supplier_code
    WHERE si.primary_yn = 'Y'
      AND si.unit_price IS NOT NULL
      AND si.valid_from <= '{as_of_date}'
      AND (si.valid_to IS NULL OR si.valid_to >= '{as_of_date}')
      AND sm.active_yn = 'Y'
    GROUP BY si.item_code
    HAVING COUNT(*) = 1
),
attribute_cost AS (
    SELECT
        a.item_code,
        MAX(CAST(a.attribute_value AS REAL)) AS attribute_unit_cost
    FROM item_attribute_values a
    WHERE LOWER(a.attribute_name) = 'unit_cost'
      AND a.value_type = 'NUMBER'
      AND a.attribute_value IS NOT NULL
      AND a.valid_from <= '{as_of_date}'
      AND (a.valid_to IS NULL OR a.valid_to >= '{as_of_date}')
    GROUP BY a.item_code
)
SELECT
    e.child_item_code AS item_code,
    i.item_name AS item_name,
    e.parent_item_code AS parent_item_code,
    e.location_code AS location_code,
    COALESCE(p.supplier_unit_price, a.attribute_unit_cost) AS unit_cost,
    CASE
        WHEN p.supplier_unit_price IS NOT NULL THEN 'PRIMARY_SUPPLIER'
        ELSE 'ITEM_ATTRIBUTE'
    END AS price_source,
    p.currency_code AS currency_code
FROM material_edges e
JOIN item_master i
  ON i.item_code = e.child_item_code
LEFT JOIN primary_price p
  ON p.item_code = e.child_item_code
LEFT JOIN attribute_cost a
  ON a.item_code = e.child_item_code
WHERE COALESCE(p.supplier_unit_price, a.attribute_unit_cost) IS NOT NULL
ORDER BY
    unit_cost DESC,
    e.child_item_code,
    e.parent_item_code,
    e.location_code
LIMIT 1
""".strip()


__all__ = ["ScopedBomCostEvidenceQuery"]
