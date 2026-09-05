from __future__ import annotations

from pathlib import Path

from evaluation.release import validate_release_freeze


def _quality_report() -> dict:
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
    _write(tmp_path, "docs/DATABASE_SCHEMA.md", "current schema\n")
    _write(
        tmp_path,
        "docs/RELEASE_V4_0_0.md",
        "\n".join([
            "v4.0.0",
            "Request creation authority outside approved workflow : NO",
            "Approval authority in analysis/evaluation layer      : NO",
            "Production BOM write authority                       : NO",
            "",
        ]),
    )
    _write(tmp_path, "evaluation/README.md", "current evaluation\n")
    _write(tmp_path, "knowledge/rules/README.md", "current rules\n")
    _write(tmp_path, "rag/README.md", "current rag\n")
    _write(tmp_path, "text_to_sql/README.md", "current text-to-sql\n")
    _write(
        tmp_path,
        ".gitignore",
        ".perf/\nartifacts/\ndata/rag/\n.*_backup_*/\ndata/*.db.*_backup_*\nevaluation/text_to_sql/text_to_sql_generation_latest.json\n",
    )
    return [
        "README.md", "AGENTS.md", "docs/ARCHITECTURE.md", "docs/DATABASE_SCHEMA.md",
        "docs/RELEASE_V4_0_0.md", "evaluation/README.md", "knowledge/rules/README.md",
        "rag/README.md", "text_to_sql/README.md", ".gitignore",
    ]


def test_release_freeze_passes_for_release_contract(tmp_path):
    tracked = _project(tmp_path)
    report = validate_release_freeze(project_root=tmp_path, quality_report=_quality_report(), tracked_files=tracked)
    assert report["passed"] is True
    assert report["failed_checks"] == []


def test_release_freeze_blocks_local_artifact_in_tracked_files(tmp_path):
    tracked = _project(tmp_path)
    _write(tmp_path, "artifacts/local.json", "{}")
    tracked.append("artifacts/local.json")
    report = validate_release_freeze(project_root=tmp_path, quality_report=_quality_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "NO_LOCAL_ARTIFACTS_TRACKED" in report["failed_checks"]


def test_release_freeze_blocks_development_task_filename(tmp_path):
    tracked = _project(tmp_path)
    _write(tmp_path, "scripts/validate_final_02_evaluation_foundation.py", "pass\n")
    tracked.append("scripts/validate_final_02_evaluation_foundation.py")
    report = validate_release_freeze(project_root=tmp_path, quality_report=_quality_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "NO_DEVELOPMENT_TASK_FILENAMES" in report["failed_checks"]


def test_release_freeze_blocks_legacy_v4_source_artifact(tmp_path):
    tracked = _project(tmp_path)
    _write(tmp_path, "evaluation/datasets/agent_eval_v1.jsonl", "{}\n")
    tracked.append("evaluation/datasets/agent_eval_v1.jsonl")
    report = validate_release_freeze(project_root=tmp_path, quality_report=_quality_report(), tracked_files=tracked)
    assert report["passed"] is False
    assert "NO_LEGACY_V4_SOURCE_ARTIFACTS" in report["failed_checks"]
