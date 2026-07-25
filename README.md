# Gatekeeper

An AI use-case triage agent. Gatekeeper interviews you about a raw
"add AI to X" request, scores it against an ROI rubric, and returns a
**Go / No-Go / Not-AI** verdict.

It runs **local-first** on an open model via [Ollama](https://ollama.com)
(default: `qwen2.5:7b`), with an optional hosted-API fallback (OpenAI)
selectable by an env var — no code changes required to switch.

> **Status: Phase 2** — provider layer, rubric, and deterministic scoring.
> The discovery interview, agent loop, and Streamlit UI come in Phases 3-5;
> `agent.py` and `app.py` are still placeholders.

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

## What the rubric measures

Six dimensions, each scored 1-5 by the interview and weighted into a single
total on the same 1-5 scale:

| Dimension | Measures | Weight | Direction |
|---|---|---|---|
| `economic_impact` | Size of the financial upside if it works | 0.25 | higher is better |
| `process_frequency` | How often the target process runs | 0.15 | higher is better |
| `data_maturity` | Whether usable data exists and is accessible | 0.20 | higher is better |
| `implementation_effort` | Build, integration, and change-management cost | 0.15 | lower is better |
| `regulatory_risk` | Compliance, privacy, and liability exposure | 0.10 | lower is better |
| `non_ai_alternative` | How well a rule or query would solve it instead | 0.15 | lower is better |

A `lower is better` score is flipped (`6 - raw`) before weighting, so 5 always
means "good for this use case". Totals at or above **3.5** are `go`, below are
`no_go`.

**`not_ai` is a gate, not a low score.** It is evaluated before the bands and
overrides them, fired by a hard-blocking anti-pattern from `patterns.yaml` or
by `non_ai_alternative` scoring 4 or above. A use case can total 4.10 and still
be Not-AI because a SQL query already solves it — catching exactly that case is
the point of the product.

A dimension the interview could not establish is recorded as unknown, never
guessed. One unknown is tolerated (remaining weights are renormalized); more
than that returns `incomplete` instead of a verdict.

## Tuning it without writing code

`rubric.yaml` and `patterns.yaml` are the source of truth and are meant to be
edited directly:

- **Weights** — must sum to exactly 1.0.
- **Anchors** — the one-line description of what each score of 1-5 means for a
  dimension. These matter more than the weights: they are what makes two
  different interviewers score the same case the same way. Keep them concrete
  and observable ("about one quarter, two or three teams to coordinate"), never
  vague ("medium effort").
- **Verdict bands** — must tile the 1.0-5.0 scale with no gap or overlap.
- **The Not-AI gate** — which dimension fires it and at what threshold.
- **Archetypes and anti-patterns** in `patterns.yaml`, including which
  anti-patterns `hard_block`.

Changing any of these changes verdicts with no Python edit. `config.py`
validates the files at import time and refuses to load a broken one, so run
`pytest` after editing — the suite checks every invariant and includes a
hand-computed worked example that will catch an accidental weight change.

To score against an alternative rubric (say an OT-specific variant), pass its
path to `load_rubric()`; no code change is needed.

## Running it

Smoke-test the provider — sends a trivial prompt and prints the reply:

```bash
python scripts/smoke_provider.py
```

The measurement spikes behind the architecture (see `docs/DECISIONS.md`) can be
re-run; results land in `evals/` as JSON:

```bash
python scripts/spike_toolcalling.py --trials 10    # native tool-calling reliability
python scripts/spike_schema_shape.py --trials 10   # schema shape vs. prompt prose
```

## Tests

```bash
pytest
```

All tests run offline with no model needed. The Ollama integration tests skip
automatically when no server is reachable at `OLLAMA_HOST`.

## How it is put together

| File | Role |
|---|---|
| `provider.py` | Generic LLM layer: Ollama / OpenAI / mock, tool calls and constrained JSON |
| `config.py` | Loads and validates `rubric.yaml` and `patterns.yaml` |
| `schemas.py` | The structured output the model produces — no verdict, no total |
| `scoring.py` | Pure deterministic scoring: weights, gates, bands, explanation |
| `docs/DECISIONS.md` | Why the architecture is shaped this way, with the measurements |

The model scores dimensions and cites evidence; Python does the arithmetic and
picks the verdict. That split is deliberate — see ADR-007 in
`docs/DECISIONS.md`.
