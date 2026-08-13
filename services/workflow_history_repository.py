from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class WorkflowHistoryRepository:
    """CSV 기반 설계변경·품평회 이력 조회 저장소.

    화면과 MCP는 이 인터페이스만 사용합니다. STEP24에서는 동일한 반환
    형식을 유지한 SQLite Repository로 교체할 수 있습니다.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent.parent / "data"

    def _read(self, name: str) -> pd.DataFrame:
        path = self.data_dir / name
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")

    @staticmethod
    def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        return frame.fillna("").to_dict(orient="records") if not frame.empty else []

    @staticmethod
    def _workflow_status(row: dict[str, Any], review: dict[str, Any] | None) -> str:
        apply_status = str(row.get("apply_status", "")).upper()
        approval = str(row.get("approval_status", "")).upper()
        analysis = str(row.get("analysis_result", "")).upper()
        review_status = str((review or {}).get("review_status", "")).upper()
        review_result = str((review or {}).get("review_result", "")).upper()
        if apply_status == "APPLIED":
            return "완료"
        if analysis == "FAIL" or approval == "REJECTED" or review_status == "REJECTED":
            return "반려"
        if analysis == "CONDITIONAL" or review_result == "CONDITIONAL":
            return "사용자 확인 필요"
        if review_status in {"APPROVED", "COMPLETED"}:
            return "보고서/적용 대기"
        if review:
            return "품평 진행 중"
        return "변경 요청"

    def list_design_changes(self) -> list[dict[str, Any]]:
        changes = self._read("change_bom.csv")
        items = self._read("change_bom_item.csv")
        reviews = self._read("review_bom.csv")
        if changes.empty:
            return []
        item_map = {
            str(row["change_id"]): row
            for row in self._records(items.drop_duplicates("change_id", keep="last"))
        } if not items.empty else {}
        review_map = {
            str(row["change_id"]): row
            for row in self._records(reviews.drop_duplicates("change_id", keep="last"))
        } if not reviews.empty else {}
        result = []
        for row in self._records(changes):
            change_id = str(row.get("change_id", ""))
            item = item_map.get(change_id, {})
            review = review_map.get(change_id)
            result.append({
                **row,
                "old_material_id": item.get("old_bom_child", ""),
                "new_material_id": item.get("new_bom_child", ""),
                "review_id": (review or {}).get("review_id", ""),
                "review_result": (review or {}).get("review_result", ""),
                "workflow_status": self._workflow_status(row, review),
                "source": "Agent/Workflow 공통",
            })
        return sorted(result, key=lambda x: (x.get("requested_date", ""), x.get("change_id", "")), reverse=True)

    def get_design_change(self, change_id: str) -> dict[str, Any]:
        normalized = str(change_id).strip().upper()
        changes = [x for x in self.list_design_changes() if str(x.get("change_id", "")).upper() == normalized]
        if not changes:
            return {"success": False, "message": "설계변경 이력을 찾을 수 없습니다.", "change_id": normalized}
        items = self._read("change_bom_item.csv")
        details = self._read("change_bom_detail.csv")
        reviews = self._read("review_bom.csv")
        review_rows = self._records(reviews[reviews["change_id"].str.upper() == normalized]) if not reviews.empty else []
        return {
            "success": True,
            "change": changes[0],
            "items": self._records(items[items["change_id"].str.upper() == normalized]) if not items.empty else [],
            "snapshot_items": self._records(details[details["change_id"].str.upper() == normalized]) if not details.empty else [],
            "reviews": review_rows,
            "production_bom_modified": False,
        }

    def list_bom_reviews(self) -> list[dict[str, Any]]:
        reviews = self._read("review_bom.csv")
        checks = self._read("review_bom_check.csv")
        if reviews.empty:
            return []
        counts: dict[str, dict[str, int]] = {}
        for row in self._records(checks):
            review_id = str(row.get("review_id", ""))
            status = str(row.get("status", "")).upper()
            key = "conditional_count" if status == "CONDITIONAL" else f"{status.lower()}_count"
            counts.setdefault(review_id, {"pass_count": 0, "conditional_count": 0, "fail_count": 0})
            if key in counts[review_id]:
                counts[review_id][key] += 1
        result = []
        for row in self._records(reviews):
            review_id = str(row.get("review_id", ""))
            result.append({**row, **counts.get(review_id, {"pass_count": 0, "conditional_count": 0, "fail_count": 0})})
        return sorted(result, key=lambda x: (x.get("created_date", ""), x.get("review_id", "")), reverse=True)

    def get_bom_review(self, review_id: str) -> dict[str, Any]:
        normalized = str(review_id).strip().upper()
        reviews = [x for x in self.list_bom_reviews() if str(x.get("review_id", "")).upper() == normalized]
        if not reviews:
            return {"success": False, "message": "품평회 이력을 찾을 수 없습니다.", "review_id": normalized}
        checks = self._read("review_bom_check.csv")
        details = self._read("review_bom_detail.csv")
        return {
            "success": True,
            "review": reviews[0],
            "checks": self._records(checks[checks["review_id"].str.upper() == normalized]) if not checks.empty else [],
            "bom_items": self._records(details[details["review_id"].str.upper() == normalized]) if not details.empty else [],
            "production_bom_modified": False,
        }
