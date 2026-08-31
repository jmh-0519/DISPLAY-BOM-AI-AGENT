from __future__ import annotations

import argparse
import json
from pathlib import Path

from database import SchemaManager, SQLiteDatabase


AS_OF_DATE = "2026-08-15"
EFFECTIVE_DATE = "2026-09-01"


SCENARIOS = (
    {
        "no": 1,
        "model": "LTA400HR11-001",
        "model_name": "40IN FHD 60HZ LCD MODULE (EOL TEST)",
        "spec": {"screen_size_inch": 40, "resolution": "FHD", "refresh_hz": 60, "market": "KR"},
        "reason": "EOL",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310101",
        "parent_name": "OLB",
        "source": "0001-310101",
        "source_name": "DRIVE-IC",
        "material_group": "OLB",
        "conditions": (("material_family", "EQ", "DRIVER_IC"), ("interface", "EQ", "LVDS"), ("operating_voltage", "LE", "3.3")),
        "attributes": {"material_family": "DRIVER_IC", "interface": "LVDS", "operating_voltage": 3.3},
    },
    {
        "no": 2,
        "model": "LTA400HR12-001",
        "model_name": "40IN FHD 120HZ LCD MODULE (SUPPLY TEST)",
        "spec": {"screen_size_inch": 40, "resolution": "FHD", "refresh_hz": 120, "market": "GLOBAL"},
        "reason": "SUPPLIER_STOP",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310201",
        "parent_name": "OLB",
        "source": "0001-310201",
        "source_name": "OLB FPCB",
        "material_group": "OLB",
        "conditions": (("material_family", "EQ", "OLB_FPCB"), ("layer_count", "IN", "4.0"), ("connector_pitch_mm", "IN", "0.5")),
        "attributes": {"material_family": "OLB_FPCB", "layer_count": 4, "connector_pitch_mm": 0.5},
    },
    {
        "no": 3,
        "model": "LTA500HR11-001",
        "model_name": "50IN UHD 60HZ LCD MODULE (LEAD TIME TEST)",
        "spec": {"screen_size_inch": 50, "resolution": "UHD", "refresh_hz": 60, "market": "KR"},
        "reason": "LEAD_TIME",
        "target_type": "ASSY",
        "primary_action": "REPLACE",
        "parent": "LTA500HR11-001",
        "parent_name": "FA",
        "source": "LJ94-310301",
        "source_name": "OLB ASSY",
        "process_name": "OLB",
        "conditions": (("process_name", "EQ", "OLB"), ("panel_size_inch", "IN", "50.0"), ("resolution", "EQ", "UHD")),
        "attributes": {"process_name": "OLB", "panel_size_inch": 50, "resolution": "UHD"},
    },
    {
        "no": 4,
        "model": "LTA500HR12-001",
        "model_name": "50IN UHD 120HZ LCD MODULE (COST TEST)",
        "spec": {"screen_size_inch": 50, "resolution": "UHD", "refresh_hz": 120, "market": "GLOBAL"},
        "reason": "COST",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310401",
        "parent_name": "CP",
        "source": "0001-310401",
        "source_name": "POLARIZER",
        "material_group": "CP",
        "conditions": (("material_family", "EQ", "POLARIZER"), ("transmittance_pct", "GE", "42"), ("thickness_um", "LE", "220")),
        "attributes": {"material_family": "POLARIZER", "transmittance_pct": 43, "thickness_um": 210},
    },
    {
        "no": 5,
        "model": "LTA550HR11-001",
        "model_name": "55IN UHD 60HZ LCD MODULE (INVENTORY TEST)",
        "spec": {"screen_size_inch": 55, "resolution": "UHD", "refresh_hz": 60, "market": "KR"},
        "reason": "INVENTORY",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310501",
        "parent_name": "LC",
        "source": "0001-310501",
        "source_name": "SEALANT",
        "material_group": "LC",
        "conditions": (("material_family", "EQ", "SEALANT"), ("curing_type", "EQ", "UV"), ("viscosity_cps", "LE", "3500")),
        "attributes": {"material_family": "SEALANT", "curing_type": "UV", "viscosity_cps": 3200},
    },
    {
        "no": 6,
        "model": "LTA550HR12-001",
        "model_name": "55IN UHD 120HZ LCD MODULE (QUALITY TEST)",
        "spec": {"screen_size_inch": 55, "resolution": "UHD", "refresh_hz": 120, "market": "GLOBAL"},
        "reason": "QUALITY",
        "target_type": "ASSY",
        "primary_action": "REPLACE",
        "parent": "LJ94-310605",
        "parent_name": "LC",
        "source": "LJ94-310601",
        "source_name": "CF ASSY",
        "process_name": "CF",
        "conditions": (("process_name", "EQ", "CF"), ("panel_size_inch", "IN", "55.0"), ("resolution", "EQ", "UHD")),
        "attributes": {"process_name": "CF", "panel_size_inch": 55, "resolution": "UHD"},
    },
    {
        "no": 7,
        "model": "LTA650HR11-001",
        "model_name": "65IN UHD 120HZ LCD MODULE (CUSTOMER SPEC TEST)",
        "spec": {"screen_size_inch": 65, "resolution": "UHD", "refresh_hz": 120, "market": "NA"},
        "reason": "CUSTOMER_SPEC",
        "target_type": "MATERIAL",
        "primary_action": "ADD",
        "parent": "LJ94-310701",
        "parent_name": "BIN",
        "source": "0001-310701",
        "source_name": "BASE BRACKET",
        "candidate_name": "EMI SHIELD TAPE",
        "material_group": "FA",
        "conditions": (("material_family", "EQ", "EMI_SHIELD_TAPE"), ("shielding_db", "GE", "60"), ("halogen_free", "EQ", "Y")),
        "attributes": {"material_family": "EMI_SHIELD_TAPE", "shielding_db": 65, "halogen_free": "Y"},
    },
    {
        "no": 8,
        "model": "LTA650HR12-001",
        "model_name": "65IN UHD 144HZ LCD MODULE (REGULATION TEST)",
        "spec": {"screen_size_inch": 65, "resolution": "UHD", "refresh_hz": 144, "market": "EU"},
        "reason": "REGULATION",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310801",
        "parent_name": "CP",
        "source": "0001-310801",
        "source_name": "OPTICAL ADHESIVE",
        "material_group": "CP",
        "conditions": (("material_family", "EQ", "OPTICAL_ADHESIVE"), ("rohs_status", "EQ", "COMPLIANT"), ("halogen_free", "EQ", "Y")),
        "attributes": {"material_family": "OPTICAL_ADHESIVE", "rohs_status": "COMPLIANT", "halogen_free": "Y"},
    },
    {
        "no": 9,
        "model": "LTA750HR11-001",
        "model_name": "75IN UHD 120HZ LCD MODULE (COMMONIZATION TEST)",
        "spec": {"screen_size_inch": 75, "resolution": "UHD", "refresh_hz": 120, "market": "GLOBAL"},
        "reason": "COMMONIZATION",
        "target_type": "MATERIAL",
        "primary_action": "REPLACE",
        "parent": "LJ94-310901",
        "parent_name": "BIN",
        "source": "0001-310901",
        "source_name": "BRACKET",
        "delete_item": "0001-310902",
        "delete_item_name": "SPACER",
        "material_group": "FA",
        "conditions": (("material_family", "EQ", "BRACKET"), ("hole_pitch_mm", "IN", "80.0"), ("material_grade", "EQ", "AL6061")),
        "attributes": {"material_family": "BRACKET", "hole_pitch_mm": 80, "material_grade": "AL6061"},
    },
    {
        "no": 10,
        "model": "LTA750HR12-001",
        "shared_model": "LTA750HR12-002",
        "model_name": "75IN UHD 144HZ LCD MODULE (COMMON ASSY TEST)",
        "spec": {"screen_size_inch": 75, "resolution": "UHD", "refresh_hz": 144, "market": "GLOBAL"},
        "reason": "COMMONIZATION",
        "target_type": "ASSY",
        "primary_action": "REPLACE",
        "parent": "LTA750HR12-001",
        "parent_name": "FA",
        "source": "LJ94-311001",
        "source_name": "OLB ASSY",
        "quantity_parent": "LJ94-311001",
        "quantity_item": "0001-311001",
        "quantity_item_name": "GATE-IC",
        "process_name": "OLB",
        "conditions": (("process_name", "EQ", "OLB"), ("panel_size_inch", "IN", "75.0"), ("resolution", "EQ", "UHD")),
        "attributes": {"process_name": "OLB", "panel_size_inch": 75, "resolution": "UHD"},
    },
)


# Each design-change scenario belongs to one primary Plant unless it explicitly
# tests a cross-Plant condition. This prevents accidental BOM/plan/inventory
# replication while keeping all four Plants covered by acceptance data.
SCENARIO_PLANT_CODES = {
    1: "P01",
    2: "P02",
    3: "P03",
    4: "P04",
    5: "P01",
    6: "P02",
    7: "P03",
    8: "P04",
    9: "P01",
    10: "P01",
}

# The baseline product is intentionally available in P01 and P02.
# It is the regression fixture for "same VERSION, Plant-scoped BOM" queries.
CROSS_PLANT_QUERY_FIXTURES = {
    "LTA400HR01-001": ("P01", "P02"),
}


SUPPLIERS = (
    ("SUP-101", "Mirae Semiconductor", "KR", "Driver IC / Electronics", "S", 98),
    ("SUP-102", "Hanseong Circuit", "KR", "FPCB / Module", "A", 95),
    ("SUP-103", "Asia Panel Solutions", "VN", "Display ASSY", "A", 93),
    ("SUP-104", "Daehan Display Materials", "KR", "Film / Adhesive", "A", 96),
    ("SUP-105", "Global Display Parts", "JP", "Display Component", "B", 90),
)


def _upsert_item(connection, code: str, item_type: str, name: str, description: str) -> None:
    connection.execute(
        """INSERT INTO item_master(item_code,item_type,item_name,description,active_yn)
           VALUES(?,?,?,?,'Y')
           ON CONFLICT(item_code) DO UPDATE SET
             item_type=excluded.item_type,item_name=excluded.item_name,
             description=excluded.description,active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
        (code, item_type, name, description),
    )


def _upsert_version(connection, scenario: dict, version_code: str, suffix: str = "001") -> None:
    spec = dict(scenario["spec"])
    spec.update({"product_name": scenario["model_name"], "product_type": "LCD MODULE", "test_dataset": "DESIGN_CHANGE_BUSINESS_SAMPLE"})
    _upsert_item(connection, version_code, "VERSION", "FA", scenario["model_name"])
    connection.execute(
        """INSERT INTO version_master(version_code,version_no,specification,active_yn)
           VALUES(?,?,?,'Y')
           ON CONFLICT(version_code) DO UPDATE SET
             version_no=excluded.version_no,specification=excluded.specification,
             active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
        (version_code, f"T{scenario['no']:02d}.{suffix}", json.dumps(spec, ensure_ascii=False)),
    )


def _upsert_assembly(
    connection,
    code: str,
    process_name: str,
    usage_type: str = "DEDICATED",
    description: str | None = None,
) -> None:
    """Store an ASSY with the process name as its only valid item_name.

    Business descriptions/specifications distinguish alternative ASSYs.  The
    item_name itself is a process-domain value and must remain one of
    OLB/CP/BIN/LC/CF/TFT.
    """
    description = description or process_name
    _upsert_item(connection, code, "ASSEMBLY", process_name, description)
    connection.execute(
        """INSERT INTO assembly_master(assembly_code,process_name,usage_type,specification,active_yn)
           VALUES(?,?,?,?, 'Y')
           ON CONFLICT(assembly_code) DO UPDATE SET
             process_name=excluded.process_name,usage_type=excluded.usage_type,
             specification=excluded.specification,active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
        (code, process_name, usage_type, description),
    )


def _assembly_description(process_name: str, attributes: dict | None = None) -> str:
    attributes = attributes or {}
    parts = [process_name]
    panel_size = attributes.get("panel_size_inch")
    if panel_size not in {None, ""}:
        size = float(panel_size)
        parts.append(f"{size:g}IN")
    resolution = attributes.get("resolution")
    if resolution:
        parts.append(str(resolution).upper())
    return "/".join(parts)


def _upsert_material(connection, code: str, name: str, group_name: str) -> None:
    description = f"{group_name}/{name}/DESIGN CHANGE BUSINESS SAMPLE"
    _upsert_item(connection, code, "MATERIAL", name, description)
    connection.execute(
        """INSERT INTO material_master(material_code,material_name,material_group,unit,specification,active_yn)
           VALUES(?,?,?,'EA',?,'Y')
           ON CONFLICT(material_code) DO UPDATE SET
             material_name=excluded.material_name,material_group=excluded.material_group,
             unit='EA',specification=excluded.specification,active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
        (code, name, group_name, description),
    )


def _upsert_attribute(connection, item_code: str, name: str, value) -> None:
    value_type = "NUMBER" if isinstance(value, (int, float)) else "TEXT"
    connection.execute(
        """INSERT INTO item_attribute_values(
             item_code,attribute_name,attribute_value,value_type,valid_from,source)
           VALUES(?,?,?,?,?,'DESIGN_CHANGE_BUSINESS_SAMPLE')
           ON CONFLICT(item_code,attribute_name,valid_from) DO UPDATE SET
             attribute_value=excluded.attribute_value,value_type=excluded.value_type,
             source=excluded.source,updated_at=CURRENT_TIMESTAMP""",
        (item_code, name, str(value), value_type, AS_OF_DATE),
    )


def _upsert_bom(
    connection, plant_code: str, parent: str, child: str,
    sequence: int, quantity: float = 1.0,
) -> None:
    row = connection.execute(
        """SELECT bom_id FROM bom_master
           WHERE plant_code=? AND parent_item_code=? AND child_item_code=?
             AND location_code='N/A'
             AND valid_from=?""",
        (plant_code, parent, child, AS_OF_DATE),
    ).fetchone()
    if row:
        connection.execute(
            """UPDATE bom_master SET sequence_no=?,quantity=?,valid_to=NULL,status='ACTIVE',
                 updated_at=CURRENT_TIMESTAMP WHERE bom_id=?""",
            (sequence, quantity, row[0]),
        )
    else:
        connection.execute(
            """INSERT INTO bom_master(plant_code,parent_item_code,child_item_code,location_code,
                 sequence_no,quantity,valid_from,status)
               VALUES(?,?,?,'N/A',?,?,?,'ACTIVE')""",
            (plant_code, parent, child, sequence, quantity, AS_OF_DATE),
        )


def _candidate_code(scenario: dict, candidate_no: int) -> str:
    prefix = "LJ94" if scenario["target_type"] == "ASSY" else "0001"
    return f"{prefix}-31{scenario['no']:02d}1{candidate_no}"


def _candidate_name(scenario: dict, candidate_no: int) -> str:
    if scenario["target_type"] == "ASSY":
        return scenario["process_name"]
    base_name = scenario.get("candidate_name") or scenario["source_name"]
    return f"{base_name} ALT-{candidate_no}"


def _rule_evaluation_item(scenario: dict) -> str:
    if scenario["target_type"] == "ASSY":
        return scenario["process_name"]
    return scenario.get("candidate_name") or scenario["source_name"]



def _remove_existing_business_sample(connection) -> None:
    """Make the deterministic business seed idempotent without touching user history."""
    business_versions = [
        row[0]
        for row in connection.execute(
            "SELECT version_code FROM version_master "
            "WHERE specification LIKE '%DESIGN_CHANGE_BUSINESS_SAMPLE%'"
        ).fetchall()
    ]
    if not business_versions:
        return

    placeholders = ",".join("?" for _ in business_versions)
    workflow_count = connection.execute(
        f"SELECT COUNT(*) FROM change_requests WHERE version_code IN ({placeholders})",
        business_versions,
    ).fetchone()[0]
    if workflow_count:
        raise RuntimeError(
            "Design-change business sample has workflow history. "
            "Rebuild from the immutable baseline instead of reseeding this DB in place."
        )

    # production_plans references version_master, so remove plans before versions.
    connection.execute(
        f"DELETE FROM production_plans WHERE version_code IN ({placeholders})",
        business_versions,
    )

    business_items = {
        row[0]
        for row in connection.execute(
            "SELECT item_code FROM item_master "
            "WHERE description LIKE '%DESIGN CHANGE BUSINESS SAMPLE%'"
        ).fetchall()
    }
    business_items.update(business_versions)
    business_items.update(
        row[0]
        for row in connection.execute(
            "SELECT DISTINCT item_code FROM item_attribute_values "
            "WHERE source='DESIGN_CHANGE_BUSINESS_SAMPLE'"
        ).fetchall()
    )
    if business_items:
        item_values = sorted(business_items)
        item_placeholders = ",".join("?" for _ in item_values)
        connection.execute(
            f"DELETE FROM inventory_balances WHERE item_code IN ({item_placeholders})",
            item_values,
        )
        connection.execute(
            f"DELETE FROM supplier_items WHERE item_code IN ({item_placeholders})",
            item_values,
        )
        connection.execute(
            f"DELETE FROM substitution_relations "
            f"WHERE source_item_code IN ({item_placeholders}) "
            f"OR candidate_item_code IN ({item_placeholders})",
            item_values + item_values,
        )
        connection.execute(
            f"DELETE FROM bom_master "
            f"WHERE parent_item_code IN ({item_placeholders}) "
            f"OR child_item_code IN ({item_placeholders})",
            item_values + item_values,
        )
        connection.execute(
            f"DELETE FROM item_attribute_values WHERE item_code IN ({item_placeholders})",
            item_values,
        )
        connection.execute(
            f"DELETE FROM material_master WHERE material_code IN ({item_placeholders})",
            item_values,
        )
        connection.execute(
            f"DELETE FROM assembly_master WHERE assembly_code IN ({item_placeholders})",
            item_values,
        )
        connection.execute(
            f"DELETE FROM version_master WHERE version_code IN ({placeholders})",
            business_versions,
        )
        connection.execute(
            f"DELETE FROM item_master WHERE item_code IN ({item_placeholders})",
            item_values,
        )

    connection.execute("DELETE FROM rule_conditions WHERE rule_id LIKE 'DC-R-%'")
    connection.execute("DELETE FROM rule_revisions WHERE rule_id LIKE 'DC-R-%'")
    connection.execute("DELETE FROM rule_definitions WHERE rule_id LIKE 'DC-R-%'")


def _copy_bom_tree_to_plant(
    connection, *, root_code: str, source_plant: str, target_plant: str
) -> int:
    """Copy one intentional product fixture to another Plant, preserving row values."""
    rows = connection.execute(
        """
        WITH RECURSIVE tree(item_code, visited) AS (
          SELECT ?, '|' || ? || '|'
          UNION ALL
          SELECT b.child_item_code, tree.visited || b.child_item_code || '|'
          FROM tree
          JOIN bom_master b
            ON b.parent_item_code=tree.item_code
           AND b.plant_code=?
          WHERE b.status='ACTIVE'
            AND b.valid_from<=?
            AND (b.valid_to IS NULL OR b.valid_to>=?)
            AND instr(tree.visited, '|' || b.child_item_code || '|')=0
        )
        SELECT DISTINCT b.parent_item_code,b.child_item_code,b.location_code,
               b.sequence_no,b.quantity,b.valid_from,b.valid_to,b.status
        FROM tree
        JOIN bom_master b
          ON b.parent_item_code=tree.item_code
         AND b.plant_code=?
        WHERE b.status='ACTIVE'
          AND b.valid_from<=?
          AND (b.valid_to IS NULL OR b.valid_to>=?)
        ORDER BY b.parent_item_code,b.sequence_no,b.child_item_code,b.location_code
        """,
        (
            root_code, root_code, source_plant, AS_OF_DATE, AS_OF_DATE,
            source_plant, AS_OF_DATE, AS_OF_DATE,
        ),
    ).fetchall()
    if not rows:
        raise RuntimeError(
            f"Cross-Plant fixture source BOM is missing: {source_plant}/{root_code}"
        )

    for row in rows:
        existing = connection.execute(
            """SELECT bom_id FROM bom_master
               WHERE plant_code=? AND parent_item_code=? AND child_item_code=?
                 AND location_code=? AND valid_from=?""",
            (
                target_plant, row["parent_item_code"], row["child_item_code"],
                row["location_code"], row["valid_from"],
            ),
        ).fetchone()
        if existing:
            connection.execute(
                """UPDATE bom_master SET sequence_no=?,quantity=?,valid_to=?,status=?,
                     updated_at=CURRENT_TIMESTAMP WHERE bom_id=?""",
                (
                    row["sequence_no"], row["quantity"], row["valid_to"],
                    row["status"], existing[0],
                ),
            )
        else:
            connection.execute(
                """INSERT INTO bom_master(
                     plant_code,parent_item_code,child_item_code,location_code,
                     sequence_no,quantity,valid_from,valid_to,status)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    target_plant, row["parent_item_code"], row["child_item_code"],
                    row["location_code"], row["sequence_no"], row["quantity"],
                    row["valid_from"], row["valid_to"], row["status"],
                ),
            )
    return len(rows)


def _seed_cross_plant_query_fixtures(connection) -> None:
    for root_code, plant_codes in CROSS_PLANT_QUERY_FIXTURES.items():
        source_plant = plant_codes[0]
        for target_plant in plant_codes[1:]:
            _copy_bom_tree_to_plant(
                connection,
                root_code=root_code,
                source_plant=source_plant,
                target_plant=target_plant,
            )

def _seed_organization(connection) -> dict[str, list[str]]:
    locations_by_plant: dict[str, list[str]] = {}
    plants = (
        ("P01", "국내 AA PLANT", "KR"),
        ("P02", "국내 BB PLANT", "KR"),
        ("P03", "중국 CC PLANT", "CN"),
        ("P04", "베트남 DD PLANT", "VN"),
    )
    for plant_code, plant_name, country_code in plants:
        locations_by_plant[plant_code] = []
        connection.execute(
            """INSERT INTO plants(plant_code,plant_name,country_code,active_yn)
               VALUES(?,?,?,'Y') ON CONFLICT(plant_code) DO UPDATE SET
                 plant_name=excluded.plant_name,country_code=excluded.country_code,active_yn='Y'""",
            (plant_code, plant_name, country_code),
        )
        for warehouse_suffix, warehouse_name in (("RM", "Raw Material Warehouse"), ("LINE", "Line-side Warehouse")):
            warehouse_code = f"{plant_code}-{warehouse_suffix}"
            connection.execute(
                """INSERT INTO warehouses(warehouse_code,plant_code,warehouse_name)
                   VALUES(?,?,?) ON CONFLICT(warehouse_code) DO UPDATE SET
                     plant_code=excluded.plant_code,warehouse_name=excluded.warehouse_name,active_yn='Y'""",
                (warehouse_code, plant_code, warehouse_name),
            )
            for location_no in (1, 2):
                location_code = f"{warehouse_code}-A{location_no:02d}"
                locations_by_plant[plant_code].append(location_code)
                connection.execute(
                    """INSERT INTO inventory_locations(
                         inventory_location_code,warehouse_code,location_name)
                       VALUES(?,?,?) ON CONFLICT(inventory_location_code) DO UPDATE SET
                         warehouse_code=excluded.warehouse_code,location_name=excluded.location_name,
                         active_yn='Y'""",
                    (location_code, warehouse_code, f"Rack A{location_no:02d}"),
                )
    return locations_by_plant



def _seed_baseline_operational_readiness(
    connection, locations_by_plant: dict[str, list[str]]
) -> None:
    """Add operational evidence to the baseline without hardcoding scenarios.

    Baseline BOMs predate the production-plan / supplier / inventory
    tables.  Candidate analysis must not turn missing operational fixtures into a
    fake PASS, but the functional sample DB still needs at least one realistic
    end-to-end path.  We therefore enrich whatever baseline VERSION/Plant pairs
    already exist *before* design-change scenario rows are inserted.

    The enrichment is data-driven:
    - every existing baseline VERSION/Plant BOM gets a future CONFIRMED plan when
      one is missing;
    - existing baseline MATERIAL masters get a deterministic complete supplier
      option when they have no supplier data;
    - the same materials receive stock in baseline Plants only when that Plant has
      no inventory row for the item.

    No runtime service depends on item codes created here and no business decision
    branches on a specific test model/material code.
    """
    root_pairs = connection.execute(
        """SELECT DISTINCT b.plant_code,b.parent_item_code AS version_code
           FROM bom_master b
           JOIN version_master v ON v.version_code=b.parent_item_code
           WHERE b.status='ACTIVE' AND b.valid_from<=?
             AND (b.valid_to IS NULL OR b.valid_to>=?)
           ORDER BY b.plant_code,b.parent_item_code""",
        (AS_OF_DATE, AS_OF_DATE),
    ).fetchall()
    if not root_pairs:
        return

    # A baseline product should be able to resolve demand automatically when the
    # user omits requested quantity.  Never overwrite a real/sample plan that is
    # already present.
    for row in root_pairs:
        exists = connection.execute(
            """SELECT 1 FROM production_plans
               WHERE version_code=? AND plant_code=? AND plan_date>=?
                 AND status='CONFIRMED' LIMIT 1""",
            (row["version_code"], row["plant_code"], AS_OF_DATE),
        ).fetchone()
        if exists:
            continue
        plan_id = f"PLAN-BASE-{row['version_code']}-{row['plant_code']}"
        connection.execute(
            """INSERT INTO production_plans(
                 plan_id,version_code,plant_code,plan_date,planned_quantity,status)
               VALUES(?,?,?,?,12,'CONFIRMED')
               ON CONFLICT(plan_id) DO UPDATE SET
                 version_code=excluded.version_code,plant_code=excluded.plant_code,
                 plan_date=excluded.plan_date,planned_quantity=excluded.planned_quantity,
                 status='CONFIRMED',updated_at=CURRENT_TIMESTAMP""",
            (plan_id, row["version_code"], row["plant_code"], EFFECTIVE_DATE),
        )

    # These are the MATERIALs already present in the migrated baseline.  Grouping
    # by business name + description gives comparable sample price bands without
    # relying on code prefixes or scenario IDs.
    materials = connection.execute(
        """SELECT i.item_code,i.item_name,COALESCE(i.description,'') AS description
           FROM item_master i
           JOIN material_master m ON m.material_code=i.item_code
           WHERE i.item_type='MATERIAL' AND i.active_yn='Y' AND m.active_yn='Y'
           ORDER BY i.item_name,COALESCE(i.description,''),i.item_code"""
    ).fetchall()
    grouped: dict[tuple[str, str], list] = {}
    for row in materials:
        grouped.setdefault((row["item_name"], row["description"]), []).append(row)

    baseline_plants = sorted({row["plant_code"] for row in root_pairs})
    for group_index, (_group_key, rows) in enumerate(sorted(grouped.items()), start=1):
        for rank, row in enumerate(rows, start=1):
            item_code = row["item_code"]

            # Preserve any existing commercial evidence.  Only fill a true gap.
            has_supplier = connection.execute(
                """SELECT 1 FROM supplier_items
                   WHERE item_code=? AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?) LIMIT 1""",
                (item_code, AS_OF_DATE, AS_OF_DATE),
            ).fetchone()
            if not has_supplier:
                # Deterministic sample price.  Within an equivalent group, sorted
                # items receive increasing prices so Cost Scan can demonstrate both
                # verified saving and non-saving alternatives with real evidence.
                unit_price = float(1000 + group_index * 100 + rank * 25)
                connection.execute(
                    """INSERT INTO supplier_items(
                         supplier_code,item_code,unit_price,currency_code,lead_time_days,
                         quality_grade,stability_score,primary_yn,supply_status,valid_from)
                       VALUES('SUP-104',?,?,'KRW',7,'A',95,'Y','AVAILABLE',?)
                       ON CONFLICT(supplier_code,item_code,valid_from) DO NOTHING""",
                    (item_code, unit_price, AS_OF_DATE),
                )

            for plant_code in baseline_plants:
                has_inventory = connection.execute(
                    """SELECT 1
                       FROM inventory_balances b
                       JOIN inventory_locations l USING(inventory_location_code)
                       JOIN warehouses w USING(warehouse_code)
                       WHERE b.item_code=? AND w.plant_code=? LIMIT 1""",
                    (item_code, plant_code),
                ).fetchone()
                if has_inventory:
                    continue
                locations = locations_by_plant.get(plant_code) or []
                if not locations:
                    continue
                # Keep enough stock for the baseline sample production plan even
                # for components with multi-unit BOM usage.
                location_code = locations[0]
                connection.execute(
                    """INSERT INTO inventory_balances(
                         inventory_location_code,item_code,on_hand_quantity,reserved_quantity,
                         safety_stock,hold_quantity,incoming_quantity,incoming_date)
                       VALUES(?,?,500,10,20,0,0,NULL)
                       ON CONFLICT(inventory_location_code,item_code) DO NOTHING""",
                    (location_code, item_code),
                )


def _seed_suppliers(connection) -> None:
    for supplier in SUPPLIERS:
        connection.execute(
            """INSERT INTO supplier_master(
                 supplier_code,supplier_name,country,specialty,grade,quality_score,active_yn)
               VALUES(?,?,?,?,?,?,'Y') ON CONFLICT(supplier_code) DO UPDATE SET
                 supplier_name=excluded.supplier_name,country=excluded.country,
                 specialty=excluded.specialty,grade=excluded.grade,
                 quality_score=excluded.quality_score,active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
            supplier,
        )


def _seed_rule(connection, scenario: dict) -> None:
    rule_id = f"DC-R-{scenario['no']:03d}"
    rule_name = f"{scenario['reason']} {scenario['target_type']} suitability"
    connection.execute(
        """INSERT INTO rule_definitions(rule_id,rule_name,description)
           VALUES(?,?,?) ON CONFLICT(rule_id) DO UPDATE SET
             rule_name=excluded.rule_name,description=excluded.description,
             updated_at=CURRENT_TIMESTAMP""",
        (rule_id, rule_name, f"Design-change business sample rule for {scenario['source_name']}"),
    )
    connection.execute(
        """INSERT INTO rule_revisions(
             rule_id,revision_no,target_type,change_reason,evaluation_item,
             required_yn,weight,pass_score,conditional_score,valid_from,active_yn)
           VALUES(?,1,?,?,?,'Y',100,90,60,?,'Y')
           ON CONFLICT(rule_id,revision_no) DO UPDATE SET
             target_type=excluded.target_type,change_reason=excluded.change_reason,
             evaluation_item=excluded.evaluation_item,required_yn='Y',weight=100,
             pass_score=90,conditional_score=60,valid_from=excluded.valid_from,
             valid_to=NULL,active_yn='Y'""",
        (rule_id, scenario["target_type"], scenario["reason"], _rule_evaluation_item(scenario), AS_OF_DATE),
    )
    connection.execute("DELETE FROM rule_conditions WHERE rule_id=? AND revision_no=1", (rule_id,))
    for sequence, (attribute, operator, expected) in enumerate(scenario["conditions"], 1):
        connection.execute(
            """INSERT INTO rule_conditions(
                 rule_id,revision_no,condition_seq,attribute_name,operator,
                 expected_value,missing_result,fail_result,score)
               VALUES(?,1,?,?,?,?, 'CONDITIONAL','FAIL',100)""",
            (rule_id, sequence, attribute, operator, expected),
        )


def _seed_supplier_options(connection, candidate_code: str, scenario_no: int, candidate_no: int) -> None:
    base_price = 900 + scenario_no * 80 + candidate_no * 25
    options = (
        ("SUP-101" if scenario_no in {1, 2, 10} else "SUP-104", base_price * 1.03, 5 + candidate_no, "S" if candidate_no == 1 else "A", 97 - candidate_no, "Y", "AVAILABLE"),
        ("SUP-102" if scenario_no in {1, 2, 3, 6, 10} else "SUP-103", base_price * 0.98, 7 + candidate_no, "A", 94 - candidate_no, "N", "AVAILABLE"),
        ("SUP-105", base_price * 0.94, 10 + candidate_no, "B", 89 - candidate_no, "N", "STOPPED" if candidate_no == 5 else "AVAILABLE"),
    )
    for supplier_code, price, lead, quality, stability, primary, status in options:
        connection.execute(
            """INSERT INTO supplier_items(
                 supplier_code,item_code,unit_price,currency_code,lead_time_days,
                 quality_grade,stability_score,primary_yn,supply_status,valid_from)
               VALUES(?,?,?,'KRW',?,?,?,?,?,?)
               ON CONFLICT(supplier_code,item_code,valid_from) DO UPDATE SET
                 unit_price=excluded.unit_price,lead_time_days=excluded.lead_time_days,
                 quality_grade=excluded.quality_grade,stability_score=excluded.stability_score,
                 primary_yn=excluded.primary_yn,supply_status=excluded.supply_status,
                 valid_to=NULL,updated_at=CURRENT_TIMESTAMP""",
            (
                supplier_code,
                candidate_code,
                round(price, 2),
                lead,
                quality,
                stability,
                primary,
                status,
                AS_OF_DATE,
            ),
        )


def _seed_inventory(connection, candidate_code: str, candidate_no: int, locations: list[str]) -> None:
    on_hand = {1: 60, 2: 50, 3: 40, 4: 38, 5: 20}[candidate_no]
    for index, location_code in enumerate(locations):
        connection.execute(
            """INSERT INTO inventory_balances(
                 inventory_location_code,item_code,on_hand_quantity,reserved_quantity,
                 safety_stock,hold_quantity,incoming_quantity,incoming_date)
               VALUES(?,?,?,5,5,0,?,?)
               ON CONFLICT(inventory_location_code,item_code) DO UPDATE SET
                 on_hand_quantity=excluded.on_hand_quantity,
                 reserved_quantity=excluded.reserved_quantity,
                 safety_stock=excluded.safety_stock,hold_quantity=excluded.hold_quantity,
                 incoming_quantity=excluded.incoming_quantity,
                 incoming_date=excluded.incoming_date,updated_at=CURRENT_TIMESTAMP""",
            (location_code, candidate_code, on_hand + index % 2, 10 if candidate_no == 1 else 0, "2026-08-25"),
        )


def _seed_candidates(
    connection, scenario: dict, locations_by_plant: dict[str, list[str]]
) -> None:
    for candidate_no in range(1, 6):
        code = _candidate_code(scenario, candidate_no)
        name = _candidate_name(scenario, candidate_no)
        if scenario["target_type"] == "ASSY":
            _upsert_assembly(
                connection,
                code,
                scenario["process_name"],
                description=_assembly_description(
                    scenario["process_name"], scenario["attributes"]
                ),
            )
            component_code = f"0001-32{scenario['no']:02d}1{candidate_no}"
            _upsert_material(connection, component_code, f"{scenario['process_name']} CORE PART ALT-{candidate_no}", scenario["process_name"])
            plant_code = SCENARIO_PLANT_CODES[scenario["no"]]
            _upsert_bom(connection, plant_code, code, component_code, 10, 1)
        else:
            _upsert_material(connection, code, name, scenario["material_group"])

        candidate_attributes = dict(scenario["attributes"])
        missing_attribute = scenario["conditions"][-1][0]
        failed_attribute = scenario["conditions"][1][0]
        if candidate_no == 4:
            candidate_attributes.pop(missing_attribute, None)
        elif candidate_no == 5:
            operator = scenario["conditions"][1][1]
            candidate_attributes[failed_attribute] = 0 if operator in {"GE", "GT", "EQ"} else 999999
        candidate_attributes.update(
            {
                "lifecycle_status": "ACTIVE",
                "quality_score": 99 - candidate_no * 2,
                "unit_cost": 100 + scenario["no"] * 5 + candidate_no * 3,
            }
        )
        for attribute_name, value in candidate_attributes.items():
            _upsert_attribute(connection, code, attribute_name, value)

        if scenario["primary_action"] == "REPLACE":
            connection.execute(
                """INSERT INTO substitution_relations(
                     source_item_code,candidate_item_code,relation_type,priority,valid_from,active_yn)
                   VALUES(?,?,'REGISTERED',?,?,'Y')
                   ON CONFLICT(source_item_code,candidate_item_code,valid_from) DO UPDATE SET
                     relation_type='REGISTERED',priority=excluded.priority,valid_to=NULL,
                     active_yn='Y',updated_at=CURRENT_TIMESTAMP""",
                (scenario["source"], code, candidate_no, AS_OF_DATE),
            )
        _seed_supplier_options(connection, code, scenario["no"], candidate_no)
        plant_code = SCENARIO_PLANT_CODES[scenario["no"]]
        _seed_inventory(
            connection, code, candidate_no, locations_by_plant[plant_code]
        )


def _seed_process_path(
    connection,
    *,
    model_code: str,
    target_code: str,
    target_name: str,
    target_process: str,
    scenario_no: int,
    plant_code: str,
    model_spec: dict | None = None,
) -> None:
    """Create a hierarchy-valid VERSION→OLB→CP→BIN→LC path."""
    process_order = ("OLB", "CP", "BIN", "LC", "CF", "TFT")
    if target_process not in process_order:
        raise ValueError(f"Unsupported target process: {target_process}")
    process_index = process_order.index(target_process)
    parent = model_code
    for index, process in enumerate(process_order[: process_index + 1], 1):
        code = target_code if process == target_process else f"LJ94-33{scenario_no:02d}{index:02d}"
        _upsert_assembly(
            connection, code, process,
            description=_assembly_description(process, model_spec),
        )
        _upsert_bom(connection, plant_code, parent, code, 10, 1)
        parent = code


def _seed_scenario_bom(connection, scenario: dict) -> None:
    _upsert_version(connection, scenario, scenario["model"])
    plant_code = SCENARIO_PLANT_CODES[scenario["no"]]
    if scenario["target_type"] == "ASSY":
        usage_type = "COMMON" if scenario["no"] == 10 else "DEDICATED"
        _upsert_assembly(
            connection, scenario["source"], scenario["process_name"], usage_type,
            description=_assembly_description(
                scenario["process_name"], scenario["attributes"]
            ),
        )
        if scenario["parent"] == scenario["model"]:
            _upsert_bom(connection, plant_code, scenario["model"], scenario["source"], 10, 1)
        else:
            _seed_process_path(
                connection,
                model_code=scenario["model"],
                target_code=scenario["parent"],
                target_name=scenario["parent_name"],
                target_process=scenario["parent_name"],
                scenario_no=scenario["no"],
                plant_code=plant_code,
                model_spec=scenario.get("spec"),
            )
            _upsert_bom(connection, plant_code, scenario["parent"], scenario["source"], 10, 1)
    else:
        _seed_process_path(
            connection,
            model_code=scenario["model"],
            target_code=scenario["parent"],
            target_name=scenario["parent_name"],
            target_process=scenario["parent_name"],
            scenario_no=scenario["no"],
            plant_code=plant_code,
            model_spec=scenario.get("spec"),
        )
        _upsert_material(connection, scenario["source"], scenario["source_name"], scenario["material_group"])
        _upsert_bom(connection, plant_code, scenario["parent"], scenario["source"], 10, 1)

    # REPLACE/DELETE/QUANTITY_CHANGE scenarios compare an existing source item, so
    # the source carries the scenario's technical attributes.  ADD is different:
    # the scenario conditions describe the *new item family to discover*, not the
    # already-existing anchor material in the BOM.  Copying those attributes to
    # the anchor would incorrectly make it an ADD candidate (for example a BASE
    # BRACKET looking like an EMI SHIELD TAPE).
    source_attributes = {} if scenario.get("primary_action") == "ADD" else dict(scenario["attributes"])
    source_attributes["lifecycle_status"] = "EOL" if scenario["reason"] == "EOL" else "ACTIVE"
    for name, value in source_attributes.items():
        _upsert_attribute(connection, scenario["source"], name, value)

    if scenario.get("delete_item"):
        _upsert_material(connection, scenario["delete_item"], scenario["delete_item_name"], scenario["material_group"])
        _upsert_bom(
            connection, plant_code, scenario["parent"], scenario["delete_item"], 20, 2
        )

    if scenario.get("quantity_item"):
        _upsert_material(connection, scenario["quantity_item"], scenario["quantity_item_name"], "LC")
        _upsert_bom(
            connection, plant_code, scenario["quantity_parent"], scenario["quantity_item"], 10, 1
        )

    if scenario.get("shared_model"):
        _upsert_version(connection, scenario, scenario["shared_model"], suffix="002")
        _upsert_bom(
            connection, plant_code, scenario["shared_model"], scenario["source"], 10, 1
        )


def _seed_production_plans(connection, scenario: dict) -> None:
    versions = [scenario["model"]]
    if scenario.get("shared_model"):
        versions.append(scenario["shared_model"])
    plant_code = SCENARIO_PLANT_CODES[scenario["no"]]
    plan_by_plant = {
        "P01": ("2026-08-20", 120),
        "P02": ("2026-08-22", 80),
        "P03": ("2026-08-24", 100),
        "P04": ("2026-08-26", 90),
    }
    plan_date, quantity = plan_by_plant[plant_code]
    for version in versions:
        plan_id = f"PLAN-{version}-{plant_code}"
        connection.execute(
            """INSERT INTO production_plans(
                 plan_id,version_code,plant_code,plan_date,planned_quantity,status)
               VALUES(?,?,?,?,?,'CONFIRMED') ON CONFLICT(plan_id) DO UPDATE SET
                 version_code=excluded.version_code,plant_code=excluded.plant_code,
                 plan_date=excluded.plan_date,planned_quantity=excluded.planned_quantity,
                 status='CONFIRMED',updated_at=CURRENT_TIMESTAMP""",
            (plan_id, version, plant_code, plan_date, quantity),
        )


def seed_design_change_business_sample(database: SQLiteDatabase) -> None:
    """Extend the Display BOM with deterministic design-change business sample data."""
    SchemaManager(database).initialize()
    with database.transaction() as connection:
        _remove_existing_business_sample(connection)
        baseline = connection.execute(
            "SELECT 1 FROM version_master WHERE version_code='LTA400HR01-001'"
        ).fetchone()
        if not baseline:
            raise RuntimeError(
                "기준 모델 LTA400HR01-001이 없습니다. "
                "Canonical Seed DB를 기반으로 생성된 DB를 사용하세요."
            )
        locations_by_plant = _seed_organization(connection)
        _seed_cross_plant_query_fixtures(connection)
        _seed_suppliers(connection)
        _seed_baseline_operational_readiness(connection, locations_by_plant)
        for scenario in SCENARIOS:
            _seed_scenario_bom(connection, scenario)
            _seed_rule(connection, scenario)
            _seed_candidates(connection, scenario, locations_by_plant)
            _seed_production_plans(connection, scenario)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic design-change business sample data")
    parser.add_argument("--database", default=".pytest_tmp_runtime/test_display_bom.db")
    args = parser.parse_args()
    database = SQLiteDatabase(Path(args.database))
    seed_design_change_business_sample(database)
    print(f"Design-change business sample initialized: {args.database}")


if __name__ == "__main__":
    main()
