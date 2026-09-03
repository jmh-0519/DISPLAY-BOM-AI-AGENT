from __future__ import annotations
import json
from pathlib import Path

from agents.capability_requirement_resolver import DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER
from agents.selective_planner import DEFAULT_SELECTIVE_PLANNER


def main() -> None:
    path = Path("evaluation/planning/selective_planner_eval_cases.json")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    planned = 0

    for case in catalog["cases"]:
        req = DEFAULT_CAPABILITY_REQUIREMENT_RESOLVER.resolve(case["query"])
        plan = DEFAULT_SELECTIVE_PLANNER.plan_if_needed(
            case["query"], requirement=req
        )
        actual_caps = list(req.capability_names)
        actual_order = (
            [step.capability.value for step in plan.steps]
            if plan is not None else []
        )
        actual_planned = plan is not None
        if actual_planned:
            planned += 1

        if actual_caps != case["caps"]:
            failures.append(
                f"{case['id']} capabilities expected={case['caps']} actual={actual_caps}"
            )
        if actual_planned != case["planned"]:
            failures.append(
                f"{case['id']} planned expected={case['planned']} actual={actual_planned}"
            )
        if actual_order != case["order"]:
            failures.append(
                f"{case['id']} order expected={case['order']} actual={actual_order}"
            )
        if plan is not None and (
            plan.execution_enabled or plan.write_authority_granted
        ):
            failures.append(f"{case['id']} authority guard failed")

        print(
            f"- {case['id']} planned={actual_planned} "
            f"capabilities={','.join(actual_caps)} "
            f"order={','.join(actual_order) if actual_order else 'BYPASS'}"
        )

    status = "PASS" if not failures else "FAIL"
    print(f"PLAN-01 Selective Planner Foundation {status}")
    print(f"case_count={len(catalog['cases'])}")
    print(f"passed={len(catalog['cases']) - len(failures)}")
    print(f"failed={len(failures)}")
    print(f"planned_multi_count={planned}")
    print(f"bypassed_single_count={len(catalog['cases']) - planned}")
    print("planner_llm_calls=0")
    print("runtime_execution_enabled=NO")
    print("write_authority_granted=NO")
    for failure in failures:
        print("FAIL:", failure)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
