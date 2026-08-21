from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models.design_change import EvaluationStatus, RuleResult


class RuleEngine:
    """Deterministic Phase3 rule and attribute evaluator."""

    @staticmethod
    def grade(score: float) -> str:
        if score >= 90:
            return "S"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        return "C"

    @staticmethod
    def _compare(actual: Any, operator: str, expected: str | None) -> bool:
        if operator == "PRESENT":
            return actual is not None and str(actual).strip() != ""
        if operator == "IN":
            return str(actual) in {value.strip() for value in str(expected or "").split(",")}
        if operator in {"GT", "GE", "LT", "LE"}:
            try:
                left, right = float(actual), float(expected)
            except (TypeError, ValueError):
                return False
            return {
                "GT": left > right, "GE": left >= right,
                "LT": left < right, "LE": left <= right,
            }[operator]
        if operator == "EQ":
            return str(actual).upper() == str(expected).upper()
        if operator == "NE":
            return str(actual).upper() != str(expected).upper()
        raise ValueError(f"Unsupported rule operator: {operator}")

    @staticmethod
    def _condition_reason(*, status: str, attribute: str, actual: Any,
                          operator: str, expected: Any) -> str:
        if status == "PASS":
            return f"{attribute} 실제값 {actual}이(가) 조건 {operator} {expected}을 충족합니다."
        if actual is None:
            return f"{attribute} 값이 없어 조건 {operator} {expected}을 검증할 수 없습니다."
        return f"{attribute} 실제값 {actual}이(가) 조건 {operator} {expected}을 충족하지 못합니다."

    def evaluate_rules(self, attributes: dict[str, Any], rules: list[dict]) -> dict:
        results: list[RuleResult] = []
        snapshots: list[dict] = []
        for rule in rules:
            condition_statuses: list[EvaluationStatus] = []
            condition_scores: list[float] = []
            evidence = []
            for seq, condition in enumerate(rule.get("conditions", []), 1):
                name = condition["attribute_name"]
                actual = attributes.get(name)
                condition_score = float(condition.get("score") or 0.0)
                if actual is None:
                    status = EvaluationStatus(condition["missing_result"])
                    score = 0.0
                elif self._compare(actual, condition["operator"], condition.get("expected_value")):
                    status = EvaluationStatus.PASS
                    score = condition_score
                else:
                    status = EvaluationStatus(condition["fail_result"])
                    score = 0.0
                condition_statuses.append(status)
                condition_scores.append(score)
                evidence.append({
                    "condition_seq": int(condition.get("condition_seq") or seq),
                    "attribute": name,
                    "present": actual is not None,
                    "actual_value": actual,
                    "operator": condition["operator"],
                    "expected_value": condition.get("expected_value"),
                    "missing_result": condition["missing_result"],
                    "fail_result": condition["fail_result"],
                    "condition_score": condition_score,
                    "awarded_score": score,
                    "status": status.value,
                    "reason": self._condition_reason(
                        status=status.value,
                        attribute=name,
                        actual=actual,
                        operator=condition["operator"],
                        expected=condition.get("expected_value"),
                    ),
                })

            if EvaluationStatus.FAIL in condition_statuses:
                status = EvaluationStatus.FAIL
            elif EvaluationStatus.CONDITIONAL in condition_statuses:
                status = EvaluationStatus.CONDITIONAL
            else:
                status = EvaluationStatus.PASS
            raw_score = sum(condition_scores) / len(condition_scores) if condition_scores else 0.0
            result = RuleResult(
                rule_id=rule["rule_id"], revision_no=int(rule["revision_no"]),
                status=status, raw_score=raw_score, weight=float(rule["weight"]),
                evidence={
                    "conditions": evidence,
                    "required": rule["required_yn"] == "Y",
                    "rule_name": rule.get("rule_name"),
                    "rule_description": rule.get("description"),
                    "change_reason": rule.get("change_reason"),
                    "evaluation_item": rule.get("evaluation_item"),
                },
            )
            results.append(result)
            snapshots.append({
                "rule_id": rule["rule_id"],
                "rule_name": rule.get("rule_name"),
                "description": rule.get("description"),
                "revision_no": int(rule["revision_no"]),
                "change_reason": rule.get("change_reason"),
                "target_type": rule.get("target_type"),
                "evaluation_item": rule.get("evaluation_item"),
                "required_yn": rule["required_yn"],
                "weight": float(rule["weight"]),
                "conditions": rule.get("conditions", []),
            })

        required_failure = any(
            result.status == EvaluationStatus.FAIL and result.evidence["required"]
            for result in results
        )
        any_failure = any(result.status == EvaluationStatus.FAIL for result in results)
        any_conditional = any(result.status == EvaluationStatus.CONDITIONAL for result in results)
        status = (
            EvaluationStatus.FAIL if required_failure or any_failure
            else EvaluationStatus.CONDITIONAL if any_conditional
            else EvaluationStatus.PASS
        )
        weight_total = sum(result.weight for result in results)
        score = (
            sum(result.weighted_score for result in results) / weight_total
            if weight_total else 0.0
        )
        return {
            "status": status.value,
            "total_score": round(score, 2),
            "grade": self.grade(score),
            "rule_results": [asdict(result) for result in results],
            "rule_snapshots": snapshots,
        }

    def evaluate_attributes(
        self,
        source: dict[str, Any],
        candidate: dict[str, Any],
        evaluation_items: list[str],
    ) -> dict:
        if not evaluation_items:
            return {
                "status": "CONDITIONAL", "total_score": 0.0, "grade": "C",
                "missing_data": ["evaluation_items"], "attribute_results": [],
            }
        results = []
        missing = []
        for name in evaluation_items:
            source_value = source.get(name)
            candidate_value = candidate.get(name)
            if source_value is None or candidate_value is None:
                missing.append(name)
                missing_side = (
                    "SOURCE_AND_CANDIDATE" if source_value is None and candidate_value is None
                    else "SOURCE" if source_value is None else "CANDIDATE"
                )
                results.append({
                    "attribute": name,
                    "source_value": source_value,
                    "candidate_value": candidate_value,
                    "expected_value": source_value,
                    "comparison": "EQ",
                    "matched": None,
                    "present": False,
                    "missing_side": missing_side,
                    "status": "CONDITIONAL",
                    "reason": f"{name} 비교에 필요한 값이 부족합니다 ({missing_side}).",
                })
            else:
                matched = str(source_value).upper() == str(candidate_value).upper()
                status = "PASS" if matched else "FAIL"
                results.append({
                    "attribute": name,
                    "source_value": source_value,
                    "candidate_value": candidate_value,
                    "expected_value": source_value,
                    "comparison": "EQ",
                    "matched": matched,
                    "present": True,
                    "missing_side": None,
                    "status": status,
                    "reason": (
                        f"{name} 값이 동일합니다: {source_value}"
                        if matched
                        else f"{name} 값이 다릅니다: {source_value} → {candidate_value}"
                    ),
                })
        if any(row["status"] == "FAIL" for row in results):
            status = "FAIL"
        elif missing:
            status = "CONDITIONAL"
        else:
            status = "PASS"
        score = 100 * sum(row["status"] == "PASS" for row in results) / len(results)
        return {
            "status": status, "total_score": round(score, 2), "grade": self.grade(score),
            "missing_data": missing, "attribute_results": results,
        }
