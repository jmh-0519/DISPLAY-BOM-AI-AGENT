from __future__ import annotations

from collections import Counter
from datetime import date
import uuid

from database import SQLiteDatabase
from repositories.sqlite_repository import SQLiteBomRepository
from services.repository_bom_service import RepositoryBomService
from services.sqlite_production_bom_service import SQLiteProductionBomService


class SQLiteDesignChangeWorkflowService:
    """SQLite-only design-change, review and reporting workflow.

    Every write is committed as one transaction.  Production BOM rows are only
    changed by ``SQLiteProductionBomService`` after an approved Review revision.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.repository = SQLiteBomRepository(database)
        self.bom = RepositoryBomService(self.repository)

    @staticmethod
    def _norm(value: str) -> str:
        return str(value).strip().upper()

    @staticmethod
    def _event_id() -> str:
        return f"EVT-{uuid.uuid4().hex[:12].upper()}"

    def analyze_replace(self, product_id: str, old_material_id: str,
                        new_material_id: str, as_of_date: str | None = None) -> dict:
        product = self._norm(product_id)
        old_code = self._norm(old_material_id)
        new_code = self._norm(new_material_id)
        if not product or not old_code or not new_code:
            raise ValueError("제품, 기존 자재, 신규 자재 코드는 필수입니다.")
        if old_code == new_code:
            raise ValueError("기존 자재와 신규 자재는 달라야 합니다.")

        checks: list[dict] = []
        version = self.repository.resolve_version_code(product)
        checks.append({"check": "PRODUCT_EXISTS", "status": "PASS" if version else "FAIL",
                       "message": f"대상 VERSION: {version or product}"})
        if not version:
            return self._analysis_result(product, old_code, new_code, checks)

        tree = self.repository.get_tree(version, as_of_date)
        targets = [row for row in tree if self._norm(row["child_item_code"]) == old_code]
        checks.append({"check": "OLD_MATERIAL_IN_BOM", "status": "PASS" if len(targets) == 1 else "FAIL",
                       "message": f"현재 BOM 대상 관계 {len(targets)}건"})
        new_item = self.repository.get_item(new_code)
        checks.append({"check": "NEW_MATERIAL_EXISTS", "status": "PASS" if new_item else "FAIL",
                       "message": f"신규 자재: {new_code}"})
        if new_item:
            checks.append({"check": "NEW_MATERIAL_LIFECYCLE",
                           "status": "PASS" if new_item["active_yn"] == "Y" else "FAIL",
                           "message": f"active_yn={new_item['active_yn']}"})
        if len(targets) == 1 and new_item:
            same_type = targets[0]["child_item_type"] == new_item["item_type"]
            checks.append({"check": "ITEM_TYPE_COMPATIBILITY", "status": "PASS" if same_type else "FAIL",
                           "message": f"{targets[0]['child_item_type']} → {new_item['item_type']}"})
            with self.database.connection() as con:
                incompatible = con.execute(
                    """SELECT result,reason FROM material_compatibility
                       WHERE source_item_code=? AND active_yn='Y'
                         AND ((target_type='VERSION' AND target_code=?)
                           OR (target_type='MATERIAL' AND target_code=?))
                       ORDER BY CASE result WHEN 'INCOMPATIBLE' THEN 1 WHEN 'CONDITIONAL' THEN 2 ELSE 3 END
                       LIMIT 1""", (new_code, version, old_code)).fetchone()
            status = "PASS"
            message = "등록된 부적합 호환성 조건 없음"
            if incompatible:
                status = {"COMPATIBLE": "PASS", "CONDITIONAL": "CONDITIONAL",
                          "INCOMPATIBLE": "FAIL"}[incompatible["result"]]
                message = incompatible["reason"] or incompatible["result"]
            checks.append({"check": "COMPATIBILITY", "status": status, "message": message})
        result = self._analysis_result(version, old_code, new_code, checks)
        if len(targets) == 1:
            result["target"] = targets[0]
        return result

    @staticmethod
    def _analysis_result(product: str, old_code: str, new_code: str,
                         checks: list[dict]) -> dict:
        statuses = {row["status"] for row in checks}
        result = "FAIL" if "FAIL" in statuses else "CONDITIONAL" if "CONDITIONAL" in statuses else "PASS"
        return {"success": result != "FAIL", "result": result, "product_id": product,
                "old_material_id": old_code, "new_material_id": new_code,
                "checks": checks, "production_bom_modified": False}

    def create_change_request(self, *, product_id: str, old_material_id: str,
                              new_material_id: str, reason: str, effective_date: str,
                              requested_by: str, as_of_date: str | None = None) -> dict:
        analysis = self.analyze_replace(product_id, old_material_id, new_material_id, as_of_date)
        if analysis["result"] == "FAIL":
            return {"success": False, "result": "ANALYSIS_FAILED", "analysis": analysis,
                    "production_bom_modified": False}
        target = analysis["target"]
        change_id = f"CHG-{date.today():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        with self.database.transaction() as con:
            old_revision = con.execute(
                """SELECT row_revision FROM bom_master WHERE parent_item_code=? AND
                   child_item_code=? AND location_code=? AND status='ACTIVE'
                   ORDER BY valid_from DESC LIMIT 1""",
                (target["parent_item_code"], self._norm(old_material_id), target["location_code"]),
            ).fetchone()
            con.execute("""INSERT INTO design_changes(
                change_id,version_code,change_type,requested_date,effective_date,reason,
                analysis_result,approval_status,apply_status,workflow_status,
                expected_bom_revision,requested_by)
                VALUES(?,?, 'REPLACE',?,?,?,?, 'AI_REVIEW_PENDING','REQUESTED','ANALYZED',?,?)""",
                (change_id, analysis["product_id"], date.today().isoformat(), effective_date,
                 str(reason).strip(), analysis["result"], old_revision[0] if old_revision else 1,
                 str(requested_by).strip()))
            con.execute("""INSERT INTO design_change_items(
                change_id,item_seq,action,parent_item_code,old_item_code,new_item_code,
                location_code,sequence_no,quantity,effective_date)
                VALUES(?,1,'REPLACE',?,?,?,?,?,?,?)""",
                (change_id, target["parent_item_code"], self._norm(old_material_id),
                 self._norm(new_material_id), target["location_code"], target["sequence_no"],
                 target["quantity"], effective_date))
            for seq, check in enumerate(analysis["checks"], 1):
                con.execute("""INSERT INTO design_change_checks(
                    change_id,item_seq,check_seq,check_type,target_code,result,blocking_yn,message)
                    VALUES(?,1,?,?,?,?,?,?)""", (change_id, seq, check["check"],
                    self._norm(new_material_id), check["status"],
                    "Y" if check["status"] == "FAIL" else "N", check["message"]))
            con.execute("""INSERT INTO workflow_events(event_id,change_id,event_type,
                to_status,actor_type,actor_id,reason) VALUES(?,?,'CHANGE_REQUESTED',
                'ANALYZED','USER',?,?)""", (self._event_id(), change_id, requested_by, reason))
        return {"success": True, "result": "CHANGE_REQUESTED", "change_id": change_id,
                "analysis": analysis, "production_bom_modified": False}

    def create_review_bom(self, *, change_id: str, created_by: str,
                          created_date: str) -> dict:
        change_code = self._norm(change_id)
        review_id = f"REV-{uuid.uuid4().hex[:10].upper()}"
        snapshot_id = f"SNP-{uuid.uuid4().hex[:10].upper()}"
        with self.database.transaction() as con:
            change = con.execute("SELECT * FROM design_changes WHERE change_id=?", (change_code,)).fetchone()
            item = con.execute("SELECT * FROM design_change_items WHERE change_id=? AND item_seq=1", (change_code,)).fetchone()
            if not change or not item:
                raise ValueError("SQLite 설계변경 요청 또는 변경 Item을 찾을 수 없습니다.")
            if con.execute("SELECT 1 FROM review_boms WHERE change_id=?", (change_code,)).fetchone():
                raise ValueError("이미 Review BOM이 생성된 설계변경입니다.")
            tree = self.repository.get_tree(change["version_code"], created_date)
            if not tree:
                raise ValueError("Review BOM을 생성할 Production BOM이 없습니다.")
            con.execute("INSERT INTO design_change_snapshots(snapshot_id,change_id,version_code,source_bom_revision) VALUES(?,?,?,?)",
                        (snapshot_id, change_code, change["version_code"], change["expected_bom_revision"] or 1))
            con.execute("""INSERT INTO review_boms(review_id,change_id,version_code,review_status,
                current_revision,created_by,created_at) VALUES(?,?,?,'CREATED',1,?,?)""",
                (review_id, change_code, change["version_code"], created_by, created_date))
            con.execute("INSERT INTO review_bom_revisions(review_id,revision_no,source,created_by,created_at) VALUES(?,1,'AI_PREVIEW',?,?)",
                        (review_id, created_by, created_date))
            for row in tree:
                is_target = (row["parent_item_code"] == item["parent_item_code"] and
                             row["child_item_code"] == item["old_item_code"] and
                             row["location_code"] == item["location_code"])
                child = item["new_item_code"] if is_target else row["child_item_code"]
                action = "REPLACE" if is_target else "KEEP"
                path = row["bom_path"]
                if is_target:
                    path = path.rsplit("/", 1)[0] + "/" + child
                values = (row["parent_item_code"], child, row["location_code"], row["sequence_no"],
                          row["quantity"], row["level"], path, row["required_quantity"], action)
                con.execute("""INSERT INTO design_change_snapshot_items(snapshot_id,parent_item_code,
                    child_item_code,location_code,sequence_no,quantity,level,bom_path,
                    required_quantity,change_action) VALUES(?,?,?,?,?,?,?,?,?,?)""", (snapshot_id, *values))
                con.execute("""INSERT INTO review_bom_items(review_id,revision_no,version_code,
                    parent_item_code,child_item_code,location_code,sequence_no,quantity,level,
                    bom_path,required_quantity,review_action,source,modified_yn,modified_by,modified_at)
                    VALUES(?,1,?,?,?,?,?,?,?,?,?,?,'AI_PREVIEW',?,?,?)""",
                    (review_id, change["version_code"], *values[:-1], action,
                     "Y" if is_target else "N", created_by if is_target else None,
                     created_date if is_target else None))
            con.execute("""UPDATE design_changes SET apply_status='IN_REVIEW',workflow_status='IN_REVIEW',
                updated_at=CURRENT_TIMESTAMP WHERE change_id=?""", (change_code,))
            con.execute("""INSERT INTO workflow_events(event_id,change_id,review_id,event_type,
                from_status,to_status,actor_type,actor_id) VALUES(?,?,?,'REVIEW_CREATED',
                'ANALYZED','IN_REVIEW','USER',?)""", (self._event_id(), change_code, review_id, created_by))
        return {"success": True, "result": "REVIEW_CREATED", "change_id": change_code,
                "review_id": review_id, "review_revision": 1, "current_revision": 1,
                "production_bom_modified": False}

    def run_ai_review(self, *, review_id: str, reviewed_by: str, checked_date: str) -> dict:
        review_code = self._norm(review_id)
        bom_review_id = f"AI-{uuid.uuid4().hex[:10].upper()}"
        with self.database.transaction() as con:
            review = con.execute("SELECT * FROM review_boms WHERE review_id=?", (review_code,)).fetchone()
            if not review:
                raise ValueError("SQLite Review BOM을 찾을 수 없습니다.")
            checks = con.execute("SELECT * FROM design_change_checks WHERE change_id=? ORDER BY check_seq",
                                 (review["change_id"],)).fetchall()
            statuses = {row["result"] for row in checks}
            result = "FAIL" if "FAIL" in statuses else "CONDITIONAL" if "CONDITIONAL" in statuses else "PASS"
            con.execute("""INSERT INTO bom_reviews(bom_review_id,review_id,revision_no,
                reviewer_type,result,reviewer_id,started_at,completed_at)
                VALUES(?,?,?,'AI',?,?,?,?)""", (bom_review_id, review_code,
                review["current_revision"], result, reviewed_by, checked_date, checked_date))
            for seq, row in enumerate(checks, 1):
                con.execute("""INSERT INTO bom_review_checks(bom_review_id,check_seq,check_type,
                    target_code,result,actual_value,expected_value,blocking_yn,message,checked_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""", (bom_review_id, seq, row["check_type"],
                    row["target_code"], row["result"], row["actual_value"], row["expected_value"],
                    row["blocking_yn"], row["message"], checked_date))
            if result == "FAIL":
                review_status, approval, apply_status, workflow = "RECHECK_REQUIRED", "AI_REVIEW_PENDING", "VALIDATION_FAILED", "VALIDATION_FAILED"
            else:
                review_status, approval, apply_status, workflow = "APPROVED", "APPROVED", "APPROVED_TO_APPLY", "APPROVED_TO_APPLY"
            con.execute("""UPDATE review_boms SET review_status=?,approved_revision=?,reviewed_by=?,
                decision_reason=?,updated_at=CURRENT_TIMESTAMP WHERE review_id=?""",
                (review_status, review["current_revision"] if result != "FAIL" else None,
                 reviewed_by, f"AI 검증 {result}", review_code))
            con.execute("""UPDATE design_changes SET approval_status=?,apply_status=?,workflow_status=?,
                approved_by=?,approved_at=?,updated_at=CURRENT_TIMESTAMP WHERE change_id=?""",
                (approval, apply_status, workflow, reviewed_by if result != "FAIL" else None,
                 checked_date if result != "FAIL" else None, review["change_id"]))
        rule_results = [{"check": row["check_type"], "check_type": row["check_type"],
                         "status": row["result"], "message": row["message"]} for row in checks]
        return {"success": result != "FAIL", "review_id": review_code,
                "review_revision": review["current_revision"], "ai_review_result": result,
                "rule_results": rule_results, "compatibility_results": [],
                "workflow_result": "AI_REVIEW_COMPLETED" if result != "FAIL" else "REVIEW_FAILED",
                "production_bom_modified": False,
                "next_step": "READY_TO_APPLY" if result != "FAIL" else "RECHECK_REQUIRED"}

    def generate_report(self, change_id: str) -> dict:
        change_code = self._norm(change_id)
        with self.database.connection() as con:
            change = con.execute("SELECT * FROM design_changes WHERE change_id=?", (change_code,)).fetchone()
            if not change:
                return {"success": False, "change_id": change_code, "message": "설계변경 정보를 찾을 수 없습니다."}
            items = [dict(row) for row in con.execute("SELECT * FROM design_change_items WHERE change_id=? ORDER BY item_seq", (change_code,))]
            review = con.execute("SELECT * FROM review_boms WHERE change_id=?", (change_code,)).fetchone()
            checks: list[dict] = []
            if review:
                checks = [dict(row) for row in con.execute("""SELECT c.* FROM bom_review_checks c
                    JOIN bom_reviews b ON b.bom_review_id=c.bom_review_id WHERE b.review_id=?
                    AND b.revision_no=? ORDER BY c.check_seq""",
                    (review["review_id"], review["approved_revision"] or review["current_revision"]))]
        mapped_items = [{"action": row["action"], "bom_parent": row["parent_item_code"],
                         "old_bom_child": row["old_item_code"], "new_bom_child": row["new_item_code"],
                         "location": row["location_code"], "quantity": row["quantity"]} for row in items]
        summary: dict[str, dict] = {}
        for check_type in {row["check_type"] for row in checks}:
            group = [row for row in checks if row["check_type"] == check_type]
            counts = Counter(row["result"] for row in group)
            status = "FAIL" if counts["FAIL"] else "CONDITIONAL" if counts["CONDITIONAL"] else "PASS"
            summary[check_type] = {"status": status, "count": len(group),
                                   "conditional_count": counts["CONDITIONAL"], "fail_count": counts["FAIL"]}
        review_dict = dict(review) if review else None
        if review_dict:
            review_dict["review_result"] = "FAIL" if any(x["result"] == "FAIL" for x in checks) else "PASS"
            review_dict["completed_date"] = review_dict.get("updated_at")
        return {"success": True, "change_id": change_code, "product_id": change["version_code"],
                "change": dict(change), "change_items": mapped_items, "change_bom": [],
                "review": review_dict, "report_revision": review["approved_revision"] if review else None,
                "review_revision_history": [], "approved_review_bom": [], "review_checks": checks,
                "review_check_summary": summary, "change_to_review_diff": [],
                "production_before_bom": [], "production_after_bom": [], "production_diff": [],
                "report_stage": "PRE_APPLY", "production_bom_modified": False}

    def apply_reviewed_bom(self, *, review_id: str, applied_by: str,
                           applied_date: str | None = None) -> dict:
        result = SQLiteProductionBomService(self.database).apply_approved_review(
            review_id=review_id, applied_by=applied_by, applied_date=applied_date)
        result["review_id"] = self._norm(review_id)
        return result
