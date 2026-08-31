from __future__ import annotations

from datetime import date

from database import SQLiteDatabase
from repositories.design_change_repository import SQLiteDesignChangeRepository


def iter_dynamic_replace_contexts(database: SQLiteDatabase):
    """Yield valid REPLACE contexts from current DB/metadata without fixture codes."""
    repository = SQLiteDesignChangeRepository(database)
    today = date.today().isoformat()

    with database.connection() as connection:
        sources = connection.execute(
            """
            SELECT DISTINCT r.source_item_code, i.item_type
            FROM substitution_relations r
            JOIN item_master i ON i.item_code=r.source_item_code
            WHERE r.active_yn='Y'
              AND i.active_yn='Y'
              AND r.valid_from<=?
              AND (r.valid_to IS NULL OR r.valid_to>=?)
            ORDER BY r.source_item_code
            """,
            (today, today),
        ).fetchall()
        reason_rows = connection.execute(
            """
            SELECT s.reason_code, s.target_type, a.alias_text, a.priority, a.alias_id
            FROM change_reason_scope s
            JOIN change_reason_alias a
              ON a.reason_code=s.reason_code AND a.active_yn='Y'
            WHERE s.active_yn='Y' AND s.action_type='REPLACE'
            ORDER BY s.reason_code, a.priority, a.alias_id
            """
        ).fetchall()

    for source in sources:
        target_type = (
            "ASSY" if source["item_type"] == "ASSEMBLY"
            else "MATERIAL" if source["item_type"] == "MATERIAL"
            else None
        )
        if target_type is None:
            continue

        reasons = []
        seen_reasons = set()
        for row in reason_rows:
            if row["target_type"] != target_type or row["reason_code"] in seen_reasons:
                continue
            reasons.append({
                "reason_code": row["reason_code"],
                "alias_text": row["alias_text"],
            })
            seen_reasons.add(row["reason_code"])

        with database.connection() as connection:
            plants = [
                row["plant_code"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT plant_code
                    FROM bom_master
                    WHERE child_item_code=?
                      AND status='ACTIVE'
                      AND valid_from<=?
                      AND (valid_to IS NULL OR valid_to>=?)
                    ORDER BY plant_code
                    """,
                    (source["source_item_code"], today, today),
                ).fetchall()
            ]

        for plant_code in plants:
            ancestors = repository.get_recursive_ancestors(
                source["source_item_code"], plant_code, today
            )
            for ancestor in ancestors:
                if ancestor["item_type"] != "VERSION":
                    continue

                relations = repository.find_version_source_relations(
                    version_code=ancestor["item_code"],
                    child_item_code=source["source_item_code"],
                    plant_code=plant_code,
                    as_of_date=today,
                )
                if len(relations) != 1:
                    continue

                yield {
                    "plant_code": plant_code,
                    "version_code": ancestor["item_code"],
                    "source_item_code": source["source_item_code"],
                    "target_type": target_type,
                    "relation": relations[0],
                    "reasons": reasons,
                }
