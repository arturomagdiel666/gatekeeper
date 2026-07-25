"""Smoke test for the provider layer.

Loads .env, prints the active provider and model, sends a trivial prompt to
the real backing provider, and prints the reply.

Usage:
    python scripts/smoke_provider.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provider import get_provider  # noqa: E402


def main() -> int:
    """Run the smoke test; return a process exit code."""
    load_dotenv()

    provider = get_provider()
    model = getattr(provider, "model", "n/a (mock)")
    print(f"Provider: {type(provider).__name__}")
    print(f"Model:    {model}")
    print(f"LLM_PROVIDER env: {os.environ.get('LLM_PROVIDER', '(unset, default ollama)')}")

    print('Sending prompt: "Reply with the single word: READY."')
    response = provider.chat(
        [{"role": "user", "content": "Reply with the single word: READY."}]
    )
    print(f"Reply:    {response.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
