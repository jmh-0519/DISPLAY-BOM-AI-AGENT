from __future__ import annotations

from datetime import date
import json

import pandas as pd

from repositories.protocols import BomReadRepository


class RepositoryBomService:
    """v2 Repository 결과를 기존 Query Tool용 DataFrame으로 변환합니다."""

    BOM_COLUMNS = [
        "plant_code",
        "plant_name",
        "version_code",
        "bom_parent",
        "bom_parent_name",
        "bom_parent_type",
        "bom_child",
        "bom_child_name",
        "bom_child_type",
        "item_type",
        "location",
        "sequence_no",
        "quantity",
        "start_date",
        "end_date",
    ]
    TREE_COLUMNS = BOM_COLUMNS + [
        "level",
        "root_model",
        "bom_path",
        "required_quantity",
    ]

    def __init__(self, repository: BomReadRepository) -> None:
        self.repository = repository

    def _resolve_parent(self, value: str) -> str:
        return self.repository.resolve_version_code(value) or value

    def _resolve_bom_root(self, value: str) -> tuple[str | None, str | None]:
        """VERSION/legacy product/ASSEMBLY를 조회 가능한 Root로 식별합니다."""
        version_code = self.repository.resolve_version_code(value)
        root_code = version_code or value
        item = self.repository.get_item(root_code)
        if not item or item["item_type"] not in {"VERSION", "ASSEMBLY"}:
            return None, None
        return item["item_code"], item["item_type"]

    @staticmethod
    def _relation_record(
        row: dict,
        version_code: str | None = None,
        plant: dict | None = None,
    ) -> dict:
        return {
            "plant_code": row.get("plant_code") or (plant or {}).get("plant_code"),
            "plant_name": (plant or {}).get("plant_name"),
            "version_code": version_code,
            "bom_parent": row["parent_item_code"],
            "bom_parent_name": row["parent_item_name"],
            "bom_parent_type": row["parent_item_type"],
            "bom_child": row["child_item_code"],
            "bom_child_name": row["child_item_name"],
            "bom_child_type": row["child_item_type"],
            "item_type": row["child_item_type"],
            "location": row["location_code"],
            "sequence_no": row["sequence_no"],
            "quantity": row["quantity"],
            "start_date": row["valid_from"],
            "end_date": row["valid_to"],
        }

    def get_bom(
        self,
        plant_code: str,
        parent_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        plant = self._require_plant(plant_code)
        parent = self._resolve_parent(parent_id)
        version_code = self.repository.resolve_version_code(parent_id)
        rows = [
            self._relation_record(row, version_code=version_code, plant=plant)
            for row in self.repository.get_children(plant["plant_code"], parent, as_of_date)
        ]
        return pd.DataFrame(rows, columns=self.BOM_COLUMNS)

    def get_bom_explosion(
        self,
        plant_code: str,
        model_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        plant = self._require_plant(plant_code)
        root_code, root_type = self._resolve_bom_root(model_id)
        if not root_code:
            item = self.repository.get_item(model_id)
            if item and item["item_type"] == "MATERIAL":
                raise ValueError(
                    "MATERIAL은 하위 BOM을 가질 수 없습니다. "
                    "VERSION 또는 ASSEMBLY 코드를 입력해 주세요."
                )
            return pd.DataFrame(columns=self.TREE_COLUMNS)
        records = []
        for row in self.repository.get_tree(plant["plant_code"], root_code, as_of_date):
            record = self._relation_record(
                row,
                version_code=root_code if root_type == "VERSION" else None,
                plant=plant,
            )
            record.update(
                {
                    "level": row["level"],
                    "root_model": root_code,
                    "root_code": root_code,
                    "root_type": root_type,
                    "bom_title": "제품 BOM" if root_type == "VERSION" else "ASSY BOM",
                    "bom_path": row["bom_path"],
                    "required_quantity": row["required_quantity"],
                }
            )
            records.append(record)
        columns = self.TREE_COLUMNS + ["root_code", "root_type", "bom_title"]
        return pd.DataFrame(records, columns=columns)

    def _require_plant(self, plant_code: str) -> dict:
        normalized = str(plant_code or "").strip().upper()
        if not normalized:
            raise ValueError("PLANT를 선택해 주세요.")
        plant = self.repository.get_plant(normalized)
        if not plant or plant.get("active_yn") != "Y":
            raise ValueError(f"활성 PLANT를 찾을 수 없습니다: {normalized}")
        return plant

    def list_plants(
        self,
        reference_code: str | None = None,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(self.repository.list_plants(reference_code, as_of_date))

    @staticmethod
    def _product_record(item: dict) -> dict:
        return {
            "product_id": item["item_code"],
            "product_name": item["description"] or item["item_name"],
            "product_type": "VERSION",
            "version_code": item["item_code"],
            "status": "ACTIVE" if item["active_yn"] == "Y" else "INACTIVE",
        }

    def get_product(self, product_id: str) -> dict | None:
        version_code = self.repository.resolve_version_code(product_id)
        if not version_code:
            return None
        item = self.repository.get_item(version_code)
        return self._product_record(item) if item else None

    def list_products(self) -> pd.DataFrame:
        rows = [
            self._product_record(item)
            for item in self.repository.list_items("VERSION")
        ]
        return pd.DataFrame(rows)

    def search_product(self, keyword: str) -> pd.DataFrame:
        resolved = self.repository.resolve_version_code(keyword)
        if resolved:
            item = self.repository.get_item(resolved)
            rows = [self._product_record(item)] if item else []
        else:
            rows = [
                self._product_record(item)
                for item in self.repository.search_items(keyword, "VERSION")
            ]
        return pd.DataFrame(rows)

    @staticmethod
    def _material_record(item: dict) -> dict:
        return {
            "material_id": item["item_code"],
            "material_name": item["item_name"],
            "material_type": item["item_type"],
            "category": item["item_name"] if item["item_type"] == "ASSEMBLY" else None,
            "specification": item["description"],
            "lifecycle_status": (
                "ACTIVE" if item["active_yn"] == "Y" else "INACTIVE"
            ),
        }

    def list_materials(self) -> pd.DataFrame:
        items = [
            *self.repository.list_items("ASSEMBLY"),
            *self.repository.list_items("MATERIAL"),
        ]
        return pd.DataFrame([self._material_record(item) for item in items])

    def search_material(self, keyword: str) -> pd.DataFrame:
        items = [
            item
            for item in self.repository.search_items(keyword)
            if item["item_type"] != "VERSION"
        ]
        return pd.DataFrame([self._material_record(item) for item in items])
    @staticmethod
    def _decode_specification(value):
        if value in {None, ""}:
            return {}
        if isinstance(value, dict):
            return value
        text = str(value).strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"specification": text}
        return decoded if isinstance(decoded, dict) else {"specification": decoded}

    def get_where_used(
        self,
        plant_code: str,
        item_code: str,
        as_of_date: str | date | None = None,
    ) -> dict:
        """Return reverse BOM usage paths from an item to its top-level VERSION(s)."""
        plant = self._require_plant(plant_code)
        normalized = str(item_code or "").strip().upper()
        if not normalized:
            raise ValueError("역방향 BOM 조회 대상 코드를 입력해 주세요.")
        item = self.repository.get_item(normalized)
        if not item:
            return {
                "plant_code": plant["plant_code"],
                "plant_name": plant["plant_name"],
                "item_code": normalized,
                "item": None,
                "where_used": [],
                "top_models": [],
                "message": "등록된 품목이 아닙니다.",
            }

        rows = self.repository.get_parents_tree(plant["plant_code"], normalized, as_of_date)
        top_models: dict[str, dict] = {}
        direct_parents: dict[str, dict] = {}
        for row in rows:
            parent_code = str(row.get("parent_item_code") or "")
            if row.get("level") == 1 and parent_code:
                direct_parents[parent_code] = {
                    "item_code": parent_code,
                    "item_name": row.get("parent_item_name"),
                    "description": row.get("parent_description"),
                    "item_type": row.get("parent_item_type"),
                    "location": row.get("location_code"),
                    "quantity": row.get("quantity"),
                }
            if row.get("parent_item_type") == "VERSION" and parent_code:
                top_models[parent_code] = {
                    "model_code": parent_code,
                    "model_name": row.get("parent_item_name"),
                    "description": row.get("parent_description"),
                    "path": row.get("bom_path"),
                }

        return {
            "plant_code": plant["plant_code"],
            "plant_name": plant["plant_name"],
            "item_code": normalized,
            "item": item,
            "where_used": rows,
            "direct_parents": list(direct_parents.values()),
            "top_models": list(top_models.values()),
            "message": (
                None if rows else
                "해당 품목은 선택한 PLANT의 현재 BOM에 구성되어 있지 않습니다."
            ),
        }

    def get_product_detail(
        self, product_id: str, as_of_date: str | date | None = None
    ) -> dict | None:
        version_code = self.repository.resolve_version_code(product_id)
        if not version_code:
            return None
        detail = self.repository.get_version_detail(version_code)
        if not detail:
            return None
        attributes = self.repository.get_item_attributes(version_code, as_of_date)
        specification = self._decode_specification(detail.pop("specification", None))
        base_item_name = detail.pop("item_name", None)
        return {
            "item_code": version_code,
            "item_type": "VERSION",
            "item_name": specification.get("product_name") or base_item_name,
            "description": detail.pop("description", None),
            "status": "ACTIVE" if detail.pop("active_yn", "N") == "Y" else "INACTIVE",
            "master": detail,
            "specification": specification,
            "attributes": attributes,
        }

    def get_item_detail(
        self, item_code: str, as_of_date: str | date | None = None
    ) -> dict | None:
        normalized = str(item_code or "").strip().upper()
        item = self.repository.get_item(normalized)
        if not item or item.get("item_type") == "VERSION":
            return None
        item_type = item.get("item_type")
        if item_type == "MATERIAL":
            detail = self.repository.get_material_detail(normalized)
        elif item_type == "ASSEMBLY":
            detail = self.repository.get_assembly_detail(normalized)
        else:
            detail = None
        if not detail:
            return None
        specification = self._decode_specification(detail.pop("specification", None))
        attributes = self.repository.get_item_attributes(normalized, as_of_date)
        return {
            "item_code": normalized,
            "item_type": item_type,
            "item_name": detail.pop("item_name", None),
            "description": detail.pop("description", None),
            "status": "ACTIVE" if detail.pop("active_yn", "N") == "Y" else "INACTIVE",
            "master": detail,
            "specification": specification,
            "attributes": attributes,
        }

