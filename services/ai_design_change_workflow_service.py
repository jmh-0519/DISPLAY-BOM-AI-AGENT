from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pandas as pd

from services.bom_service import BomService
from services.design_change_apply_service import DesignChangeApplyService
from services.design_change_report_service import DesignChangeReportService
from services.design_change_service import DesignChangeService
from services.review_service import ReviewService


class AiDesignChangeWorkflowService:
    """AI 품평 중심 설계변경 Workflow를 조정합니다.

    Production E-BOM 쓰기는 ``apply_to_production``에서만 발생합니다.
    앞 단계는 요청/스냅샷/Review BOM/검증/보고서 데이터만 생성합니다.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)

    @staticmethod
    def _norm(value: str) -> str:
        return str(value).strip().upper()

    def _services(self):
        bom = BomService(data_dir=str(self.data_dir))
        apply = DesignChangeApplyService(bom_service=bom, data_dir=str(self.data_dir))
        analysis = DesignChangeService(bom_service=bom, apply_service=apply, data_dir=str(self.data_dir))
        review = ReviewService(
            data_dir=str(self.data_dir),
            design_change_service=analysis,
            bom_service=bom,
        )
        return bom, apply, analysis, review

    def create_change_request(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        reason: str,
        effective_date: str,
        requested_by: str,
        as_of_date: str | None = None,
    ) -> dict:
        """분석을 통과한 변경 요청과 변경 Item을 등록합니다."""
        bom, _, analysis, _ = self._services()
        result = analysis.analyze_replace(
            product_id=product_id,
            old_material_id=old_material_id,
            new_material_id=new_material_id,
            as_of_date=as_of_date,
        )
        status = self._norm(result.get("result", "FAIL"))
        if status == "FAIL":
            return {
                "success": False,
                "result": "ANALYSIS_FAILED",
                "analysis": result,
                "production_bom_modified": False,
                "message": "FAIL 분석은 설계변경 요청으로 등록할 수 없습니다.",
            }

        current_bom = bom.get_bom_explosion(product_id, as_of_date=as_of_date)
        target = current_bom[
            current_bom["bom_child"].astype(str).str.strip().str.upper().eq(
                self._norm(old_material_id)
            )
        ]
        if len(target) != 1:
            return {
                "success": False,
                "result": "TARGET_AMBIGUOUS",
                "target_count": len(target),
                "production_bom_modified": False,
                "message": "기존 자재 관계가 정확히 한 건이어야 합니다.",
            }

        requested_date = date.today().isoformat()
        change_id = f"CHG-{date.today():%Y%m%d}-{uuid4().hex[:6].upper()}"
        header_path = self.data_dir / "change_bom.csv"
        item_path = self.data_dir / "change_bom_item.csv"
        headers = pd.read_csv(header_path, encoding="utf-8-sig")
        items = pd.read_csv(item_path, encoding="utf-8-sig")
        row = target.iloc[0]
        headers = pd.concat([headers, pd.DataFrame([{
            "change_id": change_id,
            "product_id": product_id.strip(),
            "change_type": "REPLACE",
            "requested_date": requested_date,
            "effective_date": effective_date,
            "reason": reason.strip(),
            "analysis_result": status,
            "approval_status": "AI_REVIEW_PENDING",
            "apply_status": "REQUESTED",
            "applied_date": "",
            "requested_by": requested_by.strip(),
            "approved_by": "",
            "applied_by": "",
        }])], ignore_index=True)
        items = pd.concat([items, pd.DataFrame([{
            "change_id": change_id,
            "item_seq": 1,
            "action": "REPLACE",
            "bom_parent": str(row["bom_parent"]).strip(),
            "old_bom_child": old_material_id.strip(),
            "new_bom_child": new_material_id.strip(),
            "location": row.get("location", ""),
            "sequence_no": row.get("sequence_no", ""),
            "quantity": row.get("quantity", 1),
            "effective_date": effective_date,
        }])], ignore_index=True)
        headers.to_csv(header_path, index=False, encoding="utf-8-sig")
        items.to_csv(item_path, index=False, encoding="utf-8-sig")
        return {
            "success": True,
            "result": "CHANGE_REQUESTED",
            "change_id": change_id,
            "analysis": result,
            "production_bom_modified": False,
        }

    def create_review_bom(self, change_id: str, created_by: str, created_date: str) -> dict:
        """변경 예정 BOM Snapshot과 품평회 BOM Rev.1을 생성합니다."""
        _, apply, _, _ = self._services()
        snapshot = apply.create_design_change_bom(change_id, created_date)
        if not snapshot.get("success"):
            return snapshot
        _, _, _, review = self._services()
        result = review.create_review(change_id, created_by, created_date)
        result["change_bom_snapshot"] = snapshot
        result["production_bom_modified"] = False
        return result

    def run_ai_review(self, review_id: str, reviewed_by: str, checked_date: str) -> dict:
        """기존 Rule/Compatibility 체크를 AI Agent가 실행하고 근거를 저장합니다."""
        _, _, _, review = self._services()
        validation = review.revalidate_review(review_id, checked_date)
        if not validation.get("success"):
            return validation
        result = self._norm(validation.get("review_result", "FAIL"))
        response = {
            "success": True,
            "review_id": self._norm(review_id),
            "review_revision": validation.get("review_revision"),
            "ai_review_result": result,
            "rule_results": validation.get("rule_results", []),
            "compatibility_results": validation.get("compatibility_results", []),
            "production_bom_modified": False,
        }
        if result == "PASS":
            approval = review.approve_review(
                review_id=review_id,
                reviewed_by=reviewed_by,
                completed_date=checked_date,
                decision_reason="AI Agent Rule/Compatibility 자동검증 PASS",
            )
            response.update({"workflow_result": "AI_REVIEW_COMPLETED", "approval": approval})
        elif result == "CONDITIONAL":
            response.update({"workflow_result": "REVIEW_NEEDS_CONFIRMATION"})
        else:
            response.update({"workflow_result": "REVIEW_FAILED"})
        return response

    def generate_report(self, change_id: str) -> dict:
        """MCP/내부 처리용 보고서 데이터를 생성합니다."""
        result = DesignChangeReportService(
            data_dir=str(self.data_dir)
        ).get_report_data(change_id)
        result["report_stage"] = "PRE_APPLY"
        result["production_bom_modified"] = False
        return result

    def apply_to_production(
        self, review_id: str, applied_by: str, applied_date: str | None = None
    ) -> dict:
        """사용자의 명시적 최종 승인 후 Review BOM을 Production E-BOM에 반영합니다."""
        bom, apply, _, _ = self._services()
        result = apply.apply_approved_review(review_id, applied_by, applied_date)
        result["production_bom_modified"] = bool(
            result.get("success") and self._norm(result.get("result", "")) == "APPLIED"
        )
        return result
