from __future__ import annotations

from datetime import date

from database import SQLiteDatabase
from repositories.common import iso_date


class SQLiteBomRepository:
    """SQLite의 FA-root BOM을 조회합니다. 내부 bom_id는 반환하지 않습니다."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_item(self, item_code: str) -> dict | None:
        with self.database.connection() as con:
            row = con.execute(
                """
                SELECT item_code,item_type,item_name,description,active_yn
                FROM item_master
                WHERE UPPER(item_code)=UPPER(?)
                """,
                (item_code,),
            ).fetchone()
        return dict(row) if row else None

    def get_plant(self, plant_code: str) -> dict | None:
        with self.database.connection() as con:
            row = con.execute(
                """SELECT plant_code,plant_name,country_code,active_yn
                   FROM plants WHERE UPPER(plant_code)=UPPER(?)""",
                (plant_code,),
            ).fetchone()
        return dict(row) if row else None

    def list_plants(
        self,
        reference_code: str | None = None,
        as_of_date: str | date | None = None,
    ) -> list[dict]:
        """Return active Plants, optionally scoped to where the target actually exists.

        VERSION: Plant must contain an active BOM rooted at the VERSION.
        ASSEMBLY: Plant must contain the ASSY as a BOM parent or child.
        MATERIAL: Plant must contain the material as a BOM child.

        If reference_code is absent, this returns
        all active Plants.  An unknown/resolved target returns an empty list rather
        than suggesting unrelated Plants.
        """
        normalized = str(reference_code or "").strip().upper()
        target = iso_date(as_of_date)
        with self.database.connection() as con:
            if not normalized:
                rows = con.execute(
                    """SELECT plant_code,plant_name,country_code,active_yn
                       FROM plants WHERE active_yn='Y' ORDER BY plant_code"""
                ).fetchall()
                return [dict(row) for row in rows]

            version_code = self.resolve_version_code(normalized)
            item_code = version_code or normalized
            item = con.execute(
                "SELECT item_code,item_type FROM item_master WHERE UPPER(item_code)=UPPER(?)",
                (item_code,),
            ).fetchone()
            if not item:
                return []

            item_type = str(item["item_type"] or "").upper()
            if item_type == "VERSION":
                relation_sql = "b.parent_item_code=?"
                params = [item_code]
            elif item_type == "ASSEMBLY":
                relation_sql = "(b.parent_item_code=? OR b.child_item_code=?)"
                params = [item_code, item_code]
            elif item_type == "MATERIAL":
                relation_sql = "b.child_item_code=?"
                params = [item_code]
            else:
                return []

            rows = con.execute(
                f"""SELECT DISTINCT p.plant_code,p.plant_name,p.country_code,p.active_yn
                    FROM plants p
                    JOIN bom_master b ON b.plant_code=p.plant_code
                    WHERE p.active_yn='Y' AND {relation_sql}
                      AND b.status='ACTIVE' AND b.valid_from<=?
                      AND (b.valid_to IS NULL OR b.valid_to>=?)
                    ORDER BY p.plant_code""",
                (*params, target, target),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_items(
        self, keyword: str, item_type: str | None = None
    ) -> list[dict]:
        pattern = f"%{keyword.strip().upper()}%"
        sql = """
            SELECT item_code,item_type,item_name,description,active_yn
            FROM item_master
            WHERE (UPPER(item_code) LIKE ? OR UPPER(item_name) LIKE ?)
        """
        params: list[str] = [pattern, pattern]
        if item_type:
            sql += " AND item_type=?"
            params.append(item_type.upper())
        sql += " ORDER BY item_code"
        with self.database.connection() as con:
            return [dict(row) for row in con.execute(sql, params)]

    def list_items(self, item_type: str | None = None) -> list[dict]:
        sql = "SELECT item_code,item_type,item_name,description,active_yn FROM item_master"
        params: tuple[str, ...] = ()
        if item_type:
            sql += " WHERE item_type=?"
            params = (item_type.upper(),)
        sql += " ORDER BY item_code"
        with self.database.connection() as con:
            return [dict(row) for row in con.execute(sql, params)]

    def resolve_version_code(self, value: str) -> str | None:
        with self.database.connection() as con:
            row = con.execute(
                """
                SELECT v.version_code
                FROM version_master v
                WHERE UPPER(v.version_code)=UPPER(?)
                   OR UPPER(COALESCE(json_extract(v.specification,'$.legacy_product_id'),''))=UPPER(?)
                LIMIT 1
                """,
                (value, value),
            ).fetchone()
        return row[0] if row else None

    def get_children(
        self,
        plant_code: str,
        parent_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]:
        target = iso_date(as_of_date)
        with self.database.connection() as con:
            rows = con.execute(
                """
                SELECT
                  b.parent_item_code,
                  p.item_name AS parent_item_name,
                  p.item_type AS parent_item_type,
                  b.child_item_code,
                  c.item_name AS child_item_name,
                  c.item_type AS child_item_type,
                  b.location_code,
                  b.sequence_no,
                  b.quantity,
                  b.valid_from,
                  b.valid_to,
                  b.status
                FROM bom_master b
                JOIN item_master p ON p.item_code=b.parent_item_code
                JOIN item_master c ON c.item_code=b.child_item_code
                WHERE UPPER(b.plant_code)=UPPER(?)
                  AND UPPER(b.parent_item_code)=UPPER(?)
                  AND b.status='ACTIVE'
                  AND b.valid_from <= ?
                  AND (b.valid_to IS NULL OR b.valid_to >= ?)
                ORDER BY b.sequence_no,b.child_item_code,b.location_code
                """,
                (plant_code, parent_code, target, target),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_tree(
        self,
        plant_code: str,
        root_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]:
        target = iso_date(as_of_date)
        with self.database.connection() as con:
            root = con.execute(
                """
                SELECT item_type FROM item_master
                WHERE UPPER(item_code)=UPPER(?)
                  AND item_type IN ('VERSION','ASSEMBLY')
                """,
                (root_code,),
            ).fetchone()
            if not root:
                return []
            rows = con.execute(
                """
                WITH RECURSIVE tree(
                  plant_code,parent_item_code,child_item_code,location_code,sequence_no,
                  quantity,valid_from,valid_to,status,level,bom_path,
                  required_quantity,visited
                ) AS (
                  SELECT
                    b.plant_code,b.parent_item_code,b.child_item_code,b.location_code,
                    b.sequence_no,b.quantity,b.valid_from,b.valid_to,b.status,
                    1,
                    b.parent_item_code || '/' || b.child_item_code,
                    b.quantity,
                    '|' || b.parent_item_code || '|' || b.child_item_code || '|'
                  FROM bom_master b
                  WHERE UPPER(b.plant_code)=UPPER(?)
                    AND UPPER(b.parent_item_code)=UPPER(?)
                    AND b.status='ACTIVE'
                    AND b.valid_from <= ?
                    AND (b.valid_to IS NULL OR b.valid_to >= ?)
                  UNION ALL
                  SELECT
                    b.plant_code,b.parent_item_code,b.child_item_code,b.location_code,
                    b.sequence_no,b.quantity,b.valid_from,b.valid_to,b.status,
                    tree.level + 1,
                    tree.bom_path || '/' || b.child_item_code,
                    tree.required_quantity * b.quantity,
                    tree.visited || b.child_item_code || '|'
                  FROM tree
                  JOIN bom_master b ON b.parent_item_code=tree.child_item_code
                    AND b.plant_code=tree.plant_code
                  WHERE b.status='ACTIVE'
                    AND b.valid_from <= ?
                    AND (b.valid_to IS NULL OR b.valid_to >= ?)
                    AND instr(tree.visited, '|' || b.child_item_code || '|')=0
                )
                SELECT
                  tree.parent_item_code,
                  tree.plant_code,
                  p.item_name AS parent_item_name,
                  p.item_type AS parent_item_type,
                  tree.child_item_code,
                  c.item_name AS child_item_name,
                  c.item_type AS child_item_type,
                  tree.location_code,
                  tree.sequence_no,
                  tree.quantity,
                  tree.valid_from,
                  tree.valid_to,
                  tree.status,
                  tree.level,
                  tree.bom_path,
                  tree.required_quantity
                FROM tree
                JOIN item_master p ON p.item_code=tree.parent_item_code
                JOIN item_master c ON c.item_code=tree.child_item_code
                ORDER BY tree.bom_path,tree.sequence_no,tree.location_code
                """,
                (plant_code, root_code, target, target, target, target),
            ).fetchall()
        return [dict(row) for row in rows]
    def get_parents_tree(
        self,
        plant_code: str,
        child_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]:
        """Return active reverse-BOM ancestors from child toward top VERSION roots."""
        target = iso_date(as_of_date)
        with self.database.connection() as con:
            rows = con.execute(
                """
                WITH RECURSIVE upward(
                  plant_code, child_item_code, parent_item_code, location_code, quantity,
                  valid_from, valid_to, level, bom_path, visited
                ) AS (
                  SELECT
                    b.plant_code,b.child_item_code,b.parent_item_code,b.location_code,b.quantity,
                    b.valid_from,b.valid_to,1,
                    b.child_item_code || ' <- ' || b.parent_item_code,
                    '|' || b.child_item_code || '|' || b.parent_item_code || '|'
                  FROM bom_master b
                  WHERE UPPER(b.plant_code)=UPPER(?)
                    AND UPPER(b.child_item_code)=UPPER(?)
                    AND b.status='ACTIVE'
                    AND b.valid_from<=?
                    AND (b.valid_to IS NULL OR b.valid_to>=?)
                  UNION ALL
                  SELECT
                    b.plant_code,upward.parent_item_code,b.parent_item_code,b.location_code,b.quantity,
                    b.valid_from,b.valid_to,upward.level+1,
                    upward.bom_path || ' <- ' || b.parent_item_code,
                    upward.visited || b.parent_item_code || '|'
                  FROM upward
                  JOIN bom_master b
                    ON b.plant_code=upward.plant_code
                   AND b.child_item_code=upward.parent_item_code
                  WHERE b.status='ACTIVE'
                    AND b.valid_from<=?
                    AND (b.valid_to IS NULL OR b.valid_to>=?)
                    AND instr(upward.visited, '|' || b.parent_item_code || '|')=0
                )
                SELECT
                  upward.plant_code,
                  upward.child_item_code,
                  c.item_name AS child_item_name,
                  c.item_type AS child_item_type,
                  upward.parent_item_code,
                  p.item_name AS parent_item_name,
                  p.description AS parent_description,
                  p.item_type AS parent_item_type,
                  upward.location_code,
                  upward.quantity,
                  upward.valid_from,
                  upward.valid_to,
                  upward.level,
                  upward.bom_path
                FROM upward
                JOIN item_master c ON c.item_code=upward.child_item_code
                JOIN item_master p ON p.item_code=upward.parent_item_code
                ORDER BY upward.bom_path, upward.level
                """,
                (plant_code, child_code, target, target, target, target),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_item_attributes(
        self,
        item_code: str,
        as_of_date: str | date | None = None,
    ) -> dict:
        target = iso_date(as_of_date)
        with self.database.connection() as con:
            rows = con.execute(
                """SELECT attribute_name,attribute_value,value_type,unit,source
                   FROM item_attribute_values
                   WHERE UPPER(item_code)=UPPER(?)
                     AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY attribute_name,valid_from""",
                (item_code, target, target),
            ).fetchall()
        values = {}
        for row in rows:
            value = row['attribute_value']
            if row['value_type'] == 'NUMBER' and value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    pass
            elif row['value_type'] == 'BOOLEAN' and value is not None:
                value = str(value).upper() in {'Y','TRUE','1'}
            values[row['attribute_name']] = {
                'value': value, 'value_type': row['value_type'],
                'unit': row['unit'], 'source': row['source'],
            }
        return values

    def get_version_detail(self, version_code: str) -> dict | None:
        with self.database.connection() as con:
            row = con.execute(
                """SELECT i.item_code,i.item_type,i.item_name,i.description,i.active_yn,
                          v.version_no,v.route_code,v.specification,v.active_yn AS version_active_yn
                   FROM item_master i
                   JOIN version_master v ON v.version_code=i.item_code
                   WHERE UPPER(i.item_code)=UPPER(?)""",
                (version_code,),
            ).fetchone()
        return dict(row) if row else None

    def get_material_detail(self, material_code: str) -> dict | None:
        with self.database.connection() as con:
            row = con.execute(
                """SELECT i.item_code,i.item_type,i.item_name,i.description,i.active_yn,
                          m.material_name,m.material_group,m.unit,m.supplier_code,m.specification,
                          m.active_yn AS material_active_yn
                   FROM item_master i
                   JOIN material_master m ON m.material_code=i.item_code
                   WHERE UPPER(i.item_code)=UPPER(?)""",
                (material_code,),
            ).fetchone()
        return dict(row) if row else None
    def get_assembly_detail(self, assembly_code: str) -> dict | None:
        with self.database.connection() as con:
            row = con.execute(
                """SELECT i.item_code,i.item_type,i.item_name,i.description,i.active_yn,
                          a.process_name,a.usage_type,a.specification,a.active_yn AS assembly_active_yn
                   FROM item_master i
                   JOIN assembly_master a ON a.assembly_code=i.item_code
                   WHERE UPPER(i.item_code)=UPPER(?)""",
                (assembly_code,),
            ).fetchone()
        return dict(row) if row else None

