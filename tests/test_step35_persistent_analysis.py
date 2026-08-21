from agents.design_change_workflow_state import (
    apply_phase3_tool_result,
    create_initial_design_change_state,
)


def test_revalidation_preserves_initial_analysis_snapshot_and_appends_history():
    initial_context = {
        "plant_code": "P01",
        "version_code": "MODEL-1",
        "demand_source": "UNAVAILABLE",
        "target_item": {"item_code": "OLD-1", "item_name": "SEALANT"},
    }
    initial_candidate = {
        "action_id": "A1",
        "candidate_item_code": "NEW-1",
        "status": "CONDITIONAL",
        "technical_status": "PASS",
        "total_score": 65,
        "inventory": {"status": "CONDITIONAL", "demand_source": "UNAVAILABLE"},
    }
    state = apply_phase3_tool_result(
        "analyze_design_change_candidates",
        create_initial_design_change_state(),
        {
            "analysis_id": "ANA-1",
            "request": {"plant_code": "P01"},
            "actions": [{"action_id": "A1", "action_type": "REPLACE"}],
            "candidates": [initial_candidate],
            "analysis_context": initial_context,
            "status_counts": {"PASS": 0, "CONDITIONAL": 1, "FAIL": 0},
        },
    )

    revalidated = apply_phase3_tool_result(
        "revalidate_design_change_analysis",
        state,
        {
            "request": {"plant_code": "P01", "demand_source": "USER"},
            "actions": [{"action_id": "A1", "action_type": "REPLACE"}],
            "candidates": [{
                **initial_candidate,
                "status": "FAIL",
                "total_score": 60,
                "inventory": {
                    "status": "FAIL",
                    "demand_source": "USER",
                    "demand_quantity": 2,
                    "available_quantity": 0,
                    "shortage_quantity": 2,
                },
            }],
            "analysis_context": {**initial_context, "demand_source": "USER"},
            "status_counts": {"PASS": 0, "CONDITIONAL": 0, "FAIL": 1},
            "revalidation": {
                "candidate_item_code": "NEW-1",
                "before": initial_candidate,
                "after": {
                    **initial_candidate,
                    "status": "FAIL",
                    "inventory": {
                        "status": "FAIL",
                        "demand_source": "USER",
                        "demand_quantity": 2,
                        "available_quantity": 0,
                        "shortage_quantity": 2,
                    },
                },
            },
        },
    )

    assert revalidated["analysis_initial_candidates"] == [initial_candidate]
    assert revalidated["analysis_initial_context"] == initial_context
    assert revalidated["candidates"][0]["status"] == "FAIL"
    assert len(revalidated["revalidation_history"]) == 1
    assert revalidated["revalidation_history"][0]["candidate_item_code"] == "NEW-1"
    assert revalidated["request_id"] is None
