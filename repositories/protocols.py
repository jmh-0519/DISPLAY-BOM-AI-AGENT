from __future__ import annotations

from datetime import date
from typing import Protocol


class BomReadRepository(Protocol):
    """Service가 저장 방식과 무관하게 사용하는 BOM 읽기 계약."""

    def get_children(
        self,
        parent_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...

    def get_tree(
        self,
        root_code: str,
        as_of_date: str | date | None = None,
    ) -> list[dict]: ...

    def get_item(self, item_code: str) -> dict | None: ...

    def search_items(
        self,
        keyword: str,
        item_type: str | None = None,
    ) -> list[dict]: ...

    def list_items(self, item_type: str | None = None) -> list[dict]: ...

    def resolve_version_code(self, value: str) -> str | None: ...
