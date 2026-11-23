"""Tests: Bedrock chat model construction (no network, client is lazy)."""

from app.config import Settings
from app.llm import get_chat_model


def test_chatbedrock_constructs_without_guardrail():
    model = get_chat_model(Settings(demo=False))
    assert model is not None


def test_chatbedrock_constructs_with_guardrail():
    model = get_chat_model(
        Settings(demo=False, bedrock_guardrail_id="gr-123")
    )
    assert model is not None
