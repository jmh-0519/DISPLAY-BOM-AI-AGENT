from __future__ import annotations

from datetime import date

import pandas as pd

from repositories.protocols import BomReadRepository


class RepositoryBomService:
    """v2 Repository 결과를 기존 Query Tool용 DataFrame으로 변환합니다."""

    BOM_COLUMNS = [
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
    def _relation_record(row: dict, version_code: str | None = None) -> dict:
        return {
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
        parent_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
        parent = self._resolve_parent(parent_id)
        version_code = self.repository.resolve_version_code(parent_id)
        rows = [
            self._relation_record(row, version_code=version_code)
            for row in self.repository.get_children(parent, as_of_date)
        ]
        return pd.DataFrame(rows, columns=self.BOM_COLUMNS)

    def get_bom_explosion(
        self,
        model_id: str,
        as_of_date: str | date | None = None,
    ) -> pd.DataFrame:
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
        for row in self.repository.get_tree(root_code, as_of_date):
            record = self._relation_record(
                row,
                version_code=root_code if root_type == "VERSION" else None,
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
