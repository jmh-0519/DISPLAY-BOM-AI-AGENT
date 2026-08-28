from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator


@dataclass(frozen=True)
class EvaluationDatabase:
    source_path: Path
    runtime_path: Path


@contextmanager
def evaluation_database_sandbox(
    source_path: str | Path,
    *,
    keep: bool = False,
    work_dir: str | Path | None = None,
) -> Iterator[EvaluationDatabase]:
    """Run evaluation against a disposable DB copy.

    Analysis sessions may write evaluation/history rows even though Production
    E-BOM is not applied.  The evaluator must therefore never point the Agent at
    the developer's runtime DB directly.
    """
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Evaluation source database not found: {source}")

    root = Path(work_dir).expanduser().resolve() if work_dir else None
    if root:
        root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="bom-agent-eval-", dir=root))
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="bom-agent-eval-"))
    runtime = temp_dir / source.name
    shutil.copy2(source, runtime)

    previous = os.environ.get("BOM_SQLITE_PATH")
    os.environ["BOM_SQLITE_PATH"] = str(runtime)
    try:
        yield EvaluationDatabase(source_path=source, runtime_path=runtime)
    finally:
        if previous is None:
            os.environ.pop("BOM_SQLITE_PATH", None)
        else:
            os.environ["BOM_SQLITE_PATH"] = previous
        if not keep:
            shutil.rmtree(temp_dir, ignore_errors=True)
