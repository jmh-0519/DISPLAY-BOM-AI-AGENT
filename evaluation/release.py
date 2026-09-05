from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from evaluation.quality_gate import load_report, run_full_regression


RELEASE_SCHEMA_VERSION = "1.0"
RELEASE_TARGET = "v4.0.0"
REQUIRED_DOCS = {
    "README.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/DATABASE_SCHEMA.md",
    "docs/RELEASE_V4_0_0.md",
    "evaluation/README.md",
    "knowledge/rules/README.md",
    "rag/README.md",
    "text_to_sql/README.md",
}
REQUIRED_GITIGNORE_LINES = {
    ".perf/",
    "artifacts/",
    "data/rag/",
    ".*_backup_*/",
    "data/*.db.*_backup_*",
    "evaluation/text_to_sql/text_to_sql_generation_latest.json",
}
# Development-task naming should not survive in the final v4 source tree.
FORBIDDEN_TRACKED_FILENAME_PATTERNS = (
    re.compile(r"(?:^|/|[_-])final[_-]?0[123](?:[_-]|\.|/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)DB_V9_SCHEMA_DECISIONS\.md$", re.IGNORECASE),
    re.compile(r"README_T2SQL02A\.md$", re.IGNORECASE),
    re.compile(r"(?:^|/)verify_clean_core_databases\.py$", re.IGNORECASE),
)


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    passed: bool
    actual: Any
    expected: Any
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "actual": self.actual,
            "expected": self.expected,
            "detail": self.detail,
        }


def _read_text(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _git_tracked_files(project_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(project_root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {completed.stderr.strip()}")
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def _git_head(project_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _is_forbidden_tracked_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    if normalized.startswith(".perf/") or normalized.startswith("artifacts/"):
        return True
    if normalized.startswith("data/rag/"):
        return True
    if "_backup_" in normalized:
        return True
    if normalized == "evaluation/text_to_sql/text_to_sql_generation_latest.json":
        return True
    if normalized == "data/display_bom.db":
        return True
    if name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
        return True
    return False


def _development_named_files(tracked: list[str]) -> list[str]:
    hits: list[str] = []
    for relative in tracked:
        normalized = relative.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in FORBIDDEN_TRACKED_FILENAME_PATTERNS):
            hits.append(normalized)
    return sorted(set(hits))


def _quality_summary_valid(report: dict[str, Any]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if report.get("passed") is not True or report.get("status") != "PASS":
        problems.append("quality gate report is not PASS")
    if report.get("release_candidate") != RELEASE_TARGET:
        problems.append("quality gate release_candidate is not v4.0.0")
    summary = report.get("summary") or {}
    accuracy = summary.get("accuracy") or {}
    for name in ("intent", "route", "tool_selection", "tool_arguments"):
        if float(accuracy.get(name) or 0.0) != 100.0:
            problems.append(f"{name} accuracy != 100")
    safety = summary.get("safety") or {}
    if float(safety.get("rate_pct") or 0.0) != 100.0 or int(safety.get("failed_assertions") or 0) != 0:
        problems.append("safety is not 100% / zero failures")
    perf = summary.get("performance") or {}
    p95 = perf.get("p95_latency_ms")
    if not isinstance(p95, (int, float)) or float(p95) > 5000.0:
        problems.append("P95 latency exceeds 5000ms")
    checks = {row.get("name"): row.get("passed") for row in report.get("checks") or []}
    for required in ("RAG_RETRIEVAL_GATE", "TEXT_TO_SQL_GATE", "FULL_REGRESSION"):
        if checks.get(required) is not True:
            problems.append(f"{required} is not PASS")
    return not problems, problems


def validate_release_freeze(
    *,
    project_root: str | Path,
    quality_report: dict[str, Any],
    tracked_files: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    checks: list[ReleaseCheck] = []

    missing_docs = sorted(path for path in REQUIRED_DOCS if not (root / path).is_file())
    checks.append(ReleaseCheck("RELEASE_DOCS", not missing_docs, missing_docs, []))

    readme = _read_text(root, "README.md") if (root / "README.md").exists() else ""
    agents = _read_text(root, "AGENTS.md") if (root / "AGENTS.md").exists() else ""
    checks.append(ReleaseCheck(
        "CURRENT_RELEASE_DOCUMENTED",
        RELEASE_TARGET in readme and RELEASE_TARGET in agents,
        {"readme": RELEASE_TARGET in readme, "agents": RELEASE_TARGET in agents},
        {"readme": True, "agents": True},
    ))

    gitignore = set(
        line.strip()
        for line in _read_text(root, ".gitignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ) if (root / ".gitignore").exists() else set()
    missing_ignores = sorted(REQUIRED_GITIGNORE_LINES - gitignore)
    checks.append(ReleaseCheck("REPOSITORY_IGNORE_POLICY", not missing_ignores, missing_ignores, []))

    tracked = list(tracked_files) if tracked_files is not None else _git_tracked_files(root)
    forbidden = sorted(path for path in tracked if _is_forbidden_tracked_path(path))
    checks.append(ReleaseCheck("NO_LOCAL_ARTIFACTS_TRACKED", not forbidden, forbidden, []))

    task_named = _development_named_files(tracked)
    checks.append(ReleaseCheck("NO_DEVELOPMENT_TASK_FILENAMES", not task_named, task_named, []))

    legacy_files = sorted(path for path in (
        "evaluation/release_gate.py",
        "scripts/finalize_agent_evaluation.py",
        "evaluation/datasets/agent_eval_v1.jsonl",
        "rag/AGENT_INTEGRATION.md",
        "text_to_sql/README_T2SQL02A.md",
    ) if path in tracked)
    checks.append(ReleaseCheck("NO_LEGACY_V4_SOURCE_ARTIFACTS", not legacy_files, legacy_files, []))

    quality_ok, quality_problems = _quality_summary_valid(quality_report)
    checks.append(ReleaseCheck("QUALITY_EVIDENCE", quality_ok, quality_problems, []))

    release_doc = _read_text(root, "docs/RELEASE_V4_0_0.md") if (root / "docs/RELEASE_V4_0_0.md").exists() else ""
    authority_markers = (
        "Request creation authority outside approved workflow : NO",
        "Approval authority in analysis/evaluation layer      : NO",
        "Production BOM write authority                       : NO",
    )
    checks.append(ReleaseCheck(
        "AUTHORITY_BOUNDARY_DOCUMENTED",
        all(marker in release_doc for marker in authority_markers),
        [marker for marker in authority_markers if marker not in release_doc],
        [],
    ))

    passed = all(check.passed for check in checks)
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "RELEASE_FREEZE",
        "release_target": RELEASE_TARGET,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "head": _git_head(root),
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "summary": {
            "tracked_file_count": len(tracked),
            "quality_run_id": quality_report.get("run_id"),
        },
    }


def evaluate_release_gate(
    *,
    freeze_validation: dict[str, Any],
    quality_report: dict[str, Any],
    tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[ReleaseCheck] = [
        ReleaseCheck("FREEZE_VALIDATION", freeze_validation.get("passed") is True, freeze_validation.get("status"), "PASS"),
    ]
    quality_ok, quality_problems = _quality_summary_valid(quality_report)
    checks.append(ReleaseCheck("QUALITY_GATE", quality_ok, quality_problems, []))
    if tests is not None:
        checks.append(ReleaseCheck(
            "FINAL_FULL_REGRESSION",
            tests.get("passed") is True,
            {"passed": tests.get("passed"), "returncode": tests.get("returncode")},
            "test command exit code 0",
            tests.get("detail"),
        ))
    passed = all(check.passed for check in checks)
    return {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "RELEASE",
        "release_target": RELEASE_TARGET,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "head": freeze_validation.get("head"),
        "quality_run_id": quality_report.get("run_id"),
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "summary": {
            "freeze_validation": freeze_validation.get("status"),
            "quality_gate": quality_report.get("status"),
            "full_regression": tests,
        },
        "notes": [
            "Release cleanup does not change Runtime business authority or evaluation thresholds.",
            "The v4.0.0 tag must point to the final source-cleanup release commit.",
            "Local HEAD, remote branch, local tag and remote tag must resolve to the same release commit.",
        ],
    }


def write_json(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return target


def write_markdown(report: dict[str, Any], path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Display BOM AI Agent v4.0.0 Release Freeze",
        "",
        f"- Status: **{report.get('status')}**",
        f"- Release target: `{report.get('release_target')}`",
        f"- HEAD at validation: `{report.get('head')}`",
        f"- Evaluation run: `{report.get('quality_run_id')}`",
        "",
        "## Gate Checks",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- [{'PASS' if check.get('passed') else 'FAIL'}] {check.get('name')}")
    lines += [
        "",
        "## Freeze Rule",
        "",
        "Release commit 후 `v4.0.0` tag를 생성하고 local HEAD / remote branch / local tag / remote tag가 동일 commit인지 확인합니다.",
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


__all__ = [
    "RELEASE_SCHEMA_VERSION",
    "RELEASE_TARGET",
    "REQUIRED_DOCS",
    "REQUIRED_GITIGNORE_LINES",
    "evaluate_release_gate",
    "load_report",
    "run_full_regression",
    "validate_release_freeze",
    "write_json",
    "write_markdown",
]
