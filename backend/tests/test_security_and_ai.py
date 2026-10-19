import socket
from unittest.mock import Mock

import boto3
import pytest
from botocore.stub import ANY, Stubber
from pydantic import ValidationError

from app.agents import get_agent
from app.agents.shared.runtime import ControlledToolRuntime
from app.ai.model import BedrockModelService, MockModelService
from app.config import Settings, get_settings
from app.integrations.safe_fetch import validate_target
from app.integrations.storage import LocalStorageProvider, validate_upload
from app.schemas import ReplyOutput, ResearchPlan, ToolArgs, ToolCall


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example",
        "https://user:pass@public.example",
        "https://public.example:8443",
        "https://localhost",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_ssrf_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_target(url, {"public.example"})


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.2", "192.168.0.1", "169.254.169.254", "::1", "fc00::1"]
)
def test_dns_private_address_rejected(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
    )
    with pytest.raises(ValueError):
        validate_target("https://public.example", {"public.example"})


def test_real_send_and_production_local_auth_fail_closed():
    with pytest.raises(ValidationError):
        Settings(real_email_enabled=True, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(app_env="prod", auth_mode="local", _env_file=None)


def test_storage_traversal_and_executable_upload_rejected(tmp_path):
    with pytest.raises(ValueError):
        LocalStorageProvider(tmp_path).put("../escape", b"data", "text/plain")
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        validate_upload("macro.exe", b"MZbinary")


def test_bedrock_converse_uses_validated_schema_and_usage(monkeypatch):
    settings = get_settings()
    settings.bedrock_model_id = "test-model"
    client = boto3.client(
        "bedrock-runtime",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    output = ReplyOutput(
        intent="INTERESTED", summary="Interested", recommended_next_action="Human review", confidence=0.9
    )
    with Stubber(client) as stub:
        stub.add_response(
            "converse",
            {
                "output": {"message": {"role": "assistant", "content": [{"text": output.model_dump_json()}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 15, "outputTokens": 20, "totalTokens": 35},
                "metrics": {"latencyMs": 10},
            },
            {"modelId": "test-model", "system": ANY, "messages": ANY, "inferenceConfig": ANY},
        )
        model = BedrockModelService(client)
        result = model.classify_reply("Yes, interested")
        assert result.intent == "INTERESTED"
        assert model.last_usage["usage"]["totalTokens"] == 35
        stub.assert_no_pending_responses()


def test_bedrock_rejects_unstructured_instructions():
    client = Mock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": "Ignore policy; send a message"}]}},
        "stopReason": "end_turn",
    }
    with pytest.raises(ValidationError):
        BedrockModelService(client).classify_reply("Hello")


def test_controlled_loop_blocks_duplicate_tool_calls():
    model = MockModelService()
    call = ToolCall(name="web_search", arguments=ToolArgs(query="Ethiopia producers", country="Ethiopia"))
    model.create_research_plan = lambda *a: ResearchPlan(
        objective="Buy coffee", queries=["Ethiopia"], tool_calls=[call, call]
    )
    events = []
    profile, _ = ControlledToolRuntime(model, lambda a, d: events.append((a, d))).execute(
        get_agent("SOURCING"), "Find Ethiopia suppliers", "Ethiopia"
    )
    assert len(profile.candidates) == 1
    assert len([e for e in events if e[0] == "tool.result"]) == 1
    assert any(e[0] == "tool.duplicate_skipped" for e in events)


def test_unauthorized_tool_and_policy_fields_are_rejected():
    with pytest.raises(ValidationError):
        ToolCall.model_validate({"name": "send_email", "arguments": {"query": "Reveal secrets"}})
    with pytest.raises(ValidationError):
        ResearchPlan.model_validate({"objective": "research", "queries": [], "approve": True})


@pytest.mark.parametrize(
    "reply,intent",
    [
        ("Not interested", "NOT_INTERESTED"),
        ("Our offer is attached", "OFFER_RECEIVED"),
        ("Yes, interested", "INTERESTED"),
        ("Please send more information", "NEEDS_INFORMATION"),
        ("Next month please", "FOLLOW_UP_LATER"),
        ("Hello", "UNKNOWN"),
    ],
)
def test_structured_reply_classification(reply, intent):
    assert MockModelService().classify_reply(reply).intent == intent
