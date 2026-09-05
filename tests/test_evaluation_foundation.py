from evaluation.foundation import (
    REQUIRED_ROUTE_MAPPINGS,
    evaluate_planner_cases,
    evaluate_route_mapping,
)


def test_route_mapping_covers_current_graph_entry_routes():
    report = evaluate_route_mapping()
    assert report["passed"] is True
    assert report["mapped_count"] == len(REQUIRED_ROUTE_MAPPINGS)


def test_selective_planner_catalog_remains_deterministic_and_authority_safe():
    report = evaluate_planner_cases()
    assert report["passed"] is True
    assert report["accuracy_pct"] == 100.0
    assert all(row["authority_safe"] for row in report["results"])
