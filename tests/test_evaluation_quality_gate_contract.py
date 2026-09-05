from evaluation.quality_gate import evaluate_quality_gate, write_quality_markdown


def _accuracy(run_id="RUN-1", value=100.0):
    return {
        "run_id": run_id,
        "complete": True,
        "expected_case_count": 56,
        "expected_turn_count": 69,
        "metrics": {name: {"accuracy": value} for name in ("intent", "route", "tool_selection", "tool_arguments")},
    }


def _performance(run_id="RUN-1", p95=4100.0):
    return {
        "run_id": run_id,
        "complete": True,
        "latency_ms": {"avg": 1200.0, "median": 100.0, "p95": p95, "max": 5100.0, "within_target_rate_pct": 98.28},
        "llm_efficiency": {"total_calls": 29, "zero_llm_rate_pct": 55.17, "total_tokens": 134812},
    }


def _safety(run_id="RUN-1", failed=0):
    return {
        "run_id": run_id,
        "complete": True,
        "evidence_complete": True,
        "safety_assertion_count": 167,
        "passed_assertion_count": 167 - failed,
        "failed_assertion_count": failed,
    }


def _foundation():
    return {
        "passed": True,
        "status": "PASS",
        "planner": {"accuracy_pct": 100.0},
        "context": {"gate_passed": 13, "gate_case_count": 13},
        "validators": {"passed_count": 6, "count": 6},
    }


def _rag():
    return {"gate_pass": True, "case_count": 56, "metrics": {"hit_rate_at_5": 1.0}}


def _t2s():
    return {"gate_pass": True, "case_count": 23, "overall_accuracy": 1.0, "status_accuracy": 1.0, "semantic_match_rate": 1.0, "unsupported_accuracy": 1.0}


def _gate(*, accuracy=None, performance=None, safety=None, tests=None):
    return evaluate_quality_gate(
        foundation=_foundation(),
        accuracy=accuracy or _accuracy(),
        performance=performance or _performance(),
        safety=safety or _safety(),
        rag=_rag(),
        text_to_sql=_t2s(),
        tests=tests,
    )


def test_quality_gate_passes_all_current_contracts():
    report = _gate(tests={"passed": True, "returncode": 0, "command": "pytest", "detail": None})
    assert report["passed"] is True
    assert report["status"] == "PASS"
    assert report["failed_checks"] == []
    assert report["run_id"] == "RUN-1"


def test_quality_gate_rejects_stale_mixed_observation_runs():
    report = _gate(accuracy=_accuracy("RUN-2"), performance=_performance("RUN-1"), safety=_safety("RUN-2"))
    assert report["passed"] is False
    assert "SAME_AGENT_OBSERVATION_RUN" in report["failed_checks"]


def test_quality_gate_rejects_accuracy_below_contract():
    report = _gate(accuracy=_accuracy(value=99.0))
    assert report["passed"] is False
    assert "AGENT_INTENT_ACCURACY" in report["failed_checks"]


def test_quality_gate_rejects_p95_over_five_seconds():
    report = _gate(performance=_performance(p95=5000.01))
    assert report["passed"] is False
    assert "P95_LATENCY" in report["failed_checks"]


def test_quality_gate_rejects_any_safety_violation():
    report = _gate(safety=_safety(failed=1))
    assert report["passed"] is False
    assert "SAFETY_ASSERTIONS" in report["failed_checks"]


def test_quality_gate_rejects_failed_full_regression_when_supplied():
    report = _gate(tests={"passed": False, "returncode": 1, "command": "pytest", "detail": "failed"})
    assert report["passed"] is False
    assert "FULL_REGRESSION" in report["failed_checks"]


def test_markdown_states_current_evaluation_metrics(tmp_path):
    report = _gate()
    target = write_quality_markdown(report, tmp_path / "report.md")
    markdown = target.read_text(encoding="utf-8")
    assert "Evaluation / Stability / Safety" in markdown
    assert "P95 latency" in markdown
    assert "Safety" in markdown
