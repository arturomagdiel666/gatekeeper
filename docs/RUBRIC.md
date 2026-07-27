# The rubric, the gates, and how to tune them

Moved out of the README when the repository was published, so the README could
stay readable in three minutes. Nothing here has been edited.


## What the rubric measures

Seven dimensions, each scored 1–5, each measuring **exactly one axis** (stated
in `rubric.yaml` above its anchors):

| Dimension | Axis | Direction | Weight |
|---|---|---|---|
| `business_value` | Magnitude of the benefit, annualized | higher | 0.22 |
| `adoption_risk` | Likelihood users will not change how they work | lower | 0.17 |
| `data_readiness` | Data exists, is obtainable, output is judgeable | higher | 0.15 |
| `process_frequency` | Instance volume per year | higher | 0.13 |
| `implementation_effort` | Total cost to production | lower | 0.13 |
| `data_governance` | Whether the data may be processed at all | lower | 0.10 |
| `non_ai_alternative` | How completely a non-AI solution suffices | lower | 0.10 |

A `lower is better` score is flipped (`6 - raw`) before weighting, so 5 always
means "good". Totals ≥ **3.5** are `go`.

`adoption_risk` is deliberately second-heaviest: internal tools fail because
nobody changes their behaviour, not because the technology fails.
`data_governance` and `non_ai_alternative` carry the lowest weights **because
both are gated at their extremes** — their weight only expresses the
non-extreme gradient. Don't raise them without removing their gates.

### Blocking gates override the bands

A weighted sum cannot express a prohibition: every dimension in an average is
compensable, so a weight fair to an ordinary request is too small to stop an
extreme one. Categorical conditions are gates, evaluated before the bands:

| Gate | Fires when | Forces | Precedence |
|---|---|---|---|
| `existing_capability_covers_it` | anti-pattern `existing_licensed_capability` | `not_ai` | 10 |
| `non_ai_alternative_suffices` | `non_ai_alternative` ≥ 4, or another hard-block anti-pattern | `not_ai` | 20 |
| `no_named_business_owner` | intake `business_owner` empty | `no_go` | 30 |
| `no_usable_data` | `data_readiness` ≤ 1 | `no_go` | 40 |
| `unacceptable_data_governance` | `data_governance` ≥ 5 | `no_go` | 50 |

With every other dimension at its best, `data_readiness = 1` totals 4.40 and
`data_governance = 5` totals 4.60 — both inside the `go` band, both stopped by
a gate. A gate never fires on a dimension left unknown, and can never force a
`go`.

Dimensions the request does not establish are recorded as unknown, never
guessed. More than one unknown returns `incomplete` naming exactly what is
missing — which is what replaces the clarifying questions a conversational
interview would have asked.

## Tuning it without writing code

Everything that decides anything is YAML:

| File | Controls |
|---|---|
| `rubric.yaml` | Dimensions, anchors, weights, bands, blocking gates |
| `patterns.yaml` | Archetypes and anti-patterns, including which hard-block |
| `contracts.yaml` | Candidate metrics, review horizons, instrumentation, triggers |
| `review_policy.yaml` | Thresholds, each trigger's recommendation, next-review intervals |

The **assessment prompt is generated from `rubric.yaml` and `patterns.yaml`**,
anchors included verbatim — so tuning the rubric tunes the prompt, and there is
no second copy to drift. Anchors matter more than weights: they are what make
two assessors score the same request the same way. Keep them observable
("about one quarter, two or three teams") not vague ("medium effort").

Config is validated at import time and a broken file fails immediately. Run
`pytest` after editing — the suite checks every invariant and includes
hand-computed worked examples that catch an accidental weight change.

## How it fits together

| File | Role |
|---|---|
| `provider.py` | Generic LLM layer: Ollama / OpenAI / mock, tool calls and constrained JSON |
| `config.py` | Loads and validates the rubric and patterns |
| `schemas.py` | Intake, the model's structured output, and the contract |
| `assess.py` | One constrained call → parse → score → contract |
| `scoring.py` | Pure deterministic scoring: gates → completeness → bands |
| `contracts.py` | Deterministic Measurement Contract assembly |
| `review.py` | Pure review policy — **no LLM anywhere** |
| `examples/` | Six reference exemplars, anchor-faithful |
| `docs/DECISIONS.md` | ADR-001..019: why it is shaped this way, with the measurements |

The model scores dimensions and cites evidence. It never computes a total and
never picks a verdict — that is what makes a Gatekeeper decision defensible
when someone asks "why No-Go?".
