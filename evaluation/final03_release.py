from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable

from evaluation.final02_gate import load_report, run_full_regression


FINAL03_SCHEMA_VERSION = "1.0"
RELEASE_TARGET = "v4.0.0"
DEVELOPMENT_STAGE_TOKEN = "phase" + "3"
LEGACY_RELEASE_TOKEN = "v3." + "1.1"
LEGACY_V311_FILES = {
    "evaluation/release_gate.py",
    "scripts/finalize_agent_evaluation.py",
    "docs/RELEASE_V4_0_0.md",
}
REQUIRED_DOCS = {
    "README.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/RELEASE_V4_0_0.md",
    "evaluation/README.md",
    "knowledge/rules/README.md",
}
REQUIRED_GITIGNORE_LINES = {
    ".perf/",
    "artifacts/",
    "data/rag/",
    ".*_backup_*/",
    "data/*.db.*_backup_*",
    "evaluation/text_to_sql/text_to_sql_generation_latest.json",
}


@dataclass(frozen=True)
class FreezeCheck:
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


def _scan_tokens(root: Path, tracked: Iterable[str]) -> dict[str, list[str]]:
    development_stage_hits: list[str] = []
    active_v311_hits: list[str] = []
    for relative in tracked:
        if Path(relative).suffix.lower() not in {".md", ".py", ".json"}:
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        lowered = text.lower()
        if DEVELOPMENT_STAGE_TOKEN in lowered:
            development_stage_hits.append(relative)
        if LEGACY_RELEASE_TOKEN in text and relative not in LEGACY_V311_FILES:
            active_v311_hits.append(relative)
    return {
        "development_stage": sorted(set(development_stage_hits)),
        "unexpected_v3_1_1": sorted(set(active_v311_hits)),
    }


def _final02_summary_valid(report: dict[str, Any]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if report.get("passed") is not True or report.get("status") != "PASS":
        problems.append("FINAL-02 report is not PASS")
    if report.get("release_candidate") != RELEASE_TARGET:
        problems.append("FINAL-02 release_candidate is not v4.0.0")
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


def validate_final03_freeze(
    *,
    project_root: str | Path,
    final02_report: dict[str, Any],
    tracked_files: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    checks: list[FreezeCheck] = []

    missing_docs = sorted(path for path in REQUIRED_DOCS if not (root / path).is_file())
    checks.append(FreezeCheck("RELEASE_DOCS", not missing_docs, missing_docs, []))

    readme = _read_text(root, "README.md") if (root / "README.md").exists() else ""
    agents = _read_text(root, "AGENTS.md") if (root / "AGENTS.md").exists() else ""
    checks.append(FreezeCheck(
        "CURRENT_RELEASE_DOCUMENTED",
        RELEASE_TARGET in readme and RELEASE_TARGET in agents,
        {"readme": RELEASE_TARGET in readme, "agents": RELEASE_TARGET in agents},
        {"readme": True, "agents": True},
    ))
    stale_active_markers = [
        marker for marker in (
            f"Current Clean Core Freeze: `{LEGACY_RELEASE_TOKEN}`",
            f"{LEGACY_RELEASE_TOKEN} Freeze 직전",
            "v3.1.0 Release 기준 최종 결과",
            "## 15. 다음 개발 로드맵",
        )
        if marker in readme or marker in agents
    ]
    checks.append(FreezeCheck("STALE_ACTIVE_RELEASE_DOCS", not stale_active_markers, stale_active_markers, []))

    gitignore = set(
        line.strip()
        for line in _read_text(root, ".gitignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ) if (root / ".gitignore").exists() else set()
    missing_ignores = sorted(REQUIRED_GITIGNORE_LINES - gitignore)
    checks.append(FreezeCheck("REPOSITORY_IGNORE_POLICY", not missing_ignores, missing_ignores, []))

    tracked = list(tracked_files) if tracked_files is not None else _git_tracked_files(root)
    forbidden = sorted(path for path in tracked if _is_forbidden_tracked_path(path))
    checks.append(FreezeCheck("NO_LOCAL_ARTIFACTS_TRACKED", not forbidden, forbidden, []))

    token_hits = _scan_tokens(root, tracked)
    checks.append(FreezeCheck("NO_DEVELOPMENT_STAGE_TERM", not token_hits["development_stage"], token_hits["development_stage"], []))
    checks.append(FreezeCheck(
        "LEGACY_V311_ISOLATED",
        not token_hits["unexpected_v3_1_1"],
        token_hits["unexpected_v3_1_1"],
        [],
        "Legacy release references are allowed only in the explicit legacy gate and release-history document.",
    ))

    final02_ok, final02_problems = _final02_summary_valid(final02_report)
    checks.append(FreezeCheck("FINAL02_QUALITY_EVIDENCE", final02_ok, final02_problems, []))

    release_doc = _read_text(root, "docs/RELEASE_V4_0_0.md") if (root / "docs/RELEASE_V4_0_0.md").exists() else ""
    authority_markers = (
        "Request creation authority outside approved workflow : NO",
        "Approval authority in analysis/evaluation layer      : NO",
        "Production BOM write authority                       : NO",
    )
    checks.append(FreezeCheck(
        "AUTHORITY_BOUNDARY_DOCUMENTED",
        all(marker in release_doc for marker in authority_markers),
        [marker for marker in authority_markers if marker not in release_doc],
        [],
    ))

    passed = all(check.passed for check in checks)
    return {
        "schema_version": FINAL03_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "FINAL-03",
        "release_target": RELEASE_TARGET,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "head": _git_head(root),
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "summary": {
            "tracked_file_count": len(tracked),
            "legacy_v311_allowed_files": sorted(LEGACY_V311_FILES),
            "final02_run_id": final02_report.get("run_id"),
        },
    }


def evaluate_final03_gate(
    *,
    freeze_validation: dict[str, Any],
    final02_report: dict[str, Any],
    tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[FreezeCheck] = [
        FreezeCheck("FREEZE_VALIDATION", freeze_validation.get("passed") is True, freeze_validation.get("status"), "PASS"),
    ]
    final02_ok, final02_problems = _final02_summary_valid(final02_report)
    checks.append(FreezeCheck("FINAL02_GATE", final02_ok, final02_problems, []))
    if tests is not None:
        checks.append(FreezeCheck(
            "FINAL_FULL_REGRESSION",
            tests.get("passed") is True,
            {"passed": tests.get("passed"), "returncode": tests.get("returncode")},
            "test command exit code 0",
            tests.get("detail"),
        ))
    passed = all(check.passed for check in checks)
    return {
        "schema_version": FINAL03_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "FINAL-03",
        "release_target": RELEASE_TARGET,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "head": freeze_validation.get("head"),
        "final02_run_id": final02_report.get("run_id"),
        "checks": [check.as_dict() for check in checks],
        "failed_checks": [check.name for check in checks if not check.passed],
        "summary": {
            "freeze_validation": freeze_validation.get("status"),
            "final02": final02_report.get("status"),
            "full_regression": tests,
        },
        "notes": [
            "FINAL-03 does not change Runtime business authority or evaluation thresholds.",
            "The v4.0.0 tag must be created only after this gate passes and the release commit is created.",
            "Local HEAD, remote branch, local tag and remote tag must point to the same release commit.",
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
        "# FINAL-03 Release Freeze",
        "",
        f"- Status: **{report.get('status')}**",
        f"- Release target: `{report.get('release_target')}`",
        f"- HEAD at validation: `{report.get('head')}`",
        f"- FINAL-02 run: `{report.get('final02_run_id')}`",
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
    "FINAL03_SCHEMA_VERSION",
    "LEGACY_V311_FILES",
    "RELEASE_TARGET",
    "REQUIRED_DOCS",
    "REQUIRED_GITIGNORE_LINES",
    "evaluate_final03_gate",
    "load_report",
    "run_full_regression",
    "validate_final03_freeze",
    "write_json",
    "write_markdown",
]
