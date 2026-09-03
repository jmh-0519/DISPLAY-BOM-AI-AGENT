from __future__ import annotations

import json
from pathlib import Path

from evaluation.context.context_eval_runner import print_report, run_evaluation


def main() -> None:
    report = run_evaluation()
    print_report(report)

    output = Path("artifacts") / "context_evaluation_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report={output}")

    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
