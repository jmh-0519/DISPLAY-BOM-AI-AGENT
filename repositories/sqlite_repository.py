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
                WHERE UPPER(b.parent_item_code)=UPPER(?)
                  AND b.status='ACTIVE'
                  AND b.valid_from <= ?
                  AND (b.valid_to IS NULL OR b.valid_to >= ?)
                ORDER BY b.sequence_no,b.child_item_code,b.location_code
                """,
                (parent_code, target, target),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_tree(
        self,
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
                  parent_item_code,child_item_code,location_code,sequence_no,
                  quantity,valid_from,valid_to,status,level,bom_path,
                  required_quantity,visited
                ) AS (
                  SELECT
                    b.parent_item_code,b.child_item_code,b.location_code,
                    b.sequence_no,b.quantity,b.valid_from,b.valid_to,b.status,
                    1,
                    b.parent_item_code || '/' || b.child_item_code,
                    b.quantity,
                    '|' || b.parent_item_code || '|' || b.child_item_code || '|'
                  FROM bom_master b
                  WHERE UPPER(b.parent_item_code)=UPPER(?)
                    AND b.status='ACTIVE'
                    AND b.valid_from <= ?
                    AND (b.valid_to IS NULL OR b.valid_to >= ?)
                  UNION ALL
                  SELECT
                    b.parent_item_code,b.child_item_code,b.location_code,
                    b.sequence_no,b.quantity,b.valid_from,b.valid_to,b.status,
                    tree.level + 1,
                    tree.bom_path || '/' || b.child_item_code,
                    tree.required_quantity * b.quantity,
                    tree.visited || b.child_item_code || '|'
                  FROM tree
                  JOIN bom_master b ON b.parent_item_code=tree.child_item_code
                  WHERE b.status='ACTIVE'
                    AND b.valid_from <= ?
                    AND (b.valid_to IS NULL OR b.valid_to >= ?)
                    AND instr(tree.visited, '|' || b.child_item_code || '|')=0
                )
                SELECT
                  tree.parent_item_code,
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
                (root_code, target, target, target, target),
            ).fetchall()
        return [dict(row) for row in rows]
