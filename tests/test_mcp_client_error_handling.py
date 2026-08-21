import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import mcp_client.client as client_module
from mcp_client.client import DisplayBomMcpClient


def test_tool_business_error_is_raised_after_mcp_contexts_close(monkeypatch):
    events = []

    @asynccontextmanager
    async def fake_stdio_client(_server_params):
        try:
            yield object(), object()
        except BaseException as error:
            events.append(("stdio_exit", type(error)))
            raise
        else:
            events.append(("stdio_exit", None))

    class FakeClientSession:
        def __init__(self, _read, _write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, _exc_value, _traceback):
            events.append(("session_exit", exc_type))

        async def initialize(self):
            return None

        async def call_tool(self, _tool_name, *, arguments):
            assert arguments == {"old_material_id": "0001-310101"}
            return SimpleNamespace(
                is_error=True,
                content=[SimpleNamespace(
                    text=(
                        "Error executing tool analyze_design_change: "
                        "기존 자재와 신규 자재는 달라야 합니다."
                    )
                )],
            )

    monkeypatch.setattr(client_module, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(client_module, "ClientSession", FakeClientSession)

    client = DisplayBomMcpClient()

    with pytest.raises(RuntimeError, match="기존 자재와 신규 자재는 달라야"):
        asyncio.run(client._call_tool(
            "analyze_design_change",
            {"old_material_id": "0001-310101"},
        ))

    assert events == [
        ("session_exit", None),
        ("stdio_exit", None),
    ]
