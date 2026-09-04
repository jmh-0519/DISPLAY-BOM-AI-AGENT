"""Deterministic read-only target evidence for Design Change Analysis composition.

This module resolves only factual BOM target evidence.  It never creates a
Design Change Request and never evaluates candidate suitability.

Supported target modes:
- explicit item code / explicit item name inside one VERSION/PLANT BOM;
- highest/lowest comparable COST target;
- highest active VERSION usage-count (COMMONALITY) target.

Every query runs through ``ReadOnlySqlExecutor``.  A top-ranked tie or repeated
BOM edge is returned as AMBIGUOUS rather than silently tie-broken.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import re
from typing import Any

from text_to_sql.read_only_executor import ReadOnlySqlExecutor


class TargetQueryStatus(str, Enum):
    READY = "READY"
    EMPTY = "EMPTY"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


@dataclass(frozen=True)
class TargetEvidenceQueryResult:
    status: TargetQueryStatus
    criterion: str
    selection_mode: str
    reason: str
    rows: tuple[dict[str, Any], ...] = ()
    sql: str = ""
    elapsed_ms: float = 0.0
    authority: str = "READ_ONLY_SCOPED_BOM_EVIDENCE"

    @property
    def ready(self) -> bool:
        return self.status == TargetQueryStatus.READY and len(self.rows) == 1

    @property
    def row(self) -> dict[str, Any] | None:
        return dict(self.rows[0]) if self.ready else None


class ScopedBomTargetEvidenceQuery:
    """Resolve one source BOM edge without LLM target selection."""

    VERSION_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
    PLANT_PATTERN = re.compile(r"^P\d{2,}$")

    def __init__(self, executor: ReadOnlySqlExecutor) -> None:
        if executor is None:
            raise ValueError("ReadOnlySqlExecutor is required")
        self.executor = executor

    def resolve_explicit(
        self,
        *,
        version_code: str,
        plant_code: str,
        item_code: str | None = None,
        target_name: str | None = None,
        as_of_date: str | None = None,
    ) -> TargetEvidenceQueryResult:
        version, plant, effective_date = self._scope(
            version_code, plant_code, as_of_date
        )
        code = str(item_code or "").strip().upper()
        name = " ".join(str(target_name or "").strip().split())
        if bool(code) == bool(name):
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.INVALID,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason="명시 Target은 item_code 또는 target_name 중 하나만 필요합니다.",
            )
        if code and self.VERSION_PATTERN.fullmatch(code) is None:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.INVALID,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason="명시된 품목코드 형식이 올바르지 않습니다.",
            )

        sql = self._explicit_sql(
            version_code=version,
            plant_code=plant,
            as_of_date=effective_date,
            item_code=code or None,
        )
        execution = self.executor.execute(sql)
        if execution.truncated:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.INVALID,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason=(
                    "명시 Target 확인 결과가 행 제한에 걸려 전체 BOM 근거를 "
                    "검증할 수 없습니다. 품목코드를 지정해 주세요."
                ),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )

        rows = [dict(row) for row in execution.rows]
        if name:
            rows = self._best_name_matches(name, rows)
        if not rows:
            label = code or name
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.EMPTY,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason=(
                    f"{version} / {plant} 활성 BOM에서 '{label}'에 해당하는 "
                    "변경 대상 품목을 찾지 못했습니다."
                ),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )

        unique_codes = {
            str(row.get("item_code") or "").strip().upper()
            for row in rows
            if str(row.get("item_code") or "").strip()
        }
        if len(unique_codes) != 1:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.AMBIGUOUS,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason=self._ambiguity_reason(
                    "명시한 이름에 해당하는 품목이 둘 이상입니다", rows
                ),
                rows=tuple(rows[:8]),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )

        # One item may legitimately appear under several parent/location edges.
        # The Service requires an exact edge, so never choose one arbitrarily.
        edge_keys = {
            (
                str(row.get("parent_item_code") or "").strip().upper(),
                str(row.get("location_code") or "").strip().upper(),
            )
            for row in rows
        }
        if len(edge_keys) != 1:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.AMBIGUOUS,
                criterion="EXPLICIT",
                selection_mode="USER_SPECIFIED",
                reason=self._ambiguity_reason(
                    "동일 품목이 현재 BOM의 여러 위치에 존재합니다", rows
                ),
                rows=tuple(rows[:8]),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )

        return TargetEvidenceQueryResult(
            status=TargetQueryStatus.READY,
            criterion="EXPLICIT",
            selection_mode="USER_SPECIFIED",
            reason="명시 Target의 활성 BOM edge를 하나로 검증했습니다.",
            rows=(rows[0],),
            sql=sql,
            elapsed_ms=execution.elapsed_ms,
        )

    def resolve_cost_rank(
        self,
        *,
        version_code: str,
        plant_code: str,
        direction: str = "HIGH",
        as_of_date: str | None = None,
    ) -> TargetEvidenceQueryResult:
        version, plant, effective_date = self._scope(
            version_code, plant_code, as_of_date
        )
        order = str(direction or "HIGH").strip().upper()
        if order not in {"HIGH", "LOW"}:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.INVALID,
                criterion="COST",
                selection_mode="TOP_1_HIGH",
                reason="COST ranking direction은 HIGH 또는 LOW만 지원합니다.",
            )
        sql = self._cost_sql(
            version_code=version,
            plant_code=plant,
            as_of_date=effective_date,
            direction=order,
        )
        execution = self.executor.execute(sql)
        rows = [dict(row) for row in execution.rows]
        selection_mode = "TOP_1_HIGH" if order == "HIGH" else "TOP_1_LOW"
        if not rows:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.EMPTY,
                criterion="COST",
                selection_mode=selection_mode,
                reason=(
                    f"{version} / {plant} 활성 BOM에는 현재 비교 가능한 "
                    "원가/단가 근거가 등록된 자재가 없습니다."
                ),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )
        return self._ranked_result(
            rows=rows,
            metric_name="unit_cost",
            criterion="COST",
            selection_mode=selection_mode,
            sql=sql,
            elapsed_ms=execution.elapsed_ms,
        )

    def resolve_commonality_rank(
        self,
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str | None = None,
    ) -> TargetEvidenceQueryResult:
        version, plant, effective_date = self._scope(
            version_code, plant_code, as_of_date
        )
        sql = self._commonality_sql(
            version_code=version,
            plant_code=plant,
            as_of_date=effective_date,
        )
        execution = self.executor.execute(sql)
        rows = [dict(row) for row in execution.rows]
        if not rows:
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.EMPTY,
                criterion="COMMONALITY",
                selection_mode="TOP_1_HIGH",
                reason=(
                    f"{version} / {plant} 활성 BOM에서 공용성 비교 대상 자재를 "
                    "찾지 못했습니다."
                ),
                sql=sql,
                elapsed_ms=execution.elapsed_ms,
            )
        return self._ranked_result(
            rows=rows,
            metric_name="active_version_usage_count",
            criterion="COMMONALITY",
            selection_mode="TOP_1_HIGH",
            sql=sql,
            elapsed_ms=execution.elapsed_ms,
        )

    @classmethod
    def _scope(
        cls,
        version_code: str,
        plant_code: str,
        as_of_date: str | None,
    ) -> tuple[str, str, str]:
        version = str(version_code or "").strip().upper()
        plant = str(plant_code or "").strip().upper()
        if cls.VERSION_PATTERN.fullmatch(version) is None:
            raise ValueError("Invalid VERSION code for scoped target evidence")
        if cls.PLANT_PATTERN.fullmatch(plant) is None:
            raise ValueError("Invalid PLANT code for scoped target evidence")
        effective_date = str(as_of_date or date.today().isoformat()).strip()
        try:
            date.fromisoformat(effective_date)
        except ValueError as error:
            raise ValueError("Invalid as_of_date") from error
        return version, plant, effective_date

    @staticmethod
    def _normalize(value: object) -> str:
        text = str(value or "").upper()
        text = re.sub(r"[^0-9A-Z가-힣\-]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _match_score(cls, query: str, row: dict[str, Any]) -> int:
        target = cls._normalize(query)
        if not target:
            return 0
        code = cls._normalize(row.get("item_code"))
        name = cls._normalize(row.get("item_name"))
        description = cls._normalize(row.get("description"))
        values = [value for value in (code, name, description) if value]
        if target in values:
            return 1000
        joined = " ".join(values)
        if target in joined:
            return 800
        tokens = target.split()
        candidate_tokens = set(joined.split())
        matched = sum(1 for token in tokens if token in candidate_tokens)
        if matched == len(tokens):
            return 500 + matched
        return matched * 10

    @classmethod
    def _best_name_matches(
        cls,
        target_name: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scored = [(cls._match_score(target_name, row), row) for row in rows]
        best = max((score for score, _ in scored), default=0)
        if best < 500:
            return []
        return [row for score, row in scored if score == best]

    @classmethod
    def _ranked_result(
        cls,
        *,
        rows: list[dict[str, Any]],
        metric_name: str,
        criterion: str,
        selection_mode: str,
        sql: str,
        elapsed_ms: float,
    ) -> TargetEvidenceQueryResult:
        first = rows[0]
        first_metric = first.get(metric_name)
        try:
            first_value = float(first_metric)
        except (TypeError, ValueError):
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.INVALID,
                criterion=criterion,
                selection_mode=selection_mode,
                reason=f"{metric_name} 비교 수치가 올바르지 않습니다.",
                rows=tuple(rows[:8]),
                sql=sql,
                elapsed_ms=elapsed_ms,
            )

        tied: list[dict[str, Any]] = []
        for row in rows:
            try:
                value = float(row.get(metric_name))
            except (TypeError, ValueError):
                continue
            if abs(value - first_value) <= 1e-12:
                tied.append(row)

        # Different item or a repeated BOM edge at the winning metric is not a
        # unique target.  The user must disambiguate it.
        if len(tied) > 1:
            label = "원가/단가" if criterion == "COST" else "공용성(사용 모델 수)"
            return TargetEvidenceQueryResult(
                status=TargetQueryStatus.AMBIGUOUS,
                criterion=criterion,
                selection_mode=selection_mode,
                reason=cls._ambiguity_reason(
                    f"{label} 최상위 조건에 해당하는 BOM edge가 둘 이상입니다",
                    tied,
                ),
                rows=tuple(tied[:8]),
                sql=sql,
                elapsed_ms=elapsed_ms,
            )

        return TargetEvidenceQueryResult(
            status=TargetQueryStatus.READY,
            criterion=criterion,
            selection_mode=selection_mode,
            reason="읽기 전용 BOM Evidence로 단일 Target을 검증했습니다.",
            rows=(first,),
            sql=sql,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _ambiguity_reason(prefix: str, rows: list[dict[str, Any]]) -> str:
        labels: list[str] = []
        for row in rows[:8]:
            code = str(row.get("item_code") or "-").strip()
            name = str(row.get("item_name") or "-").strip()
            parent = str(row.get("parent_item_code") or "-").strip()
            location = str(row.get("location_code") or "-").strip()
            metric = row.get("unit_cost")
            if metric is None:
                metric = row.get("active_version_usage_count")
            metric_text = f", metric={metric}" if metric is not None else ""
            labels.append(
                f"{code}({name}, parent={parent}, location={location}{metric_text})"
            )
        return (
            f"{prefix}: " + "; ".join(labels)
            + ". 품목코드와 필요한 경우 Parent/LOCATION을 명시해 주세요."
        )

    @staticmethod
    def _explicit_sql(
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str,
        item_code: str | None,
    ) -> str:
        code_filter = (
            f"AND UPPER(b.child_item_code) = '{item_code}'"
            if item_code else ""
        )
        return f"""
WITH RECURSIVE reachable(item_code, path, depth) AS (
    SELECT '{version_code}', '|' || '{version_code}' || '|', 0
    UNION ALL
    SELECT
        b.child_item_code,
        r.path || b.child_item_code || '|',
        r.depth + 1
    FROM reachable r
    JOIN bom_master b
      ON b.parent_item_code = r.item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND r.depth < 50
      AND instr(r.path, '|' || b.child_item_code || '|') = 0
)
SELECT DISTINCT
    b.child_item_code AS item_code,
    i.item_name AS item_name,
    i.description AS description,
    i.item_type AS target_item_type,
    b.parent_item_code AS parent_item_code,
    b.location_code AS location_code,
    b.quantity AS bom_quantity
FROM reachable r
JOIN bom_master b
  ON b.parent_item_code = r.item_code
JOIN item_master i
  ON i.item_code = b.child_item_code
WHERE b.plant_code = '{plant_code}'
  AND b.status = 'ACTIVE'
  AND b.valid_from <= '{as_of_date}'
  AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
  AND i.active_yn = 'Y'
  AND i.item_type IN ('MATERIAL', 'ASSEMBLY')
  {code_filter}
ORDER BY b.child_item_code, b.parent_item_code, b.location_code
""".strip()

    @staticmethod
    def _cost_sql(
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str,
        direction: str,
    ) -> str:
        order = "DESC" if direction == "HIGH" else "ASC"
        return f"""
WITH RECURSIVE reachable(item_code, path, depth) AS (
    SELECT '{version_code}', '|' || '{version_code}' || '|', 0
    UNION ALL
    SELECT
        b.child_item_code,
        r.path || b.child_item_code || '|',
        r.depth + 1
    FROM reachable r
    JOIN bom_master b
      ON b.parent_item_code = r.item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND r.depth < 50
      AND instr(r.path, '|' || b.child_item_code || '|') = 0
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
    'MATERIAL' AS target_item_type,
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
    unit_cost {order},
    e.child_item_code,
    e.parent_item_code,
    e.location_code
LIMIT 8
""".strip()

    @staticmethod
    def _commonality_sql(
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str,
    ) -> str:
        return f"""
WITH RECURSIVE
current_tree(item_code, path, depth) AS (
    SELECT '{version_code}', '|' || '{version_code}' || '|', 0
    UNION ALL
    SELECT
        b.child_item_code,
        t.path || b.child_item_code || '|',
        t.depth + 1
    FROM current_tree t
    JOIN bom_master b
      ON b.parent_item_code = t.item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND t.depth < 50
      AND instr(t.path, '|' || b.child_item_code || '|') = 0
),
scoped_edges AS (
    SELECT DISTINCT
        b.parent_item_code,
        b.child_item_code,
        b.location_code
    FROM current_tree t
    JOIN bom_master b
      ON b.parent_item_code = t.item_code
    JOIN item_master i
      ON i.item_code = b.child_item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND i.item_type = 'MATERIAL'
      AND i.active_yn = 'Y'
),
all_version_tree(version_code, item_code, path, depth) AS (
    SELECT
        v.version_code,
        v.version_code,
        '|' || v.version_code || '|',
        0
    FROM version_master v
    JOIN item_master vi
      ON vi.item_code = v.version_code
    WHERE vi.active_yn = 'Y'
    UNION ALL
    SELECT
        t.version_code,
        b.child_item_code,
        t.path || b.child_item_code || '|',
        t.depth + 1
    FROM all_version_tree t
    JOIN bom_master b
      ON b.parent_item_code = t.item_code
    WHERE b.plant_code = '{plant_code}'
      AND b.status = 'ACTIVE'
      AND b.valid_from <= '{as_of_date}'
      AND (b.valid_to IS NULL OR b.valid_to >= '{as_of_date}')
      AND t.depth < 50
      AND instr(t.path, '|' || b.child_item_code || '|') = 0
),
usage_count AS (
    SELECT
        item_code,
        COUNT(DISTINCT version_code) AS active_version_usage_count
    FROM all_version_tree
    GROUP BY item_code
)
SELECT
    e.child_item_code AS item_code,
    i.item_name AS item_name,
    'MATERIAL' AS target_item_type,
    e.parent_item_code AS parent_item_code,
    e.location_code AS location_code,
    COALESCE(u.active_version_usage_count, 0) AS active_version_usage_count
FROM scoped_edges e
JOIN item_master i
  ON i.item_code = e.child_item_code
LEFT JOIN usage_count u
  ON u.item_code = e.child_item_code
ORDER BY
    active_version_usage_count DESC,
    e.child_item_code,
    e.parent_item_code,
    e.location_code
LIMIT 8
""".strip()


__all__ = [
    "ScopedBomTargetEvidenceQuery",
    "TargetEvidenceQueryResult",
    "TargetQueryStatus",
]
