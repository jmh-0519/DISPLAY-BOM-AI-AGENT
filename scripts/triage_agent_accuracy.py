from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.triage import triage_accuracy_report


DEFAULT_INPUT = Path(".perf/evaluation/accuracy_report.json")
DEFAULT_OUTPUT = Path(".perf/evaluation/accuracy_failure_triage.json")


def _print_value(value):
    if value is None:
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage accuracy failures")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--show-all", action="store_true")
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Accuracy report not found: {source}")
    report = json.loads(source.read_text(encoding="utf-8"))
    triage = triage_accuracy_report(report)

    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(triage, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nAgent Evaluation - Failure Triage")
    print(f"turns evaluated            : {triage['evaluated_turn_count']}")
    print(f"failed turns               : {triage['failed_turn_count']}")
    print(f"semantic root failures     : {triage['semantic_root_failed_turns']}")
    print(f"architecture root failures : {triage['architecture_root_failed_turns']}")

    print("\nPrimary Causes")
    for key, count in triage["by_primary_cause"].items():
        print(f"  {key:24s} {count}")

    print("\nFailed Categories")
    for key, count in triage["by_category"].items():
        print(f"  {key:24s} {count}")

    print("\nFailure Detail")
    rows = triage["rows"] if args.show_all else triage["rows"][:30]
    for row in rows:
        print(f"  - {row['turn_key']}: {row['primary_cause']}")
        print(f"      failures : {', '.join(row['failures'])}")
        print(f"      intent   : {_print_value(row['expected_intent'])} -> {_print_value(row['actual_intent'])}")
        print(f"      route    : {_print_value(row['expected_route'])} -> {_print_value(row['actual_route'])}")
        print(f"      tool     : {_print_value(row['expected_tool'])} -> {_print_value(row['actual_tool'])}")
        if row.get("notes"):
            print(f"      note     : {'; '.join(row['notes'])}")
    if len(triage["rows"]) > len(rows):
        print(f"  ... {len(triage['rows']) - len(rows)} more (use --show-all)")

    print(f"\nreport: {target}")
    print("TRIAGE: PASS")


if __name__ == "__main__":
    main()
