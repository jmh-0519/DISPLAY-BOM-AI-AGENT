from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

from agents.capability_requirement_resolver import DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
from agents.selective_planner import DEFAULT_SELECTIVE_PLANNER
from evaluation.dataset import FINAL02_DATASET_PATH, dataset_summary, load_evaluation_cases
from evaluation.observation import ROUTE_TO_EXECUTION_PATH


FOUNDATION_SCHEMA_VERSION = "1.0"
DEFAULT_PLANNER_CASES = Path(__file__).resolve().parent / "planning" / "selective_planner_eval_cases.json"
REQUIRED_ROUTE_MAPPINGS = {
    "fast_chat": "FAST_PATH",
    "fast_bom_read": "FAST_PATH",
    "fast_where_used": "FAST_PATH",
    "fast_current_bom_quantity": "FAST_PATH",
    "fast_knowledge": "KNOWLEDGE_PATH",
    "fast_text_to_sql": "TEXT_TO_SQL_PATH",
    "composition_plan": "READ_ONLY_COMPOSITION",
    "workflow_composition_plan": "WORKFLOW_COMPOSITION",
    "scope_conflict": "SCOPE_CONFLICT",
    "macro_analyze": "DETERMINISTIC_MACRO",
    "agent": "AGENT_PATH",
}
DEFAULT_VALIDATORS = (
    "scripts.validate_runtime_composition",
    "scripts.validate_workflow_runtime_composition",
    "scripts.validate_workflow_cost_evidence_runtime",
    "scripts.validate_context_workflow_scope_conflict",
    "scripts.validate_generalized_workflow_target_composition",
    "scripts.validate_final_01_context_ontology",
)


def evaluate_planner_cases(path: str | Path = DEFAULT_PLANNER_CASES) -> dict[str, Any]:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in raw.get("cases") or []:
        query = str(case.get("query") or "")
        requirement = DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER.resolve(query)
        plan = DEFAULT_SELECTIVE_PLANNER.plan_if_needed(query, requirement=requirement)
        actual_caps = list(requirement.capability_names)
        actual_order = [step.capability.value for step in plan.steps] if plan else []
        actual_planned = plan is not None
        authority_safe = bool(plan is None or (
            not plan.execution_enabled and not plan.write_authority_granted
        ))
        passed = (
            actual_caps == list(case.get("caps") or [])
            and actual_planned is bool(case.get("planned"))
            and actual_order == list(case.get("order") or [])
            and authority_safe
        )
        results.append({
            "id": case.get("id"),
            "passed": passed,
            "expected_capabilities": list(case.get("caps") or []),
            "actual_capabilities": actual_caps,
            "expected_planned": bool(case.get("planned")),
            "actual_planned": actual_planned,
            "expected_order": list(case.get("order") or []),
            "actual_order": actual_order,
            "authority_safe": authority_safe,
        })
    passed_count = sum(bool(row["passed"]) for row in results)
    count = len(results)
    return {
        "case_count": count,
        "passed_count": passed_count,
        "failed_count": count - passed_count,
        "accuracy_pct": round(passed_count / count * 100.0, 2) if count else 0.0,
        "passed": bool(count and passed_count == count),
        "results": results,
    }


def evaluate_route_mapping() -> dict[str, Any]:
    mismatches = {
        route: {
            "expected": expected,
            "actual": ROUTE_TO_EXECUTION_PATH.get(route),
        }
        for route, expected in REQUIRED_ROUTE_MAPPINGS.items()
        if ROUTE_TO_EXECUTION_PATH.get(route) != expected
    }
    return {
        "required_count": len(REQUIRED_ROUTE_MAPPINGS),
        "mapped_count": len(REQUIRED_ROUTE_MAPPINGS) - len(mismatches),
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def run_validator_commands(
    *,
    project_root: str | Path,
    modules: Iterable[str] = DEFAULT_VALIDATORS,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    rows: list[dict[str, Any]] = []
    for module in modules:
        completed = subprocess.run(
            [sys.executable, "-m", str(module)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        output = completed.stdout or ""
        rows.append({
            "module": str(module),
            "passed": completed.returncode == 0,
            "returncode": completed.returncode,
            "output_tail": "\n".join(output.splitlines()[-40:]),
        })
    return {
        "count": len(rows),
        "passed_count": sum(bool(row["passed"]) for row in rows),
        "failed_count": sum(not bool(row["passed"]) for row in rows),
        "passed": all(bool(row["passed"]) for row in rows),
        "results": rows,
    }


def evaluate_foundation(
    *,
    project_root: str | Path,
    dataset_path: str | Path = FINAL02_DATASET_PATH,
    run_validators: bool = True,
) -> dict[str, Any]:
    cases = load_evaluation_cases(dataset_path)
    summary = dataset_summary(cases)
    paths = summary.get("by_execution_path") or {}
    required_paths = (
        "FAST_PATH",
        "DETERMINISTIC_MACRO",
        "AGENT_PATH",
        "KNOWLEDGE_PATH",
        "TEXT_TO_SQL_PATH",
        "READ_ONLY_COMPOSITION",
        "WORKFLOW_COMPOSITION",
        "SCOPE_CONFLICT",
    )
    path_coverage = {
        name: int(paths.get(name) or 0)
        for name in required_paths
    }
    dataset_pass = (
        summary["case_count"] >= 55
        and summary["turn_count"] >= 65
        and all(count >= 1 for count in path_coverage.values())
    )

    planner = evaluate_planner_cases()
    from evaluation.context.context_eval_runner import run_evaluation as run_context_evaluation
    context = run_context_evaluation()
    route_mapping = evaluate_route_mapping()
    validators = (
        run_validator_commands(project_root=project_root)
        if run_validators
        else {"count": 0, "passed_count": 0, "failed_count": 0, "passed": True, "results": []}
    )
    passed = bool(
        dataset_pass
        and planner.get("passed")
        and context.get("status") == "PASS"
        and route_mapping.get("passed")
        and validators.get("passed")
    )
    return {
        "schema_version": FOUNDATION_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "FINAL-02",
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "dataset": {
            **summary,
            "required_execution_path_coverage": path_coverage,
            "passed": dataset_pass,
        },
        "planner": planner,
        "context": context,
        "route_mapping": route_mapping,
        "validators": validators,
        "authority": {
            "request_creation_granted": False,
            "approval_granted": False,
            "production_bom_write_granted": False,
        },
    }


def write_foundation_report(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_PLANNER_CASES",
    "DEFAULT_VALIDATORS",
    "FOUNDATION_SCHEMA_VERSION",
    "REQUIRED_ROUTE_MAPPINGS",
    "evaluate_foundation",
    "evaluate_planner_cases",
    "evaluate_route_mapping",
    "run_validator_commands",
    "write_foundation_report",
]
