import json

from core.performance_profiler import (
    load_performance_events,
    performance_span,
    record_performance_event,
    summarize_performance_events,
)


def test_profiler_writes_and_summarizes_events(tmp_path, monkeypatch):
    profile = tmp_path / "profile.jsonl"
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE", "1")
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE_PATH", str(profile))

    with performance_span("llm", "azure_openai.chat_completion"):
        pass

    record_performance_event(
        category="llm",
        name="azure_openai.usage",
        metrics={"input": 100, "output": 20, "total": 120},
    )
    record_performance_event(
        category="context",
        name="llm.context_diet",
        metrics={
            "original_tool_chars": 1000,
            "compacted_tool_chars": 200,
            "saved_tool_chars": 800,
            "compacted_tool_messages": 2,
        },
    )

    events = load_performance_events(profile)
    summary = summarize_performance_events(events)

    assert summary["event_count"] == 3
    assert summary["llm_usage"] == {
        "input": 100,
        "output": 20,
        "total": 120,
    }
    assert summary["context_diet"]["saved_tool_chars"] == 800
    assert any(
        row["name"] == "azure_openai.chat_completion"
        for row in summary["timings"]
    )


def test_profiler_does_not_write_when_disabled(tmp_path, monkeypatch):
    profile = tmp_path / "profile.jsonl"
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE", "0")
    monkeypatch.setenv("BOM_PERFORMANCE_PROFILE_PATH", str(profile))

    record_performance_event(
        category="test",
        name="disabled",
        duration_ms=1,
    )

    assert profile.exists() is False
