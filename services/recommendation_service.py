from __future__ import annotations

import re

from services.rule_engine import RuleEngine


class RuleNotFoundError(ValueError):
    """Backward-compatible exception type; STEP28 uses attribute fallback instead."""


class RecommendationService:
    def __init__(self, repository, rule_engine: RuleEngine | None = None) -> None:
        self.repository = repository
        self.rule_engine = rule_engine or RuleEngine()

    @staticmethod
    def _unique_candidates(candidates: list[dict]) -> list[dict]:
        """Keep one evaluation row per candidate item code.

        Discovery repositories are expected to return unique item codes, but this
        service-level guard prevents supplier joins or future discovery strategies
        from surfacing the same candidate multiple times in the comparison UI.
        """
        unique: list[dict] = []
        seen: set[str] = set()
        for candidate in candidates:
            code = str(candidate.get("candidate_item_code") or "")
            if not code or code in seen:
                continue
            seen.add(code)
            unique.append(candidate)
        return unique

    def evaluate_candidates(
        self,
        *,
        source_item_code: str,
        reasons: list[str],
        target_type: str,
        as_of_date: str,
        evaluation_items: list[str],
    ) -> list[dict]:
        candidates = self.repository.find_registered_candidates(source_item_code, as_of_date)
        discovery_mode = "REGISTERED"
        if not candidates:
            candidates = self.repository.find_attribute_candidates(
                source_item_code, target_type, as_of_date,
            )
            discovery_mode = "ATTRIBUTE_DISCOVERY"
        candidates = self._unique_candidates(candidates)
        if not candidates:
            return []
        return self._evaluate_candidate_rows(
            source_item_code=source_item_code,
            candidates=candidates,
            reasons=reasons,
            target_type=target_type,
            as_of_date=as_of_date,
            evaluation_items=evaluation_items,
            discovery_mode=discovery_mode,
        )

    def evaluate_specific_candidate(
        self,
        *,
        candidate_item_code: str,
        reasons: list[str],
        target_type: str,
        as_of_date: str,
        evaluation_items: list[str],
    ) -> list[dict]:
        item = self.repository.get_item(candidate_item_code)
        expected_type = "ASSEMBLY" if target_type == "ASSY" else "MATERIAL"
        if not item or item["item_type"] != expected_type or item["active_yn"] != "Y":
            raise ValueError("ADD target item does not match target_type or is inactive")
        return self._evaluate_candidate_rows(
            source_item_code=None,
            candidates=[{
                "candidate_item_code": candidate_item_code,
                "relation_type": "DIRECT_ADD",
                "priority": 1,
                "item_type": item["item_type"],
            }],
            reasons=reasons,
            target_type=target_type,
            as_of_date=as_of_date,
            evaluation_items=evaluation_items,
            discovery_mode="DIRECT_ADD",
        )

    def evaluate_add_candidates(
        self,
        *,
        reasons: list[str],
        target_type: str,
        as_of_date: str,
        evaluation_items: list[str],
        target_item_name: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Discover and rank candidates for an ADD without a preselected item.

        Discovery is master-data driven.  Active items of the requested type are
        evaluated by the same active Rule revisions used by normal Phase3 candidate
        evaluation.  If no applicable Rule exists the candidates remain
        CONDITIONAL instead of the service inventing suitability.
        """
        candidates = self.repository.find_add_candidate_items(
            target_type=target_type, as_of_date=as_of_date,
        )
        candidates = self._unique_candidates(candidates)
        if not candidates:
            return []
        evaluated = self._evaluate_candidate_rows(
            source_item_code=None,
            candidates=candidates,
            reasons=reasons,
            target_type=target_type,
            as_of_date=as_of_date,
            evaluation_items=evaluation_items,
            discovery_mode="ADD_RULE_DISCOVERY",
            rule_scope_hint=target_item_name,
        )
        # Keep the useful rows compact for the Agent/UI while still exposing FAIL
        # evidence when fewer eligible candidates are available.
        eligible = [row for row in evaluated if row.get("status") in {"PASS", "CONDITIONAL"}]
        failed = [row for row in evaluated if row.get("status") == "FAIL"]
        return (eligible + failed)[: max(1, int(limit))]

    @staticmethod
    def _normalize_label(value: object) -> str:
        return re.sub(r"[^0-9A-Z가-힣]", "", str(value or "").upper())

    def _item_profile(self, item_code: str, as_of_date: str) -> dict:
        getter = getattr(self.repository, "get_item_profile", None)
        if getter is not None:
            return getter(item_code, as_of_date)
        return self.repository.get_item_attributes(item_code, as_of_date)

    def _applicable_rules(self, rules: list[dict], source_item_code: str | None,
                          as_of_date: str) -> list[dict]:
        if not source_item_code:
            return rules
        profile = self._item_profile(source_item_code, as_of_date)
        labels = {
            self._normalize_label(profile.get(name))
            for name in ("item_name", "material_name", "process_name", "material_family")
            if profile.get(name)
        }
        applicable = []
        for rule in rules:
            evaluation_item = self._normalize_label(rule.get("evaluation_item"))
            if not evaluation_item or evaluation_item in {"ALL", "ANY"}:
                applicable.append(rule)
            elif evaluation_item in labels:
                applicable.append(rule)
        return applicable

    @classmethod
    def _select_add_rules(cls, rules: list[dict], target_item_name: str | None) -> list[dict]:
        """Narrow ADD rules by the user-requested item family when metadata supports it."""
        hint = cls._normalize_label(target_item_name)
        if not hint:
            return rules
        matched = []
        for rule in rules:
            labels = [
                cls._normalize_label(rule.get("evaluation_item")),
                cls._normalize_label(rule.get("rule_name")),
                cls._normalize_label(rule.get("description")),
            ]
            if any(label and (hint in label or label in hint) for label in labels):
                matched.append(rule)
        return matched or rules

    @staticmethod
    def _identity_rule_conditions(rule: dict) -> list[dict]:
        """Return categorical conditions that identify an ADD item family/process."""
        identity_tokens = ("family", "type", "name", "process", "category", "group")
        return [
            condition for condition in rule.get("conditions") or []
            if str(condition.get("operator") or "").upper() in {"EQ", "IN"}
            and any(token in str(condition.get("attribute_name") or "").lower() for token in identity_tokens)
            and condition.get("expected_value") not in {None, ""}
        ]

    def _filter_add_candidates_by_rule_identity(
        self, candidates: list[dict], rules: list[dict], as_of_date: str
    ) -> list[dict]:
        """Exclude unrelated master items before ADD ranking.

        The filter is driven entirely by active Rule metadata (for example
        material_family/process_name), never by scenario IDs or item codes.
        """
        scoped_rules = [
            (rule, self._identity_rule_conditions(rule))
            for rule in rules
            if self._identity_rule_conditions(rule)
        ]
        if not scoped_rules:
            return candidates

        matched: list[dict] = []
        for candidate in candidates:
            profile = self._item_profile(candidate["candidate_item_code"], as_of_date)
            for _rule, conditions in scoped_rules:
                rule_match = True
                for condition in conditions:
                    attr = str(condition.get("attribute_name") or "")
                    actual = self._normalize_label(profile.get(attr))
                    expected_values = [
                        self._normalize_label(value)
                        for value in str(condition.get("expected_value") or "").split(",")
                    ]
                    operator = str(condition.get("operator") or "").upper()
                    if operator == "EQ":
                        condition_match = bool(actual and expected_values and actual == expected_values[0])
                    else:
                        condition_match = bool(actual and actual in expected_values)
                    if not condition_match:
                        rule_match = False
                        break
                if rule_match:
                    matched.append(candidate)
                    break
        return matched

    @staticmethod
    def _functional_attributes(attributes: dict) -> list[str]:
        excluded_tokens = (
            "status", "cost", "price", "quality", "lead", "inventory",
            "stock", "quantity", "supplier",
        )
        return [
            name for name in attributes
            if not any(token in name.lower() for token in excluded_tokens)
        ]

    def _attribute_context(self, source_item_code: str, as_of_date: str,
                           requested_items: list[str]) -> tuple[dict, list[str]]:
        source_attributes = self.repository.get_item_attributes(source_item_code, as_of_date)
        if requested_items:
            profile = self._item_profile(source_item_code, as_of_date)
            return profile, requested_items
        if source_attributes:
            items = self._functional_attributes(source_attributes)
            return source_attributes, items
        profile = self._item_profile(source_item_code, as_of_date)
        master_items = [
            name for name in (
                "material_name", "material_group", "process_name", "specification",
                "unit", "item_name",
            )
            if name in profile
        ]
        return profile, master_items

    def _evaluate_candidate_rows(
        self,
        *,
        source_item_code: str | None,
        candidates: list[dict],
        reasons: list[str],
        target_type: str,
        as_of_date: str,
        evaluation_items: list[str],
        discovery_mode: str,
        rule_scope_hint: str | None = None,
    ) -> list[dict]:
        all_rules = self.repository.get_active_rules(reasons, target_type, as_of_date)
        if source_item_code is None:
            all_rules = self._select_add_rules(all_rules, rule_scope_hint)
            candidates = self._filter_add_candidates_by_rule_identity(
                candidates, all_rules, as_of_date
            )
            if not candidates:
                return []
        rules = self._applicable_rules(all_rules, source_item_code, as_of_date)

        source_comparison: dict = {}
        comparison_items: list[str] = []
        if source_item_code and not rules:
            source_comparison, comparison_items = self._attribute_context(
                source_item_code, as_of_date, evaluation_items,
            )

        evaluations = []
        for candidate in candidates:
            candidate_code = candidate["candidate_item_code"]
            if rules:
                attributes = self.repository.get_item_attributes(candidate_code, as_of_date)
                result = self.rule_engine.evaluate_rules(attributes, rules)
                result["evaluation_mode"] = "RULE"
                result["missing_data"] = []
            elif source_item_code:
                if self.repository.get_item_attributes(source_item_code, as_of_date):
                    candidate_profile = self.repository.get_item_attributes(
                        candidate_code, as_of_date
                    )
                else:
                    candidate_profile = self._item_profile(candidate_code, as_of_date)
                result = self.rule_engine.evaluate_attributes(
                    source_comparison, candidate_profile, comparison_items,
                )
                result.update({
                    "evaluation_mode": "ATTRIBUTE",
                    "rule_results": [],
                    "rule_snapshots": [],
                })
            else:
                # ADD without an applicable Rule cannot compare against an old item.
                result = {
                    "status": "CONDITIONAL",
                    "total_score": 0.0,
                    "grade": "C",
                    "missing_data": ["applicable_rule_or_source_item"],
                    "attribute_results": [],
                    "rule_results": [],
                    "rule_snapshots": [],
                    "evaluation_mode": "ATTRIBUTE",
                }
            evaluations.append({
                **candidate,
                **result,
                "candidate_item_code": candidate_code,
                "discovery_mode": discovery_mode,
            })

        status_order = {"PASS": 0, "CONDITIONAL": 1, "FAIL": 2}
        evaluations.sort(key=lambda row: (
            status_order[row["status"]], -row["total_score"], row["candidate_item_code"],
        ))
        rank = 0
        for evaluation in evaluations:
            if evaluation["status"] == "FAIL":
                evaluation["rank"] = None
            else:
                rank += 1
                evaluation["rank"] = rank
        return evaluations
