from evaluation.performance import AgentPerformanceEvaluator, distribution, percentile


def _obs(case_id, latency, path, *, llm=0, inp=0, out=0, tool=None):
    return {
        "run_id": "run-1",
        "case_id": case_id,
        "turn_index": 1,
        "latency_ms": latency,
        "execution_path": path,
        "llm_call_count": llm,
        "llm_input_tokens": inp,
        "llm_output_tokens": out,
        "llm_total_tokens": inp + out,
        "prompt_budget_avg_chars": 1000 if llm else 0,
        "primary_tool": tool,
        "tool_calls": ([{"name": tool, "arguments": {}}] if tool else []),
        "error": None,
    }


def test_percentile_and_distribution_are_deterministic():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    stats = distribution([100, 200, 300, 400])
    assert stats["count"] == 4
    assert stats["avg"] == 250.0
    assert stats["median"] == 250.0
    assert stats["max"] == 400.0


def test_performance_report_aggregates_latency_by_execution_path():
    rows = [
        _obs("A", 100, "FAST_PATH"),
        _obs("B", 200, "FAST_PATH"),
        _obs("C", 8000, "DETERMINISTIC_MACRO", llm=1, inp=1000, out=100, tool="analyze_design_change_candidates"),
        _obs("D", 4000, "AGENT_PATH", llm=1, inp=500, out=50),
    ]
    report = AgentPerformanceEvaluator(target_latency_ms=5000).evaluate(rows, expected_turn_count=4)
    assert report["complete"] is True
    assert report["latency_ms"]["within_target_turns"] == 3
    assert report["latency_by_execution_path"]["FAST_PATH"]["count"] == 2
    assert report["hybrid_execution"]["DETERMINISTIC_MACRO"]["rate_pct"] == 25.0


def test_llm_and_token_efficiency_are_weighted_correctly():
    rows = [
        _obs("A", 100, "FAST_PATH"),
        _obs("B", 1000, "AGENT_PATH", llm=2, inp=800, out=200),
        _obs("C", 1200, "AGENT_PATH", llm=1, inp=400, out=100),
    ]
    report = AgentPerformanceEvaluator().evaluate(rows)
    llm = report["llm_efficiency"]
    assert llm["total_calls"] == 3
    assert llm["zero_llm_turns"] == 1
    assert llm["input_tokens"] == 1200
    assert llm["output_tokens"] == 300
    assert llm["total_tokens"] == 1500
    assert llm["avg_total_tokens_per_llm_call"] == 500.0


def test_mcp_latency_prefers_outer_mcp_tool_span_to_avoid_double_counting():
    rows = [_obs("A", 1000, "FAST_PATH", tool="get_bom")]
    events = [
        {"category": "mcp_tool", "name": "get_bom", "duration_ms": 100.0},
        {"category": "tool", "name": "mcp.call.get_bom", "duration_ms": 95.0},
    ]
    report = AgentPerformanceEvaluator().evaluate(rows, profile_events=events)
    mcp = report["mcp_tool_latency_ms"]
    assert mcp["source"] == "mcp_tool"
    assert mcp["rows"][0]["count"] == 1
    assert mcp["rows"][0]["avg"] == 100.0


def test_mcp_latency_falls_back_to_mcp_call_span():
    rows = [_obs("A", 1000, "FAST_PATH", tool="get_bom")]
    events = [
        {"category": "tool", "name": "mcp.call.get_bom", "duration_ms": 90.0},
        {"category": "tool", "name": "mcp.call.get_bom", "duration_ms": 110.0},
    ]
    report = AgentPerformanceEvaluator().evaluate(rows, profile_events=events)
    mcp = report["mcp_tool_latency_ms"]
    assert mcp["source"] == "mcp.call.*"
    assert mcp["rows"][0]["avg"] == 100.0


def test_slowest_turns_are_sorted_descending():
    rows = [
        _obs("A", 300, "FAST_PATH"),
        _obs("B", 9000, "AGENT_PATH"),
        _obs("C", 5000, "DETERMINISTIC_MACRO"),
    ]
    report = AgentPerformanceEvaluator(slowest_limit=2).evaluate(rows)
    assert [row["case_id"] for row in report["slowest_turns"]] == ["B", "C"]


def test_profile_diagnostic_coverage_does_not_invent_missing_timings():
    rows = [_obs("A", 100, "FAST_PATH")]
    events = [
        {"category": "routing", "name": "graph.gateway.route", "duration_ms": None},
        {"category": "request", "name": "agent.request", "duration_ms": 100.0},
        {"category": "llm", "name": "azure_openai.chat_completion", "duration_ms": 50.0},
    ]
    report = AgentPerformanceEvaluator().evaluate(rows, profile_events=events)
    coverage = report["diagnostic_coverage"]
    assert coverage["gateway_route_observed"] is True
    assert coverage["gateway_internal_timing"] is False
    assert coverage["context_builder_internal_timing"] is False
    assert coverage["request_total_timing"] is True
    assert coverage["llm_timing"] is True


def test_incomplete_observation_count_is_reported():
    report = AgentPerformanceEvaluator().evaluate(
        [_obs("A", 100, "FAST_PATH")],
        expected_turn_count=58,
    )
    assert report["complete"] is False
    assert report["observed_turn_count"] == 1
    assert report["expected_turn_count"] == 58
