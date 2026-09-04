"""Deterministic Design Change source-target resolution planning.

The planner classifies only how a source target should be resolved.  It does
not access the database, execute Tools, create Analysis Sessions, or grant any
write/approval authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from agents.domain_intent_router import (
    DEFAULT_DOMAIN_INTENT_ROUTER,
    DomainIntentRouter,
)


class TargetResolutionMode(str, Enum):
    EXPLICIT = "EXPLICIT"
    DETERMINISTIC_ANALYTICS = "DETERMINISTIC_ANALYTICS"


class TargetCriterion(str, Enum):
    EXPLICIT = "EXPLICIT"
    COST = "COST"
    COMMONALITY = "COMMONALITY"


@dataclass(frozen=True)
class WorkflowTargetResolutionRequest:
    mode: TargetResolutionMode
    criterion: TargetCriterion
    selection_mode: str
    explicit_item_code: str | None = None
    explicit_target_name: str | None = None
    reason: str = ""

    @property
    def analytics_required(self) -> bool:
        return self.mode == TargetResolutionMode.DETERMINISTIC_ANALYTICS

    @property
    def explicit(self) -> bool:
        return self.mode == TargetResolutionMode.EXPLICIT

    def as_dict(self) -> dict[str, str | None | bool]:
        return {
            "mode": self.mode.value,
            "criterion": self.criterion.value,
            "selection_mode": self.selection_mode,
            "explicit_item_code": self.explicit_item_code,
            "explicit_target_name": self.explicit_target_name,
            "analytics_required": self.analytics_required,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WorkflowTargetResolutionDecision:
    request: WorkflowTargetResolutionRequest | None
    blocked_reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.request is not None and not self.blocked_reason


class WorkflowTargetResolutionPlanner:
    """Classify explicit vs deterministic-analytics target resolution."""

    UNIQUE_PATTERNS = (
        re.compile(r"(?:가장|제일).{0,18}(?:높|낮|많|적|비싸|저렴|싼)", re.IGNORECASE),
        re.compile(r"(?:상위|하위|TOP|BOTTOM)\s*1\s*(?:개|건)?", re.IGNORECASE),
        re.compile(r"(?:최고|최대|최저|최소).{0,12}(?:원가|단가|가격|공용|사용)", re.IGNORECASE),
        re.compile(r"(?:원가|단가|가격|공용성).{0,18}(?:가장|제일)", re.IGNORECASE),
    )
    LOW_MARKERS = (
        "가장 낮", "제일 낮", "최저", "최소", "하위 1", "하위1",
        "가장 저렴", "제일 저렴", "가장 싼", "제일 싼", "bottom 1",
    )
    GENERIC_TARGETS = {
        "", "자재", "품목", "부품", "material", "assy", "어셈블리",
        "이 자재", "그 자재", "해당 자재", "이 품목", "그 품목",
        "자재 1개", "자재 하나", "품목 1개", "품목 하나",
    }

    def __init__(self, *, domain_router: DomainIntentRouter | None = None) -> None:
        self.domain_router = domain_router or DEFAULT_DOMAIN_INTENT_ROUTER

    def resolve(
        self,
        user_goal: str,
        *,
        scope_version_code: str,
    ) -> WorkflowTargetResolutionDecision:
        goal = " ".join(str(user_goal or "").strip().split())
        if not goal:
            return WorkflowTargetResolutionDecision(None, "변경 분석 요청이 비어 있습니다.")

        normalized = self.domain_router.normalize(goal)
        if self.domain_router.is_delete_instruction(goal):
            return WorkflowTargetResolutionDecision(
                None, "현재 Evidence Composition은 DELETE Target 자동선정을 지원하지 않습니다."
            )
        if self.domain_router.is_quantity_change_instruction(goal):
            return WorkflowTargetResolutionDecision(
                None, "현재 Evidence Composition은 수량변경 Target 자동선정을 지원하지 않습니다."
            )
        if any(marker in normalized for marker in ("추가", "넣어")):
            return WorkflowTargetResolutionDecision(
                None, "현재 Evidence Composition은 ADD Target 자동선정을 지원하지 않습니다."
            )

        version = str(scope_version_code or "").strip().upper()
        codes = [code.upper() for code in self.domain_router.item_codes(goal)]
        source_codes = list(dict.fromkeys(code for code in codes if code != version))
        if len(source_codes) > 1:
            return WorkflowTargetResolutionDecision(
                None,
                (
                    "현재 요청에 변경 대상 후보 코드가 둘 이상 포함되어 있습니다. "
                    "기존/신규 품목을 동시에 지정하는 분석은 기존 명시 Pair 경로를 "
                    "사용하고, Evidence Target 자동선정에는 단일 source 품목만 지정해 주세요."
                ),
            )
        if len(source_codes) == 1:
            return WorkflowTargetResolutionDecision(
                WorkflowTargetResolutionRequest(
                    mode=TargetResolutionMode.EXPLICIT,
                    criterion=TargetCriterion.EXPLICIT,
                    selection_mode="USER_SPECIFIED",
                    explicit_item_code=source_codes[0],
                    reason="사용자가 source 품목코드를 직접 지정했습니다.",
                )
            )

        # Ranking language owns target resolution before name extraction.
        # Otherwise a sentence such as "원가가 높은 자재들을 보고 적당한 걸
        # 변경해줘" could be misread as a literal item name.
        criterion = self.domain_router.comparison_criterion(goal)
        if criterion in {"COST", "COMMONALITY"}:
            if not self._has_unique_selection(goal):
                return WorkflowTargetResolutionDecision(
                    None,
                    (
                        "복수 자재 중 하나를 시스템이 임의 선택하지 않습니다. "
                        "'가장 ... 1개'처럼 유일한 선택 기준을 명시하거나 품목을 직접 선택해 주세요."
                    ),
                )
            if criterion == "COST":
                selection_mode = (
                    "TOP_1_LOW" if any(marker in normalized for marker in self.LOW_MARKERS)
                    else "TOP_1_HIGH"
                )
                target_criterion = TargetCriterion.COST
            else:
                selection_mode = "TOP_1_HIGH"
                target_criterion = TargetCriterion.COMMONALITY

            return WorkflowTargetResolutionDecision(
                WorkflowTargetResolutionRequest(
                    mode=TargetResolutionMode.DETERMINISTIC_ANALYTICS,
                    criterion=target_criterion,
                    selection_mode=selection_mode,
                    reason="사용자가 deterministic 단일 ranking 기준을 명시했습니다.",
                )
            )

        target_name = self._explicit_target_name(goal)
        if target_name:
            return WorkflowTargetResolutionDecision(
                WorkflowTargetResolutionRequest(
                    mode=TargetResolutionMode.EXPLICIT,
                    criterion=TargetCriterion.EXPLICIT,
                    selection_mode="USER_SPECIFIED",
                    explicit_target_name=target_name,
                    reason="사용자가 source 품목명을 직접 지정했습니다.",
                )
            )

        if criterion not in {"COST", "COMMONALITY"}:
            return WorkflowTargetResolutionDecision(
                None,
                (
                    "변경 대상을 자동 선정할 근거가 명확하지 않습니다. 품목코드/품목명을 "
                    "직접 지정하거나 '가장 원가가 높은 자재 1개', "
                    "'공용성이 가장 높은 자재 1개'처럼 단일 선정 기준을 명시해 주세요."
                ),
            )

    def _has_unique_selection(self, user_goal: str) -> bool:
        text = " ".join(str(user_goal or "").strip().split())
        return any(pattern.search(text) for pattern in self.UNIQUE_PATTERNS)

    def _explicit_target_name(self, user_goal: str) -> str | None:
        """Extract a name immediately attached to a REPLACE analysis phrase.

        This is intentionally narrower than general entity extraction.  Scope
        codes and grammar are stripped first; generic pronouns such as "그 자재"
        are rejected so analytics-selected targets remain analytics-selected.
        """
        raw = " ".join(str(user_goal or "").strip().split())
        if not raw:
            return None

        # If the sentence contains more than one replacement concept, target
        # roles can belong to different clauses (for example a Knowledge rule
        # clause followed by the real source item).  Do not guess which clause
        # owns the target; preserve the existing Agent/workflow path instead.
        action_hits = re.findall(
            r"(?:변경|교체|대체|바꾸|바꿔)",
            raw,
            flags=re.IGNORECASE,
        )
        if len(action_hits) != 1:
            return None

        candidate = raw
        for code in self.domain_router.item_codes(raw):
            candidate = re.sub(re.escape(code), " ", candidate, flags=re.IGNORECASE)
        candidate = self.domain_router.PLANT_CODE_PATTERN.sub(" ", candidate)
        # Scope nouns can be immediately followed by a Korean particle
        # (for example ``모델에서``).  ``\b`` is not a safe delimiter there
        # because both the noun and the particle are Unicode word characters.
        # Strip only leading scope grammar after VERSION/PLANT codes have been
        # removed so a legitimate target name containing MODEL/BOM elsewhere is
        # not damaged.
        candidate = re.sub(
            r"^\s*(?:(?:모델|제품|VERSION|MODEL|BOM)\s*"
            r"(?:에서는|에서의|내에서|내의|에서|의|내)?\s*)+",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = " ".join(candidate.split())
        # Removing a PLANT/VERSION token from Korean scope phrases leaves a
        # leading particle such as "에서".  It is grammar, not part of the
        # business item name.
        candidate = re.sub(
            r"^(?:에서|에서는|에서의|내에서|내의|내|의|에)\s*",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()

        patterns = (
            r"(?P<target>[A-Z0-9가-힣][A-Z0-9가-힣 _/\-]{1,80}?)\s*"
            r"(?:자재|품목|부품|MATERIAL|ASSY|어셈블리)?\s*(?:을|를)?\s*"
            r"(?:다른\s*(?:자재|품목|부품)\s*(?:로|으로)\s*)?"
            r"(?:변경|교체|대체|바꾸|바꿔)",
        )
        match = re.search(patterns[0], candidate, flags=re.IGNORECASE)
        if not match:
            return None
        target = " ".join(str(match.group("target") or "").strip().split())
        target = re.sub(
            r"^(?:이|그|해당|현재)\s+",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()
        target = re.sub(
            r"\s*(?:자재|품목|부품|MATERIAL|ASSY|어셈블리)\s*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()
        target = re.sub(r"(?:을|를|은|는|이|가|의)$", "", target).strip()
        if target.lower() in self.GENERIC_TARGETS:
            return None
        # Ranking phrases are not item names.
        lowered = target.lower()
        if any(marker in lowered for marker in (
            "가장 원가", "원가가 가장", "공용성이 가장", "가장 공용",
            "상위 1", "상위1", "최고 원가", "최대 원가",
        )):
            return None
        return target or None


DEFAULT_WORKFLOW_TARGET_RESOLUTION_PLANNER = WorkflowTargetResolutionPlanner()


__all__ = [
    "DEFAULT_WORKFLOW_TARGET_RESOLUTION_PLANNER",
    "TargetCriterion",
    "TargetResolutionMode",
    "WorkflowTargetResolutionDecision",
    "WorkflowTargetResolutionPlanner",
    "WorkflowTargetResolutionRequest",
]
