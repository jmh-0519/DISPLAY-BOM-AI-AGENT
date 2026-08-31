from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable


_ALLOWED_TARGET_TYPES = {"MATERIAL", "ASSY"}
_ALLOWED_ACTION_TYPES = {"REPLACE", "ADD", "DELETE", "QUANTITY_CHANGE"}
_ALLOWED_STATUS = {"ACTIVE", "INACTIVE"}
_ALLOWED_LANGUAGES = {"KO", "EN"}
_ALLOWED_MATCH_TYPES = {"EXACT", "KEYWORD"}


class ReasonCatalogError(ValueError):
    """A design-change reason document violates the knowledge contract."""


def normalize_reason_text(value: object) -> str:
    return re.sub(r"[^0-9A-Z가-힣]", "", str(value or "").upper())


def _validate_iso_date(value: str, field_name: str) -> None:
    if not value:
        raise ReasonCatalogError(f"{field_name} is required")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ReasonCatalogError(f"{field_name} must use YYYY-MM-DD: {value}") from exc


def _split_toml_front_matter(text: str, path: Path) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "+++":
        raise ReasonCatalogError(f"{path}: TOML front matter must start with +++")
    try:
        end_index = next(
            index for index, line in enumerate(lines[1:], 1) if line.strip() == "+++"
        )
    except StopIteration as exc:
        raise ReasonCatalogError(f"{path}: TOML front matter closing +++ not found") from exc
    metadata = "\n".join(lines[1:end_index]).strip()
    body = "\n".join(lines[end_index + 1 :]).strip()
    if not metadata:
        raise ReasonCatalogError(f"{path}: empty TOML front matter")
    return metadata, body


@dataclass(frozen=True)
class ReasonAlias:
    text: str
    normalized_alias: str
    language_code: str
    match_type: str
    priority: int

    @classmethod
    def from_dict(cls, raw: dict, *, path: Path) -> "ReasonAlias":
        text = str(raw.get("text") or "").strip()
        if not text:
            raise ReasonCatalogError(f"{path}: alias.text is required")
        normalized = str(raw.get("normalized_alias") or normalize_reason_text(text)).strip()
        if not normalized:
            raise ReasonCatalogError(f"{path}: alias.normalized_alias is required")
        language = str(raw.get("language") or "KO").strip().upper()
        match_type = str(raw.get("match_type") or "KEYWORD").strip().upper()
        priority = int(raw.get("priority", 100))
        if language not in _ALLOWED_LANGUAGES:
            raise ReasonCatalogError(f"{path}: invalid alias language {language}")
        if match_type not in _ALLOWED_MATCH_TYPES:
            raise ReasonCatalogError(f"{path}: invalid alias match_type {match_type}")
        if priority < 1:
            raise ReasonCatalogError(f"{path}: alias.priority must be >= 1")
        return cls(
            text=text,
            normalized_alias=normalized,
            language_code=language,
            match_type=match_type,
            priority=priority,
        )


@dataclass(frozen=True)
class ReasonScope:
    target_type: str
    action_type: str

    @classmethod
    def from_dict(cls, raw: dict, *, path: Path) -> "ReasonScope":
        target = str(raw.get("target_type") or "").strip().upper()
        action = str(raw.get("action_type") or "").strip().upper()
        if target not in _ALLOWED_TARGET_TYPES:
            raise ReasonCatalogError(f"{path}: invalid scope target_type {target or '<empty>'}")
        if action not in _ALLOWED_ACTION_TYPES:
            raise ReasonCatalogError(f"{path}: invalid scope action_type {action or '<empty>'}")
        return cls(target_type=target, action_type=action)


@dataclass(frozen=True)
class ReasonDocument:
    reason_code: str
    reason_name_ko: str
    description: str
    category: str
    status: str
    valid_from: str
    valid_to: str | None
    aliases: tuple[ReasonAlias, ...]
    scopes: tuple[ReasonScope, ...]
    body: str
    source_path: Path
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_markdown(cls, path: str | Path) -> "ReasonDocument":
        source_path = Path(path)
        metadata_text, body = _split_toml_front_matter(
            source_path.read_text(encoding="utf-8"), source_path
        )
        try:
            metadata = tomllib.loads(metadata_text)
        except tomllib.TOMLDecodeError as exc:
            raise ReasonCatalogError(
                f"invalid TOML front matter in {source_path}: {exc}"
            ) from exc

        reason_code = str(metadata.get("reason_code") or "").strip().upper()
        reason_name_ko = str(metadata.get("reason_name_ko") or "").strip()
        description = str(metadata.get("description") or "").strip()
        category = str(metadata.get("category") or "").strip().upper()
        if not all((reason_code, reason_name_ko, description, category)):
            raise ReasonCatalogError(
                f"{source_path}: reason_code, reason_name_ko, description, category are required"
            )

        status = str(metadata.get("status") or "ACTIVE").strip().upper()
        if status not in _ALLOWED_STATUS:
            raise ReasonCatalogError(f"{source_path}: invalid status {status}")

        valid_from = str(metadata.get("valid_from") or "2026-01-01").strip()
        valid_to_raw = metadata.get("valid_to")
        valid_to = str(valid_to_raw).strip() if valid_to_raw else None
        _validate_iso_date(valid_from, f"{source_path}: valid_from")
        if valid_to:
            _validate_iso_date(valid_to, f"{source_path}: valid_to")
            if valid_to < valid_from:
                raise ReasonCatalogError(f"{source_path}: valid_to must be >= valid_from")

        aliases_raw = metadata.get("aliases") or []
        if not isinstance(aliases_raw, list):
            raise ReasonCatalogError(f"{source_path}: aliases must be a list")
        aliases = tuple(
            ReasonAlias.from_dict(value, path=source_path) for value in aliases_raw
        )
        normalized_aliases = [alias.normalized_alias for alias in aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ReasonCatalogError(f"{source_path}: duplicate normalized alias")

        scopes_raw = metadata.get("scopes")
        if not isinstance(scopes_raw, list) or not scopes_raw:
            raise ReasonCatalogError(f"{source_path}: at least one [[scopes]] entry is required")
        scopes = tuple(ReasonScope.from_dict(value, path=source_path) for value in scopes_raw)
        scope_keys = [(scope.target_type, scope.action_type) for scope in scopes]
        if len(scope_keys) != len(set(scope_keys)):
            raise ReasonCatalogError(f"{source_path}: duplicate reason scope")

        tags_raw = metadata.get("tags") or []
        if not isinstance(tags_raw, list):
            raise ReasonCatalogError(f"{source_path}: tags must be a list")
        tags = tuple(str(value).strip() for value in tags_raw if str(value).strip())

        return cls(
            reason_code=reason_code,
            reason_name_ko=reason_name_ko,
            description=description,
            category=category,
            status=status,
            valid_from=valid_from,
            valid_to=valid_to,
            aliases=aliases,
            scopes=scopes,
            body=body,
            source_path=source_path,
            tags=tags,
        )

    def as_master_record(self) -> dict:
        return {
            "reason_code": self.reason_code,
            "reason_name_ko": self.reason_name_ko,
            "description": self.description,
            "category": self.category,
            "active_yn": "Y" if self.status == "ACTIVE" else "N",
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "knowledge_source": self.source_path.as_posix(),
        }

    def alias_records(self) -> list[dict]:
        return [
            {
                "alias_id": index,
                "alias_text": alias.text,
                "normalized_alias": alias.normalized_alias,
                "reason_code": self.reason_code,
                "language_code": alias.language_code,
                "match_type": alias.match_type,
                "priority": alias.priority,
                "active_yn": "Y" if self.status == "ACTIVE" else "N",
                "knowledge_source": self.source_path.as_posix(),
            }
            for index, alias in enumerate(self.aliases, 1)
        ]

    def allows(self, *, target_type: str, action_type: str) -> bool:
        target = str(target_type or "").strip().upper()
        action = str(action_type or "").strip().upper()
        return any(
            scope.target_type == target and scope.action_type == action
            for scope in self.scopes
        )

    def rag_text(self) -> str:
        aliases = ", ".join(alias.text for alias in self.aliases) or "-"
        scopes = ", ".join(
            f"{scope.target_type}/{scope.action_type}" for scope in self.scopes
        )
        return (
            f"Reason: {self.reason_name_ko}\n"
            f"Reason Code: {self.reason_code}\n"
            f"Category: {self.category}\n"
            f"Description: {self.description}\n"
            f"Aliases: {aliases}\n"
            f"Scopes: {scopes}\n\n"
            f"{self.body}"
        ).strip()


class ReasonCatalog:
    """Deterministic external catalog for design-change reason metadata."""

    def __init__(self, reasons: Iterable[ReasonDocument]) -> None:
        by_code: dict[str, ReasonDocument] = {}
        names: set[str] = set()
        for reason in reasons:
            if reason.reason_code in by_code:
                raise ReasonCatalogError(f"duplicate reason_code: {reason.reason_code}")
            if reason.reason_name_ko in names:
                raise ReasonCatalogError(f"duplicate reason_name_ko: {reason.reason_name_ko}")
            by_code[reason.reason_code] = reason
            names.add(reason.reason_name_ko)
        self._reasons = tuple(sorted(by_code.values(), key=lambda value: value.reason_code))
        self._by_code = by_code

    @classmethod
    def from_directory(cls, path: str | Path) -> "ReasonCatalog":
        directory = Path(path)
        if not directory.exists():
            raise ReasonCatalogError(f"reason directory not found: {directory}")
        documents = [
            ReasonDocument.from_markdown(file_path)
            for file_path in sorted(directory.rglob("*.md"))
            if file_path.name.lower() != "readme.md"
        ]
        if not documents:
            raise ReasonCatalogError(f"no reason documents found in {directory}")
        return cls(documents)

    @property
    def reasons(self) -> tuple[ReasonDocument, ...]:
        return self._reasons

    def get(self, reason_code: str) -> ReasonDocument | None:
        return self._by_code.get(str(reason_code or "").strip().upper())

    def active_master_records(self) -> list[dict]:
        return [
            reason.as_master_record()
            for reason in self._reasons
            if reason.status == "ACTIVE"
        ]

    def active_alias_records(self) -> list[dict]:
        records: list[dict] = []
        alias_id = 0
        for reason in self._reasons:
            if reason.status != "ACTIVE":
                continue
            for record in reason.alias_records():
                alias_id += 1
                value = dict(record)
                value["alias_id"] = alias_id
                records.append(value)
        return sorted(records, key=lambda row: (int(row["priority"]), int(row["alias_id"])))

    def is_scope_allowed(
        self, *, reason_code: str, target_type: str, action_type: str
    ) -> bool:
        reason = self.get(reason_code)
        return bool(
            reason
            and reason.status == "ACTIVE"
            and reason.allows(target_type=target_type, action_type=action_type)
        )
