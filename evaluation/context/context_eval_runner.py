from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from langchain_core.messages import HumanMessage

from agents.bom_agent_node import BomAgentNode
from agents.bom_graph_gateway import BomGraphGateway
from agents.design_change_workflow_state import create_initial_design_change_state
from agents.domain_intent_router import DEFAULT_DOMAIN_INTENT_ROUTER


DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "context_eval_cases.json"


def load_cases(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_CASES_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _workflow(value: dict[str, Any] | None) -> dict[str, Any]:
    base = create_initial_design_change_state()
    if value:
        base.update(value)
    return base


def _projection_for_case(case: dict[str, Any]) -> str:
    node = BomAgentNode(Mock(), Mock(), "context evaluation")
    query = str(case["query"])
    workflow = _workflow(case.get("workflow"))
    step = str(workflow.get("current_step") or "NOT_STARTED").upper()
    follow_up_intent = case.get("follow_up_intent")
    decision = DEFAULT_DOMAIN_INTENT_ROUTER.route(
        query,
        workflow_active=(
            step in BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
            and step not in {"APPLIED", "BLOCKED", "REPORT_COMPLETED"}
        ),
        workflow_state=workflow,
    )
    result = node._build_llm_context_projection(
        messages=[HumanMessage(content=query)],
        raw_user_query=query,
        state={
            "active_bom_context": case.get("active_bom"),
            "design_change": workflow,
        },
        workflow_state=workflow,
        routing_decision=decision,
        routing_step=step,
        follow_up_intent=follow_up_intent,
        design_change_mode=bool(
            decision.design_change_mode or follow_up_intent
        ),
        product_cost_scan_intent=decision.product_cost_scan,
    )
    return result.text


def _evaluate_gate_case(case: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    if "expected_route" in case:
        route = BomGraphGateway(
            design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
        ).route({
            "messages": [HumanMessage(content=str(case["query"]))],
            "user_query": str(case["query"]),
            "design_change": _workflow(case.get("workflow")),
            "active_bom_context": case.get("active_bom"),
        })
        if route != case["expected_route"]:
            failures.append(
                f"route expected={case['expected_route']} actual={route}"
            )

    needs_projection = any(
        key in case
        for key in (
            "projection_contains",
            "projection_excludes",
            "projection_must_be_empty",
            "max_projection_chars",
        )
    )
    projection = _projection_for_case(case) if needs_projection else ""

    if case.get("projection_must_be_empty") and projection:
        failures.append("projection expected empty")

    for value in case.get("projection_contains", []):
        if value not in projection:
            failures.append(f"projection missing: {value}")

    for value in case.get("projection_excludes", []):
        if value in projection:
            failures.append(f"projection must exclude: {value}")

    maximum = case.get("max_projection_chars")
    if isinstance(maximum, int) and len(projection) > maximum:
        failures.append(
            f"projection chars expected<={maximum} actual={len(projection)}"
        )

    return {
        "id": case["id"],
        "category": case["category"],
        "passed": not failures,
        "failures": failures,
        "projection_chars": len(projection),
    }


def _diagnose_case(case: dict[str, Any]) -> dict[str, Any]:
    gateway = BomGraphGateway(
        design_change_active_steps=BomAgentNode.DESIGN_CHANGE_ACTIVE_STEPS
    )
    state = {
        "messages": [HumanMessage(content=str(case["query"]))],
        "user_query": str(case["query"]),
        "design_change": _workflow(case.get("workflow")),
        "active_bom_context": case.get("active_bom"),
    }
    actual_route = gateway.route(state)
    return {
        "id": case["id"],
        "category": case["category"],
        "actual_route": actual_route,
        "required_capabilities": case.get("required_capabilities", []),
        "preferred_future_route": case.get("preferred_future_route"),
        "single_route_claimed": actual_route != "agent",
        "diagnostic_only": True,
    }


def run_evaluation(path: str | Path | None = None) -> dict[str, Any]:
    cases = load_cases(path)
    gate_results = [
        _evaluate_gate_case(case)
        for case in cases.get("gate_cases", [])
    ]
    diagnostics = [
        _diagnose_case(case)
        for case in cases.get("diagnostic_cases", [])
    ]
    failed = [row for row in gate_results if not row["passed"]]

    category_counts: dict[str, int] = {}
    for row in gate_results:
        category = str(row["category"])
        category_counts[category] = category_counts.get(category, 0) + 1

    return {
        "status": "PASS" if not failed else "FAIL",
        "gate_case_count": len(gate_results),
        "gate_passed": len(gate_results) - len(failed),
        "gate_failed": len(failed),
        "category_counts": category_counts,
        "gate_results": gate_results,
        "diagnostics": diagnostics,
    }


def print_report(report: dict[str, Any]) -> None:
    print("CTX-04 Context-aware Evaluation " + str(report["status"]))
    print(f"gate_case_count={report['gate_case_count']}")
    print(f"gate_passed={report['gate_passed']}")
    print(f"gate_failed={report['gate_failed']}")

    for row in report["gate_results"]:
        if row["passed"]:
            continue
        print(
            f"FAIL {row['id']} {row['category']}: "
            + "; ".join(row["failures"])
        )

    print("cross_capability_diagnostics:")
    for row in report["diagnostics"]:
        required = ",".join(row["required_capabilities"])
        print(
            f"- {row['id']} route={row['actual_route']} "
            f"required={required} "
            f"single_route_claimed={row['single_route_claimed']}"
        )


__all__ = [
    "DEFAULT_CASES_PATH",
    "load_cases",
    "print_report",
    "run_evaluation",
]
