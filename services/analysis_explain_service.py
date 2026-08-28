from __future__ import annotations

from collections import Counter
from typing import Any


class DesignChangeAnalysisExplainService:
    """Read-only Design Change analysis explanation and candidate comparison service.

    STEP32 keeps the *persisted* evidence as the source of truth. The service may
    enrich that evidence with item master descriptions, but it never recomputes a
    candidate decision or changes workflow state.
    """

    COMMERCIAL_TOKENS = (
        "status", "cost", "price", "quality", "lead", "inventory",
        "stock", "quantity", "supplier", "active_yn", "usage_type",
    )

    def __init__(self, repository) -> None:
        self.repository = repository

    def _item_summary(self, item_code: str | None, as_of_date: str) -> dict:
        if not item_code:
            return {}
        item = self.repository.get_item(item_code)
        if not item:
            return {}
        profile = self.repository.get_item_profile(item_code, as_of_date)
        return {
            "item_code": item_code,
            "item_type": item.get("item_type"),
            "item_name": item.get("item_name"),
            "description": item.get("description") or profile.get("specification"),
            "profile": profile,
        }

    @classmethod
    def _functional_profile(cls, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in profile.items()
            if value not in {None, ""}
            and not any(token in key.lower() for token in cls.COMMERCIAL_TOKENS)
        }

    @staticmethod
    def _status_counts(rows: list[dict]) -> dict[str, int]:
        return {
            status: sum(row.get("final_status") == status for row in rows)
            for status in ("PASS", "CONDITIONAL", "FAIL")
        }

    @staticmethod
    def _inventory_reason(inventory: dict) -> list[str]:
        status = inventory.get("status")
        if not inventory:
            return ["재고 평가 결과가 저장되어 있지 않습니다."]
        bom_quantity = inventory.get("demand_quantity")
        if status == "CONDITIONAL":
            return [
                "BOM QUANTITY 기준 재고 판정에 필요한 재고/Location 기준정보가 일부 부족하여 "
                "CONDITIONAL입니다."
            ]
        if status == "FAIL":
            shortage = inventory.get("shortage_quantity")
            available = inventory.get("available_quantity")
            return [
                f"BOM 수량 {bom_quantity}, 가용재고 {available}, 부족수량 {shortage}로 "
                "현재 재고가 BOM 수량을 충족하지 못합니다."
            ]
        if status == "PASS":
            return [
                f"BOM 수량 {bom_quantity}, 가용재고 {inventory.get('available_quantity')}로 "
                "재고 조건을 충족합니다."
            ]
        return ["재고 평가 상태를 확인할 수 없습니다."]

    def _technical_checks(self, detail: dict, request: dict) -> list[dict]:
        checks: list[dict] = []
        candidate_profile = self.repository.get_item_profile(
            detail["candidate_item_code"], request["as_of_date"]
        )
        source_profile = self.repository.get_item_profile(
            detail.get("old_item_code"), request["as_of_date"]
        ) if detail.get("old_item_code") else {}

        for rule in detail.get("rule_results") or []:
            snapshot = rule.get("rule_snapshot") or {}
            snapshot_conditions = {
                value.get("attribute_name"): value
                for value in snapshot.get("conditions") or []
            }
            rule_evidence = rule.get("evidence") or {}
            for evidence in rule_evidence.get("conditions") or []:
                attribute = evidence.get("attribute")
                condition = snapshot_conditions.get(attribute) or {}
                actual = evidence.get("actual_value")
                if actual is None and attribute:
                    actual = candidate_profile.get(attribute)
                checks.append({
                    "evaluation_mode": "RULE",
                    "rule_id": rule.get("rule_id"),
                    "rule_name": rule_evidence.get("rule_name") or snapshot.get("rule_name"),
                    "rule_description": (
                        rule_evidence.get("rule_description") or snapshot.get("description")
                    ),
                    "rule_revision": rule.get("rule_revision"),
                    "change_reason": rule_evidence.get("change_reason") or snapshot.get("change_reason"),
                    "evaluation_item": rule_evidence.get("evaluation_item") or snapshot.get("evaluation_item"),
                    "required": bool(rule_evidence.get("required")),
                    "condition_seq": evidence.get("condition_seq"),
                    "attribute": attribute,
                    "source_value": source_profile.get(attribute),
                    "candidate_value": actual,
                    "operator": evidence.get("operator") or condition.get("operator"),
                    "expected_value": (
                        evidence.get("expected_value")
                        if "expected_value" in evidence
                        else condition.get("expected_value")
                    ),
                    "condition_score": evidence.get("condition_score"),
                    "awarded_score": evidence.get("awarded_score"),
                    "status": evidence.get("status"),
                    "present": evidence.get("present"),
                    "reason": evidence.get("reason"),
                })

        for value in detail.get("attribute_results") or []:
            attribute = value.get("attribute")
            source_value = (
                value.get("source_value")
                if "source_value" in value
                else source_profile.get(attribute)
            )
            candidate_value = (
                value.get("candidate_value")
                if "candidate_value" in value
                else candidate_profile.get(attribute)
            )
            checks.append({
                "evaluation_mode": "ATTRIBUTE",
                "rule_id": None,
                "rule_name": None,
                "rule_description": None,
                "rule_revision": None,
                "change_reason": None,
                "evaluation_item": None,
                "required": True,
                "condition_seq": None,
                "attribute": attribute,
                "source_value": source_value,
                "candidate_value": candidate_value,
                "operator": value.get("comparison") or "EQ",
                "expected_value": value.get("expected_value", source_value),
                "condition_score": None,
                "awarded_score": None,
                "status": value.get("status"),
                "present": value.get("present", value.get("status") != "CONDITIONAL"),
                "missing_side": value.get("missing_side"),
                "reason": value.get("reason"),
            })
        return checks

    @staticmethod
    def _technical_explanation(checks: list[dict], final_status: str) -> list[str]:
        failed = [row for row in checks if row.get("status") == "FAIL"]
        conditional = [row for row in checks if row.get("status") == "CONDITIONAL"]
        if failed:
            values = []
            for row in failed[:8]:
                if row.get("reason"):
                    values.append(str(row["reason"]))
                elif row.get("evaluation_mode") == "ATTRIBUTE":
                    values.append(
                        f"{row.get('attribute')}: {row.get('source_value')} → "
                        f"{row.get('candidate_value')} 불일치"
                    )
                else:
                    values.append(
                        f"{row.get('attribute')}: 실제값 {row.get('candidate_value')} / "
                        f"조건 {row.get('operator')} {row.get('expected_value')}"
                    )
            return values
        if conditional:
            return [
                str(row.get("reason") or f"{row.get('attribute')}: 평가 데이터 부족")
                for row in conditional[:8]
            ]
        if checks:
            return ["평가된 기술/Spec 조건을 모두 충족했습니다."]
        if final_status in {"FAIL", "CONDITIONAL"}:
            return ["저장된 기술 평가 세부 근거가 부족합니다."]
        return ["기술 평가 세부 조건이 별도로 저장되어 있지 않습니다."]

    @staticmethod
    def _missing_requirements(checks: list[dict], inventory: dict,
                              supplier_evaluation: dict) -> list[dict]:
        requirements: list[dict] = []
        for row in checks:
            if row.get("status") != "CONDITIONAL":
                continue
            attribute = row.get("attribute")
            missing_side = row.get("missing_side")
            if missing_side == "SOURCE":
                hint = f"기존 품목의 {attribute} 값을 등록한 뒤 재검증하세요."
            elif missing_side == "CANDIDATE":
                hint = f"후보 품목의 {attribute} 값을 등록한 뒤 재검증하세요."
            else:
                hint = f"{attribute} 평가에 필요한 값을 보완한 뒤 재검증하세요."
            requirements.append({
                "category": "TECHNICAL",
                "field": attribute,
                "reason": row.get("reason") or "기술 평가 데이터 부족",
                "resolution_hint": hint,
            })
        for field in inventory.get("missing_data") or []:
            requirements.append({
                "category": "INVENTORY",
                "field": field,
                "reason": "재고 판정에 필요한 수요 데이터가 부족합니다.",
                "resolution_hint": inventory.get("resolution_hint") or (
                    "BOM QUANTITY와 재고/Location 기준정보를 확인하세요."
                ),
            })
        recommended = (supplier_evaluation or {}).get("recommended") or {}
        for field in recommended.get("missing_data") or (supplier_evaluation or {}).get("missing_data") or []:
            hint = (
                "후보 품목에 유효한 공급사와 구매조건을 등록한 뒤 재평가하세요."
                if field == "supplier_options"
                else f"공급사 {field} 데이터를 등록한 뒤 재평가하세요."
            )
            requirements.append({
                "category": "SUPPLIER",
                "field": field,
                "reason": "추천 공급사 평가 데이터가 부족합니다.",
                "resolution_hint": hint,
            })
        unique = {}
        for row in requirements:
            unique[(row["category"], str(row["field"]))] = row
        return list(unique.values())

    def get_candidate_detail(
        self,
        *,
        request_id: str,
        candidate_item_code: str,
        action_id: str | None = None,
    ) -> dict:
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        detail = self.repository.get_candidate_evaluation_detail(
            request_id=request_id,
            candidate_item_code=candidate_item_code,
            action_id=action_id,
        )
        if not detail:
            raise ValueError("Candidate evaluation not found in this request")
        if detail.get("ambiguous"):
            return {
                **detail,
                "message": "동일 후보가 여러 Action에 존재합니다. action_id를 지정해 주세요.",
                "production_bom_modified": False,
            }

        action_context = next(
            (value for value in request.get("actions", [])
             if value.get("action_id") == detail.get("action_id")),
            {},
        )
        primary_reason = action_context.get("primary_reason") or {}
        secondary_reasons = action_context.get("secondary_reasons") or []
        reason_codes = [
            value.get("reason_code") for value in action_context.get("reasons", [])
            if value.get("reason_code")
        ]
        checks = self._technical_checks(detail, request)
        item = self._item_summary(candidate_item_code, request["as_of_date"])
        source = self._item_summary(detail.get("old_item_code"), request["as_of_date"])
        inventory = detail.get("inventory") or {}
        persisted_supplier = detail.get("supplier_evaluation") or {}
        supplier = persisted_supplier.get("recommended") or detail.get("recommended_supplier") or {}
        supplier_status = persisted_supplier.get("status")
        if not supplier_status:
            supplier_status = (
                "FAIL" if supplier.get("supply_status") == "STOPPED"
                else "CONDITIONAL" if (not supplier or supplier.get("supply_status") == "LIMITED")
                else "PASS"
            )
        technical_status = (
            "FAIL" if any(row.get("status") == "FAIL" for row in checks)
            else "CONDITIONAL" if any(row.get("status") == "CONDITIONAL" for row in checks)
            else "PASS" if checks else None
        )
        rule_evaluations = []
        for rule in detail.get("rule_results") or []:
            snapshot = rule.get("rule_snapshot") or {}
            evidence = rule.get("evidence") or {}
            rule_evaluations.append({
                "rule_id": rule.get("rule_id"),
                "rule_name": evidence.get("rule_name") or snapshot.get("rule_name"),
                "description": evidence.get("rule_description") or snapshot.get("description"),
                "revision": rule.get("rule_revision"),
                "change_reason": evidence.get("change_reason") or snapshot.get("change_reason"),
                "required": bool(evidence.get("required")),
                "status": rule.get("status"),
                "raw_score": rule.get("raw_score"),
                "weight": rule.get("weight"),
                "weighted_score": rule.get("weighted_score"),
            })
        missing_requirements = self._missing_requirements(
            checks, inventory, persisted_supplier
        )
        return {
            "request_id": request_id,
            "action_id": detail.get("action_id"),
            "candidate_id": detail.get("candidate_id"),
            "reason_context": {
                "primary_reason": primary_reason.get("reason_code"),
                "secondary_reasons": [
                    value.get("reason_code") for value in secondary_reasons
                    if value.get("reason_code")
                ],
                "all_reasons": reason_codes,
            },
            "source_item": source,
            "candidate_item": item,
            "final_status": detail.get("final_status"),
            "total_score": detail.get("total_score"),
            "grade": detail.get("grade"),
            "rank": detail.get("rank_no"),
            "technical_evaluation": {
                "status": technical_status,
                "checks": checks,
                "rule_evaluations": rule_evaluations,
                "explanation": self._technical_explanation(checks, detail.get("final_status")),
            },
            "inventory_evaluation": {
                **inventory,
                "demand_context": detail.get("demand_context") or {},
                "explanation": self._inventory_reason(inventory),
            },
            "supplier_evaluation": {
                "status": supplier_status,
                "supplier_item_id": supplier.get("supplier_item_id"),
                "supplier_code": supplier.get("supplier_code"),
                "supplier_name": supplier.get("supplier_name"),
                "unit_price": supplier.get("unit_price"),
                "currency_code": supplier.get("currency_code"),
                "lead_time_days": supplier.get("lead_time_days"),
                "quality_grade": supplier.get("quality_grade"),
                "stability_score": supplier.get("stability_score"),
                "supply_status": supplier.get("supply_status"),
                "score": supplier.get("score"),
                "component_scores": supplier.get("component_scores") or {},
                "weights": supplier.get("weights") or persisted_supplier.get("weights") or {},
                "reason_codes": persisted_supplier.get("reason_codes") or [],
                "weight_reason_codes": persisted_supplier.get("weight_reason_codes") or [],
                "decision_reason": (
                    supplier.get("decision_reason") or persisted_supplier.get("decision_reason")
                ),
                "missing_data": supplier.get("missing_data") or persisted_supplier.get("missing_data") or [],
                "option_count": len(persisted_supplier.get("options") or []),
                "data_available": bool(supplier),
            },
            "missing_data": detail.get("missing_data") or [],
            "missing_requirements": missing_requirements,
            "production_bom_modified": False,
        }

    def get_analysis(self, request_id: str) -> dict:
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        rows = self.repository.list_request_candidate_evaluations(request_id)
        counts = self._status_counts(rows)
        if not rows:
            search_status = "NO_CANDIDATES"
            summary = "검색된 후보가 없습니다."
        elif counts["PASS"] + counts["CONDITIONAL"] == 0:
            search_status = "NO_ELIGIBLE_CANDIDATES"
            summary = (
                f"후보는 {len(rows)}개 검색되었지만 모두 FAIL이어서 "
                "현재 선택 가능한 후보는 0개입니다."
            )
        else:
            search_status = "ELIGIBLE_CANDIDATES"
            summary = (
                f"후보 {len(rows)}개 중 PASS {counts['PASS']}개, "
                f"CONDITIONAL {counts['CONDITIONAL']}개, FAIL {counts['FAIL']}개입니다."
            )

        failure_counter: Counter[str] = Counter()
        conditional_counter: Counter[str] = Counter()
        inventory_statuses: Counter[str] = Counter()
        inventory_reason_counter: Counter[str] = Counter()
        missing_counter: Counter[str] = Counter()
        action_summaries = []
        for action in request.get("actions") or []:
            action_rows = [row for row in rows if row.get("action_id") == action["action_id"]]
            action_counts = self._status_counts(action_rows)
            source = self._item_summary(
                action.get("old_item_code") or action.get("new_item_code"),
                request["as_of_date"],
            )
            for row in action_rows:
                inventory = row.get("inventory") or {}
                inventory_statuses[str(inventory.get("status") or "UNKNOWN")] += 1
                if inventory.get("status") in {"CONDITIONAL", "FAIL"}:
                    for reason in self._inventory_reason(inventory):
                        inventory_reason_counter[reason] += 1
                detail = self.repository.get_candidate_evaluation_detail(
                    request_id=request_id,
                    candidate_item_code=row["candidate_item_code"],
                    action_id=action["action_id"],
                )
                if not detail or detail.get("ambiguous"):
                    continue
                checks = self._technical_checks(detail, request)
                for check in checks:
                    attribute = str(check.get("attribute") or "unknown")
                    if check.get("status") == "FAIL":
                        failure_counter[attribute] += 1
                    elif check.get("status") == "CONDITIONAL":
                        conditional_counter[attribute] += 1
                for requirement in self._missing_requirements(
                    checks, detail.get("inventory") or {}, detail.get("supplier_evaluation") or {}
                ):
                    missing_counter[f"{requirement['category']}:{requirement['field']}"] += 1
            action_summaries.append({
                "action_id": action["action_id"],
                "action_type": action.get("action_type"),
                "target_type": action.get("target_type"),
                "primary_reason": (action.get("primary_reason") or {}).get("reason_code"),
                "secondary_reasons": [
                    value.get("reason_code") for value in action.get("secondary_reasons", [])
                    if value.get("reason_code")
                ],
                "all_reasons": [
                    value.get("reason_code") for value in action.get("reasons", [])
                    if value.get("reason_code")
                ],
                "source_item": source,
                "candidate_count": len(action_rows),
                "status_counts": action_counts,
            })

        return {
            "request_id": request_id,
            "plant_code": request.get("plant_code"),
            "version_code": request.get("version_code"),
            "workflow_status": request.get("workflow_status"),
            "reasons": request.get("reasons") or [],
            "candidate_search_status": search_status,
            "summary": summary,
            "candidate_count": len(rows),
            "status_counts": counts,
            "top_fail_attributes": [
                {"attribute": name, "candidate_count": count}
                for name, count in failure_counter.most_common(10)
            ],
            "top_conditional_attributes": [
                {"attribute": name, "candidate_count": count}
                for name, count in conditional_counter.most_common(10)
            ],
            "inventory_status_counts": dict(inventory_statuses),
            "inventory_reasons": [
                {"reason": reason, "candidate_count": count}
                for reason, count in inventory_reason_counter.most_common(10)
            ],
            "missing_requirements": [
                {"requirement": name, "candidate_count": count}
                for name, count in missing_counter.most_common(20)
            ],
            "actions": action_summaries,
            "guidance": {
                "no_candidates_vs_no_eligible": (
                    "NO_CANDIDATES는 검색 자체가 0건이고, "
                    "NO_ELIGIBLE_CANDIDATES는 후보는 검색됐지만 모두 FAIL인 상태입니다."
                ),
                "technical_fail_overrides_supplier": True,
            },
            "production_bom_modified": False,
        }

    def compare_candidates(
        self,
        *,
        request_id: str,
        candidate_item_codes: list[str] | None = None,
        action_id: str | None = None,
        criterion: str = "SPEC_SIMILARITY",
    ) -> dict:
        request = self.repository.get_request(request_id)
        if not request:
            raise ValueError("Change request not found")
        rows = self.repository.list_request_candidate_evaluations(request_id)
        if action_id:
            rows = [row for row in rows if row.get("action_id") == action_id]
        else:
            action_ids = {row.get("action_id") for row in rows}
            if len(action_ids) > 1:
                raise ValueError("Multiple evaluated actions exist; action_id is required")
        requested = [
            str(code).strip().upper()
            for code in (candidate_item_codes or [])
            if str(code).strip()
        ]
        if requested:
            requested_set = set(requested)
            rows = [
                row for row in rows
                if str(row.get("candidate_item_code")).upper() in requested_set
            ]
        if not rows:
            raise ValueError("No candidate evaluations match the comparison request")

        normalized = str(criterion or "SPEC_SIMILARITY").strip().upper()
        aliases = {
            "SPEC": "SPEC_SIMILARITY", "SIMILARITY": "SPEC_SIMILARITY",
            "SCORE": "TOTAL_SCORE", "PRICE": "COST", "UNIT_PRICE": "COST",
            "LEAD": "LEAD_TIME", "STOCK": "INVENTORY",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"SPEC_SIMILARITY", "TOTAL_SCORE", "COST", "LEAD_TIME", "INVENTORY"}:
            raise ValueError("Unsupported comparison criterion")

        comparison_rows = []
        for row in rows:
            detail = self.get_candidate_detail(
                request_id=request_id,
                candidate_item_code=row["candidate_item_code"],
                action_id=row["action_id"],
            )
            checks = detail.get("technical_evaluation", {}).get("checks") or []
            considered = [value for value in checks if value.get("status") in {"PASS", "FAIL", "CONDITIONAL"}]
            passed = [value for value in considered if value.get("status") == "PASS"]
            spec_similarity = (
                round(len(passed) / len(considered) * 100.0, 2)
                if considered else 0.0
            )
            differences = []
            for check in considered:
                differences.append({
                    "attribute": check.get("attribute"),
                    "before": check.get("source_value"),
                    "candidate": check.get("candidate_value"),
                    "expected": check.get("expected_value"),
                    "operator": check.get("operator"),
                    "status": check.get("status"),
                    "reason": check.get("reason"),
                    "evaluation_mode": check.get("evaluation_mode"),
                })
            supplier = detail.get("supplier_evaluation") or {}
            inventory = detail.get("inventory_evaluation") or {}
            item = detail.get("candidate_item") or {}
            comparison_rows.append({
                "action_id": row["action_id"],
                "candidate_item_code": row["candidate_item_code"],
                "candidate_name": item.get("item_name"),
                "candidate_description": item.get("description"),
                "final_status": row.get("final_status"),
                "selectable": row.get("final_status") in {"PASS", "CONDITIONAL"},
                "total_score": row.get("total_score"),
                "grade": row.get("grade"),
                "spec_similarity": spec_similarity,
                "technical_status": detail.get("technical_evaluation", {}).get("status"),
                "technical_differences": differences,
                "failed_attributes": [
                    value.get("attribute") for value in differences if value.get("status") == "FAIL"
                ],
                "conditional_attributes": [
                    value.get("attribute") for value in differences if value.get("status") == "CONDITIONAL"
                ],
                "unit_price": supplier.get("unit_price"),
                "supplier_score": supplier.get("score"),
                "supplier_status": supplier.get("status"),
                "lead_time_days": supplier.get("lead_time_days"),
                "quality_grade": supplier.get("quality_grade"),
                "stability_score": supplier.get("stability_score"),
                "available_quantity": inventory.get("available_quantity"),
                "demand_quantity": inventory.get("demand_quantity"),
                "shortage_quantity": inventory.get("shortage_quantity"),
                "inventory_status": inventory.get("status"),
                "missing_requirements": detail.get("missing_requirements") or [],
            })

        def numeric(value, default):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        if normalized == "SPEC_SIMILARITY":
            key = lambda row: (
                -numeric(row.get("spec_similarity"), -1),
                -numeric(row.get("total_score"), -1), row["candidate_item_code"],
            )
        elif normalized == "TOTAL_SCORE":
            key = lambda row: (
                -numeric(row.get("total_score"), -1),
                -numeric(row.get("spec_similarity"), -1), row["candidate_item_code"],
            )
        elif normalized == "COST":
            key = lambda row: (
                numeric(row.get("unit_price"), float("inf")),
                -numeric(row.get("total_score"), -1), row["candidate_item_code"],
            )
        elif normalized == "LEAD_TIME":
            key = lambda row: (
                numeric(row.get("lead_time_days"), float("inf")),
                -numeric(row.get("total_score"), -1), row["candidate_item_code"],
            )
        else:
            key = lambda row: (
                -numeric(row.get("available_quantity"), -1),
                -numeric(row.get("total_score"), -1), row["candidate_item_code"],
            )
        comparison_rows.sort(key=key)
        for rank, row in enumerate(comparison_rows, 1):
            row["comparison_rank"] = rank

        best = comparison_rows[0]
        return {
            "request_id": request_id,
            "action_id": comparison_rows[0]["action_id"],
            "criterion": normalized,
            "candidate_count": len(comparison_rows),
            "best_candidate": best,
            "best_candidate_is_selectable": best["selectable"],
            "candidates": comparison_rows,
            "note": (
                "비교 1위가 FAIL이면 가장 가까운 후보라는 의미일 뿐, "
                "설계변경 후보로 승인할 수 있다는 의미는 아닙니다."
            ),
            "production_bom_modified": False,
        }
