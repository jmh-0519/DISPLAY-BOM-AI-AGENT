from __future__ import annotations

from datetime import date, timedelta
import uuid

from database import SQLiteDatabase
from repositories.unit_of_work import SQLiteUnitOfWork


class ProductionBomConflictError(RuntimeError):
    pass


class SQLiteProductionBomService:
    """승인 완료된 자재 교체를 단일 SQLite Transaction으로 적용합니다."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def apply_approved_review(
        self, *, review_id: str, applied_by: str, applied_date: str | date | None = None
    ) -> dict:
        """승인 Review를 재검증하고 해당 교체 Item을 Production에 적용합니다."""
        effective_override = date.fromisoformat(str(applied_date)) if applied_date else None
        with self.database.connection() as con:
            review = con.execute(
                """SELECT r.review_id,r.change_id,r.version_code,r.review_status,
                r.current_revision,r.approved_revision,c.effective_date,c.apply_status
                FROM review_boms r JOIN design_changes c ON c.change_id=r.change_id
                WHERE UPPER(r.review_id)=UPPER(?)""",
                (review_id,),
            ).fetchone()
            if not review:
                raise ValueError("SQLite 품평회 정보를 찾을 수 없습니다.")
            if review["review_status"] != "APPROVED":
                raise ValueError("APPROVED 품평회만 Production에 적용할 수 있습니다.")
            if review["approved_revision"] is None or review["approved_revision"] != review["current_revision"]:
                raise ValueError("현재 Review Revision이 최종 승인 Revision과 일치하지 않습니다.")
            blocking = con.execute(
                """SELECT COUNT(*) FROM bom_review_checks bc
                JOIN bom_reviews br ON br.bom_review_id=bc.bom_review_id
                WHERE br.review_id=? AND br.revision_no=?
                  AND bc.blocking_yn='Y' AND bc.result='FAIL'""",
                (review["review_id"], review["approved_revision"]),
            ).fetchone()[0]
            if blocking:
                raise ValueError("차단 품평 항목이 있어 Production 적용을 중단했습니다.")
            items = con.execute(
                """SELECT * FROM design_change_items
                WHERE change_id=? AND action='REPLACE' ORDER BY item_seq""",
                (review["change_id"],),
            ).fetchall()
            if len(items) != 1:
                raise ValueError("적용 가능한 REPLACE Item이 정확히 1건이어야 합니다.")
            item = items[0]
            effective = effective_override or date.fromisoformat(
                item["effective_date"] or review["effective_date"]
            )
            old = con.execute(
                """SELECT row_revision FROM bom_master
                WHERE parent_item_code=? AND child_item_code=? AND location_code=?
                  AND status='ACTIVE' AND valid_from<=?
                  AND (valid_to IS NULL OR valid_to>=?)""",
                (item["parent_item_code"], item["old_item_code"], item["location_code"],
                 effective.isoformat(), effective.isoformat()),
            ).fetchall()
            if len(old) != 1:
                raise ProductionBomConflictError(
                    "승인 후 Production BOM이 변경되었거나 적용 대상이 유효하지 않습니다."
                )
            expected_revision = old[0]["row_revision"]
        return self.apply_replace(
            change_id=review["change_id"], version_code=review["version_code"],
            parent_item_code=item["parent_item_code"], old_item_code=item["old_item_code"],
            new_item_code=item["new_item_code"], location_code=item["location_code"],
            effective_date=effective, expected_row_revision=expected_revision,
            applied_by=applied_by,
        )

    def apply_replace(
        self,
        *,
        change_id: str,
        version_code: str,
        parent_item_code: str,
        old_item_code: str,
        new_item_code: str,
        location_code: str,
        effective_date: str | date,
        expected_row_revision: int,
        applied_by: str,
    ) -> dict:
        effective = date.fromisoformat(str(effective_date))
        values = {
            "change_id": change_id,
            "version_code": version_code,
            "parent_item_code": parent_item_code,
            "old_item_code": old_item_code,
            "new_item_code": new_item_code,
            "location_code": location_code,
            "applied_by": applied_by,
        }
        if any(not str(value).strip() for value in values.values()):
            raise ValueError("Production BOM 적용 필수값은 비어 있을 수 없습니다.")
        if old_item_code == new_item_code:
            raise ValueError("기존 품목과 신규 품목은 달라야 합니다.")
        if expected_row_revision < 1:
            raise ValueError("expected_row_revision은 1 이상이어야 합니다.")

        application_id = f"APPLY-{uuid.uuid4().hex[:12].upper()}"
        event_id = f"EVT-{uuid.uuid4().hex[:12].upper()}"
        with SQLiteUnitOfWork(self.database) as uow:
            con = uow.connection
            assert con is not None
            change = con.execute(
                """
                SELECT approval_status,apply_status,workflow_status
                FROM design_changes
                WHERE change_id=? AND version_code=?
                """,
                (change_id, version_code),
            ).fetchone()
            if not change:
                raise ValueError("SQLite 설계변경 요청을 찾을 수 없습니다.")
            if (
                change["approval_status"] != "APPROVED"
                or change["apply_status"] != "APPROVED_TO_APPLY"
                or change["workflow_status"] != "APPROVED_TO_APPLY"
            ):
                raise ValueError("승인 완료된 설계변경만 Production에 적용할 수 있습니다.")

            old = con.execute(
                """
                SELECT bom_id,sequence_no,quantity,valid_from,valid_to,row_revision
                FROM bom_master
                WHERE parent_item_code=? AND child_item_code=? AND location_code=?
                  AND status='ACTIVE'
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR valid_to >= ?)
                """,
                (
                    parent_item_code, old_item_code, location_code,
                    effective.isoformat(), effective.isoformat(),
                ),
            ).fetchall()
            if len(old) != 1:
                raise ProductionBomConflictError(
                    "적용 대상 활성 BOM 관계가 정확히 1건이어야 합니다."
                )
            old = old[0]
            if old["row_revision"] != expected_row_revision:
                raise ProductionBomConflictError(
                    "BOM Revision이 변경되어 적용을 중단했습니다."
                )
            duplicate = con.execute(
                """
                SELECT 1 FROM bom_master
                WHERE parent_item_code=? AND child_item_code=? AND location_code=?
                  AND status='ACTIVE'
                  AND valid_from <= ?
                  AND (valid_to IS NULL OR valid_to >= ?)
                """,
                (
                    parent_item_code, new_item_code, location_code,
                    effective.isoformat(), effective.isoformat(),
                ),
            ).fetchone()
            if duplicate:
                raise ProductionBomConflictError(
                    "신규 품목이 같은 위치에 이미 활성 상태입니다."
                )
            self._validate_same_item_type(con, old_item_code, new_item_code)

            updated = con.execute(
                """
                UPDATE bom_master
                   SET valid_to=?,row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP
                 WHERE bom_id=? AND row_revision=?
                """,
                (
                    (effective - timedelta(days=1)).isoformat(),
                    old["bom_id"],
                    expected_row_revision,
                ),
            ).rowcount
            if updated != 1:
                raise ProductionBomConflictError("BOM 동시 변경 충돌이 발생했습니다.")
            con.execute(
                """
                INSERT INTO bom_master(
                  parent_item_code,child_item_code,location_code,sequence_no,
                  quantity,valid_from,valid_to,row_revision,status
                ) VALUES(?,?,?,?,?,?,?,1,'ACTIVE')
                """,
                (
                    parent_item_code, new_item_code, location_code,
                    old["sequence_no"], old["quantity"], effective.isoformat(),
                    old["valid_to"],
                ),
            )
            con.execute(
                """
                INSERT INTO production_apply_history(
                  application_id,change_id,version_code,before_bom_revision,
                  after_bom_revision,apply_result,applied_by,completed_at
                ) VALUES(?,?,?,?,?,'SUCCEEDED',?,CURRENT_TIMESTAMP)
                """,
                (
                    application_id, change_id, version_code,
                    expected_row_revision, expected_row_revision + 1, applied_by,
                ),
            )
            con.execute(
                """
                INSERT INTO workflow_events(
                  event_id,change_id,event_type,from_status,to_status,
                  actor_type,actor_id,reason
                ) VALUES(?,?,'PRODUCTION_BOM_REPLACED',
                         'APPROVED_TO_APPLY','APPLIED','USER',?,?)
                """,
                (
                    event_id, change_id, applied_by,
                    f"{parent_item_code}: {old_item_code} → {new_item_code}",
                ),
            )
            con.execute(
                """
                UPDATE design_changes
                   SET apply_status='APPLIED',workflow_status='APPLIED',
                       applied_by=?,applied_at=CURRENT_TIMESTAMP,
                       row_revision=row_revision+1,updated_at=CURRENT_TIMESTAMP
                 WHERE change_id=?
                """,
                (applied_by, change_id),
            )
            self._refresh_usage_type(con, old_item_code)
            self._refresh_usage_type(con, new_item_code)
            self._before_commit(con)

        return {
            "success": True,
            "result": "APPLIED",
            "application_id": application_id,
            "change_id": change_id,
            "version_code": version_code,
            "parent_item_code": parent_item_code,
            "old_item_code": old_item_code,
            "new_item_code": new_item_code,
            "location_code": location_code,
            "effective_date": effective.isoformat(),
            "production_bom_modified": True,
        }

    def _before_commit(self, connection) -> None:
        """통합 테스트와 향후 추가 무결성 검증을 위한 Commit 직전 Hook입니다."""
        return None

    @staticmethod
    def _validate_same_item_type(con, old_code: str, new_code: str) -> None:
        rows = con.execute(
            "SELECT item_code,item_type FROM item_master WHERE item_code IN (?,?)",
            (old_code, new_code),
        ).fetchall()
        types = {row["item_code"]: row["item_type"] for row in rows}
        if len(types) != 2:
            raise ValueError("기존 또는 신규 품목 Master를 찾을 수 없습니다.")
        if types[old_code] != types[new_code]:
            raise ValueError("교체 품목의 item_type이 서로 다릅니다.")

    @staticmethod
    def _refresh_usage_type(con, item_code: str) -> None:
        assembly = con.execute(
            "SELECT 1 FROM assembly_master WHERE assembly_code=?", (item_code,)
        ).fetchone()
        if not assembly:
            return
        parent_count = con.execute(
            """
            SELECT COUNT(DISTINCT parent_item_code)
            FROM bom_master WHERE child_item_code=? AND status='ACTIVE'
            """,
            (item_code,),
        ).fetchone()[0]
        con.execute(
            "UPDATE assembly_master SET usage_type=?,updated_at=CURRENT_TIMESTAMP "
            "WHERE assembly_code=?",
            ("COMMON" if parent_count >= 2 else "DEDICATED", item_code),
        )
