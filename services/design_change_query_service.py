from datetime import timedelta
from pathlib import Path

import pandas as pd

from services.bom_service import BomService


class DesignChangeQueryService:

    def __init__(
        self,
        bom_service: BomService,
        data_dir: str = "data",
    ) -> None:
        self.bom_service = bom_service
        self.data_dir = Path(data_dir)

        self.design_changes = self._load_csv(
            "change_bom.csv"
        )

        self.design_change_items = self._load_csv(
            "change_bom_item.csv"
        )

    def _load_csv(
        self,
        file_name: str,
    ) -> pd.DataFrame:
        file_path = self.data_dir / file_name

        if not file_path.exists():
            raise FileNotFoundError(
                "데이터 파일을 찾을 수 없습니다: "
                f"{file_path.resolve()}"
            )

        return pd.read_csv(
            file_path,
            encoding="utf-8-sig",
        )

    def get_change_result(
        self,
        change_id: str,
    ) -> dict:
        """
        change_id 기준으로 설계변경 Header, Detail,
        변경 전/후 BOM을 조회합니다.
        """

        normalized_change_id = (
            change_id.strip().upper()
        )

        change_rows = self.design_changes[
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ]

        if change_rows.empty:
            return {
                "success": False,
                "change_id": change_id,
                "message": (
                    "설계변경 정보를 찾을 수 없습니다."
                ),
            }

        change = change_rows.iloc[0]

        items = self.design_change_items[
            self.design_change_items["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ].copy()

        product_id = str(
            change["product_id"]
        ).strip()

        effective_date = pd.Timestamp(
            change["effective_date"]
        ).normalize()

        before_date = (
            effective_date
            - timedelta(days=1)
        )

        before_bom = (
            self.bom_service.get_bom_explosion(
                product_id,
                as_of_date=before_date.strftime(
                    "%Y-%m-%d"
                ),
            )
        )

        after_bom = (
            self.bom_service.get_bom_explosion(
                product_id,
                as_of_date=effective_date.strftime(
                    "%Y-%m-%d"
                ),
            )
        )

        return {
            "success": True,
            "change_id": str(
                change["change_id"]
            ),
            "product_id": product_id,
            "change_type": str(
                change["change_type"]
            ),
            "analysis_result": str(
                change["analysis_result"]
            ),
            "approval_status": str(
                change["approval_status"]
            ),
            "apply_status": str(
                change["apply_status"]
            ),
            "effective_date": (
                effective_date.strftime(
                    "%Y-%m-%d"
                )
            ),
            "before_date": (
                before_date.strftime(
                    "%Y-%m-%d"
                )
            ),
            "items": (
                items.to_dict(
                    orient="records"
                )
            ),
            "before_bom": before_bom,
            "after_bom": after_bom,
        }