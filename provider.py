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
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

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


def _normalize_and_flag(arguments: Any) -> tuple[dict, bool]:
    """Return ``(normalized_arguments, was_malformed)``.

    ``was_malformed`` is ``True`` only when the fallback to ``{}`` lost
    information: malformed JSON, JSON that is not an object, or an unexpected
    type. Genuinely argument-less payloads — an empty dict, an empty or
    whitespace-only string, or ``None`` (Ollama may omit the key entirely) —
    are *not* malformed. Every malformed fallback emits a ``logging`` warning
    with the offending payload (truncated) and its type.
    """
    if isinstance(arguments, dict):
        return arguments, False
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}, False
        try:
            parsed = json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            _warn_malformed(arguments)
            return {}, True
        if isinstance(parsed, dict):
            return parsed, False
        _warn_malformed(arguments)
        return {}, True
    if arguments is None:
        return {}, False
    _warn_malformed(arguments)
    return {}, True


def _warn_malformed(arguments: Any) -> None:
    """Log a warning about a tool-call arguments payload we had to discard."""
    logger.warning(
        "Malformed tool-call arguments (type %s) replaced with {}: %.200r",
        type(arguments).__name__,
        arguments,
    )


def normalize_arguments(arguments: Any) -> dict:
    """Coerce a tool-call ``arguments`` payload into a real ``dict``.

    The two SDKs disagree on the type of ``arguments``:

    * Ollama returns an already-parsed ``dict`` — passed through unchanged.
    * OpenAI returns a JSON ``str`` — parsed with :func:`json.loads`.

    A malformed string, a JSON payload that is not an object, or any other
    unexpected type falls back to ``{}`` rather than raising — with a logged
    warning, and providers surface it via
    :attr:`ChatResponse.malformed_tool_calls`. The original provider payload
    is always preserved in ``ChatResponse.raw`` for debugging.

    Args:
        arguments: The raw ``arguments`` value from a provider tool call.

    Returns:
        A ``dict`` of tool-call arguments (possibly empty).
    """
    return _normalize_and_flag(arguments)[0]


class ChatResponse(BaseModel):
    """Provider-agnostic response from a single chat completion.

    Attributes:
        text: The assistant's textual reply (empty string if the model only
            returned tool calls).
        tool_calls: Tool invocations requested by the model, normalized to
            ``[{"name": str, "arguments": dict, "id": str | None}]``. Empty
            list if none. ``id`` carries the provider's tool-call id (OpenAI
            requires it echoed back on the ``role="tool"`` result message);
            Ollama does not emit one, so it is ``None`` there — never
            synthesized.
        malformed_tool_calls: ``True`` when any tool call's ``arguments``
            payload was malformed (unparseable JSON, non-object JSON, or an
            unexpected type) and had to fall back to ``{}``. Downstream code
            must not treat such a response as a clean argument-less call;
            ``raw`` always holds the original payload for forensics.
        raw: The untouched provider response payload, for debugging.
    """

    text: str
    tool_calls: list[dict] = Field(default_factory=list)
    malformed_tool_calls: bool = False
    raw: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_tool_calls(self) -> "ChatResponse":
        """Enforce the ``{"name": str, "arguments": dict, "id": ...}`` shape.

        ``arguments`` is run through the normalization helper, so a JSON
        string sneaking in here still comes out as a ``dict`` — and if that
        re-normalization hits a malformed payload, ``malformed_tool_calls``
        is set as well (a provider-set ``True`` is never cleared). ``id`` is
        preserved when it is a string and defaults to ``None``; genuinely
        unknown keys are stripped.
        """
        normalized: list[dict] = []
        malformed = self.malformed_tool_calls
        for call in self.tool_calls:
            name = call.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"tool call missing a string 'name': {call!r}")
            arguments, was_malformed = _normalize_and_flag(call.get("arguments"))
            malformed = malformed or was_malformed
            call_id = call.get("id")
            normalized.append(
                {
                    "name": name,
                    "arguments": arguments,
                    "id": call_id if isinstance(call_id, str) else None,
                }
            )
        self.tool_calls = normalized
        self.malformed_tool_calls = malformed
        return self


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
        are already a ``dict`` and are passed through unchanged, and Ollama
        does not emit tool-call ids, so ``id`` is always ``None``.
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
        tool_calls: list[dict] = []
        malformed = False
        for call in message.get("tool_calls") or []:
            arguments, was_malformed = _normalize_and_flag(
                call["function"].get("arguments")
            )
            malformed = malformed or was_malformed
            tool_calls.append(
                {"name": call["function"]["name"], "arguments": arguments, "id": None}
            )
        return ChatResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            malformed_tool_calls=malformed,
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
        input, flagged via ``malformed_tool_calls``, with the original
        preserved in ``raw``). The provider's ``tool_calls[].id`` is kept so
        tool results can be sent back with a matching ``tool_call_id``.
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
        tool_calls: list[dict] = []
        malformed = False
        for call in message.get("tool_calls") or []:
            arguments, was_malformed = _normalize_and_flag(
                call["function"].get("arguments")
            )
            malformed = malformed or was_malformed
            tool_calls.append(
                {
                    "name": call["function"]["name"],
                    "arguments": arguments,
                    "id": call.get("id"),
                }
            )
        return ChatResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            malformed_tool_calls=malformed,
            raw=raw,
        )


class MockProvider(LLMProvider):
    """Deterministic, network-free backend for tests and CI.

    Always returns the same canned reply. When ``tools`` is passed, it also
    echoes one fixed tool call (with ``arguments`` already a ``dict`` and the
    stable id ``"mock_call_1"``) so downstream tool-handling code can be
    exercised deterministically.
    """

    CANNED_TEXT = "MOCK: READY."
    CANNED_TOOL_CALL = {
        "name": "mock_tool",
        "arguments": {"echo": "mock"},
        "id": "mock_call_1",
    }

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
