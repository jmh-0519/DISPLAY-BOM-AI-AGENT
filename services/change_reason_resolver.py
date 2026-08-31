from __future__ import annotations

import re
from dataclasses import dataclass


class ReasonResolutionError(ValueError):
    """The request cannot safely be mapped to registered business reasons."""


@dataclass(frozen=True)
class ResolvedReason:
    reason_code: str
    raw_reason_text: str
    llm_reason_code: str | None
    resolution_status: str
    resolution_source: str
    confidence: float
    evidence: dict
    is_primary: str = "Y"

    def as_record(self) -> dict:
        return {
            "reason_code": self.reason_code,
            "raw_reason_text": self.raw_reason_text,
            "llm_reason_code": self.llm_reason_code,
            "resolution_status": self.resolution_status,
            "resolution_source": self.resolution_source,
            "confidence": self.confidence,
            "is_primary": self.is_primary,
            "evidence": self.evidence,
        }


class ChangeReasonResolver:
    """Maps free user language to active, scope-valid design-change reasons.

    One primary reason is used for business classification while preserving
    every additional detected reason as a secondary reason. All persisted reasons
    can then participate in candidate/rule/supply evaluation.
    """

    def __init__(self, repository) -> None:
        self.repository = repository

    @staticmethod
    def normalize_text(value: str) -> str:
        return re.sub(r"[^0-9A-Z가-힣]", "", str(value or "").upper())

    @staticmethod
    def _proposal_token(value: object) -> str:
        return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")

    def _detect_alias_matches(self, text: str) -> tuple[list[str], dict[str, list[str]]]:
        """Return reason codes ordered by first appearance in the user text."""
        compact_text = self.normalize_text(text)
        matched_aliases: dict[str, list[str]] = {}
        first_position: dict[str, int] = {}
        first_priority: dict[str, int] = {}
        for alias in self.repository.list_active_reason_aliases():
            normalized_alias = self.normalize_text(alias["normalized_alias"])
            if not normalized_alias:
                continue
            position = compact_text.find(normalized_alias)
            if position < 0:
                continue
            code = alias["reason_code"]
            matched_aliases.setdefault(code, []).append(alias["alias_text"])
            priority = int(alias.get("priority") or 999999)
            if code not in first_position or (position, priority) < (
                first_position[code], first_priority[code]
            ):
                first_position[code] = position
                first_priority[code] = priority
        ordered = sorted(
            first_position,
            key=lambda code: (first_position[code], first_priority[code], code),
        )
        return ordered, matched_aliases

    def resolve_all(
        self,
        *,
        proposed_reasons: list[str] | str | None,
        original_request: str,
        target_type: str,
        action_type: str,
        explicit_action_reason: str | None = None,
    ) -> list[ResolvedReason]:
        master = {
            row["reason_code"]: row
            for row in self.repository.list_active_reason_metadata()
        }
        if not master:
            raise ReasonResolutionError("REASON_METADATA_NOT_FOUND")

        values = (
            [proposed_reasons]
            if isinstance(proposed_reasons, str)
            else list(proposed_reasons or [])
        )
        registered_proposals: list[str] = []
        for value in values:
            token = self._proposal_token(value)
            if token in master and token not in registered_proposals:
                registered_proposals.append(token)

        explicit_code = self._proposal_token(explicit_action_reason)
        if explicit_code and explicit_code not in master:
            raise ReasonResolutionError(
                f"REASON_RESOLUTION_REQUIRED: 등록되지 않은 사유 코드입니다: {explicit_code}"
            )

        text = " ".join([original_request or "", *[str(value) for value in values]])
        alias_codes, matched_aliases = self._detect_alias_matches(text)

        ordered_codes: list[str] = []
        # An explicitly confirmed action reason is the business primary reason.
        if explicit_code:
            ordered_codes.append(explicit_code)
        # Otherwise respect registered proposal order, then natural-language order.
        for code in [*registered_proposals, *alias_codes]:
            if code not in ordered_codes:
                ordered_codes.append(code)

        default_user_request = False
        if not ordered_codes:
            # A user may request a concrete design-change Action without also
            # spelling out a business reason. Do not interrupt REPLACE/ADD/DELETE/
            # QUANTITY_CHANGE with an extra reason question in that case. Instead,
            # use the registered neutral USER_REQUEST reason. This is an explicit
            # system fallback, not an LLM-invented reason.
            nonempty_proposals = [
                str(value).strip() for value in values if str(value or "").strip()
            ]
            if (
                not nonempty_proposals
                and "USER_REQUEST" in master
                and self.repository.is_reason_scope_allowed(
                    reason_code="USER_REQUEST",
                    target_type=target_type,
                    action_type=action_type,
                )
            ):
                ordered_codes.append("USER_REQUEST")
                default_user_request = True
            else:
                raise ReasonResolutionError(
                    "REASON_RESOLUTION_REQUIRED: 등록된 설계변경 사유를 확정할 수 없습니다."
                )

        disallowed = [
            code for code in ordered_codes
            if not self.repository.is_reason_scope_allowed(
                reason_code=code,
                target_type=target_type,
                action_type=action_type,
            )
        ]
        if disallowed:
            raise ReasonResolutionError(
                "REASON_SCOPE_NOT_ALLOWED: 다음 사유는 "
                f"{target_type}/{action_type} 조합에 사용할 수 없습니다: "
                + ", ".join(disallowed)
            )

        result: list[ResolvedReason] = []
        for index, reason_code in enumerate(ordered_codes):
            proposal_match = reason_code in registered_proposals
            alias_match = reason_code in alias_codes
            is_explicit = bool(explicit_code and reason_code == explicit_code)
            if default_user_request and reason_code == "USER_REQUEST":
                source = "SYSTEM_DEFAULT"
                confidence = 1.0
            elif is_explicit:
                source = "ACTION_CODE"
                confidence = 1.0
            elif proposal_match and alias_match:
                source = "LLM_CODE+ALIAS"
                confidence = 0.98
            elif proposal_match:
                source = "LLM_CODE"
                confidence = 0.95
            else:
                source = "ALIAS"
                confidence = 0.90
            result.append(ResolvedReason(
                reason_code=reason_code,
                raw_reason_text=original_request or text,
                llm_reason_code=reason_code if proposal_match else None,
                resolution_status="RESOLVED",
                resolution_source=source,
                confidence=confidence,
                is_primary="Y" if index == 0 else "N",
                evidence={
                    "alias_matches": matched_aliases.get(reason_code, []),
                    "all_detected_reason_codes": ordered_codes,
                    "primary_reason_code": ordered_codes[0],
                },
            ))
        return result

    def resolve(
        self,
        *,
        proposed_reasons: list[str] | str | None,
        original_request: str,
        target_type: str,
        action_type: str,
        explicit_action_reason: str | None = None,
    ) -> ResolvedReason:
        """Single-result API returning the resolved primary reason."""
        return self.resolve_all(
            proposed_reasons=proposed_reasons,
            original_request=original_request,
            target_type=target_type,
            action_type=action_type,
            explicit_action_reason=explicit_action_reason,
        )[0]
