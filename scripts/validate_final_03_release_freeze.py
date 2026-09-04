from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.final03_release import load_report, validate_final03_freeze, write_json


def _args() -> argparse.Namespace:
    root = PROJECT_ROOT / ".perf" / "evaluation"
    parser = argparse.ArgumentParser(description="Validate FINAL-03 release documentation, repository hygiene and FINAL-02 quality evidence.")
    parser.add_argument("--final02", default=str(root / "final02_gate_report.json"))
    parser.add_argument("--output", default=str(root / "final03_freeze_validation.json"))
    return parser.parse_args()


def main() -> int:
    args = _args()
    report = validate_final03_freeze(
        project_root=PROJECT_ROOT,
        final02_report=load_report(args.final02),
    )
    output = write_json(report, args.output)
    print(f"FINAL-03 Release Freeze Validation {report['status']}")
    print(f"release_target={report.get('release_target')}")
    print(f"head={report.get('head')}")
    print(f"final02_run_id={(report.get('summary') or {}).get('final02_run_id')}")
    print(f"checks={len(report.get('checks') or []) - len(report.get('failed_checks') or [])}/{len(report.get('checks') or [])}")
    print(f"failed_checks={','.join(report.get('failed_checks') or []) or 'NONE'}")
    print(f"report={output}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
