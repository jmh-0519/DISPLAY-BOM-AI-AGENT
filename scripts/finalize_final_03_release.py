from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.final03_release import (
    evaluate_final03_gate,
    load_report,
    run_full_regression,
    validate_final03_freeze,
    write_json,
    write_markdown,
)


def _args() -> argparse.Namespace:
    root = PROJECT_ROOT / ".perf" / "evaluation"
    parser = argparse.ArgumentParser(description="Finalize FINAL-03 v4.0.0 release freeze gate.")
    parser.add_argument("--final02", default=str(root / "final02_gate_report.json"))
    parser.add_argument("--validation-output", default=str(root / "final03_freeze_validation.json"))
    parser.add_argument("--output", default=str(root / "final03_release_report.json"))
    parser.add_argument("--markdown", default=str(root / "final03_release_report.md"))
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--require-tests", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.require_tests and not args.run_tests:
        print("FINAL-03 GATE: FAIL (--require-tests requires --run-tests)")
        return 2

    final02 = load_report(args.final02)
    validation = validate_final03_freeze(project_root=PROJECT_ROOT, final02_report=final02)
    validation_path = write_json(validation, args.validation_output)

    tests = None
    if args.run_tests:
        print("Running final full regression...")
        tests = run_full_regression(project_root=PROJECT_ROOT)
        print(tests.get("output_tail") or "")

    report = evaluate_final03_gate(
        freeze_validation=validation,
        final02_report=final02,
        tests=tests,
    )
    output = write_json(report, args.output)
    markdown = write_markdown(report, args.markdown)

    print(f"FINAL-03 v4.0.0 Release Freeze {report['status']}")
    print(f"head={report.get('head')}")
    print(f"final02_run_id={report.get('final02_run_id')}")
    print(f"freeze_validation={validation.get('status')}")
    print(f"full_regression={'PASS' if tests is not None and tests.get('passed') else ('NOT_RUN' if tests is None else 'FAIL')}")
    print(f"validation_report={validation_path}")
    print(f"json_report={output}")
    print(f"md_report={markdown}")
    print(f"FINAL-03 GATE: {report['status']}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
