from evaluation.context.context_eval_runner import (
    print_report,
    run_evaluation,
)


def main() -> None:
    report = run_evaluation()
    print_report(report)

    diagnostics = report["diagnostics"]
    problems = []
    for row in diagnostics:
        if not row["composition_required"]:
            problems.append(f"{row['id']}: composition_required=False")
        if not row["requirements_match"]:
            problems.append(
                f"{row['id']}: required={row['required_capabilities']} "
                f"resolved={row['resolved_capabilities']}"
            )
        if row["actual_route"] != "agent":
            problems.append(
                f"{row['id']}: route must defer to agent before PLAN-01, "
                f"actual={row['actual_route']}"
            )

    if report["status"] != "PASS" or problems:
        for value in problems:
            print(f"FAIL {value}")
        raise SystemExit(1)

    print("CTX-05 Capability Requirement validation PASS")
    print(f"composition_case_count={len(diagnostics)}")
    print("planner_enabled=NO")


if __name__ == "__main__":
    main()
