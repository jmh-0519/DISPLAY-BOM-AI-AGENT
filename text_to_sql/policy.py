from __future__ import annotations

from dataclasses import dataclass, field


# Initial Text-to-SQL scope deliberately excludes workflow, approval, apply,
# rule-management and internal metadata tables. Those may be considered later
# as separate read-only analytics capabilities after evaluation.
DEFAULT_ALLOWED_TABLES = frozenset(
    {
        "plants",
        "supplier_master",
        "item_master",
        "version_master",
        "assembly_master",
        "material_master",
        "location_master",
        "bom_master",
        "item_attribute_values",
        "substitution_relations",
        "supplier_items",
        "warehouses",
        "inventory_locations",
        "inventory_balances",
        "production_plans",
    }
)

# SQLite authorizer reports built-in function names through SQLITE_FUNCTION.
# Keep the first release intentionally small and deterministic. More functions
# can be added only when a real evaluation case requires them.
DEFAULT_ALLOWED_FUNCTIONS = frozenset(
    {
        "abs",
        "avg",
        "coalesce",
        "count",
        "date",
        "datetime",
        "ifnull",
        "julianday",
        "length",
        "lower",
        "ltrim",
        "max",
        "min",
        "nullif",
        "printf",
        "replace",
        "round",
        "rtrim",
        "strftime",
        "substr",
        "substring",
        "sum",
        "time",
        "trim",
        "unixepoch",
        "upper",
    }
)


TABLE_DESCRIPTIONS = {
    "plants": "PLANT master: plant code, name, country and active status.",
    "supplier_master": "Supplier master including specialty, grade and quality score.",
    "item_master": "Global VERSION/ASSEMBLY/MATERIAL item identity and lifecycle registry; active_yn lives here.",
    "version_master": "Display VERSION/FA business attributes: product name/type, screen size, resolution, refresh rate, market and legacy product id.",
    "assembly_master": "ASSY master with process_name and COMMON/DEDICATED usage type.",
    "material_master": "MATERIAL subtype attributes: material group, unit and specification. Lifecycle comes from item_master; suppliers come from supplier_items.",
    "location_master": "BOM location master such as TOP/BOTTOM/LEFT/RIGHT.",
    "bom_master": "Plant-scoped effective-dated E-BOM parent-child rows and quantities.",
    "item_attribute_values": "Effective-dated technical/specification attributes for items.",
    "substitution_relations": "Registered or attribute/commonization substitution relationships between items.",
    "supplier_items": "Supplier-item commercial/supply data: price, lead time, quality, stability and supply status.",
    "warehouses": "Warehouse master belonging to a PLANT.",
    "inventory_locations": "Inventory location master belonging to a warehouse.",
    "inventory_balances": "Inventory quantities by inventory location and item.",
    "production_plans": "Plant/version/date production plan quantities and status.",
}


@dataclass(frozen=True)
class TextToSqlPolicy:
    allowed_tables: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TABLES)
    allowed_functions: frozenset[str] = field(default_factory=lambda: DEFAULT_ALLOWED_FUNCTIONS)
    max_rows: int = 200
    max_sql_length: int = 12_000
    timeout_seconds: float = 2.0
    progress_check_opcodes: int = 1_000

    def __post_init__(self) -> None:
        if not self.allowed_tables:
            raise ValueError("Text-to-SQL allowed_tables must not be empty")
        if self.max_rows < 1:
            raise ValueError("Text-to-SQL max_rows must be >= 1")
        if self.max_sql_length < 100:
            raise ValueError("Text-to-SQL max_sql_length must be >= 100")
        if self.timeout_seconds <= 0:
            raise ValueError("Text-to-SQL timeout_seconds must be > 0")
        if self.progress_check_opcodes < 1:
            raise ValueError("progress_check_opcodes must be >= 1")


DEFAULT_TEXT_TO_SQL_POLICY = TextToSqlPolicy()
