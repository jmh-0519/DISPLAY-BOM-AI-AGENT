from core.performance_profiler import (
    load_performance_events,
    record_performance_event,
    summarize_performance_events,
)


def test_prompt_budget_summary_breaks_down_llm_input_components(
    tmp_path,
    monkeypatch,
):
    profile = tmp_path / "prompt-budget.jsonl"
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE", "1")
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE_PATH", str(profile))

    record_performance_event(
        category="prompt",
        name="skill.loaded",
        metadata={"skill_name": "bom-query"},
        metrics={"chars": 8000, "lines": 200},
    )
    record_performance_event(
        category="prompt",
        name="skill.loaded",
        metadata={"skill_name": "bom-design-change"},
        metrics={"chars": 18000, "lines": 450},
    )
    record_performance_event(
        category="prompt",
        name="llm.prompt_budget",
        metrics={
            "core_system_chars": 300,
            "skill_wrapper_chars": 80,
            "base_skill_chars": 26000,
            "runtime_gate_chars": 5000,
            "message_payload_chars": 4000,
            "human_content_chars": 100,
            "assistant_content_chars": 100,
            "tool_content_chars": 3300,
            "tool_definition_chars": 20000,
            "tool_definition_count": 20,
            "approx_total_chars": 55380,
        },
    )
    record_performance_event(
        category="prompt",
        name="llm.tool_schema_budget",
        metadata={"tool_name": "analyze_design_change_candidates"},
        metrics={"schema_chars": 4200},
    )
    record_performance_event(
        category="llm",
        name="azure_openai.usage",
        metrics={"input": 11000, "output": 200, "total": 11200},
    )

    summary = summarize_performance_events(
        load_performance_events(profile)
    )

    avg = summary["prompt_budget"]["avg_per_call"]
    assert avg["base_skill_chars"] == 26000
    assert avg["tool_definition_chars"] == 20000
    assert avg["tool_definition_count"] == 20
    assert summary["skills"]["bom-query"]["chars"] == 8000
    assert summary["skills"]["bom-design-change"]["chars"] == 18000
    assert (
        summary["tool_schemas"][0]["tool_name"]
        == "analyze_design_change_candidates"
    )
    assert summary["llm_usage"]["input"] == 11000


def test_prompt_budget_averages_multiple_llm_calls(
    tmp_path,
    monkeypatch,
):
    profile = tmp_path / "prompt-budget-multi.jsonl"
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE", "1")
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE_PATH", str(profile))

    for value in (1000, 3000):
        record_performance_event(
            category="prompt",
            name="llm.prompt_budget",
            metrics={
                "base_skill_chars": value,
                "approx_total_chars": value * 2,
            },
        )

    summary = summarize_performance_events(
        load_performance_events(profile)
    )

    avg = summary["prompt_budget"]["avg_per_call"]
    assert avg["call_count"] == 2
    assert avg["base_skill_chars"] == 2000
    assert avg["approx_total_chars"] == 4000
