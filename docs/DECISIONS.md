# Gatekeeper — Decision log

Architecture decisions, in the order they were made, with the evidence behind
each one. Written so that someone who was not present can audit the reasoning
and, if they disagree, know exactly which measurement to rerun.

Raw data for every spike referenced here is committed under `evals/`.

---

## ADR-001 — A provider abstraction, local-first with a hosted fallback

**Date:** 2026-07-24 · **Commit:** `f7ff509` · **Status:** accepted

Gatekeeper targets a local open model (Ollama, `qwen2.5:7b`) so it can run
on-premises, but a live demo cannot depend on an unproven small model. All LLM
access therefore goes through `provider.py`, which normalizes Ollama, OpenAI,
and a deterministic mock behind one interface selected by the `LLM_PROVIDER`
environment variable.

The layer hides one asymmetry that would otherwise leak everywhere: Ollama
returns tool-call `arguments` as a parsed `dict`, OpenAI as a JSON *string*.
`ChatResponse.tool_calls[].arguments` is always a real `dict`.

---

## ADR-002 — Tool-call ids are preserved; malformed arguments are never silent

**Date:** 2026-07-25 · **Commit:** `76396d6` · **Status:** accepted

Two corrections to ADR-001:

1. Normalized tool calls carry `id`. OpenAI requires the original call id
   echoed back on the `role="tool"` result message; without this the agent loop
   would have to reach into `ChatResponse.raw` with provider-specific
   knowledge, defeating the abstraction. Ollama emits no ids, so `id` is `None`
   there — never synthesized.
2. `ChatResponse.malformed_tool_calls` flags any `arguments` payload that had
   to fall back to `{}`. Previously, unparseable arguments were
   indistinguishable from a correct call with no arguments. In an agent whose
   product is a verdict, that difference is the difference between "scored on
   no evidence" and "scored correctly", and it would have been invisible.

An empty payload (`{}`, `""`, or absent) is *not* malformed — Ollama routinely
omits the key.

---

## ADR-003 — Native tool-calling measured before building on it (Phase 1.5)

**Date:** 2026-07-24 · **Commit:** `2ce12d3` · **Status:** superseded in part by ADR-004

The whole local-first premise rested on an unmeasured assumption about small
models and structured tool-calling. Thresholds were **pre-registered before the
run** so the result could not be rationalized afterwards.

Four scenarios, 10 trials each, `qwen2.5:7b` at temperature 0.2
(`evals/spike_toolcalling_20260724_214802.json`):

| Scenario | Result |
|---|---|
| A — obvious single tool | 10/10 fully valid |
| B — tool selection among two | 10/10 fully valid |
| C — no tool applicable | 0/10 false positives (perfect restraint) |
| D — rubric-shaped nested call | **0/10 fully valid** |

Verdict per the pre-registered table: **RED**.

Every scenario-D trial called the right tool with correct top-level fields
(`use_case`, `data_readiness=4`, `verdict="go"`) and then emitted
`rationale.paragraph` where the schema declared `rationale.summary`; one trial
also dropped `risks` entirely.

Two observations that shaped everything after:

- The prompt said *"give a one-paragraph summary"*. Prose vocabulary appeared
  to be overriding the schema key name.
- The failures were **not** flagged `malformed_tool_calls` — the JSON was
  well-formed. The model broke the schema *contract*, not the JSON *syntax*.
  These are different failure layers, and ADR-002's flag catches only the
  lower one.

---

## ADR-004 — The RED was a lexical collision, not nesting (Phase 1.6)

**Date:** 2026-07-25 · **Commit:** `a95f54a` · **Status:** accepted

Scenario D differed from the passing scenarios in **two** ways at once: it
introduced a nested object *and* a lexical collision between the prompt's prose
and a schema key. Those imply opposite fixes — flatten the schema permanently,
or merely fix the naming — so a 2×2 factorial was run to separate them, plus
two grammar-constrained arms as a mechanism baseline
(`evals/spike_schema_shape_20260725_074944.json`, 10 trials per arm).

| Arm | Shape | Prose | Mechanism | Fully valid | Failures |
|---|---|---|---|---|---|
| D1 | nested | clean | native tools | 80% | 2 × `no_call` |
| D2 | nested | colliding | native tools | **0%** | 6 × `key_renamed`, 4 × `rationale` emitted as a string |
| D3 | flat | colliding | native tools | 100% | — |
| D4 | flat | clean | native tools | 90% | 1 × `no_call` |
| S1 | nested | clean | `format=` JSON schema | 100% | — |
| S2 | flat | clean | `format=` JSON schema | 100% | — |

**Replication check passed:** D2 reproduced Phase 1.5 scenario D verbatim at 0%,
so the harness is comparable to the baseline.

### Why the pre-registered pattern table did not match

The script printed `PATTERN UNMATCHED` and, per protocol, withheld a
conclusion. D1 at 80% was too low for the "lexical collision" row (needs ≥90%)
and too high for the "nesting" row (needs <70%).

The table did not match because the `fully-valid` metric **collapsed two
independent failure layers into one number**:

1. **Call emission** — did the model invoke the tool at all? (`no_call`)
2. **Key fidelity, given a call** — was the payload's key structure correct?

These have different causes and different fixes, and averaging them produces a
number that answers neither question. Re-scoring the same trials on layer 2
alone — key fidelity *conditioned on a call having been emitted* — resolves it
immediately:

| Arm | Fully valid / calls emitted |
|---|---|
| D1 nested + clean | 8/8 = **100%** |
| D2 nested + colliding | 0/10 = **0%** |
| D3 flat + colliding | 10/10 = **100%** |
| D4 flat + clean | 9/9 = **100%** |

That is exactly pre-registered row 1 — D1 and D4 both ≥90%, D2 <70% — giving:

> **CAUSE = LEXICAL COLLISION. Nesting is safe.** The Phase 2 fix is schema-key
> naming hygiene plus prompts that never use a near-synonym of a key.

The re-scoring is a *re-analysis of the same trials on a pre-existing recorded
field*, not a new metric invented to rescue a result: the per-trial
`failure_class` was recorded before the run, precisely so failures could be
separated by kind.

Layer 1 tells a separate story: native tool arms lost calls (D1 20%, D4 10%)
while the `format=` arms structurally cannot — there is no tool to fail to call.

### Statistical caveat — take these numbers with the right amount of salt

At n=10 per arm, most of these differences are not distinguishable. 95% Wilson
intervals:

| Observed | 95% interval |
|---|---|
| 0/10 | 0.00 – 0.28 |
| 8/10 | 0.49 – 0.94 |
| 9/10 | 0.60 – 0.98 |
| 10/10 | 0.72 – 1.00 |

So 8/10, 9/10 and 10/10 are **not** statistically distinguishable from one
another; their intervals overlap heavily. **Only D2's 0/10 is distinguishable**
— its interval is disjoint from every other arm's.

What this permits and forbids:

- **Supported:** the collision effect is real. D2 (0%) versus D1/D3/D4
  (80–100%) is far outside noise, and the mechanism is directly observable in
  the recorded payloads (`summary` → `paragraph`).
- **NOT supported by the statistics:** that `format=` (100%) is more reliable
  than native tools (80–90%). That gap is within noise at this n.

The decision to use `format=` for the payload therefore rests on a
**categorical** argument, not the observed percentages: with no tool offered,
`no_call` is structurally impossible, and grammar-constrained decoding forces
the output to match the schema rather than merely encouraging it. If a
statistically supported claim about the mechanism is needed for publication,
rerun the S and D arms at n≥100.

---

## ADR-005 — Hybrid architecture: constrained JSON for payloads, native tools for control flow

**Date:** 2026-07-25 · **Commits:** `cf9b041`, `666d991` · **Status:** accepted

Following ADR-004, each mechanism is used for what it demonstrably does well:

- **The scoring payload is produced by constrained JSON generation**
  (`response_schema` → Ollama `format=`), never by native tool arguments.
- **Native tools are reserved for flat control-flow decisions** — which action
  to take, when to score. Never a nested payload in tool arguments.
- **Nesting is safe** in the scoring schema, so it is designed for clarity.
- **Naming hygiene is mandatory.** `schemas.py` documents the near-synonyms
  that prompts must never use for each field.

`provider.py` enforces the split: passing `tools` and `response_schema` in the
same call raises `ValueError`. They are alternative channels — `format=`
constrains message content, tool schemas constrain tool-call arguments — and
silently accepting both would reintroduce exactly the ambiguity ADR-004 was run
to eliminate.

---

## ADR-006 — The rubric lives in YAML, not in Python

**Date:** 2026-07-25 · **Commit:** `666d991` · **Status:** accepted

Weights, anchors, verdict bands, and gate thresholds live in `rubric.yaml`;
`config.py` only loads and validates them. This costs a validation layer up
front and buys two things: a domain expert can retune Gatekeeper without
touching code, and the same case can be scored against several rubric
configurations without a commit per experiment — which is what makes rubric
sensitivity analysis tractable.

The cost is that a malformed config could reach the scorer, so validation is
deliberately aggressive and fails at import time: weights must sum to 1.0,
every level needs an anchor, bands must tile the scale with no gap or overlap,
ids must be unique, and the gate must name a real dimension.

An OT-specific variant (adding e.g. `process_criticality` and
`false_positive_cost`) is an alternative YAML file, not a code change.

---

## ADR-007 — The model scores dimensions; Python computes and decides

**Date:** 2026-07-25 · **Commit:** this phase · **Status:** accepted

The LLM never does arithmetic and never picks the verdict. It supplies
per-dimension scores plus evidence; `scoring.py` computes the weighted total
and applies the bands.

`schemas.Assessment` deliberately contains **no verdict field and no total
field**, and a test walks the generated JSON Schema recursively to prove it.
Offering a model a verdict field invites it to choose the conclusion first and
reason the dimensions backwards to justify it — the same bias that
pre-registering the spike thresholds was meant to prevent on the human side.

This is what makes a verdict defensible. Asked "why No-Go?", you can point at
the exact line of arithmetic and the exact sentence of evidence behind it.

---

## ADR-008 — Not-AI is a gate, never a band

**Date:** 2026-07-25 · **Commit:** this phase · **Status:** accepted

`not_ai` is an override evaluated *before* the verdict bands, fired by a
hard-blocking anti-pattern or by a high enough raw score on
`non_ai_alternative`. It is not the bottom of the score range.

A use case can score 4.10 and still be Not-AI because a SQL query already
solves it — a case covered directly by a test. If Not-AI were merely a low
band, that case would come out as **Go**, which is precisely the error the
product exists to prevent.

`config.py` enforces this structurally: `VerdictBand.verdict` is typed
`Literal["go", "no_go"]`, so a config that tries to make `not_ai` reachable
through a band is rejected at load time.

Gates are also evaluated *before* the completeness check, because they are
positive findings — learning that a rule already solves the problem is enough
to stop, even with half the interview unanswered.

---

## ADR-009 — Unknowns are recorded, never invented

**Date:** 2026-07-25 · **Commit:** this phase · **Status:** accepted

A dimension the interview could not establish is recorded as `None`. Up to
`completeness.max_unknown_dimensions` may be unknown and still produce a
verdict, with the remaining weights renormalized to sum to 1.0. Above that
limit the scorer returns `incomplete` with the list of what is missing, rather
than a verdict computed from a mostly-empty interview.

Related: every LLM-facing model sets `extra="forbid"`. In the Phase 1.5
scenario-D failures the model emitted a perfect `verdict="go"` while the
rationale evaporated. Under a lax validator, Gatekeeper would have emitted a Go
verdict with no justification and nobody would have noticed. That is the worst
available failure mode for an agent whose entire product is the verdict.

---

## ADR-010 — Gates are a general mechanism, not a Not-AI special case

**Date:** 2026-07-25 · **Commit:** Phase 2.1 Part A · **Status:** accepted ·
**Supersedes:** the `not_ai_gate` block introduced in ADR-008

### The defect

ADR-008 built the gate mechanism for `not_ai` alone. Review of Phase 2 found
two further conditions that are categorical rather than gradual, and which
therefore fell through to the bands where their weights are far too small to
stop them. Both are demonstrable arithmetic, not a matter of taste.

**A use case with no data at all scored `go`.** With `data_maturity` at raw 1
and every other dimension at its best:

```
economic_impact       5 x 0.25 = 1.25
process_frequency     5 x 0.15 = 0.75
data_maturity         1 x 0.20 = 0.20   <- the entire penalty
implementation_effort (6-1)=5 x 0.15 = 0.75
regulatory_risk       (6-1)=5 x 0.10 = 0.50
non_ai_alternative    (6-1)=5 x 0.15 = 0.75
                              total = 4.20  -> go
```

`data_does_not_exist_yet` had been left advisory on the reasoning that it would
"depress `data_maturity` and land in `no_go` through the bands". It cannot:
0.20 of weight cannot offset 4.00 from everywhere else.

**A use case with maximum regulatory exposure scored `go`.**
`regulatory_risk` carries the smallest weight in the rubric (0.10), so the
whole distance from "embarrassing and reversible" to "legal force,
protected-class exposure, irreversible harm, a regulator must approve" is a
0.40 swing. An otherwise strong case totals 4.60 and passes. Gatekeeper would
have greenlit a use case a regulator has to approve.

### The general principle

**No weighted average can express "this is disqualifying."** A weight small
enough to be fair to an ordinary case is too small to stop an extreme one, and
a weight large enough to stop the extreme case distorts every ordinary one.
When a condition is binary, it belongs in a gate, not in the weights.

### The fix

`not_ai_gate` is generalized into a `blocking_gates` list in `rubric.yaml`.
Each gate declares an `id`, the `verdict` it forces, a `precedence`, a
human-readable `reason`, and `any_of` conditions — either a dimension threshold
(`at_least` / `at_most`) or a reference to hard-blocking anti-patterns.

Three gates ship:

| Gate | Condition | Forces |
|---|---|---|
| `not_ai_alternative_suffices` | `non_ai_alternative` ≥ 4, **or** any hard-blocking anti-pattern | `not_ai` |
| `no_usable_data` | `data_maturity` ≤ 1 | `no_go` |
| `unacceptable_regulatory_exposure` | `regulatory_risk` ≥ 5 | `no_go` |

Design constraints, each enforced at config-load time:

- A gate may force only `no_go` or `not_ai` — **never** `go`. Gates stop cases;
  they do not wave them through.
- **Precedence is explicit in config, not implicit in evaluation order.**
  `not_ai` (1) outranks `no_go` (2): if a rule already solves it *and* the data
  does not exist, the useful answer is still "this is not an AI problem". Every
  gate that fired is reported; the lowest precedence decides.
- **A gate cannot fire on an unknown dimension.** An unknown is not evidence,
  and letting it fire a gate would defeat the purpose of recording it as
  unknown. The dimension is reported in `unknown_dimensions` as usual.
- Evaluation order is unchanged: gates → completeness → bands.
- Deleting a gate from `rubric.yaml` restores band behaviour for that
  condition, with no code change.

### `data_does_not_exist_yet` stays advisory

It remains `hard_block: false` in `patterns.yaml`, with its `better_alternative`
documenting that `no_usable_data` is what actually stops it. Hard-blocking it
would route a genuine AI use case whose only problem is *sequencing* into
`not_ai` — "never" instead of "not yet". The gate sends it to `no_go`, which
is the correct verdict and leaves the door open to re-triage once the data
exists. One line of YAML to reverse if that judgement is wrong.

### Consequence for `Outcome`

`triggered_gates` changes from `list[str]` to `list[TriggeredGate]`, carrying
the gate id, forced verdict, precedence, config `reason`, the `detail` of what
actually fired it (e.g. "data_maturity scored 1, at most 1"), and any
contributing anti-pattern ids. `Outcome.triggered_gate_ids` gives the plain id
list. This is a wider change than the phase brief implied; it was taken so the
outcome stays self-explaining now that a gate can produce two different
verdicts for several different reasons.
