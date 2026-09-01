"""Rule-based Display BOM domain intent routing.

This module owns the deterministic natural-language rules used before the LLM.
It intentionally handles only high-confidence, domain-specific routing signals.
Ambiguous or complex requests fall back to the normal LLM Agent path.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class DomainRoutingDecision:
    """Structured result of deterministic domain intent routing."""

    intent: str
    fast_path_candidate: bool
    design_change_mode: bool
    product_cost_scan: bool
    recommendation: bool
    change: bool
    delete: bool
    quantity_change: bool
    where_used: bool
    plain_bom: bool
    requires_plant: bool
    plant_code: str | None
    reference_code: str | None
    where_used_item_code: str | None
    new_quantity: float | None
    current_bom_quantity: bool
    current_bom_subject: str | None
    chat_response: str | None


class DomainIntentRouter:
    """Deterministic router for high-confidence Display BOM business intents.

    Responsibility boundary:
    - CURRENT user turn -> intent classification
    - Domain regex / keyword rules -> entity and slot extraction
    - High-confidence intent -> Fast Path candidate
    - Ambiguous/complex intent -> LLM fallback

    The router does not execute Tools and does not change BOM data.
    """

    FOLLOW_UP_EXPLAIN_MARKERS = (
        "왜", "이유", "사유", "근거", "원인", "설명", "탈락",
        "fail", "conditional", "조건부", "후보가 없", "후보 없음",
        "적합 후보", "spec", "스펙", "재고평가", "재고 평가",
    )
    FOLLOW_UP_COMPARE_MARKERS = (
        "비교", "차이", "뭐가 더", "어떤 게 더", "어떤게 더",
        "가장", "비슷", "유사", "가까운", "저렴", "싼",
        "재고가 많은", "재고 많은", "점수가 높은",
    )
    ANALYSIS_RESTART_MARKERS = (
        "다시 처음", "처음부터 다시", "처음부터 확인", "처음부터 분석",
        "다시 분석", "새로 분석", "분석 다시", "다시 조회", "처음부터 보자",
        "다시 확인하자", "새로 시작",
    )
    DESIGN_CHANGE_RECOMMENDATION_MARKERS = (
        "추천", "후보", "찾아", "대체 가능", "대체가능", "대체재", "대체품",
        "변경 가능", "변경가능", "recommend", "candidate", "alternative",
        "replacement material",
    )
    PRODUCT_COST_SCAN_SCOPE_MARKERS = (
        "대상모델", "대상 모델", "모델 전체", "제품 전체", "전체 bom", "bom 전체",
        "bom에 구성", "bom 구성", "구성된 자재", "구성 자재", "모델 원가", "제품 원가",
    )
    PRODUCT_COST_SCAN_COST_MARKERS = ("원가", "비용", "cost", "저렴", "절감")
    PRODUCT_COST_SCAN_ACTION_MARKERS = (
        "대체", "변경 가능", "변경가능", "후보", "찾아", "줄일",
    )
    ASSY_PROCESS_NAMES = ("OLB", "CP", "BIN", "LC", "CF", "TFT")

    DESIGN_CHANGE_INTENT_MARKERS = (
        "변경", "교체", "대체", "바꾸", "추가", "삭제", "제거",
        "없애", "빼", "제외", "수량", "증량", "감량",
    )
    DESIGN_CHANGE_EXPLICIT_ACTION_MARKERS = (
        "추가", "삭제", "제거", "없애", "빼", "제외", "증량", "감량",
    )
    DESIGN_CHANGE_DIRECTIVE_LANGUAGE_MARKERS = (
        "하고싶", "하고 싶",
        "해줘", "해 줘", "해주세요", "해 주세요",
        "하자", "진행하자",
        "바꿔줘", "바꿔 줘",
        "교체해줘", "교체해 줘",
        "변경해줘", "변경해 줘",
        "대체해줘", "대체해 줘",
    )
    REPLACE_ACTION_MARKERS = ("변경", "교체", "대체", "바꾸", "바꿔")
    DESIGN_CHANGE_APPLY_INTENT_MARKERS = (
        "설계변경 bom 반영", "설계변경 bom반영", "bom 반영", "bom반영",
        "production bom 반영", "production e-bom 반영", "apply",
    )
    DESIGN_CHANGE_REASON_LANGUAGE_MARKERS = (
        "단종", "eol", "공급 중단", "공급중단", "납기", "원가", "비용", "재고",
        "품질", "불량", "고객 사양", "고객사양", "규제", "인증", "공용화", "공통화",
    )

    ITEM_CODE_PATTERN = re.compile(
        # Support both ordinary codes (LJ94-100006) and hierarchical ASSY
        # codes with alpha segments (AS-FA-001) without matching only the
        # trailing substring (FA-001).  The final numeric segment keeps this
        # pattern from treating normal hyphenated words as item codes.
        r"(?<![A-Z0-9])(?:[A-Z]{2,}[A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d{3,}(?:-\d+)?|\d{4}-\d{6})(?![A-Z0-9])",
        re.IGNORECASE,
    )
    PLANT_CODE_PATTERN = re.compile(r"(?<![A-Z0-9])P\d{2,}(?![A-Z0-9])", re.IGNORECASE)
    PLANT_REQUIRED_QUERY_MARKERS = ("bom", "설계변경", "변경", "교체", "대체", "후보")
    WHERE_USED_MARKERS = (
        "역방향 bom", "역방향", "where used", "where-used", "사용처",
        "가지고 있는 모델", "포함하는 모델", "포함한 모델", "포함된 모델",
        "들어간 모델", "들어있는 모델", "사용한 모델", "사용된 모델", "사용되는 모델",
        "어떤 모델", "어느 모델", "상위 assy", "상위assy", "상위 모델",
        "어디에 사용", "어디에 들어", "어디에 포함",
    )
    PLAIN_BOM_QUERY_MARKERS = ("bom", "조회", "보여", "알려", "확인")
    CURRENT_BOM_QUANTITY_QUESTION_MARKERS = (
        "몇", "얼마", "뭐", "알려", "확인", "인가", "이야", "입니까", "나요",
    )
    SIMPLE_CHAT_EXACT = {
        "안녕", "안녕하세요", "안녕하세요.", "반가워", "반갑습니다",
        "고마워", "고마워요", "감사", "감사합니다",
    }

    @staticmethod
    def normalize(user_query: str) -> str:
        return " ".join(str(user_query or "").strip().lower().split())

    def route(
        self,
        user_query: str,
        *,
        workflow_active: bool = False,
        workflow_state: dict[str, Any] | None = None,
    ) -> DomainRoutingDecision:
        """Classify the current turn and return a structured routing decision."""
        workflow_state = workflow_state or {}
        chat_response = self.fast_chat_response(user_query)
        product_cost_scan = self.is_product_cost_scan_request(user_query)
        recommendation = self.is_design_change_recommendation_request(user_query)
        change = self.is_design_change_request(user_query)
        delete = self.is_delete_instruction(user_query)
        quantity_change = self.is_quantity_change_instruction(user_query)
        new_quantity = self.extract_new_quantity(user_query)
        current_bom_subject = self.extract_current_bom_quantity_subject(user_query)
        current_bom_quantity = (
            current_bom_subject is not None
            and not change
            and not recommendation
            and not product_cost_scan
        )

        # A current-turn write/change intent takes precedence over a read-only
        # WHERE_USED phrase. Conversation history must never define current intent.
        where_used = (
            self.is_where_used_request(user_query)
            and not change
            and not recommendation
        )
        design_change_mode = product_cost_scan or recommendation or change or workflow_active
        plain_bom = self.is_plain_bom_query(user_query, design_change_mode=design_change_mode)
        requires_plant = self.requires_plant_context(
            user_query,
            design_change_mode=design_change_mode,
            where_used=where_used,
        )

        if chat_response is not None:
            intent = "CHAT"
        elif product_cost_scan:
            intent = "PRODUCT_COST_SCAN"
        elif change:
            intent = "DESIGN_CHANGE"
        elif recommendation:
            intent = "DESIGN_CHANGE_RECOMMENDATION"
        elif where_used:
            intent = "WHERE_USED"
        elif current_bom_quantity:
            intent = "CURRENT_BOM_QUANTITY"
        elif plain_bom:
            intent = "BOM_READ"
        else:
            intent = "LLM_FALLBACK"

        return DomainRoutingDecision(
            intent=intent,
            fast_path_candidate=intent in {
                "CHAT", "WHERE_USED", "BOM_READ", "CURRENT_BOM_QUANTITY",
            },
            design_change_mode=design_change_mode,
            product_cost_scan=product_cost_scan,
            recommendation=recommendation,
            change=change,
            delete=delete,
            quantity_change=quantity_change,
            where_used=where_used,
            plain_bom=plain_bom,
            requires_plant=requires_plant,
            plant_code=self.extract_plant_code(user_query),
            reference_code=self.reference_code_for_plant_lookup(user_query, workflow_state),
            where_used_item_code=self.where_used_item_code(user_query),
            new_quantity=new_quantity,
            current_bom_quantity=current_bom_quantity,
            current_bom_subject=current_bom_subject,
            chat_response=chat_response,
        )

    def fast_chat_response(self, user_query: str) -> str | None:
        if self.normalize(user_query) not in self.SIMPLE_CHAT_EXACT:
            return None
        return "안녕하세요. Display BOM AI Agent입니다. 무엇을 도와드릴까요?"

    def is_plain_bom_query(self, user_query: str, *, design_change_mode: bool) -> bool:
        if design_change_mode or self.is_where_used_request(user_query):
            return False
        normalized = self.normalize(user_query)
        if "bom" not in normalized:
            return False
        if not any(marker in normalized for marker in self.PLAIN_BOM_QUERY_MARKERS):
            return False
        # Fast Path requires an explicit root code. Ambiguous targets go to LLM.
        return self.first_item_code(user_query) is not None

    def extract_current_bom_quantity_subject(
        self,
        user_query: str,
    ) -> str | None:
        """Extract the subject of a read-only quantity question.

        Examples:
        - "실런트 자재수량은 몇이야?" -> "실런트"
        - "0001-200010 수량은 몇이야?" -> "0001-200010"

        An actual quantity-change instruction is deliberately excluded.
        """
        if self.is_quantity_change_instruction(user_query):
            return None

        normalized = self.normalize(user_query)
        if "수량" not in normalized:
            return None
        if not any(
            marker in normalized
            for marker in self.CURRENT_BOM_QUANTITY_QUESTION_MARKERS
        ):
            return None

        raw = " ".join(str(user_query or "").strip().split())
        match = re.search(
            r"^(.*?)\s*(?:자재|품목)?\s*(?:의\s*)?"
            r"(?:bom\s*)?수량",
            raw,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        subject = str(match.group(1) or "").strip()
        subject = re.sub(
            r"^(?:현재|이|그)\s+",
            "",
            subject,
            flags=re.IGNORECASE,
        ).strip(" ,:：")
        return subject or None

    def is_current_bom_quantity_query(self, user_query: str) -> bool:
        return self.extract_current_bom_quantity_subject(user_query) is not None

    def is_product_cost_scan_request(self, user_query: str) -> bool:
        normalized = self.normalize(user_query)
        return (
            any(marker in normalized for marker in self.PRODUCT_COST_SCAN_SCOPE_MARKERS)
            and any(marker in normalized for marker in self.PRODUCT_COST_SCAN_COST_MARKERS)
            and any(marker in normalized for marker in self.PRODUCT_COST_SCAN_ACTION_MARKERS)
        )

    def is_where_used_request(self, user_query: str) -> bool:
        normalized = self.normalize(user_query)
        return any(marker in normalized for marker in self.WHERE_USED_MARKERS)

    def item_codes(self, user_query: str) -> list[str]:
        return [
            match.group(0).upper()
            for match in self.ITEM_CODE_PATTERN.finditer(str(user_query or ""))
        ]

    def first_item_code(self, user_query: str) -> str | None:
        codes = self.item_codes(user_query)
        return codes[0] if codes else None

    def where_used_item_code(self, user_query: str) -> str | None:
        codes = self.item_codes(user_query)
        return codes[-1] if codes else None

    def explicit_model_scope_code(self, user_query: str) -> str | None:
        """Return a code explicitly described as a model/product/version.

        This is used only to decide whether an active BOM context may be
        inherited. Current-turn explicit scope always wins over inherited scope.
        """
        text = str(user_query or "")
        upper = text.upper()
        markers = ("모델", "제품", "VERSION", "MODEL")

        for code in self.item_codes(text):
            index = upper.find(code.upper())
            if index < 0:
                continue
            window = upper[max(0, index - 24): index + len(code) + 28]
            if any(marker.upper() in window for marker in markers):
                return code
        return None

    def active_version_code(self, workflow_state: dict[str, Any]) -> str | None:
        request = workflow_state.get("analysis_request") or {}
        value = request.get("version_code")
        if value:
            return str(value).strip().upper()
        context = workflow_state.get("analysis_context") or {}
        value = context.get("version_code")
        return str(value).strip().upper() if value else None

    def reference_code_for_plant_lookup(
        self,
        user_query: str,
        workflow_state: dict[str, Any],
    ) -> str | None:
        active_version = self.active_version_code(workflow_state)
        return active_version or self.first_item_code(user_query)

    def is_plant_only_selection(self, user_query: str) -> bool:
        """Return True for a compact PLANT slot answer such as `P01`.

        This is not a new intent. It is only a slot-completion signal that may
        reuse the immediately preceding request's entity context.
        """
        normalized = self.normalize(user_query).upper()
        return self.PLANT_CODE_PATTERN.fullmatch(normalized) is not None

    def is_explicit_replacement_pair_analysis(self, user_query: str) -> bool:
        """Detect a read-only suitability analysis for an explicit old/new pair.

        Example::

            MODEL-789의 1234-567890을 1234-567891로 교체 가능한지 분석해줘

        This used to be routed to the removed ``analyze_design_change``
        Tool.  The current Core routes the same intent into the read-only
        ``analyze_design_change_candidates`` Analysis Session instead.
        """
        normalized = self.normalize(user_query)
        version_code = self.explicit_model_scope_code(user_query)
        non_version_codes = [
            code
            for code in self.item_codes(user_query)
            if not version_code or code != version_code
        ]
        unique_codes = list(dict.fromkeys(non_version_codes))
        if len(unique_codes) < 2:
            return False

        if not any(
            marker in normalized
            for marker in (
                "가능한지",
                "가능 여부",
                "가능여부",
                "적합",
                "호환",
                "분석",
                "검증",
            )
        ):
            return False

        # A direct execution instruction remains a write/change request.
        return not any(
            marker in normalized
            for marker in (
                "교체해줘",
                "교체해 줘",
                "변경해줘",
                "변경해 줘",
                "바꿔줘",
                "바꿔 줘",
                "대체해줘",
                "대체해 줘",
                "교체하자",
                "변경하자",
                "바꾸자",
                "대체하자",
            )
        )

    def is_design_change_recommendation_request(self, user_query: str) -> bool:
        if self.is_explicit_replacement_pair_analysis(user_query):
            return True
        normalized = self.normalize(user_query)
        return any(marker in normalized for marker in self.DESIGN_CHANGE_RECOMMENDATION_MARKERS)

    def has_design_change_reason_language(self, user_query: str) -> bool:
        normalized = self.normalize(user_query)
        return any(marker in normalized for marker in self.DESIGN_CHANGE_REASON_LANGUAGE_MARKERS)

    def is_delete_instruction(self, user_query: str) -> bool:
        normalized = self.normalize(user_query)
        return any(marker in normalized for marker in ("삭제", "제거", "없애", "빼", "제외"))

    def extract_quantity_only_input(self, user_query: str) -> float | None:
        normalized = self.normalize(user_query)
        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(?:개|ea)?",
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def extract_new_quantity(self, user_query: str) -> float | None:
        normalized = self.normalize(user_query)
        patterns = (
            r"(?:수량|quantity)\s*(?:을|를)?\s*"
            r"(?:\d+(?:\.\d+)?\s*(?:에서|->|→)\s*)?"
            r"(\d+(?:\.\d+)?)\s*(?:개|ea)?\s*(?:로|으로)?",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not match:
                continue
            try:
                value = float(match.group(1))
            except (TypeError, ValueError):
                continue
            return value if value > 0 else None
        return None

    def is_quantity_change_instruction(self, user_query: str) -> bool:
        normalized = self.normalize(user_query)
        if any(marker in normalized for marker in ("증량", "감량")):
            return True
        if "수량" not in normalized:
            return False
        return any(marker in normalized for marker in (
            "변경", "바꾸", "바꿔", "조정", "수정",
            "늘리", "늘려", "줄이", "줄여", "증가", "감소",
        ))

    def is_design_change_apply_instruction(self, user_query: str) -> bool:
        """Detect an explicit request to apply a design change to Production BOM.

        This is a write/safety intent even when the sentence also contains words
        such as ``후보`` or ``FAIL``.  Routing it as recommendation would weaken
        the approval guard because the user is explicitly asking for BOM apply.
        """
        normalized = self.normalize(user_query)
        return any(marker in normalized for marker in self.DESIGN_CHANGE_APPLY_INTENT_MARKERS)

    def is_design_change_request(self, user_query: str) -> bool:
        """Return True only for an actual design-change instruction.

        Recommendation/analysis wording such as ``대체 후보 추천해줘`` or
        ``교체 후보 분석해줘`` must not become a write/change intent merely
        because the sentence contains a generic ``해줘`` attached to
        ``추천``/``분석``.  Conversely, natural Korean directives such as
        ``바꾸고 싶어`` and ``교체하고 싶어`` are explicit change requests.
        """
        normalized = self.normalize(user_query)

        if self.is_quantity_change_instruction(user_query):
            return True
        if self.is_delete_instruction(user_query):
            return True
        if self.is_design_change_apply_instruction(user_query):
            return True

        # ADD is a concrete BOM action when phrased as an instruction/wish.
        if any(marker in normalized for marker in ("추가", "넣어")):
            if any(marker in normalized for marker in (
                "추가하고 싶", "추가하고싶", "추가해줘", "추가해 줘",
                "추가해주세요", "추가해 주세요", "추가하자", "추가하고",
                "넣어줘", "넣어 줘", "넣고 싶", "넣고싶", "넣고",
            )):
                return True
            # Short imperative forms such as ``자재 추가`` are also treated
            # as an action unless the user explicitly asks only for candidates.
            if not self.is_design_change_recommendation_request(user_query):
                return True
            return False

        has_replace_action = any(
            marker in normalized for marker in self.REPLACE_ACTION_MARKERS
        )
        if not has_replace_action:
            return False

        if self._has_direct_replace_directive(normalized):
            return True

        # Reason + terse action is still a concrete change request, but a
        # recommendation/analysis request remains read-only Analysis intent.
        if (
            self.has_design_change_reason_language(user_query)
            and not self.is_design_change_recommendation_request(user_query)
        ):
            return True
        return False

    @staticmethod
    def _has_direct_replace_directive(normalized: str) -> bool:
        patterns = (
            r"(?:변경|교체|대체)\s*(?:하고\s*싶|하고싶|해\s*줘|해주세요|해\s*주세요|하자)",
            r"(?:바꾸|바꿔)\s*(?:고\s*싶|고싶|줘|\s*줘|주세요|자)",
        )
        return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)

    def classify_analysis_follow_up(
        self,
        user_query: str,
        workflow_state: dict[str, Any],
        *,
        active_steps: set[str] | frozenset[str],
    ) -> str | None:
        step = workflow_state.get("current_step")
        if step not in active_steps:
            return None
        normalized = self.normalize(user_query)
        if not normalized:
            return None
        if workflow_state.get("analysis_id") and not workflow_state.get("request_id"):
            if any(marker in normalized for marker in self.ANALYSIS_RESTART_MARKERS):
                return "RESTART_ANALYSIS"
        if any(marker in normalized for marker in self.FOLLOW_UP_EXPLAIN_MARKERS):
            mentioned = self.mentioned_candidate_codes(user_query, workflow_state)
            return "EXPLAIN_CANDIDATE" if mentioned else "EXPLAIN_ANALYSIS"
        if not workflow_state.get("candidates"):
            return None
        if any(marker in normalized for marker in self.FOLLOW_UP_COMPARE_MARKERS):
            if any(marker in normalized for marker in (
                "가장", "비슷", "유사", "저렴", "납기", "재고", "점수",
            )):
                return "RANK_CANDIDATES"
            return "COMPARE_CANDIDATES"
        return None

    def mentioned_candidate_codes(
        self,
        user_query: str,
        workflow_state: dict[str, Any],
    ) -> list[str]:
        available = {
            str(value.get("candidate_item_code") or "").upper()
            for value in workflow_state.get("candidates", [])
            if value.get("candidate_item_code")
        }
        mentioned: list[str] = []
        for code in self.item_codes(user_query):
            if code in available and code not in mentioned:
                mentioned.append(code)
        return mentioned

    def extract_plant_code(self, user_query: str) -> str | None:
        match = self.PLANT_CODE_PATTERN.search(str(user_query or ""))
        return match.group(0).upper() if match else None

    def requires_plant_context(
        self,
        user_query: str,
        *,
        design_change_mode: bool,
        where_used: bool | None = None,
    ) -> bool:
        normalized = self.normalize(user_query)
        resolved_where_used = (
            self.is_where_used_request(user_query)
            if where_used is None
            else where_used
        )
        return (
            design_change_mode
            or resolved_where_used
            or any(marker in normalized for marker in self.PLANT_REQUIRED_QUERY_MARKERS)
        )

    def extract_add_target_type(self, user_query: str) -> str | None:
        """Return an explicit ADD target type without guessing.

        MATERIAL is accepted only from explicit material wording.
        ASSY is accepted only from explicit assembly wording.
        Generic "품목" remains ambiguous and therefore falls back to Agent Path.
        """
        normalized = self.normalize(user_query)
        material_markers = ("자재", "material")
        assy_markers = ("assy", "어셈블리", "어셈블리")

        material = any(marker in normalized for marker in material_markers)
        assy = any(marker in normalized for marker in assy_markers)
        if material == assy:
            return None
        return "MATERIAL" if material else "ASSY"

    def extract_add_target_name(self, user_query: str) -> str | None:
        """Extract the requested item family/name from an ADD instruction.

        Example:
            LTA400HR01-001 P01 모델에 SEALANT 자재를 추가하고싶어
            -> SEALANT
        """
        raw = " ".join(str(user_query or "").strip().split())
        normalized = self.normalize(raw)
        if not raw or not any(marker in normalized for marker in ("추가", "넣어")):
            return None

        # Remove one explicit MODEL/VERSION scope and PLANT. Any remaining item
        # code may be an ASSY parent and is handled separately.
        candidate = self.ITEM_CODE_PATTERN.sub(" ", raw, count=1)
        candidate = self.PLANT_CODE_PATTERN.sub(" ", candidate)
        candidate = re.sub(
            r"\b(?:모델|제품|VERSION|MODEL)\s*(?:에서|의|에)?",
            " ",
            candidate,
            flags=re.IGNORECASE,
        )

        # If an explicit parent relation is present, keep only the text after it.
        parent_split = re.split(
            r"(?:하위|아래|밑|부모|PARENT|UNDER)(?:에|에다가|로)?",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(parent_split) == 2:
            candidate = parent_split[1]

        target = re.split(
            r"(?:추가|넣어)",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]

        target = " ".join(str(target or "").strip().split())
        target = re.sub(r"(?:을|를|은|는|이|가|의)$", "", target).strip()
        target = re.sub(
            r"\s*(?:자재|MATERIAL|ASSY|어셈블리|어셈블리)\s*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()
        # A whole-query quote or a quoted target must never become the target
        # itself.  Strip only wrapping quote characters after the business
        # suffixes have been removed so a quoted real name such as
        # ``"SEALANT"`` still resolves to ``SEALANT``.
        target = target.strip('"\'`“”‘’').strip()

        # A parent code left inside the target makes this extraction ambiguous.
        if not target or self.item_codes(target):
            return None
        return target

    def extract_add_parent_code(
        self,
        user_query: str,
        *,
        version_code: str | None,
    ) -> str | None:
        """Return an explicitly described ADD parent.

        One non-version item code is accepted only when the sentence also
        contains an explicit parent/under marker. This prevents treating a new
        item code as a parent by accident.
        """
        normalized = self.normalize(user_query)
        parent_markers = ("하위", "아래", "밑", "부모", "parent", "under")
        if not any(marker in normalized for marker in parent_markers):
            return None

        codes = [
            code
            for code in self.item_codes(user_query)
            if not version_code or code != version_code
        ]
        unique = list(dict.fromkeys(codes))
        return unique[0] if len(unique) == 1 else None

    def extract_target_correction(self, user_query: str) -> str | None:
        """Extract a corrected source target from a short follow-up.

        Example: ``DRIVE-IC가 아니라 GATE-IC 자재였어`` -> ``GATE-IC``.
        This returns only the corrected name. Reusing MODEL/PLANT/action/reason is
        handled by DeterministicAnalysisMacroDispatch from the previous user turn.
        """
        raw = " ".join(str(user_query or "").strip().split())
        if not raw:
            return None
        parts = re.split(
            r"\s*(?:(?:이|가)\s*)?(?:아니라|말고)\s*",
            raw,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(parts) != 2:
            return None
        target = parts[1].strip()
        target = re.sub(
            r"\s*(?:자재|품목|부품|MATERIAL|ASSY)?\s*"
            r"(?:였어|이었어|였어요|이었어요|이야|야|이에요|예요|입니다|맞아|맞아요)?"
            r"[.!?。]*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()
        target = re.sub(r"(?:을|를|은|는|이|가|의)$", "", target).strip()
        if not target or self.item_codes(target):
            return None
        return target

    def extract_named_change_target(self, user_query: str) -> str | None:
        """Extract a business target name when no explicit source item code exists.

        This helper is only a routing signal. The authoritative item resolution
        happens in DesignChangeWorkflowService against the scoped product BOM.
        """
        raw = " ".join(str(user_query or "").strip().split())
        if not raw or not self.is_design_change_request(raw):
            return None

        normalized = self.normalize(raw)
        # ADD owns a dedicated target parser because Parent/target roles differ
        # from REPLACE/DELETE/QUANTITY_CHANGE.  Treating ADD text as a generic
        # named source target can accidentally start Analysis with a missing
        # ASSY Parent.
        if any(marker in normalized for marker in ("추가", "넣어")):
            return None

        # Remove current product/PLANT scope from the front of an inherited
        # active-BOM follow-up.
        candidate = self.ITEM_CODE_PATTERN.sub(" ", raw, count=1)
        candidate = self.PLANT_CODE_PATTERN.sub(" ", candidate)
        candidate = re.sub(
            r"\b(?:모델|제품|VERSION|MODEL)\s*(?:에서|의)?",
            " ",
            candidate,
            flags=re.IGNORECASE,
        )

        # Removing a PLANT token from expressions such as ``P01에서`` leaves
        # the Korean scope particle at the front.  It is grammar, not part of
        # the target name.
        candidate = re.sub(
            r"^(?:에서|에서는|에서의|내에서|내의|내|의|에)\s*",
            "",
            candidate.strip(),
            flags=re.IGNORECASE,
        )

        quantity_match = re.search(
            r"(.+?)\s*(?:자재|품목|부품)?\s*(?:의\s*)?(?:BOM\s*)?수량",
            candidate,
            flags=re.IGNORECASE,
        )
        if quantity_match:
            target = quantity_match.group(1)
        else:
            target = re.split(
                r"(?:변경|교체|대체|바꾸|삭제|제거|없애|빼|제외|증량|감량)",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]

        target = " ".join(str(target or "").strip().split())
        # Remove an attached business-reason clause from the source item name.
        # Example: ``DRIVE-IC가 단종이라 교체하고 싶어`` -> ``DRIVE-IC``.
        target = re.sub(
            r"(?:이|가|은|는)?\s*(?:단종|eol|공급\s*중단|공급중단|납기|원가|비용|재고|품질|불량|고객\s*사양|고객사양|규제|인증|공용화|공통화).*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()
        target = re.sub(
            r"(?:을|를|은|는|이|가|의)$",
            "",
            target,
        ).strip()
        target = re.sub(
            r"\s*(?:자재|품목|부품|MATERIAL|ASSY|어셈블리)\s*$",
            "",
            target,
            flags=re.IGNORECASE,
        ).strip()

        generic = {
            "", "자재", "품목", "부품", "자재 하나", "품목 하나", "부품 하나",
            "이 자재", "그 자재", "이 품목", "그 품목",
            "MATERIAL", "ASSY", "어셈블리",
        }
        if target.upper() in {value.upper() for value in generic}:
            return None

        # A remaining explicit item code means normal code-based routing.
        if self.item_codes(target):
            return None
        return target

    def has_explicit_design_change_target(self, user_query: str) -> bool:
        codes = set(self.item_codes(user_query))
        if len(codes) >= 2:
            return True
        normalized = self.normalize(user_query)
        return (
            len(codes) >= 1
            and "추가" in normalized
            and any(marker in normalized for marker in self.DESIGN_CHANGE_RECOMMENDATION_MARKERS)
        )

    def comparison_criterion(self, user_query: str) -> str:
        normalized = self.normalize(user_query)
        if any(marker in normalized for marker in ("원가", "가격", "저렴", "싼")):
            return "COST"
        if "납기" in normalized:
            return "LEAD_TIME"
        if "재고" in normalized:
            return "INVENTORY"
        if any(marker in normalized for marker in ("점수", "등급", "score")):
            return "TOTAL_SCORE"
        return "SPEC_SIMILARITY"


DEFAULT_DOMAIN_INTENT_ROUTER = DomainIntentRouter()
