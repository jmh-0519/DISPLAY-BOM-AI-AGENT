from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import Any

from database import SQLiteDatabase


class SQLiteDesignChangeRepository:
    """Design Change SQL/row mapping. Business decisions belong to services."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_item_attributes(self, item_code: str, as_of_date: str) -> dict[str, Any]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT attribute_name,attribute_value,value_type
                   FROM item_attribute_values
                   WHERE item_code=? AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY valid_from,attribute_name""",
                (item_code, as_of_date, as_of_date),
            ).fetchall()
        values: dict[str, Any] = {}
        for row in rows:
            value: Any = row["attribute_value"]
            if row["value_type"] == "NUMBER" and value is not None:
                value = float(value)
            elif row["value_type"] == "BOOLEAN" and value is not None:
                value = str(value).upper() in {"Y", "TRUE", "1"}
            values[row["attribute_name"]] = value
        return values

    def get_item_profile(self, item_code: str, as_of_date: str) -> dict[str, Any]:
        """Return generic master fields plus effective item attributes for comparison."""
        item = self.get_item(item_code)
        if not item:
            return {}
        profile: dict[str, Any] = {
            "item_name": item.get("item_name"),
            "description": item.get("description"),
        }
        with self.database.connection() as connection:
            if item["item_type"] == "MATERIAL":
                profile["material_name"] = item.get("item_name")
                row = connection.execute(
                    """SELECT material_group,unit,specification
                       FROM material_master WHERE material_code=?""",
                    (item_code,),
                ).fetchone()
                if row:
                    profile.update(dict(row))
            elif item["item_type"] == "ASSEMBLY":
                row = connection.execute(
                    """SELECT process_name,usage_type,specification
                       FROM assembly_master WHERE assembly_code=?""",
                    (item_code,),
                ).fetchone()
                if row:
                    profile.update(dict(row))
        profile.update(self.get_item_attributes(item_code, as_of_date))
        return {key: value for key, value in profile.items() if value not in {None, ""}}

    @staticmethod
    def _comparison_profile(profile: dict[str, Any]) -> dict[str, Any]:
        """Exclude commercial/status fields from functional similarity discovery."""
        excluded_tokens = (
            "status", "cost", "price", "quality", "lead", "inventory",
            "stock", "quantity", "supplier",
        )
        return {
            key: value for key, value in profile.items()
            if not any(token in key.lower() for token in excluded_tokens)
        }

    def find_registered_candidates(self, source_item_code: str, as_of_date: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT r.candidate_item_code,r.relation_type,r.priority,i.item_type
                   FROM substitution_relations r
                   JOIN item_master i ON i.item_code=r.candidate_item_code
                   WHERE r.source_item_code=? AND r.active_yn='Y'
                     AND r.valid_from<=? AND (r.valid_to IS NULL OR r.valid_to>=?)
                     AND i.active_yn='Y'
                   ORDER BY r.priority,r.candidate_item_code""",
                (source_item_code, as_of_date, as_of_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_attribute_candidates(
        self,
        source_item_code: str,
        target_type: str,
        as_of_date: str,
        limit: int = 50,
    ) -> list[dict]:
        """Discover candidates by generic master/attribute similarity.

        No product, material code, scenario ID, or pre-registered substitution is used
        as a branch condition. The source item's current master/profile drives the pool.
        """
        item_type = "ASSEMBLY" if target_type == "ASSY" else "MATERIAL"
        source_profile = self._comparison_profile(
            self.get_item_profile(source_item_code, as_of_date)
        )
        if not source_profile:
            return []

        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT item_code,item_type FROM item_master
                   WHERE item_type=? AND active_yn='Y' AND item_code<>?
                   ORDER BY item_code""",
                (item_type, source_item_code),
            ).fetchall()

        weights = {
            "item_name": 4.0, "material_group": 3.0,
            "process_name": 4.0, "specification": 4.0, "description": 1.0,
            "unit": 1.0, "usage_type": 1.0,
        }
        candidates = []
        for row in rows:
            candidate_code = row["item_code"]
            candidate_profile = self._comparison_profile(
                self.get_item_profile(candidate_code, as_of_date)
            )
            comparable = [
                key for key in source_profile
                if key in candidate_profile
            ]
            if not comparable:
                continue
            matched = [
                key for key in comparable
                if str(source_profile[key]).strip().upper()
                == str(candidate_profile[key]).strip().upper()
            ]
            matched_weight = sum(weights.get(key, 2.0) for key in matched)
            total_weight = sum(weights.get(key, 2.0) for key in comparable)
            strong_identity_fields = {
                "item_name", "process_name",
                "specification", "material_family",
            }
            if (
                matched_weight <= 0
                or total_weight <= 0
                or not strong_identity_fields.intersection(matched)
            ):
                continue
            similarity = round(matched_weight / total_weight * 100.0, 2)
            candidates.append({
                "candidate_item_code": candidate_code,
                "relation_type": "ATTRIBUTE_FALLBACK",
                "priority": 9999,
                "item_type": row["item_type"],
                "similarity_score": similarity,
                "matched_attributes": matched,
                "compared_attributes": comparable,
            })

        candidates.sort(key=lambda value: (
            -float(value["similarity_score"]),
            value["candidate_item_code"],
        ))
        return candidates[: int(limit)]

    def get_supplier_options(self, item_code: str, as_of_date: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT si.*,s.supplier_name,s.grade AS supplier_grade
                   FROM supplier_items si JOIN supplier_master s
                     ON s.supplier_code=si.supplier_code
                   WHERE si.item_code=? AND si.valid_from<=?
                     AND (si.valid_to IS NULL OR si.valid_to>=?)
                     AND s.active_yn='Y'
                   ORDER BY si.primary_yn DESC,si.stability_score DESC,si.unit_price""",
                (item_code, as_of_date, as_of_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_inventory(self, item_code: str, plant_code: str) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT b.*,l.warehouse_code,w.plant_code
                   FROM inventory_balances b
                   JOIN inventory_locations l USING(inventory_location_code)
                   JOIN warehouses w USING(warehouse_code)
                   WHERE b.item_code=? AND w.plant_code=?
                   ORDER BY w.plant_code,l.warehouse_code,
                     b.inventory_location_code""",
                (item_code, plant_code),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_production_demand(
        self, version_code: str, plant_code: str, as_of_date: str
    ) -> float | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT SUM(planned_quantity) AS quantity FROM production_plans
                   WHERE version_code=? AND plant_code=?
                     AND plan_date>=? AND status='CONFIRMED'""",
                (version_code, plant_code, as_of_date),
            ).fetchone()
        return float(row["quantity"]) if row and row["quantity"] is not None else None

    def find_add_candidate_items(
        self, *, target_type: str, as_of_date: str, limit: int = 500
    ) -> list[dict]:
        """Return active master items that may be considered for a generic ADD.

        Candidate eligibility is intentionally *not* decided here.  The repository
        only returns active items of the requested business type; RuleEngine and
        RecommendationService perform the actual suitability evaluation.  This keeps
        the runtime generic and avoids scenario/item-code branches.
        """
        expected_type = "ASSEMBLY" if str(target_type).upper() == "ASSY" else "MATERIAL"
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT item_code,item_type,item_name,description
                   FROM item_master
                   WHERE item_type=? AND active_yn='Y'
                   ORDER BY item_code
                   LIMIT ?""",
                (expected_type, int(limit)),
            ).fetchall()
        return [{
            "candidate_item_code": row["item_code"],
            "item_type": row["item_type"],
            "item_name": row["item_name"],
            "description": row["description"],
            "relation_type": "ADD_DISCOVERY",
            "priority": 999,
        } for row in rows]

    def get_active_rules(self, reasons: list[str], target_type: str, as_of_date: str) -> list[dict]:
        if not reasons:
            return []
        placeholders = ",".join("?" for _ in reasons)
        sql = f"""SELECT r.*,d.rule_name,d.description
                  FROM rule_revisions r JOIN rule_definitions d USING(rule_id)
                  WHERE r.change_reason IN ({placeholders})
                    AND r.target_type IN (?, 'ALL') AND r.active_yn='Y'
                    AND r.valid_from<=? AND (r.valid_to IS NULL OR r.valid_to>=?)
                  ORDER BY r.required_yn DESC,r.rule_id,r.revision_no DESC"""
        with self.database.connection() as connection:
            rows = connection.execute(
                sql, (*reasons, target_type, as_of_date, as_of_date),
            ).fetchall()
            results = []
            seen = set()
            for row in rows:
                key = row["rule_id"]
                if key in seen:
                    continue
                seen.add(key)
                item = dict(row)
                item["conditions"] = [dict(value) for value in connection.execute(
                    """SELECT * FROM rule_conditions WHERE rule_id=? AND revision_no=?
                       ORDER BY condition_seq""",
                    (row["rule_id"], row["revision_no"]),
                )]
                results.append(item)
        return results

    def list_active_reason_metadata(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM change_reason_master
                   WHERE active_yn='Y' ORDER BY reason_code"""
            ).fetchall()
        return [dict(row) for row in rows]

    def list_active_reason_aliases(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM change_reason_alias
                   WHERE active_yn='Y' ORDER BY priority,alias_id"""
            ).fetchall()
        return [dict(row) for row in rows]

    def is_reason_scope_allowed(
        self, *, reason_code: str, target_type: str, action_type: str
    ) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM change_reason_scope
                   WHERE reason_code=? AND target_type=? AND action_type=?
                     AND active_yn='Y'""",
                (reason_code, target_type, action_type),
            ).fetchone()
        return row is not None

    def validate_plant(self, plant_code: str) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT plant_code,plant_name,country_code,active_yn
                   FROM plants WHERE plant_code=? AND active_yn='Y'""",
                (plant_code,),
            ).fetchone()
        if not row:
            raise ValueError(f"활성 PLANT를 찾을 수 없습니다: {plant_code}")
        return dict(row)

    def create_request(
        self, request: dict, actions: list[dict],
        resolved_reasons: list | None = None,
    ) -> None:
        if len(actions) != 1:
            raise ValueError("Design Change Request must contain exactly one action")
        request = {"plant_code": "P01", **request}
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO change_requests(
                   request_id,plant_code,version_code,original_request,normalized_request,reasons_json,
                   as_of_date,effective_date,requested_by)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    request["request_id"], request["plant_code"], request["version_code"],
                    request.get("original_request"),
                    request.get("normalized_request"), json.dumps(request.get("reasons", [])),
                    request["as_of_date"], request["effective_date"], request["requested_by"],
                ),
            )
            for sequence, action in enumerate(actions, 1):
                connection.execute(
                    """INSERT INTO change_actions(
                       action_id,request_id,action_seq,plant_code,action_type,target_type,parent_item_code,
                       old_item_code,new_item_code,location_code,old_quantity,new_quantity)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        action["action_id"], request["request_id"], sequence,
                        request["plant_code"], action["action_type"], action["target_type"],
                        action["parent_item_code"],
                        action.get("old_item_code"), action.get("new_item_code"),
                        action.get("location_code", "N/A"), action.get("old_quantity"),
                        action.get("new_quantity"),
                    ),
                )
                if resolved_reasons is None:
                    continue
                action_reasons = resolved_reasons[sequence - 1]
                if isinstance(action_reasons, dict):
                    action_reasons = [action_reasons]
                for reason in action_reasons:
                    connection.execute(
                        """INSERT INTO change_action_reasons(
                           action_id,reason_code,raw_reason_text,llm_reason_code,
                           resolution_status,resolution_source,confidence,is_primary,
                           confirmed_by,evidence_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            action["action_id"], reason["reason_code"],
                            reason.get("raw_reason_text"), reason.get("llm_reason_code"),
                            reason["resolution_status"], reason["resolution_source"],
                            reason.get("confidence"), reason.get("is_primary", "N"),
                            reason.get("confirmed_by"), json.dumps(reason.get("evidence", {})),
                        ),
                    )

    def get_request(self, request_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM change_requests WHERE request_id=?", (request_id,),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["reasons"] = json.loads(result.pop("reasons_json"))
            result["actions"] = [dict(item) for item in connection.execute(
                "SELECT * FROM change_actions WHERE request_id=? ORDER BY action_seq",
                (request_id,),
            )]
            request_reason_order = {
                code: index for index, code in enumerate(result.get("reasons", []))
            }
            for action in result["actions"]:
                reason_rows = [dict(value) for value in connection.execute(
                    "SELECT * FROM change_action_reasons WHERE action_id=?",
                    (action["action_id"],),
                ).fetchall()]
                for value in reason_rows:
                    value["evidence"] = self._decode_json_field(
                        value.pop("evidence_json", None), {}
                    )
                reason_rows.sort(key=lambda value: (
                    0 if value.get("is_primary") == "Y" else 1,
                    request_reason_order.get(value.get("reason_code"), 999999),
                    str(value.get("reason_code") or ""),
                ))
                action["reasons"] = reason_rows
                action["primary_reason"] = next(
                    (value for value in reason_rows if value.get("is_primary") == "Y"), None
                )
                action["secondary_reasons"] = [
                    value for value in reason_rows if value.get("is_primary") != "Y"
                ]
        return result

    def get_action(self, action_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM change_actions WHERE action_id=?", (action_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_active_bom_relations(
        self,
        *,
        parent_item_code: str,
        child_item_code: str,
        location_code: str,
        plant_code: str,
        as_of_date: str,
    ) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM bom_master
                   WHERE plant_code=? AND parent_item_code=? AND child_item_code=? AND location_code=?
                     AND status='ACTIVE' AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY valid_from,bom_id""",
                (
                    plant_code, parent_item_code, child_item_code, location_code,
                    as_of_date, as_of_date,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_version_source_relations(
        self,
        *,
        version_code: str,
        child_item_code: str,
        as_of_date: str,
        plant_code: str,
    ) -> list[dict]:
        """Find direct source edges reachable from one product version."""
        with self.database.connection() as connection:
            rows = connection.execute(
                """WITH RECURSIVE tree(item_code,path,depth) AS (
                     SELECT ?, '|' || ? || '|', 0
                     UNION ALL
                     SELECT b.child_item_code,
                            tree.path || b.child_item_code || '|',
                            tree.depth + 1
                     FROM tree
                     JOIN bom_master b ON b.parent_item_code=tree.item_code
                       AND b.plant_code=?
                     WHERE b.status='ACTIVE' AND b.valid_from<=?
                       AND (b.valid_to IS NULL OR b.valid_to>=?)
                       AND tree.depth<50
                       AND instr(tree.path, '|' || b.child_item_code || '|')=0
                   )
                   SELECT DISTINCT b.*
                   FROM tree
                   JOIN bom_master b ON b.parent_item_code=tree.item_code
                     AND b.plant_code=?
                   WHERE b.child_item_code=? AND b.status='ACTIVE'
                     AND b.valid_from<=? AND (b.valid_to IS NULL OR b.valid_to>=?)
                   ORDER BY b.parent_item_code,b.location_code,b.valid_from,b.bom_id""",
                (
                    version_code,
                    version_code,
                    plant_code,
                    as_of_date,
                    as_of_date,
                    plant_code,
                    child_item_code,
                    as_of_date,
                    as_of_date,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_version_component_relations(
        self,
        *,
        version_code: str,
        plant_code: str,
        as_of_date: str,
    ) -> list[dict]:
        """Return every active BOM edge reachable from one product version.

        This is intentionally a generic BOM traversal.  It does not know about
        Design Change sample scenario IDs or special item codes and is therefore safe to
        use for model-wide opportunity discovery.
        """
        with self.database.connection() as connection:
            rows = connection.execute(
                """WITH RECURSIVE tree(item_code,path,depth) AS (
                     SELECT ?, '|' || ? || '|', 0
                     UNION ALL
                     SELECT b.child_item_code,
                            tree.path || b.child_item_code || '|',
                            tree.depth + 1
                     FROM tree
                     JOIN bom_master b ON b.parent_item_code=tree.item_code
                       AND b.plant_code=?
                     WHERE b.status='ACTIVE' AND b.valid_from<=?
                       AND (b.valid_to IS NULL OR b.valid_to>=?)
                       AND tree.depth<50
                       AND instr(tree.path, '|' || b.child_item_code || '|')=0
                   )
                   SELECT DISTINCT
                     b.bom_id,b.parent_item_code,b.child_item_code,b.location_code,
                     b.quantity,b.sequence_no,
                     i.item_type,i.item_name,i.description
                   FROM tree
                   JOIN bom_master b ON b.parent_item_code=tree.item_code
                     AND b.plant_code=?
                   JOIN item_master i ON i.item_code=b.child_item_code
                   WHERE b.status='ACTIVE' AND b.valid_from<=?
                     AND (b.valid_to IS NULL OR b.valid_to>=?)
                     AND i.active_yn='Y'
                   ORDER BY tree.depth,b.parent_item_code,b.sequence_no,b.bom_id""",
                (
                    version_code,
                    version_code,
                    plant_code,
                    as_of_date,
                    as_of_date,
                    plant_code,
                    as_of_date,
                    as_of_date,
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_action_evaluation_status(self, action_id: str, status: str) -> None:
        if status not in {"PASS", "CONDITIONAL", "FAIL"}:
            raise ValueError("Invalid action evaluation status")
        with self.database.transaction() as connection:
            updated = connection.execute(
                """UPDATE change_actions SET evaluation_status=?,
                   row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP
                   WHERE action_id=?""",
                (status, action_id),
            ).rowcount
            if updated != 1:
                raise ValueError("Change action not found")
            request_id = connection.execute(
                "SELECT request_id FROM change_actions WHERE action_id=?", (action_id,),
            ).fetchone()[0]
            connection.execute(
                """UPDATE change_requests SET row_revision=row_revision+1,
                   updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
                (request_id,),
            )

    def save_candidate_evaluations(self, action_id: str, evaluations: list[dict]) -> None:
        with self.database.transaction() as connection:
            action = connection.execute(
                "SELECT plant_code FROM change_actions WHERE action_id=?", (action_id,)
            ).fetchone()
            if not action:
                raise ValueError("Change action not found")
            plant_code = action["plant_code"]
            connection.execute("DELETE FROM candidate_rule_results WHERE candidate_id IN (SELECT candidate_id FROM candidate_evaluations WHERE action_id=?)", (action_id,))
            connection.execute("DELETE FROM candidate_evaluations WHERE action_id=?", (action_id,))
            for index, value in enumerate(evaluations, 1):
                candidate_id = f"{action_id}-C{index}"
                value["candidate_id"] = candidate_id
                value["action_id"] = action_id
                connection.execute(
                    """INSERT INTO candidate_evaluations(candidate_id,action_id,plant_code,candidate_item_code,
                       recommended_supplier_item_id,final_status,total_score,grade,rank_no,
                       missing_data_json,conditional_reasons_json,attribute_comparison_json,
                       inventory_result_json,supplier_evaluation_json,demand_context_json,impact_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (candidate_id, action_id, value.get("plant_code", plant_code), value["candidate_item_code"], value.get("recommended_supplier_item_id"),
                     value["status"], value["total_score"], value["grade"], value.get("rank"),
                     json.dumps(value.get("missing_data", [])), json.dumps(value.get("conditional_reasons", [])),
                     json.dumps(value.get("attribute_results", {})), json.dumps(value.get("inventory", {})),
                     json.dumps(value.get("supplier_evaluation", {})), json.dumps(value.get("demand", {})),
                     json.dumps(value.get("impact", {}))),
                )
                for sequence, rule in enumerate(value.get("rule_results", []), 1):
                    connection.execute(
                        """INSERT INTO candidate_rule_results(candidate_id,result_seq,rule_id,
                           rule_revision,rule_snapshot_json,status,raw_score,weight,weighted_score,evidence_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (candidate_id, sequence, rule["rule_id"], rule["revision_no"],
                         json.dumps(value.get("rule_snapshots", [])[sequence - 1]),
                         str(rule["status"]), rule["raw_score"], rule["weight"],
                         rule["raw_score"] * rule["weight"], json.dumps(rule.get("evidence", {}))),
                    )
            statuses = {value["status"] for value in evaluations}
            overall = (
                "PASS" if "PASS" in statuses else
                "CONDITIONAL" if "CONDITIONAL" in statuses else "FAIL"
            )
            connection.execute(
                """UPDATE change_actions SET evaluation_status=?,
                   row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP WHERE action_id=?""",
                (overall, action_id),
            )
            request_id = connection.execute("SELECT request_id FROM change_actions WHERE action_id=?", (action_id,)).fetchone()[0]
            connection.execute(
                """UPDATE change_requests SET workflow_status='CANDIDATES_EVALUATED',
                   row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
                (request_id,),
            )

    def list_candidate_evaluations(self, action_id: str) -> list[dict]:
        with self.database.connection() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM candidate_evaluations WHERE action_id=? ORDER BY final_status,rank_no",
                (action_id,),
            )]


    @staticmethod
    def _decode_json_field(value, default):
        if value in {None, ""}:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def get_candidate_evaluation_detail(
        self,
        *,
        request_id: str,
        candidate_item_code: str,
        action_id: str | None = None,
    ) -> dict | None:
        """Return one persisted candidate evaluation with decoded evidence.

        This is a read-only explainability query. It never recomputes or mutates
        the candidate decision itself.
        """
        sql = """SELECT c.*,a.request_id,a.action_type,a.target_type,a.parent_item_code,
                        a.old_item_code,a.new_item_code,a.location_code,a.old_quantity,a.new_quantity
                 FROM candidate_evaluations c
                 JOIN change_actions a ON a.action_id=c.action_id
                 WHERE a.request_id=? AND c.candidate_item_code=?"""
        params: list = [request_id, candidate_item_code]
        if action_id:
            sql += " AND c.action_id=?"
            params.append(action_id)
        sql += " ORDER BY c.action_id,c.candidate_id"
        with self.database.connection() as connection:
            rows = connection.execute(sql, params).fetchall()
            if not rows:
                return None
            if len(rows) > 1 and not action_id:
                return {
                    "ambiguous": True,
                    "request_id": request_id,
                    "candidate_item_code": candidate_item_code,
                    "action_ids": [row["action_id"] for row in rows],
                }
            row = dict(rows[0])
            rule_rows = [dict(value) for value in connection.execute(
                """SELECT * FROM candidate_rule_results
                   WHERE candidate_id=? ORDER BY result_seq""",
                (row["candidate_id"],),
            ).fetchall()]
            supplier = None
            if row.get("recommended_supplier_item_id") is not None:
                supplier_row = connection.execute(
                    """SELECT si.*,s.supplier_name,s.grade AS supplier_grade
                       FROM supplier_items si JOIN supplier_master s
                         ON s.supplier_code=si.supplier_code
                       WHERE si.supplier_item_id=?""",
                    (row["recommended_supplier_item_id"],),
                ).fetchone()
                supplier = dict(supplier_row) if supplier_row else None
        row["missing_data"] = self._decode_json_field(row.pop("missing_data_json", None), [])
        row["conditional_reasons"] = self._decode_json_field(
            row.pop("conditional_reasons_json", None), []
        )
        row["attribute_results"] = self._decode_json_field(
            row.pop("attribute_comparison_json", None), []
        )
        row["inventory"] = self._decode_json_field(row.pop("inventory_result_json", None), {})
        row["supplier_evaluation"] = self._decode_json_field(
            row.pop("supplier_evaluation_json", None), {}
        )
        row["demand_context"] = self._decode_json_field(
            row.pop("demand_context_json", None), {}
        )
        row["impact"] = self._decode_json_field(row.pop("impact_json", None), {})
        for rule in rule_rows:
            rule["rule_snapshot"] = self._decode_json_field(
                rule.pop("rule_snapshot_json", None), {}
            )
            rule["evidence"] = self._decode_json_field(
                rule.pop("evidence_json", None), {}
            )
        row["rule_results"] = rule_rows
        row["recommended_supplier"] = supplier
        return row

    def list_request_candidate_evaluations(self, request_id: str) -> list[dict]:
        """Return persisted candidate rows for all actions in one request."""
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT c.*,a.action_type,a.target_type,a.parent_item_code,
                          a.old_item_code,a.new_item_code,a.location_code,a.old_quantity,a.new_quantity
                   FROM candidate_evaluations c
                   JOIN change_actions a ON a.action_id=c.action_id
                   WHERE a.request_id=?
                   ORDER BY a.action_seq,
                     CASE c.final_status WHEN 'PASS' THEN 0 WHEN 'CONDITIONAL' THEN 1 ELSE 2 END,
                     c.rank_no,c.total_score DESC,c.candidate_item_code""",
                (request_id,),
            ).fetchall()
        results = []
        for source in rows:
            row = dict(source)
            row["missing_data"] = self._decode_json_field(row.pop("missing_data_json", None), [])
            row["conditional_reasons"] = self._decode_json_field(
                row.pop("conditional_reasons_json", None), []
            )
            row["attribute_results"] = self._decode_json_field(
                row.pop("attribute_comparison_json", None), []
            )
            row["inventory"] = self._decode_json_field(
                row.pop("inventory_result_json", None), {}
            )
            row["supplier_evaluation"] = self._decode_json_field(
                row.pop("supplier_evaluation_json", None), {}
            )
            row["demand_context"] = self._decode_json_field(
                row.pop("demand_context_json", None), {}
            )
            row["impact"] = self._decode_json_field(row.pop("impact_json", None), {})
            results.append(row)
        return results

    def has_approved_exception(self, request_id: str) -> bool:
        """Return whether a CONDITIONAL exception approval already exists."""
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT 1 FROM change_approvals
                   WHERE request_id=? AND approval_stage='CONDITIONAL_EXCEPTION'
                     AND decision='APPROVED' AND TRIM(COALESCE(decision_reason,''))<>''
                   LIMIT 1""",
                (request_id,),
            ).fetchone()
        return row is not None

    def record_approval(
        self, *, request_id: str, approval_id: str, stage: str, decision: str,
        approved_by: str, reason: str | None = None, selection: dict | None = None,
    ) -> dict:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO change_approvals(approval_id,request_id,approval_stage,decision,
                   decision_reason,selection_json,approved_by) VALUES(?,?,?,?,?,?,?)""",
                (approval_id, request_id, stage, decision, reason, json.dumps(selection or {}), approved_by),
            )
            if stage == "CANDIDATE":
                status = "APPROVED" if decision == "APPROVED" else "REJECTED"
                workflow = "CANDIDATE_APPROVED" if decision == "APPROVED" else "BLOCKED"
                connection.execute(
                    "UPDATE change_requests SET candidate_approval_status=?,workflow_status=? WHERE request_id=?",
                    (status, workflow, request_id),
                )
            elif stage == "FINAL_APPLY":
                status = "APPROVED" if decision == "APPROVED" else "REJECTED"
                workflow = "FINAL_APPROVED" if decision == "APPROVED" else "BLOCKED"
                connection.execute(
                    "UPDATE change_requests SET final_approval_status=?,workflow_status=? WHERE request_id=?",
                    (status, workflow, request_id),
                )
        return {"approval_id": approval_id, "stage": stage, "decision": decision}

    def select_candidate(self, action_id: str, candidate_id: str, supplier_item_id: int | None) -> dict:
        with self.database.transaction() as connection:
            candidate = connection.execute(
                "SELECT * FROM candidate_evaluations WHERE candidate_id=? AND action_id=?",
                (candidate_id, action_id),
            ).fetchone()
            if not candidate or candidate["final_status"] == "FAIL":
                raise ValueError("PASS or CONDITIONAL candidate is required")
            if supplier_item_id is not None:
                supplier = connection.execute(
                    "SELECT 1 FROM supplier_items WHERE supplier_item_id=? AND item_code=?",
                    (supplier_item_id, candidate["candidate_item_code"]),
                ).fetchone()
                if not supplier:
                    raise ValueError("Supplier does not supply the selected candidate")
            connection.execute(
                """UPDATE change_actions SET selected_candidate_id=?,selected_supplier_item_id=?,
                   new_item_code=?,evaluation_status=?,row_revision=row_revision+1,
                   updated_at=CURRENT_TIMESTAMP WHERE action_id=?""",
                (candidate_id, supplier_item_id, candidate["candidate_item_code"], candidate["final_status"], action_id),
            )
            request_id = connection.execute(
                "SELECT request_id FROM change_actions WHERE action_id=?", (action_id,),
            ).fetchone()[0]
            connection.execute(
                """UPDATE change_requests SET row_revision=row_revision+1,
                   updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
                (request_id,),
            )
        return {"action_id": action_id, "candidate_id": candidate_id, "supplier_item_id": supplier_item_id}

    def select_candidates_atomically(self, request_id: str, selections: list[dict]) -> list[dict]:
        results = []
        with self.database.transaction() as connection:
            for selection in selections:
                candidate = connection.execute(
                    """SELECT c.* FROM candidate_evaluations c
                       JOIN change_actions a ON a.action_id=c.action_id
                       WHERE c.candidate_id=? AND c.action_id=? AND a.request_id=?""",
                    (selection["candidate_id"], selection["action_id"], request_id),
                ).fetchone()
                if not candidate or candidate["final_status"] == "FAIL":
                    raise ValueError("PASS or CONDITIONAL candidate from this request is required")
                supplier_item_id = selection.get("supplier_item_id")
                if supplier_item_id is not None:
                    supplier = connection.execute(
                        "SELECT 1 FROM supplier_items WHERE supplier_item_id=? AND item_code=?",
                        (supplier_item_id, candidate["candidate_item_code"]),
                    ).fetchone()
                    if not supplier:
                        raise ValueError("Supplier does not supply the selected candidate")
                connection.execute(
                    """UPDATE change_actions SET selected_candidate_id=?,
                       selected_supplier_item_id=?,new_item_code=?,evaluation_status=?,
                       row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP
                       WHERE action_id=? AND request_id=?""",
                    (
                        candidate["candidate_id"], supplier_item_id,
                        candidate["candidate_item_code"], candidate["final_status"],
                        selection["action_id"], request_id,
                    ),
                )
                results.append({
                    "action_id": selection["action_id"],
                    "candidate_id": candidate["candidate_id"],
                    "supplier_item_id": supplier_item_id,
                })
            connection.execute(
                """UPDATE change_requests SET row_revision=row_revision+1,
                   updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
                (request_id,),
            )
        return results


    def list_rules(self, as_of_date: str | None = None) -> list[dict]:
        sql = """SELECT d.*,r.* FROM rule_definitions d JOIN rule_revisions r USING(rule_id)"""
        params: tuple = ()
        if as_of_date:
            sql += " WHERE r.valid_from<=? AND (r.valid_to IS NULL OR r.valid_to>=?)"
            params = (as_of_date, as_of_date)
        sql += " ORDER BY d.rule_id,r.revision_no DESC"
        with self.database.connection() as connection:
            return [dict(row) for row in connection.execute(sql, params)]

    def create_rule_revision(self, rule: dict, conditions: list[dict]) -> dict:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO rule_definitions(rule_id,rule_name,description) VALUES(?,?,?)",
                (rule["rule_id"], rule["rule_name"], rule.get("description")),
            )
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision_no),0)+1 FROM rule_revisions WHERE rule_id=?",
                (rule["rule_id"],),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO rule_revisions(rule_id,revision_no,target_type,change_reason,
                   evaluation_item,required_yn,weight,valid_from,valid_to,active_yn)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (rule["rule_id"], revision, rule["target_type"], rule["change_reason"],
                 rule["evaluation_item"], rule.get("required_yn", "N"), rule["weight"],
                 rule["valid_from"], rule.get("valid_to"), rule.get("active_yn", "N")),
            )
            for sequence, condition in enumerate(conditions, 1):
                connection.execute(
                    """INSERT INTO rule_conditions(rule_id,revision_no,condition_seq,
                       attribute_name,operator,expected_value,missing_result,fail_result,score)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (rule["rule_id"], revision, sequence, condition["attribute_name"],
                     condition["operator"], condition.get("expected_value"),
                     condition.get("missing_result", "CONDITIONAL"),
                     condition.get("fail_result", "FAIL"), condition.get("score", 100)),
                )
        return {"rule_id": rule["rule_id"], "revision_no": revision}

    def deactivate_rule(self, rule_id: str, revision_no: int) -> None:
        with self.database.transaction() as connection:
            updated = connection.execute(
                "UPDATE rule_revisions SET active_yn='N' WHERE rule_id=? AND revision_no=?",
                (rule_id, revision_no),
            ).rowcount
            if updated != 1:
                raise ValueError("Rule revision not found")

    def list_change_requests(self) -> list[dict]:
        with self.database.connection() as connection:
            return [dict(row) for row in connection.execute(
                """SELECT request_id,plant_code,version_code,original_request,reasons_json,
                   requested_by,workflow_status,candidate_approval_status,
                   final_approval_status,apply_status,created_at,updated_at
                   FROM change_requests ORDER BY created_at DESC"""
            )]

    def record_performance(self, request_id: str, measurement_day: int,
                           outcome: dict, user_rating: int | None, measured_at: str) -> dict:
        outcome_id = f"OUT-{uuid.uuid4().hex[:12].upper()}"
        with self.database.transaction() as connection:
            request = connection.execute(
                "SELECT apply_status FROM change_requests WHERE request_id=?", (request_id,),
            ).fetchone()
            if not request or request["apply_status"] != "APPLIED":
                raise ValueError("Only applied requests can receive performance outcomes")
            connection.execute(
                """INSERT INTO performance_outcomes(outcome_id,request_id,measurement_day,
                   outcome_json,user_rating,measured_at) VALUES(?,?,?,?,?,?)""",
                (outcome_id, request_id, measurement_day, json.dumps(outcome), user_rating, measured_at),
            )
        return {"outcome_id": outcome_id, "request_id": request_id,
                "measurement_day": measurement_day}

    def get_training_records(self, date_from: str | None, date_to: str | None) -> list[dict]:
        sql = "SELECT * FROM change_requests WHERE 1=1"
        params = []
        if date_from:
            sql += " AND date(created_at)>=date(?)"
            params.append(date_from)
        if date_to:
            sql += " AND date(created_at)<=date(?)"
            params.append(date_to)
        sql += " ORDER BY request_id"
        records = []
        with self.database.connection() as connection:
            for request in connection.execute(sql, params):
                item = dict(request)
                item["actions"] = [dict(row) for row in connection.execute(
                    "SELECT * FROM change_actions WHERE request_id=? ORDER BY action_seq",
                    (request["request_id"],),
                )]
                item["approvals"] = [dict(row) for row in connection.execute(
                    "SELECT approval_stage,decision,decision_reason FROM change_approvals WHERE request_id=?",
                    (request["request_id"],),
                )]
                item["outcomes"] = [dict(row) for row in connection.execute(
                    "SELECT measurement_day,outcome_json,user_rating FROM performance_outcomes WHERE request_id=?",
                    (request["request_id"],),
                )]
                records.append(item)
        return records

    def save_dataset_export(self, export_id: str, date_from: str | None, date_to: str | None,
                            record_count: int, checksum: str, created_by: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO dataset_exports(export_id,date_from,date_to,record_count,
                   checksum,created_by) VALUES(?,?,?,?,?,?)""",
                (export_id, date_from, date_to, record_count, checksum, created_by),
            )

    def get_item(self, item_code: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM item_master WHERE item_code=?", (item_code,),
            ).fetchone()
        return dict(row) if row else None

    def get_recursive_ancestors(
        self, item_code: str, plant_code: str, as_of_date: str
    ) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """WITH RECURSIVE ancestors(item_code,item_type,path,depth) AS (
                     SELECT b.parent_item_code,p.item_type,
                            b.parent_item_code || '/' || b.child_item_code,1
                     FROM bom_master b JOIN item_master p ON p.item_code=b.parent_item_code
                     WHERE b.plant_code=? AND b.child_item_code=?
                       AND b.status='ACTIVE' AND b.valid_from<=?
                       AND (b.valid_to IS NULL OR b.valid_to>=?)
                     UNION ALL
                     SELECT b.parent_item_code,p.item_type,
                            b.parent_item_code || '/' || a.path,a.depth+1
                     FROM ancestors a JOIN bom_master b ON b.child_item_code=a.item_code
                       AND b.plant_code=?
                     JOIN item_master p ON p.item_code=b.parent_item_code
                     WHERE b.status='ACTIVE' AND b.valid_from<=?
                       AND (b.valid_to IS NULL OR b.valid_to>=?)
                       AND instr('/' || a.path || '/', '/' || b.parent_item_code || '/')=0
                   ) SELECT DISTINCT item_code,item_type,path,depth FROM ancestors
                   ORDER BY depth,item_code""",
                (plant_code, item_code, as_of_date, as_of_date,
                 plant_code, as_of_date, as_of_date),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_preview(
        self,
        *,
        request_id: str,
        validation_status: str,
        snapshot: dict,
        impacts: list[dict],
        created_by: str,
        plant_code: str,
    ) -> dict:
        preview_id = f"PRE-{uuid.uuid4().hex[:12].upper()}"
        with self.database.transaction() as connection:
            revision = connection.execute(
                "SELECT COALESCE(MAX(preview_revision),0)+1 FROM change_previews WHERE request_id=?",
                (request_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO change_previews(preview_id,request_id,plant_code,preview_revision,
                   validation_status,snapshot_json,created_by) VALUES(?,?,?,?,?,?,?)""",
                (preview_id, request_id, plant_code, revision, validation_status,
                 json.dumps(snapshot), created_by),
            )
            connection.execute("DELETE FROM change_impacts WHERE request_id=?", (request_id,))
            for impact in impacts:
                connection.execute(
                    """INSERT INTO change_impacts(request_id,action_id,plant_code,impacted_item_code,
                       impact_type,impact_path) VALUES(?,?,?,?,?,?)""",
                    (
                        request_id, impact["action_id"], plant_code,
                        impact["impacted_item_code"],
                        impact["impact_type"], impact["impact_path"],
                    ),
                )
            connection.execute(
                """UPDATE change_requests SET workflow_status='WAITING_FINAL_APPROVAL',
                   updated_at=CURRENT_TIMESTAMP WHERE request_id=?""",
                (request_id,),
            )
        return {"preview_id": preview_id, "preview_revision": revision}

    def connection(self) -> sqlite3.Connection:
        """Return a transaction-capable connection for Unit-of-Work composition."""
        return self.database.connect()
