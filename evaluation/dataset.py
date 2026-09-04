from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from evaluation.schema import EvalCase, fixture_names


DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parent / "datasets" / "agent_eval_v1.jsonl"
)
FINAL02_DATASET_PATH = (
    Path(__file__).resolve().parent / "datasets" / "agent_eval_v2.jsonl"
)


def load_evaluation_cases(path: str | Path = DEFAULT_DATASET_PATH) -> list[EvalCase]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {target}")

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{target}:{line_no}: invalid JSON: {exc}") from exc
        case = EvalCase.from_dict(raw)
        if case.case_id in seen:
            raise ValueError(f"Duplicate case_id: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)

    if not cases:
        raise ValueError(f"Evaluation dataset is empty: {target}")
    return cases


def render_template(template: str, fixtures: dict[str, Any]) -> str:
    rendered = str(template)
    for name in fixture_names(template):
        if name not in fixtures:
            raise KeyError(f"Missing evaluation fixture: {name}")
        rendered = rendered.replace(f"{{{{{name}}}}}", str(fixtures[name]))
    return rendered


def render_case(case: EvalCase, fixtures: dict[str, Any]) -> list[str]:
    missing = set(case.fixture_requirements) - set(fixtures)
    if missing:
        raise KeyError(
            f"{case.case_id}: missing fixtures {sorted(missing)}"
        )
    return [render_template(turn.user_template, fixtures) for turn in case.turns]


def dataset_summary(cases: Iterable[EvalCase]) -> dict[str, Any]:
    items = list(cases)
    by_category: dict[str, int] = {}
    by_path: dict[str, int] = {}
    by_interaction: dict[str, int] = {}
    turn_count = 0

    for case in items:
        by_category[case.category] = by_category.get(case.category, 0) + 1
        for turn in case.turns:
            turn_count += 1
            path = turn.expected.execution_path
            by_path[path] = by_path.get(path, 0) + 1
            interaction = turn.expected.interaction
            by_interaction[interaction] = by_interaction.get(interaction, 0) + 1

    return {
        "case_count": len(items),
        "turn_count": turn_count,
        "by_category": dict(sorted(by_category.items())),
        "by_execution_path": dict(sorted(by_path.items())),
        "by_interaction": dict(sorted(by_interaction.items())),
    }
