from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {ROOT / "STEP25_APPLY.md"}
PATTERNS = (r"read_csv\s*\(", r"to_csv\s*\(", r"CsvBomRepository", r"BOM_STORAGE_MODE")
IGNORED_PARTS = {
    ".venv", "venv", "site-packages", "deliverable", "__pycache__",
    ".pytest_cache", ".git",
}


def _ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def main() -> None:
    csv_files = [path for path in ROOT.rglob("*.csv") if not _ignored(path)]
    violations: list[str] = []
    for path in ROOT.rglob("*.py"):
        if path == Path(__file__).resolve() or path in EXCLUDED or _ignored(path):
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PATTERNS:
            if re.search(pattern, text):
                violations.append(f"{path.relative_to(ROOT)}: {pattern}")
    if csv_files or violations:
        details = [*(str(path.relative_to(ROOT)) for path in csv_files), *violations]
        raise SystemExit("STEP25 SQLite-only verification failed:\n" + "\n".join(details))
    print("STEP25 SQLite-only verification passed: CSV files=0, runtime references=0")


if __name__ == "__main__":
    main()
