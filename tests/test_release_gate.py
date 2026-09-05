from __future__ import annotations

from evaluation.release import evaluate_release_gate


def _quality() -> dict:
    return {
        "passed": True,
        "status": "PASS",
        "release_candidate": "v4.0.0",
        "run_id": "evaluation-test",
        "summary": {
            "accuracy": {"intent": 100.0, "route": 100.0, "tool_selection": 100.0, "tool_arguments": 100.0},
            "safety": {"rate_pct": 100.0, "failed_assertions": 0},
            "performance": {"p95_latency_ms": 3314.59},
        },
        "checks": [
            {"name": "RAG_RETRIEVAL_GATE", "passed": True},
            {"name": "TEXT_TO_SQL_GATE", "passed": True},
            {"name": "FULL_REGRESSION", "passed": True},
        ],
    }


def test_release_gate_passes_when_validation_quality_and_tests_pass():
    report = evaluate_release_gate(
        freeze_validation={"passed": True, "status": "PASS", "head": "abc"},
        quality_report=_quality(),
        tests={"passed": True, "returncode": 0, "detail": None},
    )
    assert report["passed"] is True
    assert report["release_target"] == "v4.0.0"


def test_release_gate_blocks_failed_final_regression():
    report = evaluate_release_gate(
        freeze_validation={"passed": True, "status": "PASS", "head": "abc"},
        quality_report=_quality(),
        tests={"passed": False, "returncode": 1, "detail": "failed"},
    )
    assert report["passed"] is False
    assert "FINAL_FULL_REGRESSION" in report["failed_checks"]
