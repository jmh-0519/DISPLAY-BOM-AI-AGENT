from database import SQLiteDatabase
from core.database_config import sqlite_database_path


class SQLiteWorkflowHistoryRepository:
    def __init__(self) -> None:
        self.database = SQLiteDatabase(sqlite_database_path())

    def list_design_changes(self) -> list[dict]:
        with self.database.connection() as con:
            return [dict(row) for row in con.execute(
                """SELECT change_id,version_code,change_type,requested_date,effective_date,
                analysis_result,approval_status,apply_status,workflow_status,requested_by,
                approved_by,applied_by,applied_at FROM design_changes
                ORDER BY requested_date DESC,change_id DESC"""
            )]

    def get_design_change(self, change_id: str) -> dict:
        with self.database.connection() as con:
            header = con.execute("SELECT * FROM design_changes WHERE UPPER(change_id)=UPPER(?)", (change_id,)).fetchone()
            if not header:
                return {"success": False, "change_id": change_id, "message": "설계변경 정보를 찾을 수 없습니다."}
            items = [dict(row) for row in con.execute("SELECT * FROM design_change_items WHERE change_id=? ORDER BY item_seq", (header["change_id"],))]
            reviews = [dict(row) for row in con.execute("SELECT * FROM review_boms WHERE change_id=?", (header["change_id"],))]
        return {"success": True, "change": dict(header), "items": items, "reviews": reviews}

    def list_bom_reviews(self) -> list[dict]:
        with self.database.connection() as con:
            return [dict(row) for row in con.execute(
                """SELECT r.review_id,r.change_id,r.version_code,r.review_status,
                r.current_revision,r.approved_revision,r.created_by,r.reviewed_by,
                r.decision_reason,r.created_at,r.updated_at,
                (SELECT result FROM bom_reviews b WHERE b.review_id=r.review_id
                 ORDER BY b.completed_at DESC,b.bom_review_id DESC LIMIT 1) AS review_result
                FROM review_boms r ORDER BY r.created_at DESC,r.review_id DESC"""
            )]

    def get_bom_review(self, review_id: str) -> dict:
        with self.database.connection() as con:
            header = con.execute("SELECT * FROM review_boms WHERE UPPER(review_id)=UPPER(?)", (review_id,)).fetchone()
            if not header:
                return {"success": False, "review_id": review_id, "message": "품평회 정보를 찾을 수 없습니다."}
            reviews = [dict(row) for row in con.execute("SELECT * FROM bom_reviews WHERE review_id=? ORDER BY revision_no", (header["review_id"],))]
            checks = [dict(row) for row in con.execute(
                """SELECT c.* FROM bom_review_checks c JOIN bom_reviews b
                ON b.bom_review_id=c.bom_review_id WHERE b.review_id=?
                ORDER BY b.revision_no,c.check_seq""", (header["review_id"],))]
        return {"success": True, "review": dict(header), "evaluations": reviews, "checks": checks}


def _repository():
    return SQLiteWorkflowHistoryRepository()


def list_design_changes_data() -> list[dict]:
    return _repository().list_design_changes()


def get_design_change_data(change_id: str) -> dict:
    return _repository().get_design_change(change_id)


def list_bom_reviews_data() -> list[dict]:
    return _repository().list_bom_reviews()


def get_bom_review_data(review_id: str) -> dict:
    return _repository().get_bom_review(review_id)
