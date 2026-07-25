# Gatekeeper

An AI use-case triage agent. Gatekeeper interviews you about a raw
"add AI to X" request, scores it against an ROI rubric, and returns a
**Go / No-Go / Not-AI** verdict.

It runs **local-first** on an open model via [Ollama](https://ollama.com)
(default: `qwen2.5:7b`), with an optional hosted-API fallback (OpenAI)
selectable by an env var — no code changes required to switch.

> **Status: Phase 1** — repository scaffold and the LLM provider layer only.
> The interview, rubric scoring, agent loop, and UI come in later phases.

## Setup

Requires Python 3.11+ and (for the default provider) Ollama running locally
with the `qwen2.5:7b` model available.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit if needed
```

`.env` settings:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Backend: `ollama`, `openai`, or `mock` |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Local model tag |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OPENAI_API_KEY` | — | Only used when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Fallback model name |

The `openai` package is not installed by default; `pip install openai` only
if you plan to use the fallback.

## Phase 1 smoke test

Sends a trivial prompt to the active provider and prints the reply:

```bash
python scripts/smoke_provider.py
```

## Tests

```bash
pytest
```

All tests run offline. The single Ollama integration test is skipped
automatically when no server is reachable at `OLLAMA_HOST`.
