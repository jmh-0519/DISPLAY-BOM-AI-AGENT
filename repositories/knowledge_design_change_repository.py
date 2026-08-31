from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rag.reason_catalog import ReasonCatalog
from rag.rule_catalog import RuleCatalog
from repositories.design_change_repository import SQLiteDesignChangeRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REASON_DIRECTORY = PROJECT_ROOT / "knowledge" / "reasons"
DEFAULT_RULE_DIRECTORY = PROJECT_ROOT / "knowledge" / "rules"


@lru_cache(maxsize=1)
def _default_reason_catalog() -> ReasonCatalog:
    return ReasonCatalog.from_directory(DEFAULT_REASON_DIRECTORY)


@lru_cache(maxsize=1)
def _default_rule_catalog() -> RuleCatalog:
    return RuleCatalog.from_directory(DEFAULT_RULE_DIRECTORY)


class KnowledgeDesignChangeRepository(SQLiteDesignChangeRepository):
    """Design-change repository backed by DB facts plus external knowledge catalogs.

    BOM facts, workflow persistence and apply state remain SQLite-authoritative.
    Reason/Rule definitions are read from version-controlled knowledge documents.
    `change_reason_master` is retained only as a persistence projection because
    historical `change_action_reasons` rows use it as a foreign-key target.
    """

    def __init__(
        self,
        database,
        *,
        reason_catalog: ReasonCatalog | None = None,
        rule_catalog: RuleCatalog | None = None,
    ) -> None:
        super().__init__(database)
        self.reason_catalog = reason_catalog or _default_reason_catalog()
        self.rule_catalog = rule_catalog or _default_rule_catalog()

    def list_active_reason_metadata(self) -> list[dict]:
        return self.reason_catalog.active_master_records()

    def list_active_reason_aliases(self) -> list[dict]:
        return self.reason_catalog.active_alias_records()

    def is_reason_scope_allowed(
        self, *, reason_code: str, target_type: str, action_type: str
    ) -> bool:
        return self.reason_catalog.is_scope_allowed(
            reason_code=reason_code,
            target_type=target_type,
            action_type=action_type,
        )

    def get_active_rules(
        self,
        reasons: list[str],
        target_type: str,
        as_of_date: str,
        action_type: str | None = None,
    ) -> list[dict]:
        actions = (
            [str(action_type).strip().upper()]
            if str(action_type or "").strip()
            else ["REPLACE", "ADD", "DELETE", "QUANTITY_CHANGE"]
        )
        records: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for action in actions:
            for record in self.rule_catalog.find_rule_engine_records(
                reason_codes=reasons,
                target_type=target_type,
                action_type=action,
                as_of_date=as_of_date,
            ):
                key = (str(record["rule_id"]), int(record["revision_no"]))
                if key in seen:
                    continue
                seen.add(key)
                value = dict(record)
                value["action_type"] = action
                records.append(value)
        return records

    def _ensure_reason_master_projection(self, resolved_reasons: list | None) -> None:
        if not resolved_reasons:
            return
        codes: set[str] = set()
        for action_reasons in resolved_reasons:
            values = action_reasons if isinstance(action_reasons, list) else [action_reasons]
            for reason in values:
                code = str(reason.get("reason_code") or "").strip().upper()
                if code:
                    codes.add(code)
        if not codes:
            return

        documents = []
        for code in sorted(codes):
            document = self.reason_catalog.get(code)
            if document is None:
                raise ValueError(f"KNOWLEDGE_REASON_NOT_FOUND: {code}")
            documents.append(document)

        with self.database.transaction() as connection:
            for document in documents:
                record = document.as_master_record()
                connection.execute(
                    """INSERT INTO change_reason_master(
                           reason_code,reason_name_ko,description,category,active_yn,
                           valid_from,valid_to)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(reason_code) DO UPDATE SET
                         reason_name_ko=excluded.reason_name_ko,
                         description=excluded.description,
                         category=excluded.category,
                         active_yn=excluded.active_yn,
                         valid_from=excluded.valid_from,
                         valid_to=excluded.valid_to""",
                    (
                        record["reason_code"],
                        record["reason_name_ko"],
                        record["description"],
                        record["category"],
                        record["active_yn"],
                        record["valid_from"],
                        record["valid_to"],
                    ),
                )

    def create_request(
        self, request: dict, actions: list[dict], resolved_reasons: list | None = None
    ) -> None:
        self._ensure_reason_master_projection(resolved_reasons)
        super().create_request(request, actions, resolved_reasons)
