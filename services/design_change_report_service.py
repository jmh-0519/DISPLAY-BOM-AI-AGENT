from pathlib import Path

import pandas as pd

from services.bom_service import BomService


class DesignChangeReportService:
    """
    설계변경 → 품평회 → Production BOM 적용 결과를
    보고서 작성용 데이터로 조립하는 Service입니다.

    이 Service는 데이터를 수정하지 않습니다.
    조회 / 비교 / 조립만 수행합니다.
    """

    CHECK_TYPES = [
        "BOM_STRUCTURE",
        "LIFECYCLE",
        "APPROVAL",
        "SUPPLIER",
        "BOM_ATTRIBUTE",
        "COMPATIBILITY",
    ]

    def __init__(
        self,
        data_dir: str = "data",
        bom_service: BomService | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)

        self.bom_service = (
            bom_service
            if bom_service is not None
            else BomService(
                data_dir=str(self.data_dir)
            )
        )

        self.change_bom = self._load_csv(
            "change_bom.csv"
        )

        self.change_bom_item = self._load_csv(
            "change_bom_item.csv"
        )

        self.change_bom_detail = self._load_csv(
            "change_bom_detail.csv"
        )

        self.review_bom = self._load_csv(
            "review_bom.csv"
        )

        self.review_bom_detail = self._load_csv(
            "review_bom_detail.csv"
        )

        self.review_bom_check = self._load_csv(
            "review_bom_check.csv"
        )

    def _load_csv(
        self,
        file_name: str,
    ) -> pd.DataFrame:
        file_path = (
            self.data_dir / file_name
        )

        if not file_path.exists():
            raise FileNotFoundError(
                "데이터 파일을 찾을 수 없습니다: "
                f"{file_path.resolve()}"
            )

        return pd.read_csv(
            file_path,
            encoding="utf-8-sig",
        )

    @staticmethod
    def _normalize(
        value,
    ) -> str:
        return str(value).strip().upper()

    @staticmethod
    def _safe_int(
        value,
    ) -> int | None:
        if pd.isna(value):
            return None

        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_value(
        value,
    ):
        """
        NaN을 보고서용 None으로 변환합니다.
        """
        if pd.isna(value):
            return None

        if isinstance(
            value,
            pd.Timestamp,
        ):
            return value.strftime(
                "%Y-%m-%d"
            )

        return value

    def _records(
        self,
        dataframe: pd.DataFrame,
    ) -> list[dict]:
        if dataframe.empty:
            return []

        records = []

        for record in dataframe.to_dict(
            orient="records"
        ):
            records.append({
                key: self._safe_value(value)
                for key, value
                in record.items()
            })

        return records

    def _get_change(
        self,
        change_id: str,
    ) -> pd.Series | None:
        normalized_change_id = (
            self._normalize(change_id)
        )

        rows = self.change_bom[
            self.change_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ]

        if rows.empty:
            return None

        return rows.iloc[0]

    def _get_review(
        self,
        change_id: str,
    ) -> pd.Series | None:
        normalized_change_id = (
            self._normalize(change_id)
        )

        rows = self.review_bom[
            self.review_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ]

        if rows.empty:
            return None

        return rows.iloc[-1]

    def _get_review_revision(
        self,
        review_id: str,
        revision: int,
    ) -> pd.DataFrame:
        return (
            self.review_bom_detail[
                (
                    self.review_bom_detail[
                        "review_id"
                    ]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq(
                        self._normalize(
                            review_id
                        )
                    )
                )
                &
                (
                    pd.to_numeric(
                        self.review_bom_detail[
                            "review_revision"
                        ],
                        errors="coerce",
                    )
                    == revision
                )
            ]
            .copy()
        )

    def _get_review_checks(
        self,
        review_id: str,
        revision: int,
    ) -> pd.DataFrame:
        return (
            self.review_bom_check[
                (
                    self.review_bom_check[
                        "review_id"
                    ]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq(
                        self._normalize(
                            review_id
                        )
                    )
                )
                &
                (
                    pd.to_numeric(
                        self.review_bom_check[
                            "review_revision"
                        ],
                        errors="coerce",
                    )
                    == revision
                )
            ]
            .copy()
        )

    def _build_check_summary(
        self,
        check_rows: pd.DataFrame,
    ) -> dict:
        summary = {}

        for check_type in self.CHECK_TYPES:
            rows = check_rows[
                check_rows["check_type"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(check_type)
            ]

            if rows.empty:
                summary[check_type] = {
                    "status": "NOT_CHECKED",
                    "count": 0,
                    "fail_count": 0,
                    "conditional_count": 0,
                }
                continue

            statuses = (
                rows["status"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            if (
                statuses == "FAIL"
            ).any():
                status = "FAIL"

            elif (
                statuses
                == "CONDITIONAL"
            ).any():
                status = "CONDITIONAL"

            else:
                status = "PASS"

            summary[check_type] = {
                "status": status,
                "count": int(
                    len(rows)
                ),
                "fail_count": int(
                    (
                        statuses
                        == "FAIL"
                    ).sum()
                ),
                "conditional_count": int(
                    (
                        statuses
                        == "CONDITIONAL"
                    ).sum()
                ),
            }

        return summary

    def _get_revision_history(
        self,
        review_id: str,
    ) -> list[dict]:
        rows = self.review_bom_detail[
            self.review_bom_detail[
                "review_id"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                self._normalize(
                    review_id
                )
            )
        ].copy()

        if rows.empty:
            return []

        revisions = sorted(
            {
                int(value)
                for value in pd.to_numeric(
                    rows[
                        "review_revision"
                    ],
                    errors="coerce",
                )
                .dropna()
                .tolist()
            }
        )

        history = []

        for revision in revisions:
            revision_rows = rows[
                pd.to_numeric(
                    rows[
                        "review_revision"
                    ],
                    errors="coerce",
                )
                == revision
            ]

            modified_count = int(
                (
                    revision_rows[
                        "modified_yn"
                    ]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    == "Y"
                ).sum()
            )

            history.append({
                "revision": revision,
                "bom_row_count": int(
                    len(revision_rows)
                ),
                "modified_row_count": (
                    modified_count
                ),
            })

        return history

    @staticmethod
    def _bom_key(
        row: pd.Series,
    ) -> tuple:
        return (
            str(
                row["bom_parent"]
            ).strip(),
            str(
                row["location"]
            ).strip(),
            int(
                float(
                    row["sequence_no"]
                )
            ),
        )

    def _compare_bom_snapshots(
        self,
        before_bom: pd.DataFrame,
        after_bom: pd.DataFrame,
    ) -> list[dict]:
        """
        두 BOM Snapshot의 차이를 계산합니다.

        기준 Key:
        bom_parent + location + sequence_no
        """

        before_lookup = {}
        after_lookup = {}

        if not before_bom.empty:
            for _, row in (
                before_bom.iterrows()
            ):
                before_lookup[
                    self._bom_key(row)
                ] = row

        if not after_bom.empty:
            for _, row in (
                after_bom.iterrows()
            ):
                after_lookup[
                    self._bom_key(row)
                ] = row

        all_keys = (
            set(before_lookup)
            | set(after_lookup)
        )

        differences = []

        for key in sorted(all_keys):
            before_row = (
                before_lookup.get(key)
            )

            after_row = (
                after_lookup.get(key)
            )

            bom_parent, location, sequence_no = (
                key
            )

            if before_row is None:
                differences.append({
                    "action": "ADD",
                    "bom_parent": bom_parent,
                    "location": location,
                    "sequence_no": (
                        sequence_no
                    ),
                    "old_material_id": None,
                    "new_material_id": str(
                        after_row[
                            "bom_child"
                        ]
                    ).strip(),
                    "old_quantity": None,
                    "new_quantity": (
                        self._safe_value(
                            after_row.get(
                                "quantity"
                            )
                        )
                    ),
                })

                continue

            if after_row is None:
                differences.append({
                    "action": "REMOVE",
                    "bom_parent": bom_parent,
                    "location": location,
                    "sequence_no": (
                        sequence_no
                    ),
                    "old_material_id": str(
                        before_row[
                            "bom_child"
                        ]
                    ).strip(),
                    "new_material_id": None,
                    "old_quantity": (
                        self._safe_value(
                            before_row.get(
                                "quantity"
                            )
                        )
                    ),
                    "new_quantity": None,
                })

                continue

            old_material_id = str(
                before_row["bom_child"]
            ).strip()

            new_material_id = str(
                after_row["bom_child"]
            ).strip()

            old_quantity = (
                self._safe_value(
                    before_row.get(
                        "quantity"
                    )
                )
            )

            new_quantity = (
                self._safe_value(
                    after_row.get(
                        "quantity"
                    )
                )
            )

            if (
                old_material_id
                != new_material_id
            ):
                differences.append({
                    "action": "REPLACE",
                    "bom_parent": bom_parent,
                    "location": location,
                    "sequence_no": (
                        sequence_no
                    ),
                    "old_material_id": (
                        old_material_id
                    ),
                    "new_material_id": (
                        new_material_id
                    ),
                    "old_quantity": (
                        old_quantity
                    ),
                    "new_quantity": (
                        new_quantity
                    ),
                })

                continue

            if (
                old_quantity
                != new_quantity
            ):
                differences.append({
                    "action": (
                        "QUANTITY_CHANGE"
                    ),
                    "bom_parent": bom_parent,
                    "location": location,
                    "sequence_no": (
                        sequence_no
                    ),
                    "old_material_id": (
                        old_material_id
                    ),
                    "new_material_id": (
                        new_material_id
                    ),
                    "old_quantity": (
                        old_quantity
                    ),
                    "new_quantity": (
                        new_quantity
                    ),
                })

        return differences

    def get_report_data(
        self,
        change_id: str,
    ) -> dict:
        """
        change_id 기준으로 설계변경부터
        품평회 및 Production BOM 적용까지의
        보고서 데이터를 조립합니다.
        """

        normalized_change_id = (
            self._normalize(change_id)
        )

        # --------------------------------------
        # 1. Change Header
        # --------------------------------------

        change = self._get_change(
            normalized_change_id
        )

        if change is None:
            return {
                "success": False,
                "change_id": change_id,
                "message": (
                    "설계변경 정보를 "
                    "찾을 수 없습니다."
                ),
            }

        product_id = str(
            change["product_id"]
        ).strip()

        change_header = {
            key: self._safe_value(value)
            for key, value
            in change.to_dict().items()
        }

        # --------------------------------------
        # 2. Change Item
        # --------------------------------------

        change_items = (
            self.change_bom_item[
                self.change_bom_item[
                    "change_id"
                ]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(normalized_change_id)
            ]
            .copy()
        )

        # --------------------------------------
        # 3. Change BOM Detail
        # --------------------------------------

        change_detail = (
            self.change_bom_detail[
                self.change_bom_detail[
                    "change_id"
                ]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(normalized_change_id)
            ]
            .copy()
        )

        # --------------------------------------
        # 4. Review Header
        # --------------------------------------

        review = self._get_review(
            normalized_change_id
        )

        if review is None:
            return {
                "success": True,
                "change_id": (
                    normalized_change_id
                ),
                "product_id": product_id,
                "change": change_header,
                "change_items": (
                    self._records(
                        change_items
                    )
                ),
                "change_bom": (
                    self._records(
                        change_detail
                    )
                ),
                "review": None,
                "review_revision_history": [],
                "approved_review_bom": [],
                "review_checks": [],
                "review_check_summary": {},
                "change_to_review_diff": [],
                "production_before_bom": [],
                "production_after_bom": [],
                "production_diff": [],
            }

        review_id = str(
            review["review_id"]
        ).strip()

        review_header = {
            key: self._safe_value(value)
            for key, value
            in review.to_dict().items()
        }

        current_revision = (
            self._safe_int(
                review.get(
                    "current_revision"
                )
            )
        )

        approved_revision = (
            self._safe_int(
                review.get(
                    "approved_revision"
                )
            )
        )

        report_revision = (
            approved_revision
            if approved_revision is not None
            else current_revision
        )

        # --------------------------------------
        # 5. Review Revision History
        # --------------------------------------

        revision_history = (
            self._get_revision_history(
                review_id
            )
        )

        # --------------------------------------
        # 6. 최종 Review BOM
        # --------------------------------------

        if report_revision is None:
            final_review_bom = (
                pd.DataFrame()
            )
        else:
            final_review_bom = (
                self._get_review_revision(
                    review_id=review_id,
                    revision=(
                        report_revision
                    ),
                )
            )

        # --------------------------------------
        # 7. Review Check
        # --------------------------------------

        if report_revision is None:
            check_rows = (
                pd.DataFrame()
            )
        else:
            check_rows = (
                self._get_review_checks(
                    review_id=review_id,
                    revision=(
                        report_revision
                    ),
                )
            )

        if check_rows.empty:
            check_summary = {
                check_type: {
                    "status": (
                        "NOT_CHECKED"
                    ),
                    "count": 0,
                    "fail_count": 0,
                    "conditional_count": 0,
                }
                for check_type
                in self.CHECK_TYPES
            }
        else:
            check_summary = (
                self._build_check_summary(
                    check_rows
                )
            )

        # --------------------------------------
        # 8. AI Change BOM ↔ 최종 Review BOM
        # --------------------------------------

        change_to_review_diff = (
            self._compare_bom_snapshots(
                before_bom=change_detail,
                after_bom=(
                    final_review_bom
                ),
            )
            if (
                not change_detail.empty
                and
                not final_review_bom.empty
            )
            else []
        )

        # --------------------------------------
        # 9. Production Before / After
        # --------------------------------------

        production_before = (
            pd.DataFrame()
        )

        production_after = (
            pd.DataFrame()
        )

        production_diff = []

        effective_value = (
            change.get(
                "effective_date"
            )
        )

        if not pd.isna(
            effective_value
        ):
            effective_date = (
                pd.Timestamp(
                    effective_value
                ).normalize()
            )

            before_date = (
                effective_date
                - pd.Timedelta(
                    days=1
                )
            )

            production_before = (
                self.bom_service
                .get_bom_explosion(
                    product_id,
                    as_of_date=(
                        before_date
                        .strftime(
                            "%Y-%m-%d"
                        )
                    ),
                )
            )

            apply_status = self._normalize(
                change.get(
                    "apply_status",
                    "",
                )
            )

            # 실제 적용된 경우에만
            # Production After를 실제 BOM에서 조회
            if apply_status == "APPLIED":
                production_after = (
                    self.bom_service
                    .get_bom_explosion(
                        product_id,
                        as_of_date=(
                            effective_date
                            .strftime(
                                "%Y-%m-%d"
                            )
                        ),
                    )
                )

                production_diff = (
                    self._compare_bom_snapshots(
                        before_bom=(
                            production_before
                        ),
                        after_bom=(
                            production_after
                        ),
                    )
                )

        return {
            "success": True,
            "change_id": normalized_change_id,
            "product_id": product_id,

            "change": change_header,

            "change_items": self._records(
                change_items
            ),

            "change_bom": self._records(
                change_detail
            ),

            "review": review_header,

            "review_revision_history": (
                revision_history
            ),

            "report_revision": (
                report_revision
            ),

            "approved_review_bom": (
                self._records(
                    final_review_bom
                )
            ),

            "review_checks": (
                self._records(
                    check_rows
                )
            ),

            "review_check_summary": (
                check_summary
            ),

            "change_to_review_diff": (
                change_to_review_diff
            ),

            "production_before_bom": (
                self._records(
                    production_before
                )
            ),

            "production_after_bom": (
                self._records(
                    production_after
                )
            ),

            "production_diff": (
                production_diff
            ),
        }