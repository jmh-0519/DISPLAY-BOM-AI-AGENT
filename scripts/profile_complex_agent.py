from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile one complex Display BOM Agent request."
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Complete complex Agent request including MODEL/PLANT when possible.",
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / ".perf" / "complex_agent_profile.jsonl"),
    )
    parser.add_argument(
        "--keep-log",
        action="store_true",
        help="Append to an existing profile instead of clearing it.",
    )
    return parser.parse_args()


def _print_summary(summary: dict) -> None:
    print("\n=== Complex Agent Performance Summary ===")
    print(f"events: {summary['event_count']}")

    rows = summary["timings"]
    if rows:
        print("\nTiming")
        print(f"{'CATEGORY':<12} {'NAME':<42} {'COUNT':>5} {'TOTAL(ms)':>11} {'AVG(ms)':>10} {'MAX(ms)':>10}")
        print("-" * 98)
        for row in rows:
            print(
                f"{row['category']:<12} "
                f"{row['name']:<42} "
                f"{row['count']:>5} "
                f"{row['total_ms']:>11.2f} "
                f"{row['avg_ms']:>10.2f} "
                f"{row['max_ms']:>10.2f}"
            )

    usage = summary["llm_usage"]
    print("\nLLM usage")
    print(
        f"input={usage['input']} output={usage['output']} total={usage['total']}"
    )

    context = summary["context_diet"]
    original = context["original_tool_chars"]
    compacted = context["compacted_tool_chars"]
    saved = context["saved_tool_chars"]
    ratio = (saved / original * 100.0) if original else 0.0
    print("\nContext diet")
    print(
        f"tool_chars: {original} -> {compacted} "
        f"(saved {saved}, {ratio:.1f}%)"
    )
    print(
        f"compacted_tool_messages={context['compacted_tool_messages']}"
    )

    prompt = summary.get("prompt_budget", {}).get("avg_per_call", {})
    if prompt and prompt.get("call_count", 0):
        print("\nLLM prompt budget (average per Azure call, chars)")
        components = [
            ("core_system", "core_system_chars"),
            ("skill_wrapper", "skill_wrapper_chars"),
            ("base_skill", "base_skill_chars"),
            ("runtime_gate", "runtime_gate_chars"),
            ("messages", "message_payload_chars"),
            ("tool_definitions", "tool_definition_chars"),
        ]
        approx_total = float(prompt.get("approx_total_chars") or 0)
        print(f"{'COMPONENT':<22} {'CHARS':>10} {'SHARE':>9}")
        print("-" * 45)
        for label, key in components:
            value = float(prompt.get(key) or 0)
            share = (value / approx_total * 100.0) if approx_total else 0.0
            print(f"{label:<22} {value:>10.0f} {share:>8.1f}%")
        print("-" * 45)
        print(f"{'approx_total':<22} {approx_total:>10.0f} {'100.0%':>9}")
        print(
            "message content detail: "
            f"human={prompt.get('human_content_chars', 0):.0f}, "
            f"assistant={prompt.get('assistant_content_chars', 0):.0f}, "
            f"tool={prompt.get('tool_content_chars', 0):.0f}"
        )
        print(
            "tool_definition_count="
            f"{prompt.get('tool_definition_count', 0):.0f}"
        )
        if usage.get("input"):
            print(
                "actual Azure input tokens per call="
                f"{usage['input'] / max(prompt.get('call_count', 1), 1):.0f}"
            )
            print(
                "Note: component shares are measured in characters; "
                "Azure exposes only the total prompt-token count, so token "
                "attribution by component is not exact."
            )

    skills = summary.get("skills") or {}
    if skills:
        print("\nLoaded Skill files")
        print(f"{'SKILL':<30} {'CHARS':>10} {'LINES':>8}")
        print("-" * 52)
        for skill_name, budget in skills.items():
            print(
                f"{skill_name:<30} "
                f"{budget.get('chars', 0):>10} "
                f"{budget.get('lines', 0):>8}"
            )

    tool_schemas = summary.get("tool_schemas") or []
    if tool_schemas:
        print("\nLargest Tool schemas (Top 10)")
        print(f"{'TOOL':<45} {'AVG CHARS':>10}")
        print("-" * 58)
        for row in tool_schemas[:10]:
            print(
                f"{row['tool_name']:<45} "
                f"{row['avg_schema_chars']:>10.0f}"
            )


def main() -> int:
    args = _arguments()
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.keep_log:
        output.unlink()

    # Set before Agent/MCP construction so the child MCP process inherits it.
    os.environ["BOM_PERFORMANCE_PROFILE"] = "1"
    os.environ["BOM_PERFORMANCE_PROFILE_PATH"] = str(output)

    from agents.bom_agent_graph import BomAgentGraph
    from core.azure_openai_client import AzureOpenAIClient
    from core.performance_profiler import (
        load_performance_events,
        summarize_performance_events,
    )
    from core.settings import Settings
    from core.skill_loader import SkillLoader
    from mcp_client.client import DisplayBomMcpClient

    settings = Settings.from_env()

    init_started = time.perf_counter()
    azure_client = AzureOpenAIClient(settings)
    mcp_client = DisplayBomMcpClient()
    skill_loader = SkillLoader(PROJECT_ROOT / "skills")
    skill_context = skill_loader.load_many([
        "bom-query",
        "bom-design-change",
    ])
    agent = BomAgentGraph(
        client=azure_client,
        mcp_client=mcp_client,
        skill_context=skill_context,
    )
    init_ms = (time.perf_counter() - init_started) * 1000

    print(f"Agent init: {init_ms:.2f} ms")
    print(f"Profile log: {output}")

    for index in range(args.runs):
        thread_id = f"profile-{uuid.uuid4()}"
        print(f"\n--- run {index + 1}/{args.runs} ---")
        started = time.perf_counter()
        answer = agent.run(args.query, thread_id=thread_id)
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"wall clock: {elapsed_ms:.2f} ms")
        compact_answer = " ".join(str(answer).split())
        print(f"answer: {compact_answer[:240]}")

    events = load_performance_events(output)
    summary = summarize_performance_events(events)
    _print_summary(summary)

    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSummary JSON: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
