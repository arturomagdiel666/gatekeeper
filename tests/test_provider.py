"""Tests for the provider abstraction layer (Phase 1).

Everything here runs without a live model except the final integration test,
which is skipped automatically when Ollama is not reachable.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

from provider import (
    ChatResponse,
    MockProvider,
    OllamaProvider,
    get_provider,
    normalize_arguments,
)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _ollama_reachable() -> bool:
    """Return True if an Ollama server answers at OLLAMA_HOST."""
    try:
        with urllib.request.urlopen(OLLAMA_HOST, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


class TestMockProvider:
    def test_chat_returns_chat_response_with_expected_text(self):
        response = MockProvider().chat([{"role": "user", "content": "hi"}])
        assert isinstance(response, ChatResponse)
        assert response.text == MockProvider.CANNED_TEXT
        assert response.tool_calls == []

    def test_chat_with_tools_echoes_fixed_tool_call(self):
        tools = [{"type": "function", "function": {"name": "anything"}}]
        response = MockProvider().chat([{"role": "user", "content": "hi"}], tools=tools)
        assert response.tool_calls == [MockProvider.CANNED_TOOL_CALL]
        assert isinstance(response.tool_calls[0]["arguments"], dict)


class TestGetProvider:
    def test_mock_by_name(self):
        assert isinstance(get_provider("mock"), MockProvider)

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="nope"):
            get_provider("nope")

    def test_reads_env_when_name_is_none(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        assert isinstance(get_provider(), MockProvider)


class TestChatResponseValidation:
    def test_tool_calls_default_to_empty_list(self):
        response = ChatResponse(text="hi")
        assert response.tool_calls == []
        assert response.raw == {}

    def test_tool_calls_normalized_to_name_arguments_shape(self):
        response = ChatResponse(
            text="",
            tool_calls=[{"name": "score", "arguments": {"value": 3}, "junk": "x"}],
        )
        assert response.tool_calls == [{"name": "score", "arguments": {"value": 3}}]

    def test_tool_call_without_name_rejected(self):
        with pytest.raises(ValueError):
            ChatResponse(text="", tool_calls=[{"arguments": {}}])

    def test_json_string_arguments_normalized_via_model(self):
        response = ChatResponse(
            text="",
            tool_calls=[{"name": "score", "arguments": '{"value": 3}'}],
        )
        assert response.tool_calls[0]["arguments"] == {"value": 3}


class TestNormalizeArguments:
    """The provider asymmetry: OpenAI sends a JSON string, Ollama a dict."""

    def test_openai_style_json_string_becomes_dict(self):
        assert normalize_arguments('{"city": "Xalapa", "days": 3}') == {
            "city": "Xalapa",
            "days": 3,
        }

    def test_ollama_style_dict_passes_through_unchanged(self):
        arguments = {"city": "Xalapa", "days": 3}
        assert normalize_arguments(arguments) == arguments

    def test_empty_string_falls_back_to_empty_dict(self):
        assert normalize_arguments("") == {}

    def test_malformed_json_falls_back_to_empty_dict(self):
        assert normalize_arguments('{"broken":') == {}

    def test_non_object_json_falls_back_to_empty_dict(self):
        assert normalize_arguments("[1, 2, 3]") == {}

    def test_none_falls_back_to_empty_dict(self):
        assert normalize_arguments(None) == {}


@pytest.mark.skipif(
    not _ollama_reachable(),
    reason=f"Ollama not reachable at {OLLAMA_HOST}",
)
class TestOllamaIntegration:
    """Runs only when a live Ollama server is available."""

    def test_chat_returns_text(self):
        provider = OllamaProvider()
        response = provider.chat(
            [{"role": "user", "content": "Reply with the single word: READY."}]
        )
        assert isinstance(response, ChatResponse)
        assert response.text.strip()
        assert isinstance(response.tool_calls, list)
        assert response.raw
