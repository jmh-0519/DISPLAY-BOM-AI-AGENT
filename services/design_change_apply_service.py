from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from services.bom_service import BomService


class DesignChangeApplyService:
    """
    설계변경의 Preview(Virtual BOM) 및 실제 적용을 담당하는 Service입니다.

    Preview와 승인된 Preview Revision의 Controlled Apply를 제공합니다.
    """

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

        self.design_change_bom = self._load_csv(
            "change_bom_detail.csv"
        )

        self.review_bom = self._load_csv(
            "review_bom.csv"
        )

        self.review_bom_detail = self._load_csv(
            "review_bom_detail.csv"
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

    def preview_replace(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        REPLACE 적용 후의 Virtual BOM을 생성합니다.
        실제 bom.csv는 변경하지 않습니다.
        """

        current_bom = (
            self.bom_service
            .get_bom_explosion(
                model_id=product_id,
                as_of_date=as_of_date,
            )
            .copy()
        )

        if current_bom.empty:
            return current_bom

        old_material = self._find_exact_material(old_material_id)
        new_material = self._find_exact_material(new_material_id)

        if old_material is None or new_material is None:
            return current_bom

        old_type = str(
            old_material.get("material_type", "")
        ).strip().upper()

        new_type = str(
            new_material.get("material_type", "")
        ).strip().upper()

        if old_type == "COMPONENT" and new_type == "COMPONENT":
            return self._replace_component(
                current_bom=current_bom,
                old_material_id=old_material_id,
                new_material_id=new_material_id,
                new_material=new_material,
            )

        if old_type == "ASSEMBLY" and new_type == "ASSEMBLY":
            return self._replace_assembly(
                current_bom=current_bom,
                old_material_id=old_material_id,
                new_material_id=new_material_id,
                new_material=new_material,
                as_of_date=as_of_date,
            )

        return current_bom

    def create_preview_revision(
        self,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        as_of_date: str | date | None = None,
    ) -> dict:
        """변경 전·후 BOM을 비교하는 읽기 전용 Preview를 생성합니다."""

        original_bom = self.bom_service.get_bom_explosion(
            model_id=product_id,
            as_of_date=as_of_date,
        ).copy()
        preview_bom = self.preview_replace(
            product_id=product_id,
            old_material_id=old_material_id,
            new_material_id=new_material_id,
            as_of_date=as_of_date,
        )

        if original_bom.empty or preview_bom.empty:
            raise ValueError("Preview를 생성할 수 있는 BOM 데이터가 없습니다.")

        original_ids = set(
            original_bom["bom_child"].astype(str).str.strip()
        )
        preview_ids = set(
            preview_bom["bom_child"].astype(str).str.strip()
        )
        if (
            old_material_id.strip() in preview_ids
            or new_material_id.strip() not in preview_ids
        ):
            raise ValueError(
                "요청한 자재 교체가 Preview BOM에 반영되지 않았습니다."
            )

        revision_source = "|".join(
            [
                product_id.strip().upper(),
                old_material_id.strip().upper(),
                new_material_id.strip().upper(),
                str(as_of_date or "CURRENT"),
            ]
        )
        revision_hash = hashlib.sha256(
            revision_source.encode("utf-8")
        ).hexdigest()[:12].upper()

        return {
            "success": True,
            "preview_revision": f"PREVIEW-{revision_hash}",
            "product_id": product_id,
            "old_material_id": old_material_id,
            "new_material_id": new_material_id,
            "as_of_date": str(as_of_date) if as_of_date else None,
            "before_row_count": len(original_bom),
            "after_row_count": len(preview_bom),
            "removed_material_ids": sorted(original_ids - preview_ids),
            "added_material_ids": sorted(preview_ids - original_ids),
            "preview_bom": json.loads(
                preview_bom.to_json(
                    orient="records",
                    force_ascii=False,
                    date_format="iso",
                )
            ),
            "production_bom_modified": False,
            "message": (
                "변경 BOM Preview Revision이 생성되었습니다. "
                "Production BOM은 변경되지 않았습니다."
            ),
        }

    def apply_approved_preview(
        self,
        preview_revision: str,
        product_id: str,
        old_material_id: str,
        new_material_id: str,
        preview_as_of_date: str | date,
        effective_date: str | date,
        applied_by: str,
    ) -> dict:
        """승인된 동일 Preview Revision을 Production BOM에 적용합니다.

        승인 여부와 Workflow 단계는 Agent State에서 선행 검증하며, 이
        Service는 Revision 일치, 단일 활성 관계, 중복 적용을 재검증합니다.
        """

        values = {
            "preview_revision": preview_revision,
            "product_id": product_id,
            "old_material_id": old_material_id,
            "new_material_id": new_material_id,
            "preview_as_of_date": preview_as_of_date,
            "effective_date": effective_date,
            "applied_by": applied_by,
        }
        for name, value in values.items():
            if not isinstance(value, (str, date)) or not str(value).strip():
                raise ValueError(f"{name}는 비어 있을 수 없습니다.")

        expected = self.create_preview_revision(
            product_id=str(product_id).strip(),
            old_material_id=str(old_material_id).strip(),
            new_material_id=str(new_material_id).strip(),
            as_of_date=str(preview_as_of_date).strip(),
        )
        if expected["preview_revision"] != str(preview_revision).strip():
            raise ValueError("승인된 Preview Revision과 적용 요청이 일치하지 않습니다.")

        effective = pd.Timestamp(effective_date).normalize()
        current = self.bom_service.get_bom_explosion(
            model_id=str(product_id).strip(),
            as_of_date=effective.strftime("%Y-%m-%d"),
        )
        matches = current[
            current["bom_child"].astype(str).str.strip().str.upper().eq(
                str(old_material_id).strip().upper()
            )
        ]
        if len(matches) != 1:
            raise ValueError("적용 대상 활성 BOM 관계가 정확히 1건이어야 합니다.")

        relation = matches.iloc[0]
        parent_id = str(relation["bom_parent"]).strip()
        bom = self.bom_service.bom.copy(deep=True)
        active_mask = (
            bom["bom_parent"].astype(str).str.strip().str.upper().eq(parent_id.upper())
            & bom["bom_child"].astype(str).str.strip().str.upper().eq(
                str(old_material_id).strip().upper()
            )
            & (bom["start_date"].isna() | (bom["start_date"] <= effective))
            & (bom["end_date"].isna() | (bom["end_date"] >= effective))
        )
        if int(active_mask.sum()) != 1:
            raise ValueError("Production BOM의 활성 관계가 변경되어 적용을 중단했습니다.")

        duplicate_mask = (
            bom["bom_parent"].astype(str).str.strip().str.upper().eq(parent_id.upper())
            & bom["bom_child"].astype(str).str.strip().str.upper().eq(
                str(new_material_id).strip().upper()
            )
            & (bom["start_date"].isna() | (bom["start_date"] <= effective))
            & (bom["end_date"].isna() | (bom["end_date"] >= effective))
        )
        if duplicate_mask.any():
            raise ValueError("신규 자재가 이미 활성 BOM에 존재하여 중복 적용할 수 없습니다.")

        old_index = bom[active_mask].index[0]
        old_row = bom.loc[old_index].copy()
        new_material = self._find_exact_material(str(new_material_id).strip())
        if new_material is None:
            raise ValueError("신규 자재 Master를 찾을 수 없습니다.")

        bom.loc[old_index, "end_date"] = effective - pd.Timedelta(days=1)
        new_row = old_row.to_dict()
        new_row.update({
            "bom_child": str(new_material_id).strip(),
            "bom_child_name": str(new_material.get("material_name", new_material_id)),
            "start_date": effective,
            "end_date": pd.Timestamp("2099-12-31"),
        })
        bom = pd.concat([bom, pd.DataFrame([new_row])], ignore_index=True)
        original = self.bom_service.bom.copy(deep=True)
        try:
            self._save_bom(bom)
            applied = self.bom_service.get_bom_explosion(
                model_id=str(product_id).strip(),
                as_of_date=effective.strftime("%Y-%m-%d"),
            )
            applied_ids = set(applied["bom_child"].astype(str).str.strip())
            if str(old_material_id).strip() in applied_ids or str(new_material_id).strip() not in applied_ids:
                raise RuntimeError("적용 후 BOM 무결성 검증에 실패했습니다.")
        except Exception:
            self._save_bom(original)
            raise

        application_id = "APPLY-" + str(preview_revision).strip().removeprefix("PREVIEW-")
        return {
            "success": True,
            "result": "APPLIED",
            "application_id": application_id,
            "preview_revision": str(preview_revision).strip(),
            "product_id": str(product_id).strip(),
            "old_material_id": str(old_material_id).strip(),
            "new_material_id": str(new_material_id).strip(),
            "effective_date": effective.strftime("%Y-%m-%d"),
            "applied_by": str(applied_by).strip(),
            "production_bom_modified": True,
            "message": "승인된 Preview Revision이 Production BOM에 적용되었습니다.",
        }

    def _apply_change_actions(
        self,
        original_bom: pd.DataFrame,
        changed_bom: pd.DataFrame,
        old_material_id: str,
        new_material_id: str,
    ) -> pd.DataFrame:
        result = changed_bom.copy(
            deep=True
        )

        result["change_action"] = "NONE"

        # Production BOM의 parent-child 관계
        original_relations = set(
            zip(
                original_bom["bom_parent"]
                .astype(str)
                .str.strip(),
                original_bom["bom_child"]
                .astype(str)
                .str.strip(),
            )
        )

        # 변경 후 새롭게 생성된 관계 → ADD
        for index, row in result.iterrows():
            relation = (
                str(row["bom_parent"]).strip(),
                str(row["bom_child"]).strip(),
            )

            if relation not in original_relations:
                result.at[
                    index,
                    "change_action",
                ] = "ADD"

        # 직접 교체된 신규 자재는 ADD보다
        # 의미가 강한 REPLACE로 표시
        replace_mask = (
            result["bom_child"]
            .astype(str)
            .str.strip()
            .eq(
                str(new_material_id).strip()
            )
        )

        result.loc[
            replace_mask,
            "change_action",
        ] = "REPLACE"

        return result

    def create_design_change_bom(
        self,
        change_id: str,
        created_date: str,
    ) -> dict:
        """
        검증 완료된 설계변경 건의 Preview BOM을
        change_bom_detail.csv에 Snapshot으로 저장합니다.

        Production BOM은 변경하지 않습니다.
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

        item_rows = self.design_change_items[
            self.design_change_items["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        ]

        if item_rows.empty:
            return {
                "success": False,
                "change_id": change_id,
                "message": (
                    "설계변경 Item을 찾을 수 없습니다."
                ),
            }

        # 현재는 REPLACE 1건 기준
        item = item_rows.iloc[0]

        product_id = str(
            change["product_id"]
        ).strip()

        old_material_id = str(
            item["old_bom_child"]
        ).strip()

        new_material_id = str(
            item["new_bom_child"]
        ).strip()

        effective_date = str(
            change["effective_date"]
        ).strip()

        # ------------------------------------------
        # Preview BOM 생성
        # ------------------------------------------

        preview_bom = self.preview_replace(
            product_id=product_id,
            old_material_id=old_material_id,
            new_material_id=new_material_id,
            as_of_date=effective_date,
        )

        if preview_bom.empty:
            return {
                "success": False,
                "change_id": change_id,
                "message": (
                    "설계변경 BOM을 생성할 수 없습니다."
                ),
            }

        snapshot = preview_bom.copy(
            deep=True
        )

        # ------------------------------------------
        # Snapshot 관리 컬럼 추가
        # ------------------------------------------

        snapshot.insert(
            0,
            "product_id",
            product_id,
        )

        snapshot.insert(
            0,
            "change_id",
            normalized_change_id,
        )

        # ------------------------------------------
        # 변경 전 Production BOM 조회
        # ------------------------------------------

        original_bom = (
            self.bom_service.get_bom_explosion(
                product_id,
                as_of_date=effective_date,
            )
        )

        # ------------------------------------------
        # Before / After 관계 비교
        # ------------------------------------------

        snapshot = self._apply_change_actions(
            original_bom=original_bom,
            changed_bom=snapshot,
            old_material_id=old_material_id,
            new_material_id=new_material_id,
        )

        snapshot["created_date"] = created_date

        # ------------------------------------------
        # change_bom_detail 스키마에 맞춤
        # ------------------------------------------

        columns = [
            "change_id",
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
            "change_action",
            "created_date",
        ]

        snapshot = snapshot[
            columns
        ].copy()

        # ------------------------------------------
        # 동일 change_id 기존 Snapshot 제거
        # ------------------------------------------

        existing_mask = (
            self.design_change_bom["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        )

        self.design_change_bom = (
            self.design_change_bom[
                ~existing_mask
            ].copy()
        )

        # ------------------------------------------
        # 신규 Snapshot 저장
        # ------------------------------------------

        self.design_change_bom = pd.concat(
            [
                self.design_change_bom,
                snapshot,
            ],
            ignore_index=True,
        )

        self._save_design_change_bom()

        # ------------------------------------------
        # 설계변경 상태 → REVIEW_READY
        # ------------------------------------------

        change_mask = (
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(normalized_change_id)
        )

        self.design_changes.loc[
            change_mask,
            "apply_status",
        ] = "REVIEW_READY"

        self._save_design_changes()

        return {
            "success": True,
            "change_id": normalized_change_id,
            "product_id": product_id,
            "result": "REVIEW_READY",
            "bom_row_count": len(snapshot),
            "message": (
                "설계변경 BOM Snapshot이 생성되었습니다."
            ),
        }

    def apply_replace(
        self,
        change_id: str,
        applied_by: str,
        applied_date: str | date | None = None,
    ) -> dict:
        """
        승인 완료된 REPLACE 설계변경을
        실제 bom.csv에 적용합니다.

        현재 1차 구현 범위:
        - 단일 Component REPLACE
        - Assembly REPLACE는 다음 단계에서 지원

        기존 BOM 행은 삭제하지 않고
        end_date를 종료합니다.

        신규 BOM 관계는 effective_date부터
        새로운 행으로 추가합니다.
        """

        # --------------------------------------------------
        # 1. Design Change Header 조회
        # --------------------------------------------------

        change_rows = self.design_changes[
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                change_id
                .strip()
                .upper()
            )
        ]

        if change_rows.empty:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "설계변경 정보를 찾을 수 없습니다."
                ),
            }

        change = change_rows.iloc[0]

        change_type = str(
            change["change_type"]
        ).strip().upper()

        analysis_result = str(
            change["analysis_result"]
        ).strip().upper()

        approval_status = str(
            change["approval_status"]
        ).strip().upper()

        apply_status = str(
            change["apply_status"]
        ).strip().upper()

        # --------------------------------------------------
        # 2. 적용 가능 상태 확인
        # --------------------------------------------------

        if change_type != "REPLACE":
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "REPLACE 변경만 지원합니다."
                ),
            }

        if analysis_result == "FAIL":
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "설계변경 분석 결과가 FAIL이므로 "
                    "적용할 수 없습니다."
                ),
            }

        if approval_status != "APPROVED":
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "승인 완료된 설계변경만 "
                    "적용할 수 있습니다."
                ),
            }

        if apply_status != "APPROVED_TO_APPLY":
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "품평회 최종 승인이 완료된 "
                    "APPROVED_TO_APPLY 상태의 "
                    "설계변경만 Production BOM에 "
                    "적용할 수 있습니다."
                ),
            }

        # --------------------------------------------------
        # 3. Change Detail 조회
        # --------------------------------------------------

        items = self.design_change_items[
            self.design_change_items["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                change_id
                .strip()
                .upper()
            )
        ].copy()

        if items.empty:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "설계변경 Detail이 없습니다."
                ),
            }

        if len(items) != 1:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "현재 1차 구현은 단일 변경 Item만 "
                    "지원합니다."
                ),
            }

        item = items.iloc[0]

        action = str(
            item["action"]
        ).strip().upper()

        if action != "REPLACE":
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "현재 REPLACE Item만 지원합니다."
                ),
            }

        bom_parent = str(
            item["bom_parent"]
        ).strip()

        old_material_id = str(
            item["old_bom_child"]
        ).strip()

        new_material_id = str(
            item["new_bom_child"]
        ).strip()

        # --------------------------------------------------
        # 4. Component → Component인지 확인
        # --------------------------------------------------

        old_material = self._find_exact_material(
            old_material_id
        )

        new_material = self._find_exact_material(
            new_material_id
        )

        if (
            old_material is None
            or new_material is None
        ):
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "기존 또는 신규 자재 Master를 "
                    "찾을 수 없습니다."
                ),
            }

        old_type = str(
            old_material.get(
                "material_type",
                "",
            )
        ).strip().upper()

        new_type = str(
            new_material.get(
                "material_type",
                "",
            )
        ).strip().upper()

        supported_replace = (
            (
                old_type == "COMPONENT"
                and new_type == "COMPONENT"
            )
            or
            (
                old_type == "ASSEMBLY"
                and new_type == "ASSEMBLY"
            )
        )

        if not supported_replace:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "동일한 Material Type 간의 "
                    "REPLACE만 지원합니다."
                ),
            }

        # --------------------------------------------------
        # 5. Effective Date 계산
        # --------------------------------------------------

        effective_date = pd.Timestamp(
            change["effective_date"]
        ).normalize()

        old_end_date = (
            effective_date
            - pd.Timedelta(days=1)
        )

        if applied_date is None:
            applied_timestamp = (
                pd.Timestamp.today()
                .normalize()
            )
        else:
            applied_timestamp = pd.Timestamp(
                applied_date
            ).normalize()

        # --------------------------------------------------
        # 6. 현재 유효 BOM 관계 확인
        # --------------------------------------------------

        bom = self.bom_service.bom.copy()

        original_bom = bom.copy(
            deep=True
        )

        active_mask = (
            bom["bom_parent"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                bom_parent.upper()
            )
            &
            bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                old_material_id.upper()
            )
            &
            (
                bom["start_date"].isna()
                |
                (
                    bom["start_date"]
                    <= effective_date
                )
            )
            &
            (
                bom["end_date"].isna()
                |
                (
                    bom["end_date"]
                    >= effective_date
                )
            )
        )

        active_rows = bom[
            active_mask
        ]

        if active_rows.empty:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "적용 기준일에 유효한 기존 "
                    "BOM 관계를 찾을 수 없습니다."
                ),
            }

        if len(active_rows) > 1:
            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "동일한 활성 BOM 관계가 "
                    "2건 이상 존재합니다."
                ),
            }

        old_index = active_rows.index[0]
        old_row = bom.loc[
            old_index
        ].copy()

        # --------------------------------------------------
        # 7. 기존 관계 종료
        # --------------------------------------------------

        bom.loc[
            old_index,
            "end_date",
        ] = old_end_date

        # --------------------------------------------------
        # 8. 신규 관계 생성
        # --------------------------------------------------

        new_row = {
            "bom_parent": (
                old_row["bom_parent"]
            ),
            "bom_parent_name": (
                old_row["bom_parent_name"]
            ),
            "bom_child": new_material_id,
            "bom_child_name": str(
                new_material.get(
                    "material_name",
                    new_material_id,
                )
            ),
            "location": item["location"],
            "sequence_no": (
                item["sequence_no"]
            ),
            "quantity": item["quantity"],
            "start_date": effective_date,
            "end_date": pd.Timestamp(
                "2099-12-31"
            ),
        }

        bom = pd.concat(
            [
                bom,
                pd.DataFrame(
                    [new_row]
                ),
            ],
            ignore_index=True,
        )

        # --------------------------------------------------
        # 9. bom.csv 저장
        # --------------------------------------------------

        self._save_bom(
            bom
        )

        # --------------------------------------------------
        # 10. 적용 결과 Integrity Check
        # --------------------------------------------------

        integrity_result = (
            self._validate_applied_change(
                change_id=change_id,
                change=change,
                item=item,
            )
        )

        change_mask = (
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(
                change_id
                .strip()
                .upper()
            )
        )

        # --------------------------------------------------
        # 11. Integrity 실패 처리
        # --------------------------------------------------

        if not integrity_result["success"]:

            # ------------------------------------------
            # Integrity 실패 → BOM Rollback
            # ------------------------------------------

            self._save_bom(
                original_bom
            )

            self.design_changes.loc[
                change_mask,
                "apply_status",
            ] = "FAILED"

            self.design_changes.loc[
                change_mask,
                "applied_date",
            ] = applied_timestamp.strftime(
                "%Y-%m-%d"
            )

            self.design_changes.loc[
                change_mask,
                "applied_by",
            ] = applied_by

            self._save_design_changes()

            return {
                "success": False,
                "change_id": change_id,
                "result": "FAILED",
                "integrity_check": integrity_result,
                "message": (
                    "BOM 변경 후 Integrity Check에 "
                    "실패했습니다."
                ),
            }

        # --------------------------------------------------
        # 12. Integrity 성공 → APPLIED
        # --------------------------------------------------

        self.design_changes.loc[
            change_mask,
            "apply_status",
        ] = "APPLIED"

        self.design_changes.loc[
            change_mask,
            "applied_date",
        ] = applied_timestamp.strftime(
            "%Y-%m-%d"
        )

        self.design_changes.loc[
            change_mask,
            "applied_by",
        ] = applied_by

        self._save_design_changes()

        return {
            "success": True,
            "change_id": change_id,
            "result": "APPLIED",
            "product_id": str(
                change["product_id"]
            ),
            "old_material_id": old_material_id,
            "new_material_id": new_material_id,
            "material_type": old_type,
            "effective_date": (
                effective_date.strftime(
                    "%Y-%m-%d"
                )
            ),
            "integrity_check": integrity_result,
            "message": (
                f"{old_type} 설계변경이 "
                "정상 적용되었습니다."
            ),
        }

    def apply_approved_review(
        self,
        review_id: str,
        applied_by: str,
        applied_date: str | date | None = None,
    ) -> dict:
        """
        품평회 최종 승인된 Review BOM의 최신 Revision을
        기준으로 Production BOM을 적용합니다.

        현재 범위:
        - REPLACE 관계 적용
        - Review BOM 최신 Revision이 Source of Truth
        - Production BOM은 Effective Date 방식으로 이력 관리
        """

        normalized_review_id = (
            review_id.strip().upper()
        )

        # ------------------------------------------
        # 1. Review Header 확인
        # ------------------------------------------

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
                "result": "FAILED",
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

        approved_revision_value = (
            review.get("approved_revision")
        )

        if pd.isna(
            approved_revision_value
        ):
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "품평회 승인 Revision이 "
                    "지정되지 않았습니다."
                ),
            }

        approved_revision = int(
            approved_revision_value
        )

        # ------------------------------------------
        # 2. 품평회 최종 승인 여부 확인
        # ------------------------------------------

        if review_status != "APPROVED":
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "최종 승인된 품평회만 "
                    "Production BOM에 적용할 수 있습니다."
                ),
            }

        if review_result != "PASS":
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "품평회 결과가 PASS인 경우만 "
                    "Production BOM에 적용할 수 있습니다."
                ),
            }

        # ------------------------------------------
        # 3. Change Header 확인
        # ------------------------------------------

        change_rows = self.design_changes[
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(change_id.upper())
        ]

        if change_rows.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "연결된 설계변경 정보를 "
                    "찾을 수 없습니다."
                ),
            }

        change = change_rows.iloc[0]

        apply_status = str(
            change["apply_status"]
        ).strip().upper()

        if apply_status != "APPROVED_TO_APPLY":
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "APPROVED_TO_APPLY 상태의 "
                    "설계변경만 적용할 수 있습니다."
                ),
            }

        effective_date = pd.Timestamp(
            change["effective_date"]
        ).normalize()

        old_end_date = (
            effective_date
            - pd.Timedelta(days=1)
        )

        if applied_date is None:
            applied_timestamp = (
                pd.Timestamp.today()
                .normalize()
            )
        else:
            applied_timestamp = pd.Timestamp(
                applied_date
            ).normalize()

        # ------------------------------------------
        # 4. 최신 Review Revision 조회
        # ------------------------------------------

        final_review_bom = (
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
                    == approved_revision
                )
            ]
            .copy(deep=True)
        )

        if final_review_bom.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "최종 Review BOM Revision을 "
                    "찾을 수 없습니다."
                ),
            }

        # ------------------------------------------
        # 5. REPLACE 대상 추출
        # ------------------------------------------

        replace_rows = final_review_bom[
            final_review_bom["review_action"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("REPLACE")
        ].copy()

        if replace_rows.empty:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "최종 Review BOM에 "
                    "REPLACE 대상이 없습니다."
                ),
            }

        # ------------------------------------------
        # 6. Rollback용 원본 보관
        # ------------------------------------------

        bom = self.bom_service.bom.copy(
            deep=True
        )

        original_bom = bom.copy(
            deep=True
        )

        applied_items = []

        # ------------------------------------------
        # 7. Review REPLACE 관계 적용
        # ------------------------------------------

        for _, review_row in replace_rows.iterrows():

            bom_parent = str(
                review_row["bom_parent"]
            ).strip()

            new_material_id = str(
                review_row["bom_child"]
            ).strip()

            location = str(
                review_row["location"]
            ).strip()

            sequence_no = int(
                review_row["sequence_no"]
            )

            quantity = float(
                review_row["quantity"]
            )

            # 적용일 기준 동일 위치의 현재 Production BOM 관계
            active_mask = (
                bom["bom_parent"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(bom_parent.upper())
                &
                (
                    pd.to_numeric(
                        bom["sequence_no"],
                        errors="coerce",
                    )
                    == sequence_no
                )
                &
                bom["location"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(location.upper())
                &
                (
                    bom["start_date"].isna()
                    |
                    (
                        bom["start_date"]
                        <= effective_date
                    )
                )
                &
                (
                    bom["end_date"].isna()
                    |
                    (
                        bom["end_date"]
                        >= effective_date
                    )
                )
            )

            active_rows = bom[
                active_mask
            ]

            if len(active_rows) != 1:
                self._save_bom(
                    original_bom
                )

                return {
                    "success": False,
                    "review_id": normalized_review_id,
                    "change_id": change_id,
                    "result": "FAILED",
                    "message": (
                        "적용 위치의 현재 Production BOM "
                        "관계를 정확히 1건 찾을 수 없습니다. "
                        f"parent={bom_parent}, "
                        f"location={location}, "
                        f"sequence_no={sequence_no}"
                    ),
                }

            old_index = active_rows.index[0]
            old_row = bom.loc[
                old_index
            ].copy()

            old_material_id = str(
                old_row["bom_child"]
            ).strip()

            # 이미 동일한 자재면 중복 적용 방지
            if (
                old_material_id.upper()
                == new_material_id.upper()
            ):
                continue

            new_material = (
                self._find_exact_material(
                    new_material_id
                )
            )

            if new_material is None:
                self._save_bom(
                    original_bom
                )

                return {
                    "success": False,
                    "review_id": normalized_review_id,
                    "change_id": change_id,
                    "result": "FAILED",
                    "message": (
                        "Review BOM의 신규 자재 Master를 "
                        "찾을 수 없습니다: "
                        f"{new_material_id}"
                    ),
                }

            # 기존 관계 종료
            bom.loc[
                old_index,
                "end_date",
            ] = old_end_date

            # 신규 관계 생성
            new_row = {
                "bom_parent": (
                    old_row["bom_parent"]
                ),
                "bom_parent_name": (
                    old_row["bom_parent_name"]
                ),
                "bom_child": new_material_id,
                "bom_child_name": str(
                    new_material.get(
                        "material_name",
                        new_material_id,
                    )
                ),
                "location": location,
                "sequence_no": sequence_no,
                "quantity": quantity,
                "start_date": effective_date,
                "end_date": pd.Timestamp(
                    "2099-12-31"
                ),
            }

            bom = pd.concat(
                [
                    bom,
                    pd.DataFrame([new_row]),
                ],
                ignore_index=True,
            )

            applied_items.append({
                "bom_parent": bom_parent,
                "old_material_id": (
                    old_material_id
                ),
                "new_material_id": (
                    new_material_id
                ),
                "location": location,
                "sequence_no": sequence_no,
            })

        if not applied_items:
            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "message": (
                    "Production BOM에 반영할 "
                    "실제 변경사항이 없습니다."
                ),
            }

        # ------------------------------------------
        # 8. Production BOM 저장
        # ------------------------------------------

        self._save_bom(
            bom
        )

        # ------------------------------------------
        # 9. 적용 결과 Integrity Check
        # ------------------------------------------

        integrity_result = (
            self._validate_applied_review(
                review_id=normalized_review_id,
                change_id=change_id,
                effective_date=effective_date,
                applied_items=applied_items,
            )
        )

        change_mask = (
            self.design_changes["change_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(change_id.upper())
        )

        # ------------------------------------------
        # 10. Integrity 실패 → 전체 Rollback
        # ------------------------------------------

        if not integrity_result["success"]:

            self._save_bom(
                original_bom
            )

            self.design_changes.loc[
                change_mask,
                "apply_status",
            ] = "FAILED"

            self.design_changes.loc[
                change_mask,
                "applied_date",
            ] = applied_timestamp.strftime(
                "%Y-%m-%d"
            )

            self.design_changes.loc[
                change_mask,
                "applied_by",
            ] = applied_by

            self._save_design_changes()

            return {
                "success": False,
                "review_id": normalized_review_id,
                "change_id": change_id,
                "result": "FAILED",
                "integrity_check": integrity_result,
                "message": (
                    "Review BOM 적용 후 Integrity Check에 "
                    "실패하여 Production BOM을 Rollback했습니다."
                ),
            }

        # ------------------------------------------
        # 11. Integrity 성공 → APPLIED
        # ------------------------------------------

        self.design_changes.loc[
            change_mask,
            "apply_status",
        ] = "APPLIED"

        self.design_changes.loc[
            change_mask,
            "applied_date",
        ] = applied_timestamp.strftime(
            "%Y-%m-%d"
        )

        self.design_changes.loc[
            change_mask,
            "applied_by",
        ] = applied_by

        self._save_design_changes()

        return {
            "success": True,
            "review_id": normalized_review_id,
            "change_id": change_id,
            "result": "APPLIED",
            "review_revision": approved_revision,
            "effective_date": (
                effective_date.strftime(
                    "%Y-%m-%d"
                )
            ),
            "applied_items": applied_items,
            "integrity_check": integrity_result,
            "message": (
                "최종 승인된 Review BOM이 "
                "Production BOM에 정상 적용되었습니다."
            ),
        }

    def _save_bom(
        self,
        bom: pd.DataFrame,
    ) -> None:
        """
        BOM DataFrame을 bom.csv에 저장하고
        BomService Cache를 다시 로딩합니다.
        """

        save_bom = bom.copy()

        for column in [
            "start_date",
            "end_date",
        ]:
            save_bom[column] = pd.to_datetime(
                save_bom[column],
                errors="coerce",
            ).dt.strftime(
                "%Y-%m-%d"
            )

        file_path = (
            self.data_dir / "bom.csv"
        )

        save_bom.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig",
        )

        self.bom_service.bom = pd.read_csv(
            file_path,
            encoding="utf-8-sig",
        )

        self.bom_service._prepare_bom_data()

    def _save_design_changes(
        self,
    ) -> None:
        file_path = (
            self.data_dir
            / "change_bom.csv"
        )

        self.design_changes.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig",
        )

    def _save_design_change_bom(
        self,
    ) -> None:
        file_path = (
            self.data_dir
            / "change_bom_detail.csv"
        )

        self.design_change_bom.to_csv(
            file_path,
            index=False,
            encoding="utf-8-sig",
        )        

    def _validate_applied_change(
        self,
        change_id: str,
        change: pd.Series,
        item: pd.Series,
    ) -> dict:
        """
        실제 BOM 적용 결과와 Design Change 정보를 비교합니다.
        """

        effective_date = pd.Timestamp(
            change["effective_date"]
        ).normalize()

        expected_old_end_date = (
            effective_date
            - pd.Timedelta(days=1)
        )

        bom_parent = str(
            item["bom_parent"]
        ).strip()

        old_material_id = str(
            item["old_bom_child"]
        ).strip()

        new_material_id = str(
            item["new_bom_child"]
        ).strip()

        bom = self.bom_service.bom.copy()

        # ------------------------------------------
        # 기존 BOM 관계 확인
        # ------------------------------------------

        old_rows = bom[
            bom["bom_parent"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(bom_parent.upper())
            &
            bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(old_material_id.upper())
        ]

        if old_rows.empty:
            return {
                "success": False,
                "check": "OLD_BOM_HISTORY",
                "message": (
                    "기존 BOM 관계가 "
                    "존재하지 않습니다."
                ),
            }

        old_row = old_rows.iloc[-1]

        old_end_date = pd.Timestamp(
            old_row["end_date"]
        ).normalize()

        if (
            old_end_date
            != expected_old_end_date
        ):
            return {
                "success": False,
                "check": "OLD_BOM_END_DATE",
                "message": (
                    "기존 BOM의 end_date가 "
                    "올바르지 않습니다."
                ),
            }

        # ------------------------------------------
        # 신규 BOM 관계 확인
        # ------------------------------------------

        new_rows = bom[
            bom["bom_parent"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(bom_parent.upper())
            &
            bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(new_material_id.upper())
        ]

        if new_rows.empty:
            return {
                "success": False,
                "check": "NEW_BOM_EXISTS",
                "message": (
                    "신규 BOM 관계가 "
                    "존재하지 않습니다."
                ),
            }

        new_row = new_rows.iloc[-1]

        new_start_date = pd.Timestamp(
            new_row["start_date"]
        ).normalize()

        if new_start_date != effective_date:
            return {
                "success": False,
                "check": "NEW_BOM_START_DATE",
                "message": (
                    "신규 BOM의 start_date가 "
                    "올바르지 않습니다."
                ),
            }

        # ------------------------------------------
        # BOM 속성 비교
        # ------------------------------------------

        if (
            str(new_row["location"]).strip()
            != str(item["location"]).strip()
        ):
            return {
                "success": False,
                "check": "LOCATION",
                "message": (
                    "신규 BOM의 location이 "
                    "Design Change Item과 다릅니다."
                ),
            }

        if (
            int(new_row["sequence_no"])
            != int(item["sequence_no"])
        ):
            return {
                "success": False,
                "check": "SEQUENCE_NO",
                "message": (
                    "신규 BOM의 sequence_no가 "
                    "Design Change Item과 다릅니다."
                ),
            }

        if (
            float(new_row["quantity"])
            != float(item["quantity"])
        ):
            return {
                "success": False,
                "check": "QUANTITY",
                "message": (
                    "신규 BOM의 quantity가 "
                    "Design Change Item과 다릅니다."
                ),
            }

        return {
            "success": True,
            "check": "BOM_INTEGRITY",
            "message": (
                "설계변경 적용 결과와 "
                "BOM 데이터가 일치합니다."
            ),
        }

    def _validate_applied_review(
        self,
        review_id: str,
        change_id: str,
        effective_date: pd.Timestamp,
        applied_items: list[dict],
    ) -> dict:
        """
        최종 승인된 Review BOM이 Production BOM에
        정상 반영되었는지 검증합니다.
        """

        expected_old_end_date = (
            effective_date
            - pd.Timedelta(days=1)
        )

        bom = self.bom_service.bom.copy()

        check_results = []

        for item in applied_items:
            bom_parent = str(
                item["bom_parent"]
            ).strip()

            old_material_id = str(
                item["old_material_id"]
            ).strip()

            new_material_id = str(
                item["new_material_id"]
            ).strip()

            location = str(
                item["location"]
            ).strip()

            sequence_no = int(
                item["sequence_no"]
            )

            # ----------------------------------
            # 기존 관계 종료 확인
            # ----------------------------------

            old_rows = bom[
                bom["bom_parent"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(bom_parent.upper())
                &
                bom["bom_child"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(old_material_id.upper())
            ]

            if old_rows.empty:
                return {
                    "success": False,
                    "check": "OLD_BOM_HISTORY",
                    "message": (
                        "기존 Production BOM 관계를 "
                        "찾을 수 없습니다."
                    ),
                    "failed_item": item,
                }

            old_row = old_rows.iloc[-1]

            old_end_date = pd.Timestamp(
                old_row["end_date"]
            ).normalize()

            if old_end_date != expected_old_end_date:
                return {
                    "success": False,
                    "check": "OLD_BOM_END_DATE",
                    "message": (
                        "기존 Production BOM의 "
                        "end_date가 올바르지 않습니다."
                    ),
                    "failed_item": item,
                }

            # ----------------------------------
            # 신규 관계 확인
            # ----------------------------------

            new_rows = bom[
                bom["bom_parent"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(bom_parent.upper())
                &
                bom["bom_child"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(new_material_id.upper())
                &
                bom["location"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(location.upper())
                &
                (
                    pd.to_numeric(
                        bom["sequence_no"],
                        errors="coerce",
                    )
                    == sequence_no
                )
            ]

            if new_rows.empty:
                return {
                    "success": False,
                    "check": "NEW_BOM_EXISTS",
                    "message": (
                        "신규 Production BOM 관계를 "
                        "찾을 수 없습니다."
                    ),
                    "failed_item": item,
                }

            new_row = new_rows.iloc[-1]

            new_start_date = pd.Timestamp(
                new_row["start_date"]
            ).normalize()

            if new_start_date != effective_date:
                return {
                    "success": False,
                    "check": "NEW_BOM_START_DATE",
                    "message": (
                        "신규 Production BOM의 "
                        "start_date가 올바르지 않습니다."
                    ),
                    "failed_item": item,
                }

            check_results.append({
                "bom_parent": bom_parent,
                "old_material_id": old_material_id,
                "new_material_id": new_material_id,
                "status": "PASS",
            })

        return {
            "success": True,
            "check": "REVIEW_BOM_INTEGRITY",
            "review_id": review_id,
            "change_id": change_id,
            "item_count": len(applied_items),
            "check_results": check_results,
            "message": (
                "최종 Review BOM과 Production BOM "
                "적용 결과가 일치합니다."
            ),
        }
                
    def _replace_component(
        self,
        current_bom: pd.DataFrame,
        old_material_id: str,
        new_material_id: str,
        new_material: dict,
    ) -> pd.DataFrame:
        virtual_bom = current_bom.copy()

        mask = (
            virtual_bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(old_material_id.strip().upper())
        )

        virtual_bom.loc[mask, "bom_child"] = new_material_id
        virtual_bom.loc[mask, "bom_child_name"] = str(
            new_material.get("material_name", new_material_id)
        )

        return virtual_bom

    def _replace_assembly(
        self,
        current_bom: pd.DataFrame,
        old_material_id: str,
        new_material_id: str,
        new_material: dict,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        old_upper = old_material_id.strip().upper()

        old_rows = current_bom[
            current_bom["bom_child"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(old_upper)
        ]

        if old_rows.empty:
            return current_bom

        old_link_row = old_rows.iloc[0]

        old_parent = str(old_link_row["bom_parent"])
        old_parent_name = str(old_link_row["bom_parent_name"])
        old_location = str(old_link_row["location"])
        old_sequence_no = old_link_row["sequence_no"]
        old_quantity = old_link_row["quantity"]
        old_level = int(old_link_row["level"])
        old_root_model = str(old_link_row["root_model"])
        old_path = str(old_link_row["bom_path"])
        old_required_quantity = float(old_link_row["required_quantity"])

        subtree_mask = (
            current_bom["bom_path"]
            .astype(str)
            .apply(
                lambda path: (
                    f"/{old_material_id}/" in f"/{path}/"
                    or path.endswith(f"/{old_material_id}")
                )
            )
        )

        virtual_bom = current_bom[~subtree_mask].copy()

        new_material_name = str(
            new_material.get("material_name", new_material_id)
        )

        parent_path_parts = old_path.split("/")[:-1]
        new_path = "/".join(parent_path_parts + [new_material_id])

        new_link = {
            "bom_parent": old_parent,
            "bom_parent_name": old_parent_name,
            "bom_child": new_material_id,
            "bom_child_name": new_material_name,
            "location": old_location,
            "sequence_no": old_sequence_no,
            "quantity": old_quantity,
            "start_date": old_link_row["start_date"],
            "end_date": old_link_row["end_date"],
            "level": old_level,
            "root_model": old_root_model,
            "bom_path": new_path,
            "required_quantity": old_required_quantity,
        }

        virtual_bom = pd.concat(
            [virtual_bom, pd.DataFrame([new_link])],
            ignore_index=True,
        )

        new_subtree = self._get_subtree(
            root_material_id=new_material_id,
            root_level=old_level,
            root_model=old_root_model,
            root_path=new_path,
            root_required_quantity=old_required_quantity,
            as_of_date=as_of_date,
        )

        if not new_subtree.empty:
            virtual_bom = pd.concat(
                [virtual_bom, new_subtree],
                ignore_index=True,
            )

        return (
            virtual_bom
            .sort_values(
                by=["level", "bom_parent", "sequence_no"]
            )
            .reset_index(drop=True)
        )

    def _get_subtree(
        self,
        root_material_id: str,
        root_level: int,
        root_model: str,
        root_path: str,
        root_required_quantity: float,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        effective_bom = self.bom_service._get_effective_bom(
            as_of_date
        )

        result_rows: list[dict] = []

        def explode(
            current_parent: str,
            current_level: int,
            current_path: list[str],
            parent_required_quantity: float,
            visited: set[str],
        ) -> None:
            current_upper = current_parent.strip().upper()

            if current_upper in visited:
                return

            next_visited = set(visited)
            next_visited.add(current_upper)

            children = effective_bom[
                effective_bom["bom_parent"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(current_upper)
            ].copy()

            if children.empty:
                return

            children = children.sort_values(by="sequence_no")

            for _, row in children.iterrows():
                child_id = str(row["bom_child"])
                quantity = float(row["quantity"])
                required_quantity = (
                    parent_required_quantity * quantity
                )
                new_path_parts = current_path + [child_id]

                result_row = row.to_dict()
                result_row["level"] = current_level
                result_row["root_model"] = root_model
                result_row["bom_path"] = "/".join(new_path_parts)
                result_row["required_quantity"] = required_quantity
                result_rows.append(result_row)

                explode(
                    current_parent=child_id,
                    current_level=current_level + 1,
                    current_path=new_path_parts,
                    parent_required_quantity=required_quantity,
                    visited=next_visited,
                )

        explode(
            current_parent=root_material_id,
            current_level=root_level + 1,
            current_path=root_path.split("/"),
            parent_required_quantity=root_required_quantity,
            visited=set(),
        )

        if not result_rows:
            return pd.DataFrame(
                columns=self._explosion_columns()
            )

        return pd.DataFrame(result_rows)

    def _find_exact_material(
        self,
        material_id: str,
    ) -> dict | None:
        materials = self.bom_service.materials

        result = materials[
            materials["material_id"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq(material_id.strip().upper())
        ]

        if result.empty:
            return None

        return result.iloc[0].to_dict()

    @staticmethod
    def _explosion_columns() -> list[str]:
        return [
            "bom_parent",
            "bom_parent_name",
            "bom_child",
            "bom_child_name",
            "location",
            "sequence_no",
            "quantity",
            "start_date",
            "end_date",
            "level",
            "root_model",
            "bom_path",
            "required_quantity",
        ]
