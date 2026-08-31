from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable


_ALLOWED_TARGET_TYPES = {"MATERIAL", "ASSY", "ALL"}
_ALLOWED_ACTION_TYPES = {"REPLACE", "ADD", "DELETE", "QUANTITY_CHANGE"}
_ALLOWED_OPERATORS = {"PRESENT", "IN", "GT", "GE", "LT", "LE", "EQ", "NE"}
_ALLOWED_RESULTS = {"PASS", "CONDITIONAL", "FAIL"}
_ALLOWED_STATUS = {"ACTIVE", "INACTIVE"}


class RuleCatalogError(ValueError):
    """A rule knowledge document is malformed or violates the catalog contract."""


def _normalize_label(value: object) -> str:
    return re.sub(r"[^0-9A-Z가-힣]", "", str(value or "").upper())


def _upper_list(values: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise RuleCatalogError(f"{field_name} must be a non-empty list")
    normalized = tuple(str(value).strip().upper() for value in values if str(value).strip())
    if not normalized:
        raise RuleCatalogError(f"{field_name} must contain at least one value")
    return normalized


@dataclass(frozen=True)
class RuleCondition:
    attribute_name: str
    operator: str
    expected_value: str | None
    missing_result: str = "CONDITIONAL"
    fail_result: str = "FAIL"
    score: float = 100.0

    @classmethod
    def from_dict(cls, raw: dict) -> "RuleCondition":
        attribute_name = str(raw.get("attribute_name") or "").strip()
        operator = str(raw.get("operator") or "").strip().upper()
        if not attribute_name:
            raise RuleCatalogError("condition.attribute_name is required")
        if operator not in _ALLOWED_OPERATORS:
            raise RuleCatalogError(f"unsupported rule operator: {operator or '<empty>'}")

        expected = raw.get("expected_value")
        expected_value = None if expected is None else str(expected)
        if operator != "PRESENT" and expected_value is None:
            raise RuleCatalogError(
                f"condition.expected_value is required for operator {operator}"
            )

        missing_result = str(raw.get("missing_result") or "CONDITIONAL").upper()
        fail_result = str(raw.get("fail_result") or "FAIL").upper()
        if missing_result not in _ALLOWED_RESULTS:
            raise RuleCatalogError(f"invalid missing_result: {missing_result}")
        if fail_result not in _ALLOWED_RESULTS:
            raise RuleCatalogError(f"invalid fail_result: {fail_result}")

        score = float(raw.get("score", 100.0))
        if score < 0:
            raise RuleCatalogError("condition.score must be >= 0")

        return cls(
            attribute_name=attribute_name,
            operator=operator,
            expected_value=expected_value,
            missing_result=missing_result,
            fail_result=fail_result,
            score=score,
        )

    def as_rule_engine_record(self, sequence: int) -> dict:
        return {
            "condition_seq": int(sequence),
            "attribute_name": self.attribute_name,
            "operator": self.operator,
            "expected_value": self.expected_value,
            "missing_result": self.missing_result,
            "fail_result": self.fail_result,
            "score": self.score,
        }


@dataclass(frozen=True)
class RuleDocument:
    rule_id: str
    revision_no: int
    rule_name: str
    description: str
    status: str
    valid_from: str
    valid_to: str | None
    target_types: tuple[str, ...]
    action_types: tuple[str, ...]
    reason_codes: tuple[str, ...]
    evaluation_item: str
    required_yn: str
    weight: float
    conditions: tuple[RuleCondition, ...]
    body: str
    source_path: Path
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_markdown(cls, path: Path) -> "RuleDocument":
        text = path.read_text(encoding="utf-8")
        metadata_text, body = _split_toml_front_matter(text, path)
        try:
            metadata = tomllib.loads(metadata_text)
        except tomllib.TOMLDecodeError as exc:
            raise RuleCatalogError(f"invalid TOML front matter in {path}: {exc}") from exc

        rule_id = str(metadata.get("rule_id") or "").strip()
        rule_name = str(metadata.get("rule_name") or "").strip()
        description = str(metadata.get("description") or "").strip()
        evaluation_item = str(metadata.get("evaluation_item") or "").strip()
        if not rule_id or not rule_name or not description or not evaluation_item:
            raise RuleCatalogError(
                f"{path}: rule_id, rule_name, description, evaluation_item are required"
            )

        revision_no = int(metadata.get("revision_no", 1))
        if revision_no < 1:
            raise RuleCatalogError(f"{path}: revision_no must be >= 1")

        status = str(metadata.get("status") or "ACTIVE").upper()
        if status not in _ALLOWED_STATUS:
            raise RuleCatalogError(f"{path}: invalid status {status}")

        target_types = _upper_list(metadata.get("target_types"), field_name="target_types")
        invalid_targets = sorted(set(target_types) - _ALLOWED_TARGET_TYPES)
        if invalid_targets:
            raise RuleCatalogError(f"{path}: invalid target_types {invalid_targets}")

        action_types = _upper_list(metadata.get("action_types"), field_name="action_types")
        invalid_actions = sorted(set(action_types) - _ALLOWED_ACTION_TYPES)
        if invalid_actions:
            raise RuleCatalogError(f"{path}: invalid action_types {invalid_actions}")

        reason_codes = _upper_list(metadata.get("reason_codes"), field_name="reason_codes")

        valid_from = str(metadata.get("valid_from") or "").strip()
        valid_to_raw = metadata.get("valid_to")
        valid_to = str(valid_to_raw).strip() if valid_to_raw else None
        _validate_iso_date(valid_from, f"{path}: valid_from")
        if valid_to:
            _validate_iso_date(valid_to, f"{path}: valid_to")
            if valid_to < valid_from:
                raise RuleCatalogError(f"{path}: valid_to must be >= valid_from")

        required = bool(metadata.get("required", True))
        weight = float(metadata.get("weight", 100.0))
        if weight <= 0:
            raise RuleCatalogError(f"{path}: weight must be > 0")

        raw_conditions = metadata.get("conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            raise RuleCatalogError(f"{path}: at least one [[conditions]] entry is required")
        conditions = tuple(RuleCondition.from_dict(value) for value in raw_conditions)

        tags_raw = metadata.get("tags") or []
        if not isinstance(tags_raw, list):
            raise RuleCatalogError(f"{path}: tags must be a list")
        tags = tuple(str(value).strip() for value in tags_raw if str(value).strip())

        return cls(
            rule_id=rule_id,
            revision_no=revision_no,
            rule_name=rule_name,
            description=description,
            status=status,
            valid_from=valid_from,
            valid_to=valid_to,
            target_types=target_types,
            action_types=action_types,
            reason_codes=reason_codes,
            evaluation_item=evaluation_item,
            required_yn="Y" if required else "N",
            weight=weight,
            conditions=conditions,
            body=body.strip(),
            source_path=path,
            tags=tags,
        )

    def is_active_on(self, as_of_date: str | None) -> bool:
        if self.status != "ACTIVE":
            return False
        if not as_of_date:
            return True
        _validate_iso_date(as_of_date, "as_of_date")
        if as_of_date < self.valid_from:
            return False
        return self.valid_to is None or as_of_date <= self.valid_to

    def matches(
        self,
        *,
        reason_codes: Iterable[str],
        target_type: str,
        action_type: str,
        evaluation_labels: Iterable[str] | None = None,
        as_of_date: str | None = None,
    ) -> bool:
        if not self.is_active_on(as_of_date):
            return False
        requested_reasons = {str(value).strip().upper() for value in reason_codes}
        if not requested_reasons.intersection(self.reason_codes):
            return False

        target = str(target_type or "").strip().upper()
        if target not in self.target_types and "ALL" not in self.target_types:
            return False

        action = str(action_type or "").strip().upper()
        if action not in self.action_types:
            return False

        normalized_item = _normalize_label(self.evaluation_item)
        if normalized_item in {"", "ALL", "ANY"}:
            return True
        if evaluation_labels is None:
            return True
        labels = {_normalize_label(value) for value in evaluation_labels if str(value or "").strip()}
        return normalized_item in labels

    def as_rule_engine_record(self) -> dict:
        # RuleEngine currently consumes this dict contract. Keeping the adapter
        # here lets the document catalog become the source of rule definitions
        # without making the LLM the business-rule authority.
        target_type = self.target_types[0] if len(self.target_types) == 1 else "ALL"
        change_reason = self.reason_codes[0]
        return {
            "rule_id": self.rule_id,
            "revision_no": self.revision_no,
            "rule_name": self.rule_name,
            "description": self.description,
            "target_type": target_type,
            "change_reason": change_reason,
            "evaluation_item": self.evaluation_item,
            "required_yn": self.required_yn,
            "weight": self.weight,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "active_yn": "Y" if self.status == "ACTIVE" else "N",
            "conditions": [
                condition.as_rule_engine_record(index)
                for index, condition in enumerate(self.conditions, 1)
            ],
            "knowledge_source": str(self.source_path.as_posix()),
        }

    def rag_text(self) -> str:
        """Stable text representation for the later embedding/indexing stage."""
        scopes = ", ".join(self.reason_codes)
        actions = ", ".join(self.action_types)
        targets = ", ".join(self.target_types)
        condition_lines = "\n".join(
            f"- {c.attribute_name} {c.operator} {c.expected_value}"
            for c in self.conditions
        )
        return (
            f"Rule: {self.rule_name}\n"
            f"Rule ID: {self.rule_id}\n"
            f"Reason: {scopes}\n"
            f"Action: {actions}\n"
            f"Target: {targets}\n"
            f"Evaluation item: {self.evaluation_item}\n"
            f"Description: {self.description}\n"
            f"Conditions:\n{condition_lines}\n\n"
            f"{self.body}"
        ).strip()


class RuleCatalog:
    """Loads versioned business-rule documents from a filesystem directory.

    The catalog is intentionally deterministic. Semantic/RAG retrieval can later
    help *find* candidate documents, but only validated structured metadata is
    adapted into RuleEngine input.
    """

    def __init__(self, rules: Iterable[RuleDocument]) -> None:
        by_id: dict[str, RuleDocument] = {}
        for rule in rules:
            previous = by_id.get(rule.rule_id)
            if previous is not None:
                raise RuleCatalogError(
                    f"duplicate rule_id {rule.rule_id}: "
                    f"{previous.source_path} and {rule.source_path}"
                )
            by_id[rule.rule_id] = rule
        self._rules = tuple(sorted(by_id.values(), key=lambda value: value.rule_id))

    @classmethod
    def from_directory(cls, path: str | Path) -> "RuleCatalog":
        directory = Path(path)
        if not directory.exists():
            raise RuleCatalogError(f"rule directory not found: {directory}")
        documents = [
            RuleDocument.from_markdown(file_path)
            for file_path in sorted(directory.rglob("*.md"))
            if file_path.name.lower() != "readme.md"
        ]
        if not documents:
            raise RuleCatalogError(f"no rule documents found in {directory}")
        return cls(documents)

    @property
    def rules(self) -> tuple[RuleDocument, ...]:
        return self._rules

    def find(
        self,
        *,
        reason_codes: Iterable[str],
        target_type: str,
        action_type: str,
        evaluation_labels: Iterable[str] | None = None,
        as_of_date: str | None = None,
    ) -> list[RuleDocument]:
        return [
            rule
            for rule in self._rules
            if rule.matches(
                reason_codes=reason_codes,
                target_type=target_type,
                action_type=action_type,
                evaluation_labels=evaluation_labels,
                as_of_date=as_of_date,
            )
        ]

    def find_rule_engine_records(self, **kwargs) -> list[dict]:
        return [rule.as_rule_engine_record() for rule in self.find(**kwargs)]


def _split_toml_front_matter(text: str, path: Path) -> tuple[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "+++":
        raise RuleCatalogError(f"{path}: TOML front matter must start with +++")
    try:
        end_index = next(
            index for index, line in enumerate(lines[1:], 1) if line.strip() == "+++"
        )
    except StopIteration as exc:
        raise RuleCatalogError(f"{path}: TOML front matter closing +++ not found") from exc
    metadata = "\n".join(lines[1:end_index]).strip()
    body = "\n".join(lines[end_index + 1 :])
    if not metadata:
        raise RuleCatalogError(f"{path}: empty TOML front matter")
    return metadata, body


def _validate_iso_date(value: str, field_name: str) -> None:
    if not value:
        raise RuleCatalogError(f"{field_name} is required")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise RuleCatalogError(f"{field_name} must use YYYY-MM-DD: {value}") from exc
