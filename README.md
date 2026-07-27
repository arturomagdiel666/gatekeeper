# Gatekeeper

Gatekeeper triages incoming requests for AI agents against a rubric, returns
**Go / No-Go / Not-AI / Incomplete**, and — when it approves — issues a
Measurement Contract defining what failure would look like and when the agent
will be reviewed against it.

## The problem

Requests for AI arrive already shaped as solutions: not "invoice reconciliation
takes three people four days" but "we want an AI agent for invoices". They get
approved on enthusiasm, because there is no cheap way to tell a business owner
no and no agreed definition of failure to point at later. Nothing is ever
retired, because retirement requires an argument nobody wants to have. The queue
grows, capacity does not, and the worst-founded request is often the loudest.

## What it does

Structured intake states the facts a decision needs. Seven rubric dimensions,
each scored 1–5 on a single stated axis. Blocking gates evaluated before the
weighted bands, because a prohibition cannot be expressed as a weight.
`Incomplete` names which fields are missing rather than guessing them. On `Go`,
a Measurement Contract fixes the success metric, the instrumentation and the
review date, and `review.py` later judges the running agent against it with no
model involved.

## What the measurement showed

The system was scored against a reference built from two independent assessors,
keeping only slots where they agreed, across three passes each on two model
sizes.

**Rubric slots computed from a stated intake field reach κw = 0.97 against the
reference and are identical across a doubling of model size.** Slots scored by
the model reach **κ ≈ 0.04 — chance** — while reproducing their own answers at
**κw = 0.37.** The model is not noisy. It is reproducibly wrong: it holds a
stable position that is not the rubric's, so lowering its temperature would
change nothing.

**The displacement's direction belongs to the model, not the rubric.** On
`implementation_effort` the median signed error is **+1 on the 7B and −1 on the
14B**, on the same cases. Tripling the parameter count moved model-scored
self-consistency from 33% to 34%, and produced seven false approvals where the
smaller model had one — because it stopped refusing.

Applying the tool's own `non_ai_alternative` criterion to Gatekeeper's own
scoring function returns **`Not-AI`**. The instrument, pointed at itself, says
do not build this with AI — and the architecture the evidence supports is that
the model finds and quotes evidence while the form and the tables decide.

## Run it

Requires Python 3.12 and [Ollama](https://ollama.com) with `ollama pull
qwen2.5:7b`. The test suite needs neither.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest                  # 429 tests, no model, no network
streamlit run app.py    # the demo; the Triage tab has an offline checkbox
```

## What is honest about it

Thirty synthetic cases, written by one author. **Both assessors were language
models, not humans**, so "inter-rater agreement" here means agreement between
two model sessions given the same rubric — a weaker claim than the term usually
carries. Reliability is measured across six runs; **validity is not measured at
all.** The accurate dimensions depend on intake fields a requester fills in, and
the two assessors would have filled 8 and 11 of those 30 fields differently from
how they are stated. Whether the rubric measures anything worth measuring is
untested.

## Repository map

| Path | Contents |
|---|---|
| `assess.py`, `scoring.py`, `contracts.py`, `review.py` | The pipeline: one constrained call, then deterministic scoring, contract and review |
| `provider.py`, `schemas.py`, `config.py` | Model layer, structured types, validated config loading |
| `rubric.yaml`, `patterns.yaml`, `contracts.yaml`, `review_policy.yaml` | Everything that decides anything. See `docs/RUBRIC.md` |
| `app.py` | Streamlit demo |
| `tools/` | The measurement instruments: chance-corrected agreement, bias shape |
| `scripts/` | Corpus runners and the reference measurement harness |
| `evals/` | Blind case corpus, scorer files, and every raw measurement output |
| `evaluacion/` | The study write-ups, in Spanish and English. **This copy is the source of truth**; an older copy exists outside the repository and is no longer maintained |
| `docs/DECISIONS.md` | ADR-001..033 — why it is shaped this way, with the measurement that forced each change |
| `tests/` | 429 tests, all offline |
