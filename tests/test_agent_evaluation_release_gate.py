from evaluation.release_gate import evaluate_release_gate, render_release_markdown


def _accuracy(run_id="RUN-1", value=100.0):
    return {
        "run_id": run_id,
        "complete": True,
        "expected_turn_count": 58,
        "metrics": {
            name: {"accuracy": value}
            for name in ("intent", "route", "tool_selection", "tool_arguments")
        },
    }


def _performance(run_id="RUN-1", p95=4100.0):
    return {
        "run_id": run_id,
        "complete": True,
        "latency_ms": {
            "avg": 1200.0,
            "median": 100.0,
            "p95": p95,
            "max": 5100.0,
            "within_target_rate_pct": 98.28,
        },
        "llm_efficiency": {
            "total_calls": 29,
            "zero_llm_rate_pct": 55.17,
            "total_tokens": 134812,
        },
    }


def _safety(run_id="RUN-1", failed=0):
    return {
        "run_id": run_id,
        "complete": True,
        "evidence_complete": True,
        "safety_assertion_count": 143,
        "passed_assertion_count": 143 - failed,
        "failed_assertion_count": failed,
    }


def test_release_gate_passes_all_current_contracts():
    report = evaluate_release_gate(
        _accuracy(), _performance(), _safety(),
        tests={"passed": True, "returncode": 0, "command": "pytest", "detail": None},
    )
    assert report["passed"] is True
    assert report["status"] == "PASS"
    assert report["failed_checks"] == []
    assert report["run_id"] == "RUN-1"


def test_release_gate_rejects_stale_mixed_observation_runs():
    report = evaluate_release_gate(_accuracy("RUN-2"), _performance("RUN-1"), _safety("RUN-2"))
    assert report["passed"] is False
    assert "SAME_OBSERVATION_RUN" in report["failed_checks"]


def test_release_gate_rejects_accuracy_below_contract():
    report = evaluate_release_gate(_accuracy(value=99.0), _performance(), _safety())
    assert report["passed"] is False
    assert "ACCURACY_INTENT" in report["failed_checks"]


def test_release_gate_rejects_p95_over_five_seconds():
    report = evaluate_release_gate(_accuracy(), _performance(p95=5000.01), _safety())
    assert report["passed"] is False
    assert "P95_LATENCY" in report["failed_checks"]


def test_release_gate_rejects_any_safety_violation():
    report = evaluate_release_gate(_accuracy(), _performance(), _safety(failed=1))
    assert report["passed"] is False
    assert "SAFETY_ASSERTIONS" in report["failed_checks"]


def test_release_gate_rejects_failed_full_regression_when_supplied():
    report = evaluate_release_gate(
        _accuracy(), _performance(), _safety(),
        tests={"passed": False, "returncode": 1, "command": "pytest", "detail": "failed"},
    )
    assert report["passed"] is False
    assert "FULL_REGRESSION" in report["failed_checks"]


def test_markdown_states_dataset_scope_and_p95_policy():
    report = evaluate_release_gate(_accuracy(), _performance(), _safety())
    markdown = render_release_markdown(report)
    assert "Ground Truth dataset" in markdown
    assert "P95 latency <= 5 seconds" in markdown
    assert "universal real-world accuracy" in markdown
