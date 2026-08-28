from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_cases, render_case
from evaluation.fixtures import EvaluationFixtureResolver
from evaluation.observation import RuntimeObservationCollector, write_observations_jsonl
from evaluation.runtime import evaluation_database_sandbox


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect raw Agent Evaluation runtime observations without scoring them."
    )
    parser.add_argument("--database", default=str(PROJECT_ROOT / "data" / "display_bom.db"))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Case ID to execute. Repeat for multiple cases. Default: first case only.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute the full evaluation dataset. Cannot be combined with --case-id.",
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae02_observations.jsonl"),
    )
    parser.add_argument(
        "--profile",
        default=str(PROJECT_ROOT / ".perf" / "evaluation" / "ae02_profile.jsonl"),
    )
    parser.add_argument("--keep-eval-db", action="store_true")
    return parser.parse_args()


def _select_cases(cases, case_ids: list[str], limit: int | None, run_all: bool = False):
    if case_ids and run_all:
        raise SystemExit("--all cannot be combined with --case-id")
    if case_ids:
        wanted = {value.strip().upper() for value in case_ids}
        selected = [case for case in cases if case.case_id in wanted]
        missing = wanted - {case.case_id for case in selected}
        if missing:
            raise SystemExit(f"Unknown case_id: {sorted(missing)}")
    elif run_all:
        selected = list(cases)
    else:
        selected = cases[:1]
    if limit is not None:
        if limit < 1:
            raise SystemExit("--limit must be >= 1")
        selected = selected[:limit]
    return selected


def main() -> int:
    args = _arguments()
    cases = load_evaluation_cases(args.dataset)
    selected = _select_cases(cases, args.case_id, args.limit, args.all)
    if not selected:
        raise SystemExit("No evaluation cases selected.")

    output = Path(args.output).resolve()
    profile = Path(args.profile).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    profile.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    if profile.exists():
        profile.unlink()

    # Profiling must be enabled before Agent/MCP construction so every runtime
    # component writes to the same evaluation trace file.
    previous_profile_enabled = os.environ.get("BOM_PERFORMANCE_PROFILE")
    previous_profile_path = os.environ.get("BOM_PERFORMANCE_PROFILE_PATH")
    os.environ["BOM_PERFORMANCE_PROFILE"] = "1"
    os.environ["BOM_PERFORMANCE_PROFILE_PATH"] = str(profile)

    observations = []
    run_id = f"ae02-{uuid.uuid4().hex[:12]}"
    try:
        with evaluation_database_sandbox(
            args.database,
            keep=args.keep_eval_db,
            work_dir=PROJECT_ROOT / ".perf" / "evaluation",
        ) as sandbox:
            fixtures = EvaluationFixtureResolver(sandbox.runtime_path).resolve()

            # Import after BOM_SQLITE_PATH + profiler environment are set.
            from agents.bom_agent_graph import BomAgentGraph
            from core.azure_openai_client import AzureOpenAIClient
            from core.settings import Settings
            from core.skill_loader import SkillLoader
            from mcp_client.client import DisplayBomMcpClient

            settings = Settings.from_env()
            agent = BomAgentGraph(
                client=AzureOpenAIClient(settings),
                mcp_client=DisplayBomMcpClient(),
                skill_context=SkillLoader(PROJECT_ROOT / "skills").load_many(
                    ["bom-query", "bom-design-change"]
                ),
            )
            collector = RuntimeObservationCollector(
                agent,
                profile_path=profile,
                run_id=run_id,
            )

            for case in selected:
                thread_id = f"{run_id}-{case.case_id.lower()}"
                rendered_turns = render_case(case, fixtures.values)
                print(f"\n[{case.case_id}] {case.description}")
                for turn_index, user_input in enumerate(rendered_turns, start=1):
                    print(f"  turn {turn_index}: {user_input}")
                    observation = collector.collect_turn(
                        case_id=case.case_id,
                        turn_index=turn_index,
                        user_input=user_input,
                        thread_id=thread_id,
                    )
                    observations.append(observation)
                    print(
                        "    "
                        f"intent={observation.actual_intent or '-'} "
                        f"route={observation.execution_path or '-'} "
                        f"tool={observation.primary_tool or '-'} "
                        f"latency={observation.latency_ms:.2f}ms "
                        f"llm_calls={observation.llm_call_count} "
                        f"tokens={observation.llm_total_tokens} "
                        f"error={observation.error or '-'}"
                    )

            write_observations_jsonl(observations, output)
            manifest = {
                "run_id": run_id,
                "source_database": str(sandbox.source_path),
                "evaluation_database": str(sandbox.runtime_path),
                "evaluation_database_kept": bool(args.keep_eval_db),
                "case_ids": [case.case_id for case in selected],
                "turn_count": len(observations),
                "fixtures": fixtures.values,
                "observation_file": str(output),
                "profile_file": str(profile),
            }
            output.with_suffix(".manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        if previous_profile_enabled is None:
            os.environ.pop("BOM_PERFORMANCE_PROFILE", None)
        else:
            os.environ["BOM_PERFORMANCE_PROFILE"] = previous_profile_enabled
        if previous_profile_path is None:
            os.environ.pop("BOM_PERFORMANCE_PROFILE_PATH", None)
        else:
            os.environ["BOM_PERFORMANCE_PROFILE_PATH"] = previous_profile_path

    print(f"\nobservations: {len(observations)}")
    print(f"output: {output}")
    print(f"profile: {profile}")
    print("COLLECTION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
