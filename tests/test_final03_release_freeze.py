from __future__ import annotations

from pathlib import Path

from evaluation.final03_release import validate_final03_freeze


LEGACY = "v3." + "1.1"
OLD_STAGE = "phase" + "3"


def _final02_report() -> dict:
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


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project(tmp_path: Path) -> list[str]:
    _write(tmp_path, "README.md", "Display BOM AI Agent v4.0.0\n")
    _write(tmp_path, "AGENTS.md", "Display BOM AI Agent v4.0.0\n")
    _write(tmp_path, "docs/ARCHITECTURE.md", "v4 architecture\n")
    _write(
        tmp_path,
        "docs/RELEASE_V4_0_0.md",
        "\n".join(
            [
                "v4.0.0",
                "Request creation authority outside approved workflow : NO",
                "Approval authority in analysis/evaluation layer      : NO",
                "Production BOM write authority                       : NO",
                f"legacy {LEGACY} history",
                "",
            ]
        ),
    )
    _write(tmp_path, "evaluation/README.md", "current evaluation\n")
    _write(tmp_path, "knowledge/rules/README.md", "current rules\n")
    _write(tmp_path, "evaluation/release_gate.py", f"release_target = '{LEGACY}'\n")
    _write(tmp_path, "scripts/finalize_agent_evaluation.py", f"legacy = '{LEGACY}'\n")
    _write(
        tmp_path,
        ".gitignore",
        """.perf/
artifacts/
data/rag/
.*_backup_*/
data/*.db.*_backup_*
evaluation/text_to_sql/text_to_sql_generation_latest.json
""",
    )
    return [
        "README.md",
        "AGENTS.md",
        "docs/ARCHITECTURE.md",
        "docs/RELEASE_V4_0_0.md",
        "evaluation/README.md",
        "knowledge/rules/README.md",
        "evaluation/release_gate.py",
        "scripts/finalize_agent_evaluation.py",
        ".gitignore",
    ]


def test_final03_freeze_passes_for_release_contract(tmp_path):
    tracked = _project(tmp_path)
    report = validate_final03_freeze(project_root=tmp_path, final02_report=_final02_report(), tracked_files=tracked)
    assert report["passed"] is True
    assert report["failed_checks"] == []


def test_final03_freeze_blocks_local_artifact_in_tracked_files(tmp_path):
    tracked = _project(tmp_path)
    _write(tmp_path, "artifacts/local.json", "{}")
    tracked.append("artifacts/local.json")
    report = validate_final03_freeze(project_root=tmp_path, final02_report=_final02_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "NO_LOCAL_ARTIFACTS_TRACKED" in report["failed_checks"]


def test_final03_freeze_blocks_development_stage_term(tmp_path):
    tracked = _project(tmp_path)
    _write(tmp_path, "docs/ARCHITECTURE.md", f"old {OLD_STAGE} architecture\n")
    report = validate_final03_freeze(project_root=tmp_path, final02_report=_final02_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "NO_DEVELOPMENT_STAGE_TERM" in report["failed_checks"]


def test_final03_freeze_allows_legacy_release_only_in_legacy_files(tmp_path):
    tracked = _project(tmp_path)
    report = validate_final03_freeze(project_root=tmp_path, final02_report=_final02_report(), tracked_files=tracked)
    assert report["passed"] is True
    _write(tmp_path, "README.md", f"v4.0.0 active docs with {LEGACY} stale marker\n")
    report = validate_final03_freeze(project_root=tmp_path, final02_report=_final02_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "LEGACY_V311_ISOLATED" in report["failed_checks"]
