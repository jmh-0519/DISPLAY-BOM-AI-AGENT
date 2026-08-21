import pytest

from services.supply_evaluation_service import SupplyEvaluationService


class Repository:
    def get_supplier_options(self, item, as_of):
        return [
            {"supplier_item_id": 1, "supplier_code": "S1", "unit_price": 90,
             "lead_time_days": 10, "quality_grade": "A", "stability_score": 95,
             "primary_yn": "N", "supply_status": "AVAILABLE"},
            {"supplier_item_id": 2, "supplier_code": "S2", "unit_price": None,
             "lead_time_days": None, "quality_grade": "A", "stability_score": None,
             "primary_yn": "Y", "supply_status": "AVAILABLE"},
            {"supplier_item_id": 3, "supplier_code": "S3", "unit_price": 80,
             "lead_time_days": 5, "quality_grade": "S", "stability_score": 99,
             "primary_yn": "N", "supply_status": "STOPPED"},
        ]

    def get_production_demand(self, version, as_of):
        return 120.0

    def get_inventory(self, item):
        return [
            {"on_hand_quantity": 100, "reserved_quantity": 10, "hold_quantity": 5,
             "safety_stock": 15, "incoming_quantity": 20, "incoming_date": "2026-08-15"},
            {"on_hand_quantity": 40, "reserved_quantity": 0, "hold_quantity": 0,
             "safety_stock": 10, "incoming_quantity": 50, "incoming_date": "2026-09-01"},
        ]


def test_supplier_pass_conditional_fail_and_recommendation():
    result = SupplyEvaluationService(Repository()).recommend_supplier("MAT", "2026-08-14")
    assert [row["status"] for row in result["options"]] == ["PASS", "CONDITIONAL", "FAIL"]
    assert result["recommended"]["supplier_code"] == "S1"
    assert result["options"][1]["missing_data"] == [
        "unit_price", "lead_time_days", "stability_score",
    ]


def test_requested_quantity_overrides_plan_but_keeps_comparison():
    service = SupplyEvaluationService(Repository())
    result = service.resolve_demand(
        version_code="FA", as_of_date="2026-08-14", requested_quantity=80,
    )
    assert result["quantity"] == 80.0
    assert result["source"] == "USER"
    assert result["production_plan_quantity"] == 120.0
    plan = service.resolve_demand(
        version_code="FA", as_of_date="2026-08-14", requested_quantity=None,
    )
    assert plan["quantity"] == 120.0
    assert plan["source"] == "PRODUCTION_PLAN"
    assert plan["production_plan_quantity"] == 120.0
    with pytest.raises(ValueError):
        service.resolve_demand(version_code="FA", as_of_date="2026-08-14", requested_quantity=0)


def test_location_inventory_uses_only_incoming_before_effective_date():
    service = SupplyEvaluationService(Repository())
    sufficient = service.evaluate_inventory(
        item_code="MAT", demand_quantity=120, effective_date="2026-08-20",
    )
    assert sufficient["available_quantity"] == 120
    assert sufficient["status"] == "PASS"
    assert sufficient["calculation"]["net_current_available"] == 100
    assert sufficient["calculation"]["incoming_included_total"] == 20
    assert sufficient["calculation"]["incoming_excluded_total"] == 50
    assert len(sufficient["location_breakdown"]) == 2
    assert sufficient["location_breakdown"][0]["incoming_included"] is True
    assert sufficient["location_breakdown"][1]["incoming_included"] is False
    shortage = service.evaluate_inventory(
        item_code="MAT", demand_quantity=121, effective_date="2026-08-20",
    )
    assert shortage["status"] == "FAIL"
    assert shortage["shortage_quantity"] == 1


class MissingPlanRepository(Repository):
    def get_production_demand(self, version, as_of):
        return None


def test_missing_production_plan_and_demand_is_conditional():
    service = SupplyEvaluationService(MissingPlanRepository())
    demand = service.resolve_demand(
        version_code="FA", as_of_date="2026-08-14", requested_quantity=None,
    )
    inventory = service.evaluate_inventory(
        item_code="MAT", demand_quantity=demand["quantity"], effective_date="2026-08-20",
    )
    assert demand["source"] == "UNAVAILABLE"
    assert inventory["status"] == "CONDITIONAL"
