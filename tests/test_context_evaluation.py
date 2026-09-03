from evaluation.context.context_eval_runner import load_cases, run_evaluation


def test_context_evaluation_catalog_has_gate_and_diagnostic_coverage():
    cases = load_cases()

    assert len(cases["gate_cases"]) >= 10
    assert len(cases["diagnostic_cases"]) >= 2

    categories = {case["category"] for case in cases["gate_cases"]}
    assert {
        "implicit_scope",
        "explicit_override",
        "workflow_followup",
        "terminal_stale_context",
        "single_capability_routing",
        "authority_safety",
        "prompt_budget",
    }.issubset(categories)


def test_context_gate_cases_pass_against_current_runtime():
    report = run_evaluation()

    assert report["status"] == "PASS", report["gate_results"]
    assert report["gate_failed"] == 0


def test_cross_capability_cases_are_diagnostic_not_gate_failures():
    report = run_evaluation()

    assert len(report["diagnostics"]) >= 2
    assert all(row["diagnostic_only"] is True for row in report["diagnostics"])
    assert all(len(row["required_capabilities"]) >= 2 for row in report["diagnostics"])
