"""LLM provider abstraction layer for Gatekeeper.

Gatekeeper is designed to run **local-first** on an open model served by
Ollama (default: ``qwen2.5:7b``), with a hosted-API fallback (OpenAI) that can
be enabled purely through configuration. Small local models are less reliable
at structured tool-calling, so for live demos we need the ability to switch
backends with an env var and *zero* code changes.

This module provides that seam:

* :class:`ChatResponse` — a provider-agnostic response envelope. Whatever the
  backing SDK returns, downstream code always sees ``text`` (str),
  ``tool_calls`` (a list of ``{"name": str, "arguments": dict}``) and ``raw``
  (the untouched provider payload, for debugging).
* :class:`LLMProvider` — the abstract interface every backend implements.
* :class:`OllamaProvider`, :class:`OpenAIProvider`, :class:`MockProvider` —
  concrete backends. ``MockProvider`` is deterministic and network-free so
  tests and CI never need a live model.
* :func:`get_provider` — factory keyed by the ``LLM_PROVIDER`` env var.

A critical asymmetry this module hides: Ollama returns tool-call ``arguments``
as an already-parsed ``dict``, while OpenAI returns them as a JSON *string*.
:func:`normalize_arguments` accepts both and always yields a ``dict``, so no
caller ever has to care which backend produced the response.

This module is a generic, reusable LLM layer — it contains no
Gatekeeper-specific business logic.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "ChatResponse",
    "LLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "MockProvider",
    "get_provider",
    "normalize_arguments",
]

DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def normalize_arguments(arguments: Any) -> dict:
    """Coerce a tool-call ``arguments`` payload into a real ``dict``.

    The two SDKs disagree on the type of ``arguments``:

    * Ollama returns an already-parsed ``dict`` — passed through unchanged.
    * OpenAI returns a JSON ``str`` — parsed with :func:`json.loads`.

    A malformed or empty string, a JSON payload that is not an object, or any
    other unexpected type falls back to ``{}`` rather than raising; the
    original provider payload is always preserved in ``ChatResponse.raw`` for
    debugging.

    Args:
        arguments: The raw ``arguments`` value from a provider tool call.

    Returns:
        A ``dict`` of tool-call arguments (possibly empty).
    """
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}
        try:
            parsed = json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class ChatResponse(BaseModel):
    """Provider-agnostic response from a single chat completion.

    Attributes:
        text: The assistant's textual reply (empty string if the model only
            returned tool calls).
        tool_calls: Tool invocations requested by the model, normalized to
            ``[{"name": str, "arguments": dict}]``. Empty list if none.
        raw: The untouched provider response payload, for debugging.
    """

    text: str
    tool_calls: list[dict] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)

    @field_validator("tool_calls")
    @classmethod
    def _validate_tool_calls(cls, value: list[dict]) -> list[dict]:
        """Enforce the ``{"name": str, "arguments": dict}`` shape.

        ``arguments`` is run through :func:`normalize_arguments`, so a JSON
        string sneaking in here still comes out as a ``dict``.
        """
        normalized: list[dict] = []
        for call in value:
            name = call.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"tool call missing a string 'name': {call!r}"
                )
            normalized.append(
                {"name": name, "arguments": normalize_arguments(call.get("arguments"))}
            )
        return normalized


class LLMProvider(ABC):
    """Abstract chat-completion backend.

    Concrete subclasses adapt one SDK (Ollama, OpenAI, ...) to a single
    normalized interface so the rest of Gatekeeper never touches
    provider-specific response shapes.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send a chat conversation and return the normalized response.

        Args:
            messages: Conversation history as
                ``[{"role": "system|user|assistant|tool", "content": str}]``.
                Extra keys on a message dict (e.g. ``tool_call_id``, ``name``)
                are passed through to the provider unmodified — later phases
                rely on them to return tool results.
            tools: Optional list of tool schemas (OpenAI-style function
                schemas). Accepted by every provider even if it ignores them.
            temperature: Sampling temperature.
            **kwargs: Provider-specific extras, passed through when supported.

        Returns:
            A :class:`ChatResponse` with normalized ``text`` and
            ``tool_calls``, plus the raw provider payload.
        """


class OllamaProvider(LLMProvider):
    """Local backend using the ``ollama`` Python client.

    Reads ``OLLAMA_MODEL`` and ``OLLAMA_HOST`` from the environment (with
    sensible defaults) unless explicit values are given.
    """

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        """Initialize the client.

        Args:
            model: Model tag to use; defaults to ``$OLLAMA_MODEL`` or
                ``qwen2.5:7b``.
            host: Ollama server URL; defaults to ``$OLLAMA_HOST`` or
                ``http://localhost:11434``.
        """
        import ollama

        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        self.host = host or os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
        self._client = ollama.Client(host=self.host)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send the conversation to Ollama and normalize the reply.

        Ollama may omit the ``tool_calls`` key entirely when the model makes
        no tool call; that case yields an empty list. Ollama's ``arguments``
        are already a ``dict`` and are passed through unchanged.
        """
        options = {"temperature": temperature, **kwargs.pop("options", {})}
        response = self._client.chat(
            model=self.model,
            messages=messages,
            tools=tools,
            options=options,
            **kwargs,
        )

        # ollama>=0.4 returns a pydantic model; older versions return a dict.
        raw: dict = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )
        message = raw.get("message") or {}
        tool_calls = [
            {
                "name": call["function"]["name"],
                "arguments": normalize_arguments(call["function"].get("arguments")),
            }
            for call in (message.get("tool_calls") or [])
        ]
        return ChatResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            raw=raw,
        )


class OpenAIProvider(LLMProvider):
    """Hosted-API fallback backend using the ``openai`` SDK.

    The ``openai`` package is an *optional* dependency in this phase; if it is
    not installed, or ``OPENAI_API_KEY`` is not set, construction fails with a
    message naming exactly what is missing and how to fix it.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        """Initialize the client.

        Args:
            model: Model name; defaults to ``$OPENAI_MODEL`` or
                ``gpt-4o-mini``.
            api_key: API key; defaults to ``$OPENAI_API_KEY``.

        Raises:
            RuntimeError: If the ``openai`` package is not installed or no
                API key is available.
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAIProvider requires the 'openai' package, which is not "
                "installed. Install it with: pip install openai "
                "(or set LLM_PROVIDER=ollama to use the local model)."
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OpenAIProvider requires an API key but OPENAI_API_KEY is not "
                "set. Add it to your .env file "
                "(or set LLM_PROVIDER=ollama to use the local model)."
            )

        self.model = model or os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self._client = OpenAI(api_key=key)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> ChatResponse:
        """Send the conversation to OpenAI and normalize the reply.

        OpenAI returns tool-call ``arguments`` as a JSON *string*; it is
        parsed into a ``dict`` here (falling back to ``{}`` on malformed
        input, with the original preserved in ``raw``).
        """
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        if tools:
            request["tools"] = tools
        response = self._client.chat.completions.create(**request)

        raw: dict = response.model_dump()
        message = (raw.get("choices") or [{}])[0].get("message") or {}
        tool_calls = [
            {
                "name": call["function"]["name"],
                "arguments": normalize_arguments(call["function"].get("arguments")),
            }
            for call in (message.get("tool_calls") or [])
        ]
        return ChatResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            raw=raw,
        )


class MockProvider(LLMProvider):
    """Deterministic, network-free backend for tests and CI.

    Always returns the same canned reply. When ``tools`` is passed, it also
    echoes one fixed tool call (with ``arguments`` already a ``dict``) so
    downstream tool-handling code can be exercised deterministically.
    """

    CANNED_TEXT = "MOCK: READY."
    CANNED_TOOL_CALL = {"name": "mock_tool", "arguments": {"echo": "mock"}}

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> ChatResponse:
        """Return the canned response; no network involved.

        Args:
            messages: Accepted (and recorded in ``raw``) but not interpreted.
            tools: If truthy, the response includes ``CANNED_TOOL_CALL``.
            temperature: Ignored.
            **kwargs: Ignored.
        """
        tool_calls = [dict(self.CANNED_TOOL_CALL)] if tools else []
        return ChatResponse(
            text=self.CANNED_TEXT,
            tool_calls=tool_calls,
            raw={"mock": True, "messages": messages, "tools": tools or []},
        )


def get_provider(name: str | None = None) -> LLMProvider:
    """Build the provider selected by ``name`` or the ``LLM_PROVIDER`` env var.

    Args:
        name: One of ``"ollama"``, ``"openai"``, ``"mock"`` (case-insensitive).
            When ``None``, reads ``LLM_PROVIDER`` from the environment,
            defaulting to ``"ollama"``.

    Returns:
        A ready-to-use :class:`LLMProvider` instance.

    Raises:
        ValueError: If the resolved name is not a known provider.
    """
    resolved = (name or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()
    if resolved == "ollama":
        return OllamaProvider()
    if resolved == "openai":
        return OpenAIProvider()
    if resolved == "mock":
        return MockProvider()
    raise ValueError(
        f"Unknown LLM provider {resolved!r}. "
        "Valid values for LLM_PROVIDER are: ollama, openai, mock."
    )
