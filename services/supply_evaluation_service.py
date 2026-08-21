from __future__ import annotations


class SupplyEvaluationService:
    STATUS_ORDER = {"PASS": 0, "CONDITIONAL": 1, "FAIL": 2}

    def __init__(self, repository) -> None:
        self.repository = repository

    @staticmethod
    def evaluate_supplier(option: dict, weights: dict | None = None,
                          minimum_price: float | None = None) -> dict:
        required = ("unit_price", "lead_time_days", "quality_grade", "stability_score")
        missing = [name for name in required if option.get(name) is None]
        if option.get("supply_status") == "STOPPED":
            status = "FAIL"
        elif missing or option.get("supply_status") == "LIMITED":
            status = "CONDITIONAL"
        else:
            status = "PASS"
        lead = option.get("lead_time_days")
        stability = option.get("stability_score")
        quality_score = {"S": 100, "A": 90, "B": 75, "C": 60}.get(
            str(option.get("quality_grade") or "").upper(), 0,
        )
        lead_score = max(0, 100 - float(lead) * 2) if lead is not None else 0
        stability_score = float(stability) if stability is not None else 0
        price = option.get("unit_price")
        cost_score = (
            min(100.0, float(minimum_price) / float(price) * 100)
            if price not in {None, 0} and minimum_price is not None else 0
        )
        weights = weights or {"quality": 0.35, "lead": 0.20, "stability": 0.30, "cost": 0.15}
        components = {
            "quality": round(quality_score, 2),
            "lead": round(lead_score, 2),
            "stability": round(stability_score, 2),
            "cost": round(cost_score, 2),
        }
        score = round(sum(components[key] * float(weights[key]) for key in components), 2)
        if status == "FAIL":
            reason = "공급 상태가 STOPPED이므로 공급사 평가 FAIL입니다."
        elif status == "CONDITIONAL" and missing:
            reason = f"공급사 평가 데이터가 부족합니다: {', '.join(missing)}"
        elif status == "CONDITIONAL":
            reason = "공급 상태가 LIMITED이므로 추가 확인이 필요합니다."
        else:
            reason = "공급 상태와 필수 공급사 평가 데이터가 모두 유효합니다."
        return {
            **option,
            "status": status,
            "score": score,
            "cost_score": round(cost_score, 2),
            "component_scores": components,
            "weights": dict(weights),
            "minimum_price_reference": minimum_price,
            "missing_data": missing,
            "decision_reason": reason,
        }

    @staticmethod
    def _weights_for_reasons(reasons: set[str]) -> tuple[dict, list[str]]:
        default = {"quality": 0.35, "lead": 0.20, "stability": 0.30, "cost": 0.15}
        profiles = {
            "COST": {"quality": 0.20, "lead": 0.10, "stability": 0.20, "cost": 0.50},
            "LEAD_TIME": {"quality": 0.20, "lead": 0.50, "stability": 0.20, "cost": 0.10},
            "QUALITY": {"quality": 0.50, "lead": 0.10, "stability": 0.30, "cost": 0.10},
            "SUPPLIER_STOP": {"quality": 0.20, "lead": 0.15, "stability": 0.50, "cost": 0.15},
        }
        applied = [code for code in sorted(reasons) if code in profiles]
        if not applied:
            return default, []
        combined = {key: 0.0 for key in default}
        for code in applied:
            for key, value in profiles[code].items():
                combined[key] += value
        count = float(len(applied))
        return {key: round(value / count, 6) for key, value in combined.items()}, applied

    def recommend_supplier(self, item_code: str, as_of_date: str,
                           reasons: list[str] | None = None) -> dict:
        reasons = set(reasons or [])
        weights, applied_weight_reasons = self._weights_for_reasons(reasons)
        raw_options = self.repository.get_supplier_options(item_code, as_of_date)
        prices = [float(value["unit_price"]) for value in raw_options
                  if value.get("unit_price") not in {None, 0}]
        minimum_price = min(prices) if prices else None
        options = [
            self.evaluate_supplier(value, weights, minimum_price)
            for value in raw_options
        ]
        options.sort(key=lambda value: (
            self.STATUS_ORDER[value["status"]], -value["score"],
            -int(value.get("primary_yn") == "Y"),
            float(value["unit_price"]) if value.get("unit_price") is not None else float("inf"),
        ))
        recommended = options[0] if options else None
        return {
            "status": recommended["status"] if recommended else "CONDITIONAL",
            "recommended": recommended,
            "options": options,
            "missing_data": [] if options else ["supplier_options"],
            "weights": weights,
            "reason_codes": sorted(reasons),
            "weight_reason_codes": applied_weight_reasons,
            "decision_reason": (
                recommended.get("decision_reason") if recommended
                else "유효한 공급사 옵션이 없어 공급사 평가가 CONDITIONAL입니다."
            ),
        }

    def resolve_demand(
        self,
        *,
        version_code: str,
        as_of_date: str,
        requested_quantity: float | None,
        plant_code: str = "P01",
    ) -> dict:
        try:
            plan_quantity = self.repository.get_production_demand(
                version_code, plant_code, as_of_date
            )
        except TypeError:
            plan_quantity = self.repository.get_production_demand(version_code, as_of_date)
        if requested_quantity is not None:
            if requested_quantity <= 0:
                raise ValueError("requested_quantity must be greater than zero")
            return {
                "quantity": float(requested_quantity), "source": "USER",
                "production_plan_quantity": plan_quantity,
                "as_of_date": as_of_date,
                "plant_code": plant_code,
            }
        if plan_quantity is not None:
            return {
                "quantity": plan_quantity,
                "source": "PRODUCTION_PLAN",
                "production_plan_quantity": plan_quantity,
                "as_of_date": as_of_date,
                "plant_code": plant_code,
            }
        return {
            "quantity": None,
            "source": "UNAVAILABLE",
            "production_plan_quantity": None,
            "as_of_date": as_of_date,
            "plant_code": plant_code,
        }

    def evaluate_inventory(
        self,
        *,
        item_code: str,
        demand_quantity: float | None,
        effective_date: str,
        plant_code: str = "P01",
        demand_source: str | None = None,
        production_plan_quantity: float | None = None,
    ) -> dict:
        try:
            balances = self.repository.get_inventory(item_code, plant_code)
        except TypeError:
            balances = self.repository.get_inventory(item_code)

        location_breakdown: list[dict] = []
        available = 0.0
        on_hand_total = reserved_total = hold_total = safety_total = 0.0
        incoming_included_total = incoming_excluded_total = 0.0
        for balance in balances:
            on_hand = float(balance.get("on_hand_quantity") or 0)
            reserved = float(balance.get("reserved_quantity") or 0)
            hold = float(balance.get("hold_quantity") or 0)
            safety = float(balance.get("safety_stock") or 0)
            incoming = float(balance.get("incoming_quantity") or 0)
            current_available = max(0.0, on_hand - reserved - hold - safety)
            incoming_date = balance.get("incoming_date")
            incoming_included = bool(incoming_date and incoming_date <= effective_date)
            included_incoming = incoming if incoming_included else 0.0
            excluded_incoming = incoming - included_incoming
            effective_available = current_available + included_incoming
            available += effective_available
            on_hand_total += on_hand
            reserved_total += reserved
            hold_total += hold
            safety_total += safety
            incoming_included_total += included_incoming
            incoming_excluded_total += excluded_incoming
            location_breakdown.append({
                "plant_code": balance.get("plant_code") or plant_code,
                "warehouse_code": balance.get("warehouse_code"),
                "inventory_location_code": balance.get("inventory_location_code"),
                "on_hand_quantity": on_hand,
                "reserved_quantity": reserved,
                "hold_quantity": hold,
                "safety_stock": safety,
                "net_current_available": round(current_available, 4),
                "incoming_quantity": incoming,
                "incoming_date": incoming_date,
                "incoming_included": incoming_included,
                "included_incoming_quantity": round(included_incoming, 4),
                "excluded_incoming_quantity": round(excluded_incoming, 4),
                "effective_available_quantity": round(effective_available, 4),
            })

        if demand_quantity is None:
            status = "CONDITIONAL"
            shortage = None
            missing_data = ["demand_quantity"]
            resolution_hint = "요청수량을 입력하거나 유효한 생산계획을 등록한 뒤 재검증하세요."
        else:
            shortage = max(0.0, float(demand_quantity) - available)
            status = "PASS" if shortage == 0 else "FAIL"
            missing_data = []
            resolution_hint = None

        return {
            "status": status,
            "item_code": item_code,
            "available_quantity": round(available, 4),
            "demand_quantity": demand_quantity,
            "demand_source": demand_source,
            "production_plan_quantity": production_plan_quantity,
            "shortage_quantity": None if shortage is None else round(shortage, 4),
            "location_count": len(balances),
            "effective_date": effective_date,
            "plant_code": plant_code,
            "missing_data": missing_data,
            "resolution_hint": resolution_hint,
            "calculation": {
                "on_hand_total": round(on_hand_total, 4),
                "reserved_total": round(reserved_total, 4),
                "hold_total": round(hold_total, 4),
                "safety_stock_total": round(safety_total, 4),
                "net_current_available": round(
                    sum(row["net_current_available"] for row in location_breakdown), 4
                ),
                "incoming_included_total": round(incoming_included_total, 4),
                "incoming_excluded_total": round(incoming_excluded_total, 4),
                "available_quantity": round(available, 4),
            },
            "location_breakdown": location_breakdown,
        }
