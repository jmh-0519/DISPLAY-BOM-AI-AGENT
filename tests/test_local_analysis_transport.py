from mcp_client.client import DisplayBomMcpClient


def test_analysis_macro_local_transport_enabled_by_default(monkeypatch):
    monkeypatch.delenv("BOM_MCP_LOCAL_ANALYSIS_FAST_PATH", raising=False)

    assert DisplayBomMcpClient._use_local_analysis_fast_path(
        "analyze_design_change_candidates"
    ) is True


def test_analysis_macro_local_transport_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BOM_MCP_LOCAL_ANALYSIS_FAST_PATH", "0")

    assert DisplayBomMcpClient._use_local_analysis_fast_path(
        "analyze_design_change_candidates"
    ) is False


def test_apply_and_request_tools_never_use_local_analysis_transport(monkeypatch):
    monkeypatch.delenv("BOM_MCP_LOCAL_ANALYSIS_FAST_PATH", raising=False)

    protected = {
        "create_design_change_request_from_analysis",
        "create_design_change_preview",
        "record_final_apply_approval",
        "apply_approved_change_request",
    }
    for tool_name in protected:
        assert DisplayBomMcpClient._use_local_analysis_fast_path(tool_name) is False


def test_local_analysis_dispatch_calls_same_design_change_capability(monkeypatch):
    import mcp_server.capabilities.design_change_workflow as design_change_workflow

    captured = {}

    def fake_analyze_design_change_candidates_data(request, actions):
        captured["request"] = request
        captured["actions"] = actions
        return {
            "analysis_id": "ANA-LOCAL-TEST",
            "status": "ANALYSIS_READY",
        }

    monkeypatch.setattr(
        design_change_workflow,
        "analyze_design_change_candidates_data",
        fake_analyze_design_change_candidates_data,
    )

    result = DisplayBomMcpClient._call_local_analysis_tool(
        "analyze_design_change_candidates",
        {
            "request": {
                "version_code": "LTA400HR01-001",
                "plant_code": "P01",
            },
            "actions": [{
                "action_type": "REPLACE",
                "target_item_name": "SEALANT",
            }],
        },
    )

    assert result["analysis_id"] == "ANA-LOCAL-TEST"
    assert captured["request"]["version_code"] == "LTA400HR01-001"
    assert captured["actions"][0]["action_type"] == "REPLACE"


def test_unknown_tool_cannot_enter_local_analysis_dispatch():
    try:
        DisplayBomMcpClient._call_local_analysis_tool(
            "apply_approved_change_request",
            {},
        )
    except ValueError as error:
        assert "Unsupported local analysis Tool" in str(error)
    else:
        raise AssertionError("protected Tool unexpectedly entered local analysis path")
