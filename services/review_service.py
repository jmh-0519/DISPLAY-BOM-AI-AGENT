from pathlib import Path

import pandas as pd

from services.design_change_service import (
    DesignChangeService,
)
from services.bom_service import BomService

class ReviewService:

    def __init__(
        self,
        data_dir: str = "data",
        design_change_service: DesignChangeService | None = None,
        bom_service: BomService | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)

        self.change_bom = self._load_csv(
            "change_bom.csv"
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

        self.design_change_service = (
            design_change_service
        )

        self.bom_service = bom_service

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

    def _save_review_bom(
        self,
    ) -> None:
        self.review_bom.to_csv(
            self.data_dir / "review_bom.csv",
            index=False,
            encoding="utf-8-sig",
        )
      
    def _save_review_bom_detail(
        self,
    ) -> None:
        self.review_bom_detail.to_csv(
            self.data_dir
            / "review_bom_detail.csv",
            index=False,
            encoding="utf-8-sig",
        )


    def _save_review_bom_check(
        self,
    ) -> None:
        self.review_bom_check.to_csv(
            self.data_dir
            / "review_bom_check.csv",
            index=False,
            encoding="utf-8-sig",
        )

    def _get_review_check_type(
        self,
        rule: dict,
    ) -> str:
        """
        Rule Engine 결과를 품평회 검증 유형으로
        분류합니다.
        """

        metric = str(
            rule.get("metric", "")
        ).strip().upper()

        if metric == "LIFECYCLE_STATUS":
            return "LIFECYCLE"

        if metric == "APPROVAL_STATUS":
            return "APPROVAL"

        if metric == "SUPPLIER_GRADE":
            return "SUPPLIER"

        if metric == "LOCATION_EXISTS":
            return "BOM_STRUCTURE"

        return "BOM_ATTRIBUTE"        

    def _save_review_validation_results(
        self,
        review_id: str,
        change_id: str,
        review_revision: int,
        rule_results: list[dict],
        compatibility_results: list[dict],
        checked_date: str,
    ) -> None:
        """
        Review BOM Revision의 검증 결과를 저장합니다.

        동일 Review Revision을 재검증하는 경우
        기존 결과를 삭제하고 최신 결과로 교체합니다.
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        # --------------------------------------
        # 1. 동일 Revision 기존 결과 제거
        # --------------------------------------

        if not self.review_bom_check.empty:
            existing_mask = (
                self.review_bom_check["review_id"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(normalized_review_id)
                &
                (
                    pd.to_numeric(
                        self.review_bom_check[
                            "review_revision"
                        ],
                        errors="coerce",
                    )
                    == review_revision
                )
            )

            self.review_bom_check = (
                self.review_bom_check[
                    ~existing_mask
                ].copy()
            )

        rows = []
        check_seq = 1

        # --------------------------------------
        # 2. Rule 결과
        # --------------------------------------

        for rule in rule_results:
            status = str(
                rule.get("status", "PASS")
            ).strip().upper()

            target_id = str(
                rule.get(
                    "rule_id",
                    rule.get("check", ""),
                )
            ).strip()

            rows.append({
                "review_id": normalized_review_id,
                "change_id": change_id,
                "review_revision": review_revision,
                "check_seq": check_seq,
                "check_type": self._get_review_check_type(
                    rule
                ),
                "target_id": target_id,
                "status": status,
                "actual_value": rule.get(
                    "actual_value",
                    "",
                ),
                "expected_value": rule.get(
                    "expected_value",
                    "",
                ),
                "blocking_yn": (
                    "Y"
                    if status == "FAIL"
                    else "N"
                ),
                "message": rule.get(
                    "message",
                    "",
                ),
                "checked_date": checked_date,
            })

            check_seq += 1

        # --------------------------------------
        # 3. Compatibility 결과
        # --------------------------------------

        for compatibility in compatibility_results:
            status = str(
                compatibility.get(
                    "status",
                    "PASS",
                )
            ).strip().upper()

            rows.append({
                "review_id": normalized_review_id,
                "change_id": change_id,
                "review_revision": review_revision,
                "check_seq": check_seq,
                "check_type": "COMPATIBILITY",
                "target_id": compatibility.get(
                    "new_material_id",
                    "",
                ),
                "status": status,
                "actual_value": "",
                "expected_value": "",
                "blocking_yn": (
                    "Y"
                    if status == "FAIL"
                    else "N"
                ),
                "message": compatibility.get(
                    "message",
                    "",
                ),
                "checked_date": checked_date,
            })

            check_seq += 1

        # --------------------------------------
        # 4. 저장
        # --------------------------------------

        if rows:
            new_results = pd.DataFrame(
                rows,
                columns=(
                    self.review_bom_check.columns
                ),
            )

            self.review_bom_check = pd.concat(
                [
                    self.review_bom_check,
                    new_results,
                ],
                ignore_index=True,
            )

        self._save_review_bom_check()

    def _save_change_bom(
        self,
    ) -> None:
        self.change_bom.to_csv(
            self.data_dir / "change_bom.csv",
            index=False,
            encoding="utf-8-sig",
        )

    def create_review(
        self,
        change_id: str,
        created_by: str,
        created_date: str,
    ) -> dict:
        """
        설계변경 BOM을 기준으로 품평회 Header와
        Review BOM Revision 1을 생성합니다.
        """

        normalized_change_id = (
            change_id.strip().upper()
        )

        # --------------------------------------
        # 1. Change Header 확인
        # --------------------------------------

        change_rows = self.change_bom[
            self.change_bom["change_id"]
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

        # --------------------------------------
        # 2. REVIEW_READY 확인
        # --------------------------------------

        apply_status = str(
            change["apply_status"]
        ).strip().upper()

        if apply_status != "REVIEW_READY":
            return {
                "success": False,
                "change_id": normalized_change_id,
                "message": (
                    "REVIEW_READY 상태의 "
                    "설계변경만 품평회를 "
                    "생성할 수 있습니다."
                ),
            }

        # --------------------------------------
        # 3. Change BOM Detail 확인
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

        if change_detail.empty:
            return {
                "success": False,
                "change_id": normalized_change_id,
                "message": (
                    "설계변경 BOM Detail이 "
                    "존재하지 않습니다."
                ),
            }

        product_id = str(
            change["product_id"]
        ).strip()

        # --------------------------------------
        # 4. 중복 품평회 생성 방지
        # --------------------------------------

        existing = self.review_bom[
            self.review_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ]

        if not existing.empty:
            return {
                "success": False,
                "change_id": normalized_change_id,
                "message": (
                    "이미 생성된 품평회가 "
                    "존재합니다."
                ),
            }

        # --------------------------------------
        # 5. Review ID 생성
        # --------------------------------------

        review_id = (
            "REV-"
            + normalized_change_id
        )

        # --------------------------------------
        # 6. Review Header 생성
        # --------------------------------------

        header = {
            "review_id": review_id,
            "change_id": normalized_change_id,
            "product_id": product_id,
            "review_status": "CREATED",
            "current_revision": 1,
            "review_result": "PENDING",
            "created_date": created_date,
            "started_date": "",
            "completed_date": "",
            "created_by": created_by,
            "reviewed_by": "",
            "decision_reason": "",
        }

        self.review_bom = pd.concat(
            [
                self.review_bom,
                pd.DataFrame([header]),
            ],
            ignore_index=True,
        )

        # --------------------------------------
        # 7. Review BOM Rev.1 생성
        # --------------------------------------

        review_detail = change_detail.copy(
            deep=True
        )

        review_detail["review_id"] = review_id
        review_detail["review_revision"] = 1

        # 설계변경 action을 최초 Review action으로 승계
        review_detail["review_action"] = (
            review_detail["change_action"]
        )

        review_detail["source"] = (
            "DESIGN_CHANGE"
        )

        review_detail["modified_yn"] = "N"
        review_detail["modified_by"] = ""
        review_detail["modified_date"] = ""
        review_detail["remark"] = ""

        detail_columns = [
            "review_id",
            "change_id",
            "review_revision",
            "product_id",
            "bom_parent",
            "bom_parent_name",
            "bom_child",
            "bom_child_name",
            "location",
            "sequence_no",
            "quantity",
            "level",
            "bom_path",
            "required_quantity",
            "review_action",
            "source",
            "modified_yn",
            "modified_by",
            "modified_date",
            "remark",
        ]

        review_detail = review_detail[
            detail_columns
        ].copy()

        self.review_bom_detail = pd.concat(
            [
                self.review_bom_detail,
                review_detail,
            ],
            ignore_index=True,
        )

        # --------------------------------------
        # 8. 저장
        # --------------------------------------

        self._save_review_bom()
        self._save_review_bom_detail()

        # --------------------------------------
        # 9. Change 상태 → IN_REVIEW
        # --------------------------------------

        change_mask = (
            self.change_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        )

        self.change_bom.loc[
            change_mask,
            "apply_status",
        ] = "IN_REVIEW"

        self._save_change_bom()

        return {
            "success": True,
            "review_id": review_id,
            "change_id": normalized_change_id,
            "product_id": product_id,
            "review_status": "CREATED",
            "review_result": "PENDING",
            "current_revision": 1,
            "bom_row_count": len(
                review_detail
            ),
            "message": (
                "품평회 대상 BOM Rev.1이 "
                "생성되었습니다."
            ),
        }

    def revise_review_bom(
        self,
        review_id: str,
        old_material_id: str,
        new_material_id: str,
        modified_by: str,
        modified_date: str,
        remark: str = "",
    ) -> dict:
        """
        현재 Review BOM Revision을 복사한 뒤
        Component를 교체하여 새로운 Revision을 생성합니다.

        기존 Revision은 변경하지 않습니다.
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        # --------------------------------------
        # 1. Review Header 확인
        # --------------------------------------

        review_rows = self.review_bom[
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        ]

        if review_rows.empty:
            return {
                "success": False,
                "review_id": review_id,
                "message": (
                    "품평회 정보를 찾을 수 없습니다."
                ),
            }

        review = review_rows.iloc[0]

        current_revision = int(
            review["current_revision"]
        )

        new_revision = (
            current_revision + 1
        )

        # --------------------------------------
        # 2. 현재 Revision 조회
        # --------------------------------------

        current_bom = (
            self.review_bom_detail[
                (
                    self.review_bom_detail[
                        "review_id"
                    ]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq(normalized_review_id)
                )
                &
                (
                    pd.to_numeric(
                        self.review_bom_detail[
                            "review_revision"
                        ],
                        errors="coerce",
                    )
                    == current_revision
                )
            ]
            .copy(deep=True)
        )

        if current_bom.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "현재 품평회 BOM Revision을 "
                    "찾을 수 없습니다."
                ),
            }

        # --------------------------------------
        # 3. 교체 대상 확인
        # --------------------------------------

        old_mask = (
            current_bom["bom_child"]
            .astype(str)
            .str.strip()
            .eq(
                str(old_material_id).strip()
            )
        )

        if not old_mask.any():
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "품평회 BOM에서 기존 자재를 "
                    "찾을 수 없습니다."
                ),
            }

        # 현재 단계에서는 Component 한 행 교체
        if int(old_mask.sum()) != 1:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "교체 대상 자재가 여러 위치에 "
                    "존재합니다."
                ),
            }

        # --------------------------------------
        # 4. 새 Revision 생성
        # --------------------------------------

        revised_bom = current_bom.copy(
            deep=True
        )

        revised_bom[
            "review_revision"
        ] = new_revision

        # 새 Revision 전체는 이전 Revision에서
        # 복사된 것이므로 기존 이력값은 유지
        target_index = revised_bom[
            old_mask
        ].index[0]

        revised_bom.at[
            target_index,
            "bom_child",
        ] = new_material_id

        revised_bom.at[
            target_index,
            "review_action",
        ] = "REPLACE"

        revised_bom.at[
            target_index,
            "source",
        ] = "REVIEW"

        revised_bom.at[
            target_index,
            "modified_yn",
        ] = "Y"

        revised_bom.at[
            target_index,
            "modified_by",
        ] = modified_by

        revised_bom.at[
            target_index,
            "modified_date",
        ] = modified_date

        revised_bom.at[
            target_index,
            "remark",
        ] = remark

        # --------------------------------------
        # 5. 새 Revision 추가 저장
        # --------------------------------------

        self.review_bom_detail = pd.concat(
            [
                self.review_bom_detail,
                revised_bom,
            ],
            ignore_index=True,
        )

        self._save_review_bom_detail()

        # --------------------------------------
        # 6. Header 갱신
        # --------------------------------------

        header_mask = (
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        )

        self.review_bom.loc[
            header_mask,
            "current_revision",
        ] = new_revision

        self.review_bom.loc[
            header_mask,
            "review_status",
        ] = "RECHECK_REQUIRED"

        self.review_bom.loc[
            header_mask,
            "review_result",
        ] = "PENDING"

        self._save_review_bom()

        return {
            "success": True,
            "review_id": normalized_review_id,
            "previous_revision": current_revision,
            "current_revision": new_revision,
            "old_material_id": old_material_id,
            "new_material_id": new_material_id,
            "review_status": "RECHECK_REQUIRED",
            "message": (
                f"품평회 BOM Rev.{new_revision}이 "
                "생성되었습니다."
            ),
        }    

    def revise_review_assembly(
        self,
        review_id: str,
        old_assembly_id: str,
        new_assembly_id: str,
        modified_by: str,
        modified_date: str,
        as_of_date: str,
        remark: str = "",
    ) -> dict:
        """
        현재 Review BOM Revision에서 Assembly를 교체하고
        신규 Assembly subtree를 포함한 새 Revision을 생성합니다.

        기존 Revision은 수정하지 않습니다.
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        # --------------------------------------
        # 1. Review Header 확인
        # --------------------------------------

        review_rows = self.review_bom[
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        ]

        if review_rows.empty:
            return {
                "success": False,
                "review_id": review_id,
                "message": (
                    "품평회 정보를 찾을 수 없습니다."
                ),
            }

        review = review_rows.iloc[0]

        current_revision = int(
            review["current_revision"]
        )

        new_revision = (
            current_revision + 1
        )

        # --------------------------------------
        # 2. BomService 확인
        # --------------------------------------

        if self.bom_service is None:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "BomService가 설정되지 않았습니다."
                ),
            }

        # --------------------------------------
        # 3. 현재 Review BOM 조회
        # --------------------------------------

        current_bom = self._get_review_revision(
            review_id=normalized_review_id,
            revision=current_revision,
        )

        if current_bom.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "현재 Review BOM Revision을 "
                    "찾을 수 없습니다."
                ),
            }

        # --------------------------------------
        # 4. 기존 Assembly 위치 확인
        # --------------------------------------

        old_rows = current_bom[
            current_bom["bom_child"]
            .astype(str)
            .str.strip()
            .eq(
                str(old_assembly_id).strip()
            )
        ]

        if len(old_rows) != 1:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "교체 대상 Assembly를 "
                    "정확히 1건 찾을 수 없습니다."
                ),
            }

        old_row = old_rows.iloc[0]

        old_path = str(
            old_row["bom_path"]
        ).strip()

        old_level = int(
            old_row["level"]
        )

        old_required_quantity = float(
            old_row["required_quantity"]
        )

        # --------------------------------------
        # 5. 기존 Assembly + subtree 제거
        # --------------------------------------

        subtree_mask = (
            current_bom["bom_path"]
            .astype(str)
            .str.strip()
            .eq(old_path)
            |
            current_bom["bom_path"]
            .astype(str)
            .str.strip()
            .str.startswith(
                old_path + "/"
            )
        )

        revised_bom = current_bom[
            ~subtree_mask
        ].copy(deep=True)

        # --------------------------------------
        # 6. 신규 Assembly subtree 조회
        # --------------------------------------

        new_subtree = (
            self.bom_service
            .get_bom_explosion(
                new_assembly_id,
                as_of_date=as_of_date,
            )
            .copy(deep=True)
        )

        # 신규 Assembly 자체의 하위가 없어도
        # Assembly Row 자체는 만들어야 하므로 허용

        # --------------------------------------
        # 7. 신규 Assembly Root Row 생성
        # --------------------------------------

        new_root = old_row.copy()

        new_root["bom_child"] = (
            new_assembly_id
        )

        new_material = (
            self.bom_service
            .materials[
                self.bom_service.materials[
                    "material_id"
                ]
                .astype(str)
                .str.strip()
                .eq(
                    str(new_assembly_id).strip()
                )
            ]
        )

        if new_material.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "신규 Assembly의 Material Master를 "
                    "찾을 수 없습니다."
                ),
            }

        new_root["bom_child_name"] = str(
            new_material.iloc[0][
                "material_name"
            ]
        ).strip()

        new_root["review_revision"] = (
            new_revision
        )

        new_root["bom_path"] = (
            old_path.rsplit("/", 1)[0]
            + "/"
            + new_assembly_id
        )

        new_root["review_action"] = (
            "REPLACE"
        )

        new_root["source"] = "REVIEW"
        new_root["modified_yn"] = "Y"
        new_root["modified_by"] = (
            modified_by
        )
        new_root["modified_date"] = (
            modified_date
        )
        new_root["remark"] = remark

        new_root_path = str(
            new_root["bom_path"]
        )

        # --------------------------------------
        # 8. 신규 Assembly 하위 구조 변환
        # --------------------------------------

        new_rows = []

        for _, subtree_row in (
            new_subtree.iterrows()
        ):
            row = subtree_row.copy()

            relative_level = int(
                row["level"]
            )

            row["level"] = (
                old_level
                + relative_level
            )

            source_path = str(
                row["bom_path"]
            ).strip()

            if source_path.startswith(
                new_assembly_id + "/"
            ):
                relative_path = (
                    source_path[
                        len(new_assembly_id) + 1:
                    ]
                )

                row["bom_path"] = (
                    new_root_path
                    + "/"
                    + relative_path
                )
            else:
                row["bom_path"] = (
                    new_root_path
                    + "/"
                    + str(
                        row["bom_child"]
                    ).strip()
                )

            row["required_quantity"] = (
                float(
                    row["required_quantity"]
                )
                * old_required_quantity
            )

            row["review_id"] = (
                normalized_review_id
            )

            row["change_id"] = (
                review["change_id"]
            )

            row["review_revision"] = (
                new_revision
            )

            row["product_id"] = (
                review["product_id"]
            )

            row["review_action"] = "ADD"
            row["source"] = "REVIEW"
            row["modified_yn"] = "Y"
            row["modified_by"] = modified_by
            row["modified_date"] = (
                modified_date
            )
            row["remark"] = remark

            new_rows.append(row)

        # --------------------------------------
        # 9. 기존 유지 Row도 새 Revision으로
        # --------------------------------------

        revised_bom[
            "review_revision"
        ] = new_revision

        # --------------------------------------
        # 10. 신규 Root 추가
        # --------------------------------------

        revised_bom = pd.concat(
            [
                revised_bom,
                pd.DataFrame(
                    [new_root]
                ),
            ],
            ignore_index=True,
        )

        # 신규 subtree 추가
        if new_rows:
            revised_bom = pd.concat(
                [
                    revised_bom,
                    pd.DataFrame(
                        new_rows
                    ),
                ],
                ignore_index=True,
            )

        # --------------------------------------
        # 11. Review Detail 스키마 정렬
        # --------------------------------------

        detail_columns = list(
            self.review_bom_detail.columns
        )

        revised_bom = revised_bom[
            detail_columns
        ].copy()

        self.review_bom_detail = pd.concat(
            [
                self.review_bom_detail,
                revised_bom,
            ],
            ignore_index=True,
        )

        self._save_review_bom_detail()

        # --------------------------------------
        # 12. Header → 새 Revision / 재검증 필요
        # --------------------------------------

        header_mask = (
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        )

        self.review_bom.loc[
            header_mask,
            "current_revision",
        ] = new_revision

        self.review_bom.loc[
            header_mask,
            "review_status",
        ] = "RECHECK_REQUIRED"

        self.review_bom.loc[
            header_mask,
            "review_result",
        ] = "PENDING"

        # 새 Revision 생성 시 기존 승인 Revision은
        # 임의로 덮어쓰지 않음
        self._save_review_bom()

        return {
            "success": True,
            "review_id": normalized_review_id,
            "previous_revision": (
                current_revision
            ),
            "current_revision": (
                new_revision
            ),
            "old_assembly_id": (
                old_assembly_id
            ),
            "new_assembly_id": (
                new_assembly_id
            ),
            "review_status": (
                "RECHECK_REQUIRED"
            ),
            "message": (
                f"Assembly 교체가 반영된 "
                f"Review BOM Rev.{new_revision}이 "
                "생성되었습니다."
            ),
        }

    def _get_review_revision(
        self,
        review_id: str,
        revision: int,
    ) -> pd.DataFrame:
        normalized_review_id = (
            review_id.strip().upper()
        )

        return (
            self.review_bom_detail[
                (
                    self.review_bom_detail[
                        "review_id"
                    ]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq(normalized_review_id)
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
            .copy(deep=True)
        )

    def _get_review_revision_changes(
        self,
        review_id: str,
        from_revision: int,
        to_revision: int,
    ) -> list[dict]:
        """
        두 Review BOM Revision을 비교하여
        변경된 BOM 관계만 추출합니다.

        현재 기준:
        - bom_parent
        - location
        - sequence_no

        동일 위치에서 bom_child가 달라진 경우
        REPLACE 변경으로 판단합니다.
        """

        before_bom = self._get_review_revision(
            review_id=review_id,
            revision=from_revision,
        )

        after_bom = self._get_review_revision(
            review_id=review_id,
            revision=to_revision,
        )

        if before_bom.empty or after_bom.empty:
            return []

        changes = []

        key_columns = [
            "bom_parent",
            "location",
            "sequence_no",
        ]

        before_lookup = {}

        for _, row in before_bom.iterrows():
            key = (
                str(row["bom_parent"]).strip(),
                str(row["location"]).strip(),
                int(row["sequence_no"]),
            )

            before_lookup[key] = str(
                row["bom_child"]
            ).strip()

        after_lookup = {}

        for _, row in after_bom.iterrows():
            key = (
                str(row["bom_parent"]).strip(),
                str(row["location"]).strip(),
                int(row["sequence_no"]),
            )

            after_lookup[key] = str(
                row["bom_child"]
            ).strip()

        common_keys = (
            set(before_lookup.keys())
            & set(after_lookup.keys())
        )

        for key in common_keys:
            old_material_id = before_lookup[
                key
            ]

            new_material_id = after_lookup[
                key
            ]

            if old_material_id == new_material_id:
                continue

            bom_parent, location, sequence_no = (
                key
            )

            changes.append({
                "action": "REPLACE",
                "bom_parent": bom_parent,
                "location": location,
                "sequence_no": sequence_no,
                "old_material_id": old_material_id,
                "new_material_id": new_material_id,
            })

        return changes

    def revalidate_review(
        self,
        review_id: str,
        checked_date: str | None = None,
    ) -> dict:
        """
        현재 Review BOM Revision 전체를
        기존 DesignChangeService Rule Engine으로 재검증합니다.
        """

        if checked_date is None:
            checked_date = (
                pd.Timestamp.today()
                .strftime("%Y-%m-%d")
            )

        normalized_review_id = (
            review_id.strip().upper()
        )

        review_rows = self.review_bom[
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        ]

        if review_rows.empty:
            return {
                "success": False,
                "review_id": review_id,
                "message": (
                    "품평회 정보를 찾을 수 없습니다."
                ),
            }

        review = review_rows.iloc[0]

        current_revision = int(
            review["current_revision"]
        )

        product_id = str(
            review["product_id"]
        ).strip()

        current_bom = (
            self.review_bom_detail[
                (
                    self.review_bom_detail["review_id"]
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq(normalized_review_id)
                )
                &
                (
                    pd.to_numeric(
                        self.review_bom_detail[
                            "review_revision"
                        ],
                        errors="coerce",
                    )
                    == current_revision
                )
            ]
            .copy(deep=True)
        )

        if current_bom.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "현재 품평회 BOM Revision을 "
                    "찾을 수 없습니다."
                ),
            }

        if self.design_change_service is None:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "message": (
                    "DesignChangeService가 "
                    "설정되지 않았습니다."
                ),
            }

        validation = (
            self.design_change_service
            .validate_bom_rules(
                product_id=product_id,
                bom=current_bom,
            )
        )

        compatibility_results = []

        if current_revision > 1:
            changes = (
                self._get_review_revision_changes(
                    review_id=normalized_review_id,
                    from_revision=current_revision - 1,
                    to_revision=current_revision,
                )
            )

            for change in changes:
                if (
                    str(change["action"])
                    .strip()
                    .upper()
                    != "REPLACE"
                ):
                    continue

                compatibility = (
                    self.design_change_service
                    .validate_compatibility(
                        product_id=product_id,
                        new_material_id=(
                            change["new_material_id"]
                        ),
                        bom=current_bom,
                    )
                )

                compatibility_results.append({
                    "old_material_id": (
                        change["old_material_id"]
                    ),
                    "new_material_id": (
                        change["new_material_id"]
                    ),
                    "status": (
                        compatibility["status"]
                    ),
                    "message": (
                        compatibility["message"]
                    ),
                    "blocking_reasons": (
                        compatibility.get(
                            "blocking_reasons",
                            [],
                        )
                    ),
                })

        rule_result = str(
            validation["result"]
        ).strip().upper()

        compatibility_statuses = {
            str(result["status"])
            .strip()
            .upper()
            for result in compatibility_results
        }

        all_statuses = {
            rule_result
        }

        all_statuses.update(
            compatibility_statuses
        )

        if "FAIL" in all_statuses:
            validation_result = "FAIL"

        elif "CONDITIONAL" in all_statuses:
            validation_result = "CONDITIONAL"

        else:
            validation_result = "PASS"

        if validation_result in {
            "PASS",
            "CONDITIONAL",
        }:
            review_status = "IN_REVIEW"

        else:
            review_status = "RECHECK_REQUIRED"

        # --------------------------------------
        # 검증 결과 Detail 저장
        # --------------------------------------

        self._save_review_validation_results(
            review_id=normalized_review_id,
            change_id=str(
                review["change_id"]
            ).strip(),
            review_revision=current_revision,
            rule_results=validation[
                "rule_results"
            ],
            compatibility_results=(
                compatibility_results
            ),
            checked_date=checked_date,
        )


        # --------------------------------------
        # Review Header 상태 변경
        # --------------------------------------

        header_mask = (
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        )

        self.review_bom.loc[
            header_mask,
            "review_status",
        ] = review_status

        self.review_bom.loc[
            header_mask,
            "review_result",
        ] = validation_result

        self._save_review_bom()

        return {
            "success": True,
            "review_id": normalized_review_id,
            "product_id": product_id,
            "review_revision": current_revision,
            "review_status": review_status,
            "review_result": validation_result,
            "rule_result": rule_result,
            "rule_results": validation[
                "rule_results"
            ],
            "compatibility_results": (
                compatibility_results
            ),
            "message": (
                "품평회 BOM 재검증이 "
                "완료되었습니다."
            ),
        }    

    def approve_review(
        self,
        review_id: str,
        reviewed_by: str,
        completed_date: str,
        decision_reason: str = "",
    ) -> dict:
        """
        품평회 담당자가 최종 승인합니다.

        현재 1차 정책:
        - review_result = PASS인 경우만 승인 가능
        - 승인 완료 시 review_bom은 APPROVED
        - change_bom은 APPROVED_TO_APPLY
        - Production BOM 자체는 아직 변경하지 않음
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        # --------------------------------------
        # 1. Review Header 조회
        # --------------------------------------

        review_rows = self.review_bom[
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        ]

        if review_rows.empty:
            return {
                "success": False,
                "review_id": review_id,
                "message": (
                    "품평회 정보를 찾을 수 없습니다."
                ),
            }

        review = review_rows.iloc[0]

        review_status = str(
            review["review_status"]
        ).strip().upper()

        review_result = str(
            review["review_result"]
        ).strip().upper()

        change_id = str(
            review["change_id"]
        ).strip()

        # --------------------------------------
        # 2. 재검증 완료 여부 확인
        # --------------------------------------

        if review_status != "IN_REVIEW":
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "message": (
                    "재검증이 완료된 IN_REVIEW 상태의 "
                    "품평회만 승인할 수 있습니다."
                ),
            }

        # --------------------------------------
        # 3. PASS만 승인
        # --------------------------------------

        if review_result != "PASS":
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "review_result": review_result,
                "message": (
                    "현재 정책에서는 품평회 재검증 결과가 "
                    "PASS인 경우만 최종 승인할 수 있습니다."
                ),
            }

        # --------------------------------------
        # 4. Review Header 승인 처리
        # --------------------------------------

        review_mask = (
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        )

        # 빈 CSV 열은 pandas 버전에 따라 float로 추론될 수 있으므로
        # 승인 이력 문자열을 기록하기 전에 명시적으로 object로 고정한다.
        for column in (
            "review_status",
            "completed_date",
            "reviewed_by",
            "decision_reason",
        ):
            self.review_bom[column] = self.review_bom[column].astype("object")

        self.review_bom.loc[
            review_mask,
            "review_status",
        ] = "APPROVED"

        self.review_bom.loc[
            review_mask,
            "completed_date",
        ] = completed_date

        self.review_bom.loc[
            review_mask,
            "reviewed_by",
        ] = reviewed_by

        self.review_bom.loc[
            review_mask,
            "decision_reason",
        ] = decision_reason

        self.review_bom.loc[
            review_mask,
            "approved_revision",
        ] = int(
            review["current_revision"]
        )

        self._save_review_bom()

        # --------------------------------------
        # 5. Design Change 적용 가능 상태로 변경
        # --------------------------------------

        change_mask = (
            self.change_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(change_id.upper())
        )

        if not change_mask.any():
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "message": (
                    "연결된 설계변경 Header를 "
                    "찾을 수 없습니다."
                ),
            }

        self.change_bom.loc[
            change_mask,
            "apply_status",
        ] = "APPROVED_TO_APPLY"

        self.change_bom.loc[
            change_mask,
            "approved_by",
        ] = reviewed_by

        self._save_change_bom()

        return {
            "success": True,
            "review_id": normalized_review_id,
            "change_id": change_id,
            "review_status": "APPROVED",
            "review_result": "PASS",
            "apply_status": "APPROVED_TO_APPLY",
            "message": (
                "품평회 최종 승인이 완료되었습니다. "
                "Production BOM 적용이 가능합니다."
            ),
        }    

    def get_review_summary(
        self,
        review_id: str,
    ) -> dict:
        """
        Review BOM의 현재 Revision 기준 검증 결과를
        유형별로 요약합니다.
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        review_rows = self.review_bom[
            self.review_bom["review_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_review_id)
        ]

        if review_rows.empty:
            return {
                "success": False,
                "review_id": review_id,
                "message": (
                    "품평회 정보를 찾을 수 없습니다."
                ),
            }

        review = review_rows.iloc[0]

        current_revision = int(
            review["current_revision"]
        )

        check_rows = self.review_bom_check[
            (
                self.review_bom_check["review_id"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(normalized_review_id)
            )
            &
            (
                pd.to_numeric(
                    self.review_bom_check[
                        "review_revision"
                    ],
                    errors="coerce",
                )
                == current_revision
            )
        ].copy()

        if check_rows.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "review_revision": current_revision,
                "message": (
                    "현재 Revision의 품평회 검증 결과가 "
                    "존재하지 않습니다."
                ),
            }

        check_types = [
            "BOM_STRUCTURE",
            "LIFECYCLE",
            "APPROVAL",
            "SUPPLIER",
            "BOM_ATTRIBUTE",
            "COMPATIBILITY",
        ]

        summary = {}

        for check_type in check_types:
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

            if (statuses == "FAIL").any():
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
                "count": len(rows),
                "fail_count": int(
                    (statuses == "FAIL").sum()
                ),
                "conditional_count": int(
                    (
                        statuses
                        == "CONDITIONAL"
                    ).sum()
                ),
            }

        return {
            "success": True,
            "review_id": normalized_review_id,
            "change_id": str(
                review["change_id"]
            ).strip(),
            "product_id": str(
                review["product_id"]
            ).strip(),
            "review_revision": current_revision,
            "review_status": str(
                review["review_status"]
            ).strip(),
            "review_result": str(
                review["review_result"]
            ).strip(),
            "summary": summary,
        }    
