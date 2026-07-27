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

## The intake agent

> **The model asks. The form and the tables decide.**

That rule is not a preference — it is what the measurement above forced. So the
agent interviews the requester and never scores anything: it picks the single
question worth asking next, phrases it in their language, and pulls a value and a
verbatim span out of the reply. `score_and_gate()` takes a `RequestIntake` and
has no parameter a model-produced number could arrive through, and a test fails
if one ever does.

Six blocking gates override the weighted bands, the last of them added because
the measurement demanded it: **`unacceptable_adoption_risk`** stops a request
where nobody whose work changes was consulted, it replaces a way of working they
chose, and more than twenty people must change — a combination that used to be
approved at 3.68 because a weight of 0.17 cannot express a prohibition.

It asks gate-deciding questions first, because one answer can end the
conversation. It stops when a gate fires, when no remaining question can change
the verdict, when two answers in a row add nothing, or when the budget runs out —
and it always says which. Every field it fills carries the turn and the words
that filled it.

**The interview now reaches approval.** Rubric v3.0.0 converted the last three
model-scored dimensions into derivations over stated facts, so all seven can be
resolved without a model touching a score, and eight questions take the reference
`go` exemplar to a verdict of 4.49 with a full Measurement Contract. What that
cost is a *relocation*: the judgement did not disappear, it moved to the
requester. Two of the three fields are biased toward approval and none is
verified by anyone before a verdict is issued. `docs/RELOCATION.md` names each
transfer, who now makes it, and what would make it wrong.

```bash
python scripts/demo_agent.py                    # offline, scripted, no model
python scripts/demo_agent.py --scenario go      # eight questions to an approval
python scripts/demo_agent.py --scenario gate    # a gate ends it in one question
python scripts/demo_agent.py --live --human     # answer it yourself
```

## Run it

Requires Python 3.12 and [Ollama](https://ollama.com) with `ollama pull
qwen2.5:7b`. The test suite needs neither. On Debian and Ubuntu the first
command fails unless `python3.12-venv` is installed — `apt install
python3.12-venv` first.

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest                  # 486 tests, no model, no network
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
| `agent.py`, `agent_tools.py` | The intake agent: the loop, and the deterministic tools it dispatches to |
| `app.py` | Streamlit demo — triage, intake agent, review simulator |
| `tools/` | The measurement instruments: chance-corrected agreement, bias shape |
| `scripts/` | Corpus runners and the reference measurement harness |
| `evals/` | Blind case corpus, scorer files, and every raw measurement output |
| `evaluacion/` | The study write-ups, in Spanish and English. **This copy is the source of truth**; an older copy exists outside the repository and is no longer maintained |
| `docs/RELOCATION.md` | Which judgements the conversion moved onto the requester, and what would make each wrong |
| `docs/DECISIONS.md` | ADR-001..035 — why it is shaped this way, with the measurement that forced each change |
| `runs/` | Saved interview transcripts, replayable |
| `tests/` | 486 tests, all offline |
