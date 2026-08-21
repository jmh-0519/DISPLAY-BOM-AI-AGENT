from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.observability import (
    LangfuseObservability,
    summarize_messages,
    summarize_text,
    summarize_value,
)
from core.azure_openai_client import AzureOpenAIClient


class FakeManager:
    def __init__(self, observation):
        self.observation = observation

    def __enter__(self):
        return self.observation

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_missing_environment_disables_langfuse(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    observability = LangfuseObservability()

    assert observability.enabled is False
    with observability.observe("request") as span:
        span.finish(output=summarize_text("answer"))


def test_observation_records_summaries_latency_and_error_type():
    delegate = Mock()
    client = Mock()
    client.start_as_current_observation.return_value = FakeManager(delegate)
    observability = LangfuseObservability(client=client)

    with observability.observe(
        "azure-openai.chat-completion",
        as_type="generation",
        input_summary=summarize_messages([{"role": "user", "content": "secret"}]),
        model="deployment",
    ) as generation:
        generation.finish(
            output=summarize_text("private answer"),
            usage_details={"input": 2, "output": 3, "total": 5},
        )

    start_kwargs = client.start_as_current_observation.call_args.kwargs
    assert start_kwargs["as_type"] == "generation"
    assert start_kwargs["input"] == {
        "type": "messages",
        "message_count": 1,
        "roles": {"user": 1},
        "tool_call_count": 0,
    }
    update_kwargs = delegate.update.call_args.kwargs
    assert update_kwargs["usage_details"]["total"] == 5
    assert update_kwargs["output"]["character_count"] == 14
    assert update_kwargs["metadata"]["duration_ms"] >= 0

    delegate.reset_mock()
    with pytest.raises(RuntimeError):
        with observability.observe("mcp.tool"):
            raise RuntimeError("sensitive database detail")
    failure = delegate.update.call_args.kwargs
    assert failure["level"] == "ERROR"
    assert failure["metadata"]["error_type"] == "RuntimeError"
    assert "sensitive database detail" not in str(failure)


def test_sensitive_fields_and_values_are_not_in_summaries():
    summary = summarize_value({
        "api_key": "key-value",
        "supplier": "supplier-name",
        "cost": 123,
        "status": "CONDITIONAL",
    })

    assert "api_key" not in summary["fields"]
    assert "key-value" not in str(summary)
    assert "supplier-name" not in str(summary)
    assert "123" not in str(summary)
    assert summary["status"] == "CONDITIONAL"


def test_azure_completion_is_recorded_as_generation():
    delegate = Mock()
    langfuse_client = Mock()
    langfuse_client.start_as_current_observation.return_value = FakeManager(delegate)
    observability = LangfuseObservability(client=langfuse_client)

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="answer", tool_calls=None,
        ))],
        usage=SimpleNamespace(
            prompt_tokens=10, completion_tokens=4, total_tokens=14,
        ),
    )
    azure = AzureOpenAIClient.__new__(AzureOpenAIClient)
    azure.settings = SimpleNamespace(azure_openai_deployment="deployment")
    azure.observability = observability
    azure.client = Mock()
    azure.client.chat.completions.create.return_value = response

    actual = azure._create_completion(
        model="deployment",
        messages=[{"role": "user", "content": "private BOM request"}],
        temperature=0,
    )

    assert actual is response
    start = langfuse_client.start_as_current_observation.call_args.kwargs
    assert start["as_type"] == "generation"
    assert "private BOM request" not in str(start)
    update = delegate.update.call_args.kwargs
    assert update["usage_details"] == {"input": 10, "output": 4, "total": 14}

def test_only_allowed_status_values_are_recorded():
    allowed_summary = summarize_value({
        "status": "conditional",
        "result": "private BOM result",
        "success": True,
        "changeable": False,
    })

    assert allowed_summary["status"] == "CONDITIONAL"
    assert allowed_summary["success"] is True
    assert allowed_summary["changeable"] is False
    assert "result" not in allowed_summary
    assert "private BOM result" not in str(allowed_summary)

    unknown_summary = summarize_value({
        "status": "supplier ABC material discontinued",
    })

    assert "status" not in unknown_summary
    assert unknown_summary["status_present"] is True
    assert "supplier ABC" not in str(unknown_summary)
    

def test_agent_completion_allows_empty_tools_for_final_explanation():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content="근거를 설명합니다.", tool_calls=None,
        ))]
    )
    azure = AzureOpenAIClient.__new__(AzureOpenAIClient)
    azure.settings = SimpleNamespace(azure_openai_deployment="deployment")
    azure._create_completion = Mock(return_value=response)

    actual = azure.create_agent_completion(
        messages=[{"role": "user", "content": "왜 FAIL이야?"}],
        tools=[],
        skill_context="Explain skill",
    )

    assert actual is response.choices[0].message
    request = azure._create_completion.call_args.kwargs
    assert "tools" not in request
    assert "tool_choice" not in request
    assert request["temperature"] == 0
