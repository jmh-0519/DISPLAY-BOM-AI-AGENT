from __future__ import annotations

from datetime import date
from typing import Protocol


class BomReadRepository(Protocol):
    """Service가 저장 방식과 무관하게 사용하는 BOM 읽기 계약."""

    def get_children(
        self,
        plant_code: str,
        parent_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...

    def get_tree(
        self,
        plant_code: str,
        root_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...

    def get_parents_tree(
        self,
        plant_code: str,
        child_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...

    def get_item_attributes(
        self,
        item_code: str,
        as_of_date: str | date | None = None,
    ) -> dict: ...

    def get_version_detail(self, version_code: str) -> dict | None: ...

    def get_material_detail(self, material_code: str) -> dict | None: ...

    def get_assembly_detail(self, assembly_code: str) -> dict | None: ...

    def get_item(self, item_code: str) -> dict | None: ...

    def search_items(
        self,
        keyword: str,
        item_type: str | None = None,
    ) -> list[dict]: ...

    def list_items(self, item_type: str | None = None) -> list[dict]: ...

    def resolve_version_code(self, value: str) -> str | None: ...

    def get_plant(self, plant_code: str) -> dict | None: ...

    def list_plants(
        self,
        reference_code: str | None = None,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...
