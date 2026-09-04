from evaluation.final02_gate import evaluate_final02_gate


def _accuracy(run_id="run-1", value=100.0):
    return {
        "run_id": run_id,
        "complete": True,
        "expected_case_count": 56,
        "expected_turn_count": 69,
        "metrics": {
            name: {"accuracy": value}
            for name in ("intent", "route", "tool_selection", "tool_arguments")
        },
    }


def _performance(run_id="run-1", p95=3000.0):
    return {
        "run_id": run_id,
        "complete": True,
        "latency_ms": {"avg": 1000.0, "p95": p95, "within_target_rate_pct": 98.0},
        "llm_efficiency": {"total_calls": 10, "zero_llm_rate_pct": 80.0, "total_tokens": 10000},
    }


def _safety(run_id="run-1", failed=0):
    return {
        "run_id": run_id,
        "complete": True,
        "evidence_complete": True,
        "safety_assertion_count": 120,
        "passed_assertion_count": 120 - failed,
        "failed_assertion_count": failed,
    }


def _foundation(passed=True):
    return {
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "planner": {"accuracy_pct": 100.0},
        "context": {"gate_passed": 13, "gate_case_count": 13},
        "validators": {"passed_count": 6, "count": 6},
    }


def _rag(passed=True):
    return {"gate_pass": passed, "case_count": 56, "metrics": {"hit_rate_at_5": 0.95}}


def _t2s(passed=True):
    return {
        "gate_pass": passed,
        "case_count": 20,
        "overall_accuracy": 0.95,
        "status_accuracy": 1.0,
        "semantic_match_rate": 0.90,
        "unsupported_accuracy": 1.0,
    }


def test_final02_gate_passes_only_when_all_quality_domains_pass():
    report = evaluate_final02_gate(
        foundation=_foundation(),
        accuracy=_accuracy(),
        performance=_performance(),
        safety=_safety(),
        rag=_rag(),
        text_to_sql=_t2s(),
        tests={"passed": True, "returncode": 0},
    )
    assert report["passed"] is True
    assert report["release_candidate"] == "v4.0.0"


def test_final02_gate_rejects_stale_agent_reports_and_domain_gate_failures():
    report = evaluate_final02_gate(
        foundation=_foundation(),
        accuracy=_accuracy("run-a"),
        performance=_performance("run-b"),
        safety=_safety("run-a"),
        rag=_rag(False),
        text_to_sql=_t2s(False),
    )
    assert report["passed"] is False
    assert "SAME_AGENT_OBSERVATION_RUN" in report["failed_checks"]
    assert "RAG_RETRIEVAL_GATE" in report["failed_checks"]
    assert "TEXT_TO_SQL_GATE" in report["failed_checks"]


def test_final02_gate_enforces_p95_accuracy_and_safety_thresholds():
    report = evaluate_final02_gate(
        foundation=_foundation(),
        accuracy=_accuracy(value=99.0),
        performance=_performance(p95=6000.0),
        safety=_safety(failed=1),
        rag=_rag(),
        text_to_sql=_t2s(),
    )
    assert report["passed"] is False
    assert "P95_LATENCY" in report["failed_checks"]
    assert "SAFETY_ASSERTIONS" in report["failed_checks"]
    assert "AGENT_INTENT_ACCURACY" in report["failed_checks"]
