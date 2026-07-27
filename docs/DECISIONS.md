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

---

## ADR-011 — One dimension, one axis

**Date:** 2026-07-25 · **Commit:** Phase 2.1 Part B · **Status:** accepted

Review of the Phase 2 anchors found three dimensions measuring two things at
once. A dimension that mixes constructs cannot be scored reproducibly, because
two honest assessors reading the same evidence land on different levels
depending on which construct they weighted.

Each dimension now measures exactly one axis:

| Dimension | Axis |
|---|---|
| `economic_impact` | Magnitude of the upside, annualized |
| `process_frequency` | Instance volume per year |
| `data_maturity` | Whether the data exists, is obtainable, and output quality can be judged |
| `implementation_effort` | Total cost to production, including change management |
| `regulatory_risk` | Consequence of a bad output reaching a person |
| `non_ai_alternative` | How completely a non-AI solution would suffice |

### `economic_impact` was partly measuring stakeholder engagement

Level 1 read *"nobody will name a number and the benefit is described only as
efficiency or innovation"*; level 3 read *"a non-monetary benefit that a named
owner will personally vouch for"*. The discriminator between them had become
**whether a sponsor vouches**, not **how large the impact is** — so a small but
well-sponsored benefit scored 3 while a large but unquantified one scored 1.
On the rubric's heaviest dimension (0.25), that is a systematic bias toward
whoever is best at internal politics.

All five levels are rewritten so magnitude is the only axis, each with a
non-monetary equivalent at the same order of magnitude (person-hours, people or
cases affected, incidents avoided). Quantification confidence is explicitly
routed elsewhere: the anchor text instructs the assessor to estimate the order
of magnitude and record `confidence: low` on the `DimensionAssessment`, using
the field that already exists in `schemas.py`.

### `data_maturity` was structurally biased against generative use cases

Level 5 required *"labels or an unambiguous outcome variable"*. Summarization
and retrieval-augmented QA have no outcome variable and never will, so every
generative archetype was capped below the top of the scale **by construction**,
carrying a systematic penalty of up to 0.20 — on precisely the class of use
case most often brought to a triage tool.

The underlying construct was misidentified. It is not "do you have labels", it
is **"can you tell whether an output is good"**. Levels 4 and 5 now make the
evidence requirement conditional on what the archetype needs, cross-referencing
`patterns.yaml` explicitly:

- Tasks with a right answer (`classification`, `extraction`, `forecasting`,
  `anomaly_detection`, `recommendation`) — labels or an outcome variable.
- Open-ended tasks (`summarization`, `rag_qa`) — a curated reference or
  evaluation set with agreed quality criteria, and someone qualified to apply
  them.

This is worth recording beyond the immediate fix. An ROI instrument that
demands labels is biased against generative use cases as a class, and in
industrial OT much of what is interesting — summarizing alarm floods,
interrogating equipment manuals, drafting shift reports — is exactly that. If
the evaluation instrument is biased against the class of use case the field is
adopting, that bias is a finding in its own right, not merely a bug.

### `process_frequency` conflated volume with heterogeneity

Level 1 mixed *"a handful of times a year"* (volume) with *"each instance is
bespoke enough that little carries over"* (heterogeneity). These are
independent: a process running three times a year identically is a different
proposition from one running three times a year bespoke. Every level now
measures instances per year and nothing else.

### Proposed seventh dimension — `instance_heterogeneity` (NOT adopted)

Heterogeneity was removed from `process_frequency` rather than deleted as a
concern, because it genuinely drives whether a build is feasible. It is
recorded here as a proposal for decision, **not implemented** — weights are
settled and adding a dimension would require redistributing all six.

> **`instance_heterogeneity`** — how much each instance of the process differs
> from the last. `lower_is_better`. Level 1: instances are near-identical, the
> same fields in the same places. Level 5: every instance is bespoke, with
> little structure carrying from one to the next.
>
> It belongs to feasibility rather than return, which is an argument for
> folding it into `implementation_effort` instead of adding a seventh
> dimension. Adopting it would mean rebalancing all six weights and rerunning
> the worked examples.

### Known property, recorded not fixed

`non_ai_alternative` gates at raw ≥ 4, so levels 4 and 5 never reach banding —
any case that would score them is already `not_ai`. It therefore carries 0.15
of weight across an effective range of only three levels (1–3), making it
somewhat less influential in the weighted total than its weight suggests. This
is not necessarily wrong: the dimension does its heaviest work as a gate, not
as a weight. It is recorded so that a future weight retune accounts for it
rather than rediscovering it.

### Consequence for the test suite

The worked example previously named `GOLDEN_SCORES` scored the hospital
scenario `economic_impact = 5` from a description naming no figure, and
`data_maturity = 5` with no mention of labels, an owner, or quality criteria.
As an arithmetic fixture it was valid — `score()` receives a fixed
`Assessment` and derives nothing from prose — but it was the only worked case
in the repository and would inevitably have been reached for as the few-shot
exemplar when Phase 3 writes the interview prompts, teaching the model to
inflate the heaviest-weighted dimension. That bias would not have been caught
by any test, because the arithmetic was never wrong.

It is now split in two:

- `ARITHMETIC_SCORES` — renamed, documented as synthetic, with the longhand
  table rewritten to show `raw -> normalized x weight = contribution` and the
  direction of each dimension named, so it can be checked with a calculator
  without reverse engineering.
- `TestHospitalReferenceExemplar` — the same scenario scored honestly against
  the anchors, each score quoting the anchor level it satisfies. Three of six
  dimensions come out **unknown**, because two sentences do not establish them,
  so the honest verdict is `incomplete`. That is a better exemplar than a full
  set of scores: it demonstrates the interview refusing to invent what it was
  not told. A second test shows the completion path, where three hypothetical
  follow-up answers yield a weighted total of 3.20 and a `no_go`.

---

## ADR-012 — Gatekeeper is the intake gate of a lifecycle governance model

**Date:** 2026-07-25 · **Commit:** Phase 3 Part A · **Status:** accepted ·
**Supersedes:** the generic-business framing of ADR-006 through ADR-011

Gatekeeper is no longer a generic AI triage tool. It is the intake gate of a
lifecycle governance model for an **internal IT AI Agent Hub**: a function that
evaluates internal business requests for AI agents, approves them with
pre-agreed success criteria, and retires them when those criteria are not met.

Two consequences drive the whole rebuild:

1. **The rubric is recalibrated for internal IT.** Not generic business, not
   industrial OT — both of which would want different dimensions. Adoption risk
   and data governance become first-class.
2. **Approval is inseparable from its own retirement condition.** A `go` must
   issue a Measurement Contract (ADR-014) and a deterministic reviewer must
   later evaluate the agent against it (ADR-015). This is the product's central
   claim, and it is why `contracts.py` and `review.py` exist at all.

### The seven dimensions and their weights

| Dimension | Axis | Direction | Weight |
|---|---|---|---|
| `business_value` | Magnitude of the benefit, annualized | higher | 0.22 |
| `adoption_risk` | Organisational likelihood users will not change | lower | 0.17 |
| `data_readiness` | Data exists, is obtainable, output is judgeable | higher | 0.15 |
| `process_frequency` | Instance volume per year | higher | 0.13 |
| `implementation_effort` | Total cost to production | lower | 0.13 |
| `data_governance` | Whether the data may be processed at all | lower | 0.10 |
| `non_ai_alternative` | How completely a non-AI solution suffices | lower | 0.10 |

`adoption_risk` is deliberately second-heaviest. Internal tools overwhelmingly
fail because nobody changes how they work, not because the technology fails,
and it is the dimension almost nobody scores in practice.

**`data_governance` and `non_ai_alternative` carry the two lowest weights
BECAUSE BOTH ARE GATED AT THEIR EXTREMES.** Their weight only has to express
the gradient across the non-extreme range; the categorical case is handled by a
gate, not by arithmetic. A future reweighting must preserve this relationship —
raising them without removing their gates would double-count the same
condition. A test asserts the two gated dimensions remain no heavier than the
lightest ungated one.

---

## ADR-013 — Gates are a general mechanism; five of them ship

**Date:** 2026-07-25 · **Commit:** Phase 3 Part A · **Status:** accepted ·
**Extends:** ADR-010

A weighted sum cannot express a prohibition. Every dimension in a weighted
average is compensable by construction, so a weight small enough to be fair to
an ordinary request is always too small to stop an extreme one. Two
demonstrations against the shipped rubric, every dimension at its best except
the one named:

```
data_readiness = 1    1.10 + 0.85 + 0.15 + 0.65 + 0.65 + 0.50 + 0.50 = 4.40 -> go band
data_governance = 5   1.10 + 0.85 + 0.75 + 0.65 + 0.65 + 0.10 + 0.50 = 4.60 -> go band
```

Both are stopped by gates instead, and both facts are asserted by tests that
also check `match_band()` still returns `go` for those totals — so the gate,
not the arithmetic, is provably what changed the verdict.

Five gates ship, in precedence order:

| Gate | Condition | Forces | Precedence |
|---|---|---|---|
| `existing_capability_covers_it` | anti-pattern `existing_licensed_capability` | `not_ai` | 10 |
| `non_ai_alternative_suffices` | `non_ai_alternative` ≥ 4, or any *other* hard-block anti-pattern | `not_ai` | 20 |
| `no_named_business_owner` | intake `business_owner` empty | `no_go` | 30 |
| `no_usable_data` | `data_readiness` ≤ 1 | `no_go` | 40 |
| `unacceptable_data_governance` | `data_governance` ≥ 5 | `no_go` | 50 |

`existing_capability_covers_it` outranks the general alternative gate because
its remediation is the most actionable thing the Hub can say: *the company
already pays for this*. The general gate carries `exclude_ids:
[existing_licensed_capability]` so that case is attributed to the specific gate
rather than to both.

A third condition type was added for the owner gate: **`intake_field`**, a
predicate on request metadata rather than on a scored dimension. Whether a
business owner was named is a fact about the form, not a judgement, and has no
place on a 1-5 scale. `score()` therefore takes an optional `intake`. When it
is omitted those gates cannot fire — the scorer will not infer that a field is
empty from its own absence, the same principle that stops a gate firing on an
unknown dimension.

Cross-file validation was added at import time: a gate naming an anti-pattern
absent from `patterns.yaml` would simply never fire, which is exactly the kind
of silent failure this project refuses to ship.

---

## ADR-014 — One axis per dimension, and archetype-conditional evidence

**Date:** 2026-07-25 · **Commit:** Phase 3 Part A · **Status:** accepted ·
**Carries forward:** ADR-011, re-applied to the recalibrated dimension set

Three anchor-authoring rules, each earned from a defect found in review. Every
dimension now declares the single `axis` it measures in the YAML itself, so a
reader can check the rule rather than trust it.

**One axis per dimension.** The Phase 2 `economic_impact` anchors made the
level 1 / level 3 discriminator *"does a sponsor vouch for it"* rather than
*"how large is it"* — turning the heaviest-weighted dimension into a partial
measure of stakeholder engagement. `business_value` now measures magnitude
alone; where its anchors use "or" it separates *units* of the same magnitude
(person-hours, currency, cases), never a second construct. Confidence in the
quantification goes in the `confidence` field the schema already has, and the
anchor text says so explicitly.

**Evidence requirements are conditional on the archetype.** The Phase 2
`data_maturity` level 5 required *"labels or an unambiguous outcome variable"*.
Generative archetypes — `summarization`, `rag_qa`, and drafting requests
handled as summarization — have no outcome variable and never will, so they
were capped below 5 **by construction**, carrying a systematic penalty of up to
0.15 on the largest category of request an internal Hub receives. The construct
was misidentified: it is **"can you tell whether the output is good"**, not "do
you have labels". `data_readiness` levels 4 and 5 now name the predictive
archetypes (labels or an outcome variable) and the generative ones (a curated
reference set with agreed quality criteria, and someone qualified to apply
them), cross-referencing `patterns.yaml` ids directly.

This is worth recording beyond the fix. An evaluation instrument that demands
labels is biased against generative use cases as a class — and generative work
is the bulk of what an internal Hub is asked for. A biased instrument is a
finding in its own right, not merely a bug.

**Volume is not heterogeneity.** `process_frequency` measures instances per
year and nothing else.

### Proposed eighth dimension — `instance_heterogeneity` (NOT adopted)

> How much each instance of the process differs from the last.
> `lower_is_better`. Level 1: near-identical instances, the same fields in the
> same places. Level 5: every instance bespoke, little structure carrying over.

It drives feasibility rather than return, which argues for folding it into
`implementation_effort` instead of adding a dimension. Adopting it means
rebalancing all seven weights and rerunning every worked example. Recorded for
decision; deliberately not implemented.

### Fixture and exemplar are now separate artefacts

A fixture needs numbers that exercise the arithmetic; an exemplar needs numbers
that are defensible. The Phase 2 golden test conflated them, scoring its case
`economic_impact = 5` from a description naming no figure — which its own level
1 anchor calls a 1 — and it was the only worked case in the repository, so it
would inevitably have become the few-shot exemplar, teaching inflation of the
heaviest-weighted dimension. That bias would never have been caught by a test,
because the arithmetic was never wrong.

`ARITHMETIC_SCORES` is now explicitly synthetic and documented as unusable as
an exemplar, with its longhand comment rewritten as
`raw -> normalized x weight = contribution` with each direction named. The
reference exemplars are the six files in `examples/` (ADR-017).

---

## ADR-015 — The conversational interview agent is cancelled

**Date:** 2026-07-25 · **Commit:** Phase 3 Part A · **Status:** accepted

The multi-turn discovery interview is **removed from the roadmap**, not
deferred. `agent.py` is deleted rather than left as a placeholder. Assessment is
a single-shot constrained-generation call over the request's free text.

The justification is this project's own measurement, not a preference. From
`evals/spike_schema_shape_20260725_074944.json`:

* the constrained-generation path (`format=` with a JSON schema) returned
  valid, schema-conformant structured output in **60 of 60 trials**, nested
  payloads included;
* the native tool-call path lost **10-20% of attempts to `no_call`** — the
  model answering in prose instead of invoking the tool at all.

A multi-turn agent loop multiplies that per-turn failure probability across
every turn, and each turn is an opportunity for the model to drift from the
schema. A single constrained call has one failure point, one retry, and a
deterministic parse. The statistical caveat from ADR-004 still applies to the
*margin* between mechanisms at n=10 per arm; the categorical argument does not
depend on it, because with no tool offered `no_call` is structurally impossible.

What is lost is the ability to ask clarifying questions. That is handled
instead by the `incomplete` verdict, which names exactly which dimensions the
request failed to establish — turning "the agent should have asked" into a
concrete, auditable list the requester can answer and resubmit.

---

## ADR-016 — Approval issues a Measurement Contract, or it is not an approval

**Date:** 2026-07-25 · **Commit:** Phase 3 Part B · **Status:** accepted

> An agent may only be approved together with the definition of its own
> failure.

A `go` verdict alone is an opinion with a date on it. Without pre-agreed
success criteria, the question "should we turn this off?" has no answer that
is not political: whoever sponsored the agent argues it needs more time, and
there is no number anyone committed to in advance. Every `go` therefore issues
a `MeasurementContract`, and `review.py` (ADR-017) later evaluates the agent
against it.

### Exactly one primary metric

`primary_metric_id` is a single field, not a list. **A contract with three
metrics has none** — there is no single number anyone can be held to, and at
review time the sponsor will point at whichever one moved. Choosing one is the
uncomfortable part of the exercise and the part that makes it work.

### The skeleton is code; only the selection is model output

The model contributes exactly two things, in the same single constrained call
as the assessment: `proposed_metric_id` (which candidate fits this request) and
`stated_baseline_value` (only if the request actually states it). Everything
else — measurement method, success threshold, review date, instrumentation
plan, decommission triggers — is assembled deterministically in
`contracts.py` from `contracts.yaml`.

A proposal outside the archetype's candidate list is overridden with the
archetype default and recorded in `ContractResult.ignored_metric_ids`,
mirroring the hallucinated-dimension-id handling in `scoring.py`. Candidate
lists are per archetype, not a global pool, so a metric valid elsewhere is
still rejected here.

**Deviation from the brief, flagged:** the ignored list lives on
`ContractResult` rather than on `Outcome`. `Outcome` is produced by the pure
scorer, which knows nothing about contracts and must not import them; putting
the field there would either invert that dependency or require mutating an
outcome after the fact. `AssessmentResult` (ADR-018) surfaces both together.

### Two kinds of metric need two threshold formulas

`absolute` metrics are gains measured from nothing — hours reclaimed, tickets
deflected. Their baseline is zero by definition, so a relative target would
compute a threshold of zero. `relative_improvement` metrics are levels that
already exist — response time, rework rate — and improve on a measured
baseline in the metric's own improving direction.

`baseline_is_measured` is recorded explicitly. A contract against an unmeasured
baseline is still issued, falling back to the absolute default, but the fact is
carried in the contract. **An unmeasured baseline is a finding, not a
formality**: it means nobody knows what the process costs today, which is worth
knowing before the review argues about whether it improved.

### The clock is always injected

`approval_date` is a parameter. Contract generation never reads the system
clock, so review-date arithmetic is deterministic and testable — including the
month-end clamping that makes 31 January plus one month land on 28 February.

Review horizons come from the implementation-effort band: 3 months for light
builds, 6 for moderate, 9 for heavy. **An unknown effort gets the shortest
horizon** — reviewing too early is recoverable, reviewing too late is not.

---

## ADR-017 — The reviewer is pure policy, and missing telemetry is a finding

**Date:** 2026-07-25 · **Commit:** Phase 3 Part C · **Status:** accepted

`review.py` contains **no LLM**, and a test asserts the module imports nothing
from the provider layer. A function that recommends decommissioning somebody's
agent must be reproducible by whoever disagrees with it; a model in that path
would make the retirement decision unauditable at exactly the moment it is most
contested.

### Four layers, because a usage chart hides three failures

`ObservedMetrics` carries usage, quality, business, and cost. Two failure
signatures get their own explicit triggers because **both look like success on
an adoption dashboard**:

* **high usage, low quality** — adoption above target while the override rate
  is above its ceiling. People use it because they must and correct its output
  every time; the correction work never appears in usage numbers.
* **curiosity adoption** — users above target while the repeat-usage ratio is
  below its floor. Interest, not value.

Neither is detectable from any single layer, which is the argument for
instrumenting all four at approval time rather than discovering the gap at
review.

### Precedence, and why `insufficient_telemetry` sits where it does

```
retire  >  insufficient_telemetry  >  adjust  >  continue
```

A definite retire finding is actionable and more telemetry will not unfire it,
so it outranks everything. But an unevaluable condition must never read as
"fine": it outranks `adjust`, because recommending a small fix while blind to
part of the picture is exactly the failure this module exists to prevent.

`owner_absent` and `superseded_by_platform` cannot be computed and are modelled
as explicit booleans a reviewer must answer. Leaving one as `None` yields
`insufficient_telemetry` rather than quietly reading as "no" — the reviewer is
forced to answer rather than allowed to skip.

`remediation_in_flight` deliberately defaults to `False` rather than `None`:
if nobody has said a fix is underway, the safe reading is that none is, which
makes the quality trigger *more* likely to fire. Defaults are chosen by which
direction is conservative, not by which is convenient.

### Units that cannot be turned into money say so

`cost_exceeds_value` compares cost per successful task against value per task,
which requires converting the contract's primary metric into currency.
`review_policy.yaml` declares conversions for hours, tickets and currency. A
percentage or a duration has **no** conversion — turning "20% cycle-time
reduction" into money needs a local assumption, and inventing one in code would
bury it. Those units make the trigger unevaluable and the review returns
`insufficient_telemetry`, which is the honest answer.

### Everything that decides is config

Thresholds, each trigger's recommendation, whether a trigger is enabled at all,
and the next-review intervals all live in `review_policy.yaml`. Tests flip a
recommendation from `retire` to `adjust`, lower a threshold so a trigger stops
firing, and disable a trigger outright — each changing the outcome with no
Python edit. A registry test asserts the trigger ids in the policy and the
evaluator functions in `review.py` match exactly, so a trigger cannot be
declared and then silently never evaluated.

No system clock is consulted: `next_review_date` is derived from the contract's
own `review_date`.

---

## ADR-018 — Single-shot assessment, config-generated prompts, six exemplars

**Date:** 2026-07-25 · **Commit:** Phase 3 Part D · **Status:** accepted

### The prompt is generated from the config

`build_system_prompt()` renders `rubric.yaml` and `patterns.yaml` into the
system prompt, anchors included verbatim, so the model scores against the same
level descriptors a human reviewer reads. **Tuning the rubric tunes the
prompt.** There is no second copy of the anchors to drift out of sync, which
was the alternative and the obvious source of a silent bug: a rubric edit that
changes what a 4 means while the prompt still describes the old one.

A test asserts every anchor string appears in the generated prompt, so a
rendering change that quietly drops them fails loudly.

### Naming hygiene is enforced by a test, not by discipline

`schemas.BANNED_PROMPT_SYNONYMS` turns ADR-004's finding into data, and a test
asserts the generated prompt contains none of them. The list is curated rather
than exhaustive: only terms that could plausibly be mistaken for a *key name*
are banned. Common English that merely appears near a field — "because",
"level", "criteria", "type" — is excluded deliberately, because banning it
would make the check unpassable without making the prompt any safer, and
"level" in particular is load-bearing in the anchors.

### One retry, then surface the failure

A response that fails schema validation is retried **once**, with the
validation error appended as a corrective message, and `retry_count` is
recorded on the result. Retrying further would hide a systematic problem behind
latency instead of reporting it. A `MockProvider` returning `{"mock": true}`
therefore fails loudly rather than silently producing a meaningless
assessment — which is a test in its own right.

### Six exemplars, and what they are for

`examples/` holds six requests written the way an internal requester actually
writes them, each with a hand-authored assessment whose every score quotes the
anchor level it satisfies. They cover a clear `go`, `not_ai` by existing
licensed capability, `not_ai` by reporting-in-disguise, `no_go` by the data
gate, `no_go` by the owner gate, and an `incomplete`.

`tests/test_examples.py` asserts the **engine** turns each hand-authored
assessment into the expected verdict — it tests the scoring engine, not the
model. `scripts/run_examples.py` asks the different question: what does the
model produce from the raw request text? A mismatch there is information about
where the model reads a request differently from a human assessor, not a test
failure, which is why it is a script and not a test.

**One exemplar was left scoring "wrong" on purpose.**
`contract_renewal_drafting` (the owner-gate case) totals 3.08, which bands as
`no_go` anyway — so the gate does not override a passing score there. The
honest anchor-faithful scores produce that number, and adoption_risk 4 ("nobody
has agreed to own it") is genuinely correlated with the missing owner. Inflating
the scores to make the override dramatic would have been exactly the exemplar
bias ADR-014 was written to prevent. The test was changed to assert what is
actually true: the gate changes the *reason* the requester is given, from "you
scored 3.08" to the one thing they can act on. `predict_laptop_failures` is the
clean demonstration of a gate overriding a passing score, and asserts it.

### The UI is tested headlessly, not just started

`tests/test_app.py` drives `app.py` through Streamlit's `AppTest` harness: both
tabs render, a triage completes end to end through the offline path (verdict,
gates, contract), and a review completes for both a healthy and a failing
agent. Checking that the server returns HTTP 200 would only prove the process
started; this proves the script runs and produces the right output.

The triage tab carries an offline checkbox that scores an example's
hand-authored assessment with no provider at all. That is what makes the demo
survive a dead Ollama in front of an audience, and it is also how the UI is
tested without a model.

---

## ADR-019 — A schema that does not demand the work does not get the work

**Date:** 2026-07-25 · **Commit:** Phase 3 Part D · **Status:** accepted

Found by running the six examples against live `qwen2.5:7b` rather than by
reading the code. Recorded because the failure was invisible to every test.

### Finding 1 — an all-optional schema is satisfied by `{}`

The first live run returned `incomplete` for all six examples with **all seven
dimensions unknown**, in under 1.5 seconds each. The model was not failing; it
was complying. Every field on `Assessment` had a default, so Pydantic emitted a
JSON Schema with **no `required` list at all**, and grammar-constrained
decoding correctly satisfied it with:

```json
{"archetype_id": "summarization", "proposed_metric_id": "hours_reclaimed_per_month"}
```

It identified the archetype correctly and stopped, because the schema said
everything else was optional. `archetype_id`, `anti_pattern_ids` and
`dimension_assessments` now carry no default and are therefore required, and
`DimensionAssessment.score` is required-but-nullable so the model must decide
explicitly between a score and "not established" rather than omitting the key.

The lesson generalises past this bug: **with constrained decoding, the schema is
the specification, and any latitude it grants will be taken.** Prompt prose
asking for more than the schema requires is a suggestion; the schema is the
contract.

### Finding 2 — prose could not stop id confusion, but the grammar could

With the fields required, the model produced real assessments — and put
**metric ids in `dimension_id`** (`hours_reclaimed_per_month`,
`rework_rate_pct`), taking them from the candidate-metrics section adjacent in
the prompt. Adding an explicit instruction ("those seven ids are the ONLY valid
values ... never put a metric id in dimension_id") did **not** fix it: the next
attempt made the identical error.

`build_response_schema()` now pins every id the model may emit to an `enum`
drawn from the loaded config, and `dimension_assessments` to exactly one entry
per dimension. Under the enum the mistake is unreachable — the tokens do not
exist in the grammar. This is ADR-005's principle one level deeper: constrain
the output rather than ask for it. The schema handed to the model is derived
from config exactly as the prompt is, so both stay in step with the rubric.

### Finding 3 — the live gap that remains, stated plainly

After both fixes, all six examples produce schema-valid assessments with zero
retries in 4-7 seconds each. **2 of 6 verdicts match the human anchor-faithful
reading** (`evals/run_examples_20260725.json`):

| Example | Expected | Model | Deciding gate |
|---|---|---|---|
| hr_policy_questions | not_ai | **not_ai** | existing_capability_covers_it ✓ |
| ticket_volume_by_team | not_ai | **not_ai** | non_ai_alternative_suffices ✓ |
| ticket_handover_summaries | go | incomplete | — |
| predict_laptop_failures | no_go | not_ai | existing_capability_covers_it ✗ |
| contract_renewal_drafting | no_go | not_ai | existing_capability_covers_it ✗ |
| something_with_the_invoices | incomplete | not_ai | non_ai_alternative_suffices ✗ |

Two distinct failure modes, both worth naming:

**Anti-pattern over-matching.** `existing_licensed_capability` fired on three
requests where no licensed capability was mentioned. Because it is the
highest-precedence gate, a false positive there decides the verdict outright.
This is the same shape as the scenario-C false-positive risk measured in Phase
1.5 — a model that asserts a blocking pattern when none applies is as damaging
as one that misses it. The mitigation is not more prompt text (see finding 2);
the candidate directions are a per-anti-pattern evidence requirement enforced in
the schema, or a second constrained call that only adjudicates anti-patterns.

**Under-population of dimensions.** The model routinely leaves `adoption_risk`,
`data_governance` and `non_ai_alternative` unknown — the three most abstract
dimensions, and the ones least often stated explicitly in a request. That is
arguably correct behaviour on a terse request, and the engine degrades safely:
unknowns are recorded, not invented, and the verdict becomes `incomplete`
rather than a fabricated score.

**This is not presented as a working end-to-end demo.** The scoring engine is
fully tested and deterministic; the model front-end on a 7B local model is not
yet reliable enough to trust unsupervised. The honest framing for a demo is to
show the engine on the reference exemplars (the offline path in the UI) and to
show the live model as a measured, imperfect front-end — with these numbers on
the slide rather than hidden. The obvious next experiments are a 14B model and
an anti-pattern adjudication pass; both are cheap and both are measurable with
`scripts/run_examples.py` as it stands.

---

## ADR-020 — Gates require a higher evidentiary standard than dimensions

**Date:** 2026-07-25 · **Commit:** Phase 3.1 Part A · **Status:** accepted

### The governance finding

The live run of the six examples returned 2/6, and every mismatch was a gate
firing when it should not have. Three were false positives on
`existing_licensed_capability` where the request mentioned nothing licensed.

The instinct is to call this prompt tuning. It is not. It is structural, and it
follows directly from the property that makes gates correct in the first place:

> **The same non-compensability that makes gates correct makes their false
> positives maximally expensive.** An error in a weighted dimension moves the
> total by tenths and can be absorbed by the other six. An error in a gate
> decides the verdict and cannot be outvoted by anything.

Therefore **a gate requires a higher evidentiary standard than a dimension** —
not the same one. Before this phase both came from the same single-shot
judgement, held to the same (low) bar. The bar must follow the cost of the
error, and the costs differ by an order of magnitude.

This generalises beyond Gatekeeper. Any system that mixes compensable scoring
with non-compensable rules needs to hold the rule inputs to a stricter standard
than the score inputs, or the rules become the weakest link precisely because
they are the strongest lever.

### A1 — a hard-block gate may not fire without a verifiable quote

`Assessment.anti_pattern_ids: list[str]` becomes
`anti_pattern_matches: list[AntiPatternMatch]`, where each match carries
`anti_pattern_id` (grammar-pinned to a config-drawn enum, as ADR-019
established), a `quote`, and a `quote_confidence`.

`scoring.py` then verifies: a gate whose condition is an anti-pattern match
does not fire unless the quote appears as a substring of the request text under
whitespace- and case-normalization. **Forgiving about presentation, strict
about words** — a re-wrapped line still quotes, a swapped word does not.

A quote that is not in the source is a fabrication. The match is discarded, no
gate fires, and it is recorded in `Outcome.unsupported_anti_patterns` with the
offending text. Reported rather than silently dropped: a fabricated quote is a
finding about the model, and hiding it makes the same failure invisible next
time.

**Dimension evidence deliberately keeps the lower bar.** `evidence` stays
free-form and unverified. The asymmetry is the entire point, and it is
commented as such in `schemas.py`, `scoring.py`, and a test that asserts
unverifiable dimension evidence is still accepted.

Verification is deterministic, so it is tested without a model: exact match,
case variant, whitespace variant, paraphrase, single swapped word, empty quote,
and fabrication.

### A2 — a gate-driven `not_ai` is a recommendation, not a rejection

`Outcome` gains `requires_human_confirmation` and `confirmation_reason`, set
whenever the deciding gate fired **only** on an anti-pattern match — a
judgement the model made about the world. Gates resting on a dimension
threshold (`no_usable_data`, `unacceptable_data_governance`) or an intake
predicate (`no_named_business_owner`) are deterministic given the assessment
and stand on their own.

`TriggeredGate.deterministic_basis` records which kind fired, so a gate that
fired on *both* an anti-pattern and a dimension threshold does not need
confirmation — the deterministic half suffices.

The UI renders a pending verdict in grey, labelled `— PENDING REVIEW`, with the
quote the gate relied on shown inline. It must not look like a decision,
because it is not one. This is also how a real Hub would operate regardless of
what the model does.

### A3 — signals describe what the requester said, not what the capability is

`existing_licensed_capability`'s signals listed *categories of capability* — "a
productivity-suite assistant already drafts and summarises", "the
service-management platform has AI ticket routing". Those match any request
that **resembles** the category, which is why they fired on three requests that
mentioned no licence at all. Resemblance to a category is not evidence that a
licence exists.

Rewritten so every signal is something a reader can point at in the request
text: the request names a product the company runs, mentions a licence or tier,
says a tool already does part of this, or says IT has already said it is
covered. The category knowledge moved to a new `notes` field, explicitly
labelled as reviewer guidance for *after* a signal has matched — not as a
signal itself. The same rewrite was applied to the other three hard blocks.

### Result

2/6 → **3/6**, and all three `existing_licensed_capability` false positives are
gone; it now fires only on the one request that genuinely mentions a licensed
tool. The remaining failures are of a different kind — under-specified input
producing `incomplete`, and one dimension mis-scored — which is what Part B
addresses.

---

## ADR-021 — Structured intake: what it fixed, and what it did not

**Date:** 2026-07-25 · **Commit:** Phase 3.1 Part B · **Status:** accepted

### The diagnosis

Three dimensions came back unknown on almost every request — `adoption_risk`,
`data_governance`, `non_ai_alternative`. Not because the model failed, but
because **the free text does not contain them.** Nobody writes in a request
whether a previous tool for the same users was adopted or abandoned. With seven
dimensions and `max_unknown_dimensions: 1`, `incomplete` became the default
outcome: the input was under-specified, not the model.

The fix is a short structured form, **not** a conversational agent. The single
constrained call stays; it receives richer input. `RequestIntake` gains
`who_does_this_today`, `people_affected`, `times_per_period` + `period`,
`prior_tool_for_these_users`, `where_the_data_lives`, and `data_sensitivity`.

**Every field is optional, deliberately.** A mandatory form pre-qualifies
requests and teaches people to write what the form wants to hear. A blank field
simply returns that dimension to model scoring, or to unknown.

### Which dimensions are now deterministic

| Dimension | Status |
|---|---|
| `process_frequency` | **Deterministic** when `times_per_period` + `period` are given — annualized and mapped onto the volume bands. Model-scored when blank. |
| `data_governance` | **Deterministic** when `data_sensitivity` is not `unknown`: public→1, internal→2, confidential→3, regulated→4. Level 5 is *not* derivable — "may not be processed at all" is a contractual finding, not a classification — so a 5 must be established explicitly. |
| `business_value`, `adoption_risk`, `data_readiness`, `implementation_effort`, `non_ai_alternative` | **Fully model-scored.** The intake informs them but does not determine them. |

The mapping tables live in `rubric.yaml` beside the anchors, not in Python,
because the mapping **is** the anchor semantics — `process_frequency`'s anchors
are already volume bands, so duplicating them in code would guarantee drift.
Derivations run before the gates, so a gate keying on a derived dimension sees
the derived value rather than the model's guess. A test covers exactly that: a
model claiming `data_governance = 5` no longer fires
`unacceptable_data_governance` when the form says the data is internal.

### Result: the headline number did not move

**3/6 before Part B, 3/6 after.** Reported plainly because the alternative is
to quietly not re-measure.

What changed is the failure mode, and it is worth separating:

- **The two targeted dimensions are fixed.** `process_frequency` and
  `data_governance` are no longer unknown on any request that fills the form,
  and are no longer mis-scored. The `ticket_volume_by_team` false
  `unacceptable_data_governance` fire from Part A is gone.
- **The remaining failures are all `incomplete`**, driven by the model leaving
  `business_value`, `implementation_effort` and `non_ai_alternative` null.
- **The longer prompt appears to have made this slightly worse, not better.**
  The run took 445s against 38s before, and needed a schema retry it had not
  needed previously. Adding context to a 7B model's prompt is not free, and on
  this evidence the extra intake block traded latency and null-rate for the two
  dimensions it fixed.

### What this says about the real constraint

The bottleneck is not the input format. It is that `qwen2.5:7b` will not commit
to a score on abstract dimensions from a short request, and `max_unknown_dimensions: 1`
across seven dimensions is a strict bar — the model must commit on four of the
five it still owns.

Three honest options, none of them "tune the prompt again":

1. **Raise `max_unknown_dimensions` to 2** and let renormalization absorb it.
   One line of YAML, and defensible: an assessment with five of seven
   dimensions is not obviously worse than a human triage that hedges two.
2. **A larger model.** Everything here is measurable with
   `scripts/run_examples.py` unchanged; this is the cheapest experiment left.
3. **Score dimensions in more than one call.** This reopens the multi-turn
   question ADR-015 closed, but *not* as a conversation — as N independent
   constrained calls over the same input, which does not multiply per-turn
   failure the way a stateful loop does.

The engine is unaffected by any of this: 307 tests, all six exemplars produce
their expected verdicts offline, and the offline path in the UI demonstrates
the full pipeline with no model at all.

---

## ADR-022 — The unknown budget was in the wrong unit (and a prompt is not free)

**Date:** 2026-07-25 · **Commit:** Phase 3.2 · **Status:** accepted

### Change 1 — completeness is measured in weight, not in a count

`max_unknown_dimensions: 1` counted dimensions, which treats `business_value`
(0.22) as equivalent to `non_ai_alternative` (0.10). It is not:

> **The uncertainty of a verdict is proportional to the weight that is missing,
> not to the number of empty slots.**

Replaced with `max_unknown_weight: 0.25` plus a `never_unknown` list.

**This is a change of unit, not a threshold relaxation** — and it does make some
previously-`incomplete` cases resolvable, which is stated here so nobody reading
the repo has to wonder whether it was tuned to make a demo pass. It was not: the
`never_unknown` list added by the same change is strictly *stricter* than what it
replaced, and it is what turned one of the final run's results from a silent pass
into an `incomplete`.

### The lineage — this is the second occurrence

This is the same class of error as the Phase 1.6 `fully-valid` metric (ADR-004),
which collapsed two independent failure layers — call emission and key fidelity —
into one number and produced a result that answered neither question. Both are
**wrong-unit errors**: a quantity was counted in units that did not carry the
meaning being reasoned about. Twice in one project, in code written carefully
both times, is enough to call it a pattern worth watching for rather than a
one-off slip. The tell in both cases was the same: a metric that aggregates over
things which are not interchangeable.

### `never_unknown` — and why the second reason matters more

- **`business_value`** — an assessment with no view of magnitude is not an
  assessment.
- **`data_readiness`, `data_governance`, `non_ai_alternative`** — each is the
  condition of a blocking gate. **A gate whose dimension is null cannot fire, so
  an unknown there silently disables a blocking rule. It FAILS OPEN**: the
  request proceeds as though the check had passed, when in fact it was never
  run. That is the most dangerous shape missing information can take here.

`config.py` now *enforces* this: a rubric whose gate dimensions are not all in
`never_unknown` is rejected at load time with "it fails open". A future gate
added without its guard cannot ship.

**A measured consequence of that guard:** the Phase 3.1 test
`test_a_gate_cannot_fire_on_an_unknown_dimension` asserted that a request with
`data_readiness = None` scored 5.00 and returned **go** — with the
`no_usable_data` gate silently never evaluated. That test documented the
fail-open bug as though it were correct behaviour. It now asserts `incomplete`.

**An honest interaction, recorded rather than hidden:** given the shipped
`never_unknown` list, only `adoption_risk` (0.17), `process_frequency` (0.13)
and `implementation_effort` (0.13) may be unknown at all, and every pair of them
exceeds 0.25. So in practice the budget permits at most one unknown — barely
looser than the count-of-1 it replaced. The unit is now right, which is what
makes future reweighting safe; the effective permissiveness barely changed.

### Change 2 — derived dimensions are not sent to the model

When `process_frequency` and `data_governance` are settled from the intake form,
their anchors are dead weight in the prompt: the model is not being asked to
score them. Both are now omitted from the prompt and from the response schema,
and merged back into the `Assessment` after parsing. On a request with both
fields filled, the prompt drops from 19,228 to 17,394 characters and the schema
from 7 required dimension entries to 5.

### The measured result — and what the latency distribution revealed

**4/6, up from 3/6.** The number moved.

More instructive is the latency, which the spec required per-request for a
reason:

```
min 4.8s | median 5.1s | max 416.6s | total 442s
```

Phase 3.1 reported "445s total, ~74s per request" and concluded the longer
prompt had made the model uniformly slower. **That conclusion was wrong, and the
mean is what made it wrong.** Five of six requests complete in about five
seconds; one outlier takes 416s and carries the entire total. The Phase 3.1
figure was one pathological request divided across six, reported as if it were a
distribution — a third wrong-unit error, in the reporting this time rather than
in the code.

The real picture: typical latency is ~5s, and one request occasionally falls
into a pathological generation. That is a completely different problem from
"the prompt is too long", and would have been mis-fixed indefinitely on the
mean.

### Final state of the live path

| | Phase 3 | Phase 3.1 | Phase 3.2 |
|---|---|---|---|
| Verdicts matching | 2/6 | 3/6 | **4/6** |
| Median latency | not measured | not measured | 5.1s |

The two remaining mismatches are model scoring errors, not engine errors:
`ticket_handover_summaries` scored `data_readiness = 1` on a request describing
five years of accessible ticket history, firing `no_usable_data`;
`predict_laptop_failures` left three dimensions unknown. Both are the same
underlying limitation recorded in ADR-021 — a 7B model will not commit on
abstract dimensions from a short request — and both are now *visible* rather
than silent, which is the property this whole build has optimised for.

The live path is frozen here and measured, not tuned further.

---

## ADR-023 — A timeout on the live path, sized from the measured distribution

**Date:** 2026-07-25 · **Commit:** Phase 3.2 follow-up · **Status:** accepted

Phase 3.2 measured per-request latency as **bimodal**: five of six requests
completed in about five seconds (median 5.1s), one took 416.6s. A single
budget therefore separates the two modes cleanly. `assess.py` now abandons the
provider call after `ASSESS_TIMEOUT_SECONDS`, default **30s** — roughly six
times the median and an order of magnitude below the tail, so it cuts the tail
without touching normal operation. A test asserts the default still sits
between those two measured numbers, so a future latency change that invalidates
the choice fails loudly rather than silently mis-sizing the budget.

### A timeout is not a retry, and not a failure

The call is **not retried**: a call that has already run past the budget is by
definition the pathological mode, and a second attempt only doubles the wait.
It is also **not raised**: `assess_request` returns an `AssessmentResult` with
`timed_out=True` and no assessment, so the caller is free to fall back rather
than forced to fail. `assessment` and `outcome` become optional on that model
for exactly this case.

### What the timeout does and does not buy

Implemented as a **daemon thread** joined with a deadline, and both halves of
that are deliberate:

- The abandoned call **cannot be killed** — Python offers no way to interrupt a
  blocking socket read in another thread. It keeps running and keeps occupying
  the model until it finishes. What the timeout buys is that the *caller* is
  freed, not that the work stops. Claiming otherwise would be the more
  comfortable and less true description.
- The thread is a **daemon** so that orphan does not hold the interpreter open
  at exit. Without that, a 416-second outlier would turn into a 416-second hang
  for a script that had already moved on — trading a visible slow request for
  an invisible one.

A genuine provider error (connection refused, and so on) still propagates
normally: it is re-raised on the calling thread rather than being flattened into
a timeout, because "Ollama is not running" and "Ollama is slow" call for
different responses.

### A timeout is an infrastructure result, not a model result

This is the load-bearing distinction, and it is enforced in both consumers.

`scripts/run_examples.py` gives timeouts **their own outcome class**: they are
marked `--` rather than `XX`, excluded from both the numerator and the
denominator of the match rate, and counted on their own line. Folding them into
the mismatch count would aggregate over two things that are not
interchangeable — an infrastructure condition and a wrong verdict — which is
precisely the **wrong-unit error this project has now made three times**
(ADR-004's `fully-valid` metric, ADR-022's dimension count, and ADR-022's own
report of a bimodal latency as a mean). Having named the pattern, the cheap
thing is to stop repeating it where it is foreseeable.

> **Amended by ADR-024:** the count of three was itself incomplete. A fourth
> instance — the match rate this very paragraph is reasoning about — was
> identified afterwards. The irony is instructive and is left standing rather
> than edited away: this paragraph correctly refused to fold timeouts into the
> match rate while not noticing that the match rate was already folding
> together mismatches of unequal cost.

`app.py` treats it the same way in the language it shows the user: the message
says plainly that this says nothing about the request, and where an exemplar is
loaded it falls back automatically to that exemplar's stored assessment,
**labelled visibly as offline** — the engine, gates and contract shown are real,
the dimension scores were written by hand. With no exemplar loaded it shows the
message alone rather than inventing something to display.

---

## ADR-024 — The match rate is the fourth wrong-unit error

**Date:** 2026-07-25 · **Status:** accepted, **not fixed** · **Amends the count in:** ADR-023

`scripts/run_examples.py` reports "4/6 verdicts match". That count aggregates
mismatches of unequal cost into one number. A false `no_go` and an `incomplete`
each score as one mismatch, but they do different things to the requester:

* **`incomplete`** routes the request back and names what is missing. The
  requester answers and resubmits. The error is **compensable** — the next turn
  corrects it.
* **`no_go`** rejects the request. There is no next turn unless someone appeals.
  The error is **not compensable** by the process that produced it.

Counting them as one unit says they are interchangeable. They are not.

### The evidence is inside this project's own measurements

`ticket_handover_summaries` — the exemplar whose anchor-faithful reading is
`go`:

| | Verdict | Headline |
|---|---|---|
| Phase 3.1 (`evals/run_examples_after_partB.json`) | `incomplete` | 3/6 |
| Phase 3.2 (`evals/run_examples_final_phase32.json`) | `no_go`, via `no_usable_data`, total 3.24 | **4/6** |

The headline improved while **that specific case became more harmful**: a
request that had been sent back for more information was now being rejected
outright, on a `data_readiness = 1` score the request plainly contradicts. The
metric has no way to express that, so an improvement and a regression were
reported as a single upward number — and were reported that way, by me, in the
Phase 3.2 deliverable.

### The lineage — this is ADR-020 applied to the harness

ADR-020 established, for the product, that **non-compensable errors cost more
than compensable ones**, and therefore that gates need a higher evidentiary
standard than dimensions. The match rate is the same asymmetry in the
evaluation harness: it treats a rejection and a request for information as
equivalent outcomes, exactly as the pre-3.1 code treated a gate input and a
dimension input as equivalent evidence.

**The harness inherited the defect the product was corrected for.** That is the
uncomfortable part and the reason this is worth a numbered decision rather than
a footnote: the correction was applied where it was being looked for and not
where it was not. A fix that does not generalise past the place it was found is
half a fix.

This is the fourth instance in this project, and the count in ADR-023 ("three
times") is superseded by this one:

1. **ADR-004** — `fully-valid` collapsed call-emission and key-fidelity, two
   independent failure layers, into one rate.
2. **ADR-022** — `max_unknown_dimensions` counted dimensions of unequal weight.
3. **ADR-022** — a bimodal latency reported as a mean, hiding a 416s outlier
   behind a 74s average.
4. **ADR-024** — the match rate counts mismatches of unequal cost.

Four occurrences, across metrics, config, reporting and evaluation, in code
written carefully each time. The common tell is unchanged and worth stating as
a check rather than a lesson: **before reporting an aggregate, ask whether the
things being summed are interchangeable for the decision the number will
inform.** Each of the four passes review comfortably until that question is
asked.

### Not fixed, and what fixing it would take

The build is frozen. This is recorded so the number is read with its limitation
attached, not as a deferred task.

For whoever picks it up: the replacement is not a weighted score, which would
reintroduce the same problem one level up. It is a **confusion matrix over
verdicts** — six expected × six actual — read alongside a stated cost ordering,
something like:

```
false go      : worst  (approves what should have been stopped)
false no_go   : severe (rejects, no next turn)
false not_ai  : severe (rejects with a stronger claim)
false incomplete : mild (sends back, recoverable)
```

Reported as a matrix rather than a scalar, because the scalar is what caused
this. A single number will always be able to trade a severe error for two mild
ones and call it progress.

### Consequence for the recorded results

Every match rate in this log — 2/6, 3/6, 4/6 — should be read as "how many
verdicts matched", never as "how good the system is". The Phase 3.2 improvement
from 3/6 to 4/6 is real in the first sense and unproven in the second, and the
`ticket_handover_summaries` row is the specific reason to doubt it.

---

## ADR-025 — UI rendering changes, and one trade named rather than absorbed

**Date:** 2026-07-25 · **Status:** accepted · **Scope:** presentation only

Three changes to `app.py`. **Rendering only: no computation, no config, no
prompt, no schema.** The frozen live path — the assessment call, the rubric,
the scoring engine — is untouched, which is why this lands after the freeze
rather than breaching it.

1. **Evidence moved out of the dimension table into a list beneath it.** The
   evidence strings run 200-400 characters and were truncated to unreadable
   stubs inside a dataframe cell — which quietly defeated the point, since the
   evidence is what makes a verdict auditable and it was the one column nobody
   could read.
2. **Decommission triggers expanded by default.** They are the concrete answer
   to "when would you turn it off", which is the differentiating claim.
3. **Intake specifics in an expander, open on a blank form and collapsed once
   an exemplar has filled it in** (`expanded=preset is None`).

### The trade behind the third one

Collapsing the intake specifics trades **form legibility against blank-form
completion rate**, and the second half of that has a measurable consequence
worth naming rather than absorbing.

Every blank intake field returns a dimension to model scoring or to `unknown`.
Four dimensions are in `never_unknown` (ADR-022), so **a blank form has a
shorter path to `incomplete` than a filled one** — collapsing the section makes
a walk-up user less likely to open it, which pushes the blank-form path toward
`incomplete` for reasons that have nothing to do with the request.

On the exemplar path this costs nothing: the values are pre-populated and both
deterministic derivations still fire, verified by driving the collapsed form
end to end. So the conditional expander takes both — open where the user must
supply the facts, collapsed where they are already supplied and the clutter is
pure cost.

A note on the mechanism, since it is the thing worth doubting: **widgets inside
a collapsed Streamlit expander still execute and still submit their values.**
Collapsing changes what is visible, never what is sent. That was checked rather
than assumed.

---

## ADR-026 — `business_value` was a procedure with a hole in it, not a bad anchor

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** rubric, config, schemas, scoring, prompt
**Evidence:** `evaluacion/07_agreement_study.md`, `evaluacion/08_currency_hypothesis_test.md`

Phase 4, Commit 1 of 3. Everything repaired here was **measured** by the
inter-rater agreement study over 30 cases with two independent scorers, not
suspected.

### Registered predictions

Recorded before the repair, so the result cannot be reinterpreted afterwards.
The re-run that tests them is a separate protocol and has **not** been run.

| Prediction | Current | Expected after |
|---|---|---|
| `business_value` exact agreement | 63% | **rises** |
| `non_ai_alternative` exact agreement | 70% | **rises** |
| Verdict agreement | 80% | rises |
| Cases returning `incomplete` | **0 / 30** | **rises above zero** |
| Cases returning `go` | 3–5 / 30 | **may fall** |

The last two are uncomfortable on purpose. Making a vague request return
`incomplete` instead of a guessed score is the point of this commit, and it
necessarily reduces the number of requests that reach a verdict at all. **If the
`go` rate falls and `incomplete` rises, that is the change working.** Recording
it here removes the option of reading a fall in `go` as a regression later.

One honesty note about the registration: these predictions were written into
this log in the same commit as the implementation, not in a commit before it.
They are still ex ante with respect to the data — no re-run has been performed —
but the ordering was not what the phase plan asked for.

### The defect, and why the first hypothesis was wrong

`business_value` had the worst exact agreement in the study (63%) and the
heaviest weight (0.22) — the worst possible pairing. The leading explanation was
a currency mismatch: anchors in USD, every corpus figure in pesos, no conversion
basis, and reading a peso figure against a USD threshold lands exactly one level
high, which is the shape of the observed one-directional skew.

**Tested against the score files, and refuted.** Currency evidence appears in
27% of disagreements and 26% of agreements. All five agreements that cite an
explicit peso figure agree exactly. The hypothesis had no explanatory power.

What the same two queries found instead:

| | n | At least one scorer marked `confidence: low` |
|---|---|---|
| Disagreements | 11 | **11 — 100%** |
| Agreements | 19 | 13 — 68% |

Six of the eleven disagreements sit on the single 1-versus-2 boundary. Where
both scorers were confident they never once disagreed. The cause was not an
anchor at all — it was this instruction in the dimension's `description`:

> *If the request names no figure, estimate the order of magnitude from the
> process described and record `confidence: low`.*

Added in Phase 2.1 to stop the heaviest dimension from degenerating into a
measure of how well the requester writes a business case. **It fixed that bias
and introduced a reproducibility problem in its place.** Both scorers obeyed it,
both flagged low confidence, and then estimated differently — because "estimate
the order of magnitude" asks for a judgement the rubric supplies no procedure
for. A hole in a definition closes by stating the definition; a hole in a
**procedure** stays open however well the anchors are written.

### The repair: a derivation, and a refusal

The two dimensions that reached 100% agreement did so because a lookup table
replaced a judgement. So `business_value` gets one, as a four-step resolution
order — in `scoring_rule` for the model, and in `derivation` for the code:

1. **Stated magnitude** — the request names a figure in any denomination: score
   it, confidence high if already annual, medium if annualized.
2. **Computed from intake** — no stated figure, but volume and a per-instance
   duration or cost: compute the annualized magnitude, confidence medium, and
   put the full arithmetic in the evidence string.
3. **Volume only** — score the cases-per-year denomination alone, confidence
   low, and say so out loud in the evidence.
4. **Refuse** — `null`, with what is missing named. `business_value` is in
   `never_unknown`, so this returns `incomplete`.

Branch 4 is the one that changes behaviour in the field. A request whose
magnitude cannot be established is **not a low-value request, it is an
unassessable one**, and the honest output names the missing number and routes it
back.

Three design points worth recording:

**The derivation is a FALLBACK, and it is the first one.** The other two
(`intake_volume`, `intake_sensitivity`) overwrite the model: a volume is a
volume. A magnitude is not stated by any single field — it is the product of two
— so computing it only beats reading it where the request named no figure at
all. Hence `applies: when_unknown`, a `derive_fallback_scores` separate from
`derive_scores`, and the dimension staying **in** the prompt rather than being
trimmed out of it like a derived one.

**Priority order, not the larger of two.** Where both a duration and a cost are
available the denominations are tried in declaration order. Taking the higher was
considered and rejected: it would reintroduce exactly the upward skew the study
measured (A above B in 11 of 30, below in none). The bands are mutually
calibrated at roughly 50 USD per person-hour, so the two rarely disagree.

**The currency basis is stated anyway.** USD, with conversion at the rate in
effect recorded in the evidence. It was measured **not** to be the cause of the
disagreement, and it is closed because it is objectively wrong, not because it
buys agreement. Recorded so nobody later credits an agreement improvement to it.

### The second axis, removed — and an overlap found while removing it

Levels 4 and 5 carried "a cycle-time reduction on a process the business already
reports on" and "direct influence on revenue or on a regulatory obligation the
company already reports". Both are categorical facts about **strategic
salience** on a dimension whose `axis` line declares magnitude only. This is the
one-axis-per-dimension rule from ADR-014 being violated by anchors rewritten
*after* that rule was written down — which is the argument for checking it with
a test rather than with a reader, and there is now one.

Deleting the clauses exposed a second defect in the same two anchors: level 4
said "5,000-50,000 cases" while level 5 said "tens of thousands of cases", so
20,000 cases matched both. Mutual exclusivity is one of the three anchor-writing
rules at the top of `rubric.yaml`. Level 5 is now "more than about 50,000".

Strategic salience may well matter. It is **not** added as a dimension now; it
is a candidate, recorded here, to be argued on its own evidence rather than
smuggled in through the anchors of another construct.

### Two mechanisms added, one deliberately not

**`scoring_rule`, a new optional field on a dimension, rendered into the
prompt.** The phase plan suggested putting prompt-visible rules in the `axis`
line. `description` is not rendered — it is documentation for whoever tunes the
rubric — so a rule the model must follow needs somewhere else to live, and
`axis` is the wrong place: acceptance criterion 3 is "no anchor references more
than the one axis its axis line declares", and that check only works while the
axis line is a single-construct statement. A twelve-line procedure inside it
would blur exactly the thing the criterion measures. So procedure and construct
are now separate fields, both rendered, and the axis stays checkable.

**Two intake fields:** `minutes_per_instance` and `cost_per_instance`, optional
like every other structured field, plus the matching inputs on the app form.
Without a way to supply them the derivation would be unreachable from the only
UI, and every vague request would take branch 4 by default.

**Not added: a load-time invariant** that a dimension with a fallback derivation
must be in `never_unknown`. It is true of the shipped config, and it is what
makes branch 4 surface as `incomplete` rather than renormalize away — but as a
`Rubric` validator it forbids `never_unknown: []`, which is the configuration
the completeness tests need in order to exercise the weight rule on its own
(ADR-022). It was written, it broke two tests that were measuring something
real, and it was withdrawn. The property is pinned by a test against the shipped
rubric instead, where it costs no expressiveness. **A guard that only fires on
configurations nobody ships is not worth the ones it forbids.**

### What this does not fix

Nothing here improves the case where the request DOES state a figure — that path
already agreed. The gain is confined to vague requests, which the currency test
noted are also the requests a real Hub receives most often (A-01, A-03, B-07,
B-12, B-14, B-16 in the corpus). And the study's own limitation stands: both
scorers are language models, and their agreement may be correlated.

---

## ADR-027 — Three anchor sets, and the one repair code cannot enforce

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** rubric anchors and axes only
**Evidence:** `evaluacion/07_agreement_study.md` §4 and §6

Phase 4, Commit 2 of 3. No Python changed. Three dimensions, in descending
order of measured verdict leverage.

### 2A · `non_ai_alternative` — the highest-leverage repair in the rubric

**All six verdict disagreements in the study trace to this one dimension.** Four
are gate flips across the 3/4 boundary; two are band flips on totals it weights.
Five of thirty cases cross the gated line between two careful scorers — one case
in six — and one scorer flagged that single boundary on 14 of 30 cases. It has
the second-worst exact agreement in the rubric (70%) and a gate at raw >= 4.

Two distinct defects, and the second is the more interesting.

**The boundary had no operational test.** "Roughly half the cases" against "most
of it". Levels now carry numeric bands — under 25%, 25-75%, 75-99%, 99-100% —
and `scoring_rule` says out loud to put a percentage on it and to use the
requester's own number when they state one. B-09 states exactly 60% and used to
sit in the gap between two adjectives; it now lands in level 3 deterministically,
and 75% is where the gate starts.

**The UNIT was wrong, and this is the part that changes scores.** Both old
anchors were phrased as coverage *of cases*, but the alternatives requesters
actually have usually cover *part of the problem across all cases*: a
job-description template fixes structure and leaves the prose; an upstream form
field relocates a judgement instead of removing it; a process fix cures lateness
and leaves the effort untouched. Read as "does it help?" those look like level 4
and fire the gate. Read as "how many instances does it finish end to end, with
no human judgement added?" they are level 1 or 2. The second question is the one
this dimension exists to ask, because it is the one that decides whether the
agent is redundant — so the axis now names the unit and the anchors count in it.

Note the direction of that fix: it makes the gate fire **less** readily on
requests where a partial aid exists, and the numeric boundary makes it fire
**more** predictably. Those pull opposite ways on the `go` rate and no
prediction is registered about which dominates.

**Level 1 demanded impossible evidence.** It required that "rule-based attempts
have been tried and are known to fail" — proof that exists only once somebody has
wasted the effort, and that a maximally rule-immune request such as machine
translation can never produce, because nobody would attempt rules for it. Prior
failed attempts are now supporting evidence for level 1 rather than a
precondition of it. The level rests on the nature of the input, which is what it
was always trying to describe.

### 2B · `data_readiness` — two constructs, combined by `min`

The dimension bundled *does the data exist and can we get it* with *can we tell a
good output from a bad one*, and the same case answers them differently. The
corpus case that exposed it: NDA triage, where the documents are fully
retrievable but nobody ever recorded which ones required negotiation.
Availability reads 3, evaluability reads 1. One scorer read 2, the other 3, and
**neither fired the gate — level 1 is what fires `no_usable_data`.**

The dimension is **not** split: that would change the weight structure, and
weights are settled. Instead the axis declares both sub-assessments, each anchor
describes both halves, and the score is the LOWER of the two. Under that rule the
NDA case resolves to 1 and the gate fires — which is the right verdict for a
predictive archetype with no recorded outcome: "instrument the process and
resubmit" rather than a judgement on the idea. **Expect `no_usable_data` to fire
more often than before.** That is the repair working.

Two further fixes to the same anchors:

- Level 4's "quality has been checked on a real sample" is almost never stated in
  a request, so taken strictly it capped well-instrumented cases at 3 by
  construction. It now also accepts a stated, plausible path to checking.
- The access-owner clauses are gone from levels 4 **and** 5. The plan named only
  level 5, but level 4 carried the same requirement, so removing one alone would
  have left level 4 harder to satisfy than level 5 for any request that mentions
  no owner — which is most of them. Access paperwork is a real risk and it is
  already carried by `data_governance` and `implementation_effort`.

### The repair code cannot enforce, stated plainly

`min(availability, evaluability)` is computed by whoever scores, in their head.
A `DimensionAssessment` carries **one** score per dimension, so the engine never
sees the two halves and no test can assert it took the lower. The phase plan
asked for a test where the halves differ by two levels; what exists instead is a
test that the instrument *states* the rule, that every anchor describes both
halves, and that the NDA case's two halves are three levels apart in the anchor
text.

Making it mechanical means adding two sub-scores to the model's response schema,
computing the minimum in `scoring.py`, and re-measuring the gate that keys on the
result. That is a change to the frozen live path with its own failure modes — a
schema with more required fields is a schema more assessments fail to satisfy
(ADR-019) — and it deserves its own phase and its own measurement rather than a
ride along an anchor rewrite. Recorded here so the gap is a known one.

### 2C · `process_frequency` — a latent defect, fixed before it activates

100% agreement, and the reason is not the anchors: the derivation table shadowed
them on 25 of 30 cases. Where a scorer had to reason, the unit was undefined —
B-06 is 45 tenders a year or about 4,500 requirement responses, which is level 2
against level 4. The axis now defines an instance as one unit of work the agent
would handle end to end, once, with two worked examples where that is *not* the
noun the request uses, and ties the intake volume field to the same unit. The
derivation reads that field literally, so its meaning had to be settled too.

### Consequence: the exemplars pass, and two of their reference scores are stale

All six exemplar verdicts are unchanged, and that is the weaker result it looks
like. The exemplar suite scores **hand-authored fixtures**, so an anchor rewrite
cannot move it: the numbers are frozen data, not readings of the current text.
Under the sharpened unit in 2A, two reference scores are now wrong:

| Exemplar | Dimension | Reference | Correct now | Total | Verdict |
|---|---|---|---|---|---|
| `ticket_handover_summaries` | `non_ai_alternative` | 2 | 1 | 4.13 -> 4.23 | `go` (same) |
| `contract_renewal_drafting` | `non_ai_alternative` | 2 | 1 | 3.08 -> 3.18 | `no_go` (same) |

Both cite "covers a minority of the work" for a template that structures output
without finishing any instance — level 2 under the old unit, level 1 under the
new one. Neither crosses a band or a gate, so nothing was detected.

**They have deliberately not been re-authored.** The acceptance rule for this
phase is that a changed exemplar is a finding to report before anything is
adjusted, and re-scoring reference data to match a rubric edited in the same
commit is how a reference set stops being independent evidence. The follow-up is
to re-author both against the new anchors as its own reviewable change.

The general finding is worth more than the two rows: **the exemplar suite
provides no coverage of anchor text at all.** It tests the engine. Anchor
quality is now tested by the wording assertions added to `tests/test_config.py`,
which is a weaker instrument than a scored case but is the only one that fails
when an anchor changes meaning.

---

## ADR-028 — Deterministic is not the same as reliable

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** config, scoring, rubric gates, UI rendering
**Supersedes:** the confirmation half of ADR-020
**Evidence:** `evaluacion/07_agreement_study.md` §4 and §9

Phase 4, Commit 3 of 3. `requires_human_confirmation` moves from the gate to the
condition, and the values change.

### What ADR-020 decided, and what the study did to it

Phase 3.1 marked anti-pattern gates as needing human confirmation and left
dimension-threshold gates final, reasoning that a threshold gate is
"deterministic given the assessment". The agreement study inverted every part of
that:

- The anti-pattern reading disagreement — `existing_licensed_capability` matched
  4 times by one scorer and 0 by the other — **changed no verdict at all.**
  Hard-block matches were verdict-redundant in 16 of 17 instances across both
  scorers: they landed on cases the threshold had already gated.
- The `non_ai_alternative` threshold, left final, **fired every `not_ai` in the
  run**, on a dimension where two careful scorers disagree 30% of the time, at
  exactly the boundary the gate uses. Five of thirty cases cross that line
  between scorers.

> **Deterministic is not the same as reliable.** A dimension-threshold gate is
> perfectly deterministic in code and can still be the least reproducible
> decision in the system, because its input is a judgement at a boundary the
> anchors do not operationally define.

The flag was attached to the condition class that decided nothing and withheld
from the one that decided everything. The reasoning was not careless — it was
answering the wrong question. "Can this be recomputed from the assessment?" is
not "will two people produce the same assessment?", and only the second predicts
whether a verdict survives review.

### Why it had to move to the condition

`non_ai_alternative_suffices` holds both condition types in a single `any_of`:
the threshold at 4, and `hard_block_any` over the remaining anti-patterns. A
per-gate flag cannot express a per-condition-class split — either the threshold
inherits a confirmation it may not need, or the anti-pattern escapes one it does.
The fix was blocked on nothing except noticing that.

`requires_human_confirmation` is now a property of every gate condition, with a
per-type default and a per-condition override in YAML. `Outcome` reports which
condition fired (`TriggeredGate.fired_conditions`, each carrying its own flag),
and the confirmation decision reads **only** the conditions that actually fired.

**Combining rule: confirmation is required when EVERY fired condition requires
it.** One condition that stands on its own is sufficient basis for a verdict,
even where another that also fired would need review. That preserves the shape of
the old rule — a self-standing basis wins — while making the basis per-condition
rather than per-gate.

`deterministic_basis` survives as an informational field. It is still true of
this system and still worth reporting; it is simply not what decides.

### The values, and the reasoning for each

| Condition | Confirm | Measured basis |
|---|---|---|
| `anti_pattern` (both gates) | **yes** | The study's cleanest division: anti-patterns whose signals describe what the requester SAID agreed 100%; those needing a judgement about the world diverged 0-50%. Redundant in this corpus is not reliable in the next one. |
| `dimension_threshold` on `non_ai_alternative` | **yes** | 70% agreement; fired every `not_ai`; one case in six crosses the gated boundary. The entry the study most directly demands. |
| `dimension_threshold` on `data_readiness` | **yes** | 80% agreement, and level 1 — the gated value — is exactly where ADR-027 found two constructs sharing one number. The `min` rule will make it fire more often while that change is unmeasured. |
| `dimension_threshold` on `data_governance` | no | 100% agreement, and derived from an intake field. |
| `intake_field` on `business_owner` | no | A fact about the form. Nobody reads "was an owner named?" two ways. |

Type defaults are cautious where the input is a judgement: `anti_pattern` and
`dimension_threshold` default to true, `intake_field` to false. A threshold gate
added in future therefore asks for review until someone measures that it need
not. All five shipped conditions set the value explicitly anyway, because each is
a measured decision and an implicit one cannot be audited — a test enforces that.

### One objection, recorded rather than acted on

The `data_governance` entry is set to `false` on two grounds, and **the second
does not survive inspection**. The gate fires at raw >= 5, and the derivation
table cannot produce a 5: `regulated` maps to 4, because "may not be processed at
all" is a contractual finding rather than a classification. So every firing of
that gate rests on a model judgement, not on the intake field. The 100%
agreement figure covers levels 1-4, where the derivation did the work, and **no
case in the 30-case corpus scored 5 at all** — the reproducibility of the gated
value is unmeasured, not high.

It is set to `false` because that is the decision registered for this phase, and
changing it mid-implementation on an argument rather than on evidence is how a
registered prediction stops meaning anything. The objection is written next to
the condition in `rubric.yaml`, the first live 5 is the case to inspect, and
flipping it is a one-line config change with no code edit — which is now the
point of the design.

### Consequences

Two exemplar outcomes changed, **verdicts unchanged**:

| Exemplar | Verdict | `requires_human_confirmation` |
|---|---|---|
| `ticket_volume_by_team` | `not_ai` (same) | False → **True** |
| `predict_laptop_failures` | `no_go` (same) | False → **True** |

Both are the intended effect: one gated by the `non_ai_alternative` threshold,
one by `data_readiness` at level 1. Three of the six exemplars now come back
pending review rather than decided, which is the honest reading of what this
instrument can currently support on its own.

Two tests asserted the old behaviour and were rewritten rather than deleted, with
the inversion named in the docstring, because the reasoning they encoded is the
thing this ADR corrects:
`test_a_dimension_threshold_gate_does_not_require_confirmation` and
`test_a_gate_with_both_bases_does_not_require_confirmation`.

The UI shows each fired condition separately with the agreement figure behind it,
so a reviewer sees *why this particular condition* is being questioned rather
than a generic caution. Those figures are presentation only; nothing computes
from them.

### The finding underneath the finding

This ADR exists because the first version of the study's §4 reached the opposite
conclusion — that the study *validated* ADR-020 — by naming the two threshold
gates whose dimensions agreed at 80% and 100% and omitting the one that fired
every `not_ai`. The omission was not deliberate: the conclusion came first and
the supporting set assembled around it. That is the exact failure mode this
project designs against elsewhere by pre-registering thresholds and by keeping
the verdict field out of the model's schema, and it appeared in the analysis of
the study built to detect bias. What caught it was not care. It was a second
party with access to the raw files.

---

## ADR-029 — Phase 5: subtractive repair, and why the last one made things worse

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** rubric.yaml, patterns.yaml, one intake label
**Evidence:** `evaluacion/09_repair_effect.md` — run 1 (v2.0.0) against run 2 (Phase 4), same 30 cases, same two scorers

Phase 4 was measured. One of its five registered predictions held.

| Dimension | What Phase 4 did | Run 1 | Run 2 |
|---|---|---|---|
| `business_value` | **replaced** a judgement with a derivation | 63% | **100%** |
| `implementation_effort` | untouched | 77% | 80% |
| `adoption_risk` | untouched | 80% | 83% |
| `data_governance` | untouched | 100% | 96% |
| `data_readiness` | **added** a `min()` rule over unrepaired inputs | 80% | 73% |
| `non_ai_alternative` | **added** numeric bands beside existing prose | 70% | **61%** |
| `process_frequency` | **added** a unit definition beside a derivation | 100% | **88%** |

Verdict agreement fell 80% → 67%. Overall dimension agreement rose 81% → 83%, which
is the number that would have been reported as success without the
pre-registration.

> **Replacing a judgement with a procedure works. Adding a rule alongside a
> judgement makes it worse.**

Every regression has the same shape: **two rules that disagree, and no
precedence between them.** This phase deletes one rule from each pair. It does
not add a third to arbitrate, and it does not add clarifying prose — a repair
whose section gets longer is the mistake being corrected.

### Registered predictions

Written before implementing. The re-run that tests them is a separate protocol
and has **not** been run.

| Prediction | Now | Expected |
|---|---|---|
| `non_ai_alternative` agreement | 61% | rises above 70%, its pre-Phase-4 level |
| `process_frequency` agreement | 88% | returns to about 100% |
| `data_readiness` agreement | 73% | rises above 80% |
| `business_value` agreement | 100% | **unchanged — not touched** |
| `existing_licensed_capability` agreement | 0% | rises substantially |
| Verdict agreement | 67% | rises above 80% |

If `business_value` moves at all, something was touched that should not have
been. The same honesty note as ADR-026 applies: these predictions were written
into this log in the commit that implements the first of the three changes, not
in a commit before it. No re-run has happened, so they remain ex ante with
respect to the data.

---

### Commit 1 — `process_frequency`: the question was wrong, not either rule

The `axis` defined an instance as the unit of work the agent handles end to end.
The `derivation` reads the intake volume field literally. **Both are defensible
and they disagree by up to two bands** — B-06 is 45 tenders by the field and
about 4,500 requirement responses by the axis. Scorer A named it: *"the axis
defines the unit but the derivation reads the field literally, and the two
disagree by two bands."*

Neither rule is wrong. **The intake question and the scoring rule were asking
about different things.** The form asked *how often the process runs*; the rubric
asked *how many times the agent would do this task*. Those are not the same
question, and no amount of arbitrating between the two answers fixes a
mismatched question.

So the question changed, and the rules did not:

- The intake field is now **"Times this task would be done, end to end"**, with
  one line of help naming the trap: if one submission contains many items the
  agent would handle separately, count the items.
- The `derivation` is **untouched**. After the relabel the field means what the
  axis means.
- The recount instruction is **deleted from the axis** — the two worked examples
  and "fill the intake volume field in that same unit". The axis defines the
  unit; it does not also tell a scorer to override the form. Deleted from the
  `description` too, per the rule that a deleted rule is deleted from all three
  places.

**Departure from the plan, and why.** The plan's suggested label was "How many
times a year would this task be done, end to end?". The widget is a
`times_per_period` count beside a period selector, so a label saying "a year"
next to a dropdown reading "per month" is incoherent. The label carries the part
that was load-bearing — *this task, end to end* — and the period selector keeps
doing the annualising. Changing the field to a single per-year number would be a
schema change, and this phase is config plus one label.

### What the relabel exposed: three exemplars whose reference scores contradicted the config

A test was added asserting that each exemplar's volume field derives the band its
own reference assessment claims. It failed on **three of the five exemplars that
have a volume field**, all pre-existing, all invisible until now because **the
derivation silently overrides the reference score** and the verdicts were decided
elsewhere.

| Exemplar | Reference said | Form derives | Cause |
|---|---|---|---|
| `predict_laptop_failures` | 4 | 3 | The form counted laptop FAILURES (30/month). The task is one prediction per machine, and the fleet is 4,000. The reference evidence had said so in prose all along. |
| `hr_policy_questions` | 3 | 4 | Arithmetic: 40 questions a week is 2,080 a year, which is the 1,000-10,000 band. The evidence claimed "inside the 100 to 1,000 band ... at its top edge". |
| `ticket_volume_by_team` | 1 | 2 | Boundary: 12 a year is not "FEWER than about a dozen". The band table starts level 2 at 12. |

Only the first is caused by the relabel; its volume field is now 4,000 a year.
The other two are plain errors in reference data, corrected here because the band
table they contradict is **untouched by this phase** — 2,080 was outside the
level-3 band before Phase 5 and after it. That is the distinction from ADR-027,
where two exemplar scores went stale because an anchor's *meaning* changed and I
deliberately did not re-author them: correcting arithmetic against a stable rule
is not the same act as re-scoring fixtures to match a rule I just edited.

No exemplar verdict changed. `predict_laptop_failures` moved 3.74 → 3.87 and is
still gated `no_go`; the other two totals did not move at all, which is the
clearest possible demonstration that those reference scores were dead weight.

**The general finding is worth more than the three rows.** For every dimension
with a derivation, the exemplar suite has been asserting engine behaviour while
carrying reference scores that disagree with the config, and nothing failed.
A fixture that cannot contradict the thing it documents is not evidence.

---

### Commit 2 — `non_ai_alternative`: delete the softer of the two rules

The highest-agreement-cost dimension in the study, and the one that gates at
raw >= 4. Phase 4 gave it numeric bands on instances finished end to end — and
left in place the rule it was meant to replace, that an alternative relocating a
judgement rather than removing it does not count as coverage. Agreement fell 70%
to 61%. Scorer A flagged the 3/4 boundary **25 times**, up from 14 before the
"repair", and said the two rules *"pull opposite ways"*.

The bands stay. The relocation rule is deleted from all three surfaces:

- `axis` — "Counted in instances FINISHED, not in help given: an alternative that
  improves every instance but finishes none of them belongs at level 1, because
  the work still has to be done by somebody."
- `scoring_rule` — "Partial help on every instance is not coverage: a template
  that fixes tone but leaves the writing, or a process change that fixes lateness
  but leaves the effort, finishes nothing and belongs at level 1 or 2, not in the
  middle."
- `anchors[1]` — "or the only available alternative helps with every instance
  while finishing none."
- `description` — the paragraph carrying "an upstream form field moves a
  judgement rather than removing it".

Deleted, not softened. The relocation rule had no operational test: whether a
form field a human fills in counts as coverage turns on whether the category is
contested, which is a judgement about the world dressed as a rule about the
alternative. Scorer B invented a test for it ("could two competent people fill it
differently?") and said so, which is the same failure the anti-pattern in Commit 3
has.

**One sentence added, in the axis, to settle the case Scorer A could not:**

> A deterministic output that still needs a human judgement after it — a
> scorecard, a risk questionnaire, a redline — has not finished the instance.

That is the coarse-output case, resolved as a property of the output rather than
of where a judgement moved to. It is testable from the request text: does a person
have to decide something after the deterministic thing runs. It replaces four
sentences across three surfaces with one.

Phase 4's level-1 evidence fix stays. It was correct, it is not implicated in the
regression, and it is the only other thing Phase 4 did to this dimension.

Net effect on the file: `rubric.yaml` 791 → 767 lines across Commits 1 and 2.

---

### Commit 3 — `existing_licensed_capability`: a decision procedure, so nobody has to invent one

**0% agreement across both runs**, on the **highest-precedence gate** in the
system. Nothing about it changed in Phase 4. In run 1 it decided nothing, because
the `non_ai_alternative` threshold gate fired first on almost every case it
touched — hard-block matches were verdict-redundant in 16 of 17 instances. In run
2, after Phase 4 made that threshold fire less readily, this anti-pattern decides
**half of all verdict disagreements**.

> The repair did not create the unreliable mechanism. It removed the thing that
> was hiding it.

Scorer A matched it 10 times, under a rule it wrote for itself — "the request
names a platform the company runs *and* that platform is the natural home of the
requested capability" — and called that rule *"the least reproducible call in the
set"*. Scorer B matched it zero times, reading the signals narrowly and citing the
file's own warning about firing on resemblance. **Both readings were supported by
the text.** That is the defect: no anti-pattern should require a scorer to invent
its own decision procedure.

Run 1 supplied the shape of the fix. Anti-patterns whose signals describe what the
requester **said** agreed 100% — `reporting_in_disguise`, `rpa_relabeled`,
`chatbot_without_job_to_be_done`, `solution_first_no_measurable_problem`. Those
requiring a judgement about the **world** agreed 0%. So this one becomes
behavioural, as a two-part test where **both parts need their own verbatim
quote**:

- **Part A**, in `quote` — the request names a specific platform, product,
  licence, subscription, tier or module the company already runs.
- **Part B**, in `second_quote` — the request itself says, or plainly implies,
  that this platform already does this job or part of it.
- **Not Part B** — naming a platform as the place the data lives. *Salesforce as
  a data source is not Salesforce as a capability.* Stated in the signals because
  it is the exact error being ruled out, and it is what produced the 10-versus-0
  split.

If Part B cannot be quoted there is **no match**, and the request is scored on
`non_ai_alternative` like any other. **Nothing is lost by that.** That dimension
already carries "an already-licensed capability solves it completely" at level 5,
so the signal moves from an unreproducible categorical gate to a scored dimension
where it is compensable and where a wrong reading costs tenths of a point instead
of a verdict.

`deterministic_rule_suffices` (50% agreement across both runs) gets the same
discipline: Part A is the stated decision logic, Part B is that the inputs the
rule needs are already values in a system today. The four anti-patterns at 100%
are untouched.

The capability categories — productivity suite assistant, service-management AI,
CRM assistant, BI natural-language query, enterprise document search — moved into
`notes`, labelled as reviewer guidance for **after** a match. `notes` is not
rendered into the prompt, which is where that list belongs: useful to a human
deciding whether a matched claim is plausible, and never a criterion.

### The one place this phase is not config-only

Making "both parts must be quoted" real needed a mechanism, because the engine
cannot tell Part A from Part B by reading one string. Three small additions:

- `AntiPattern.two_part_evidence: bool = False` in config
- `AntiPatternMatch.second_quote: str | None = None` in the model's schema
- one check in `scoring.py`: for a two-part anti-pattern, a missing or
  unverifiable `second_quote` discards the match into
  `unsupported_anti_patterns`, exactly as a fabricated first quote already was

The field is **optional**, so the four anti-patterns at 100% agreement are
unaffected and the schema does not demand more work of the model for them —
ADR-019's warning that a schema demanding more gets less applies to required
fields. The phase plan said config only; this is the deviation, it is 30 lines,
and without it the two-part test would be prose the engine could not enforce and
the specified test — *a match without a Part B quote lands in
`unsupported_anti_patterns`* — could not be written at all.

### One test invariant narrowed, deliberately

`test_existing_licensed_capability_signals_name_categories_not_products` asserted
that no signal names a vendor, because a product list as a match criterion is
what caused the original false positives. The new "Not Part B" line names
Salesforce. The rule now applies to the two signals that **define a match**, and
the illustration of what does *not* count is exempt: a named product there cannot
produce a false positive, which is the failure the rule exists to prevent. It can
only withhold a match, and Part B is what restores one.

### Line delta for the phase

| File | Before | After | Δ |
|---|---|---|---|
| `rubric.yaml` | 791 | 767 | **−24** |
| `patterns.yaml` | 404 | 402 | **−2** |

Both shorter, which was the acceptance criterion and the point. `patterns.yaml`
first came out **+2**, because the study history had been written into a
`description` — a field that **is** rendered into the assessment prompt. Moving
it here cost nothing and removed prompt weight: rationale belongs in this log,
and the config should carry only what the model or the scorer has to act on.

---

## ADR-030 — Phase 6: `non_ai_alternative` becomes a computation

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** one dimension, one intake field
**Evidence:** `evaluacion/10_three_runs.md` — three runs, identical corpus, identical scorers

### The partition that motivates this phase

Group the seven dimensions by **how a score is arrived at** rather than by what
was done to them:

| Mechanism | Dimensions | Agreement (run 3) | Mean |
|---|---|---|---|
| **Derivation** — computed from an intake field | `process_frequency`, `data_governance`, `business_value` | 100 · 100 · 92 | **97%** |
| **Nothing** — anchors only | `adoption_risk`, `implementation_effort` | 73 · 70 | **72%** |
| **Prose procedure, no computation** | `data_readiness`, `non_ai_alternative` | 67 · 30 | **48%** |

The partition is clean and has no overlap, and at slot level across the 196
scoreable scores in run 3 it reads **97% where both scorers derived, 60% where
both judged**.

> **A procedure written in prose is 24 points worse than writing no procedure
> at all.**

`non_ai_alternative` has been repaired in prose three times — 70% → 61% → 30% —
each repair locally reasonable and evidence-driven, and it gates. It produces six
of eight verdict disagreements. **This phase stops trying to write it better.**

### Registered predictions

Written before implementing. The re-run that tests them is a separate protocol
and has **not** been run.

| Prediction | Now | Expected |
|---|---|---|
| `non_ai_alternative` agreement | 30% | **above 90%** — it joins the computation class |
| Verdict agreement | 73% | above 80% |
| Untouched dimensions | 67–100% | **stay within ±7** of run 3 |

Interpretation is fixed in advance: **above 90% confirms the mechanism
hypothesis. 70–90% means the derivation's entry point is the residual problem, as
it already is for `business_value`. Below 70% means computation does not rescue
this dimension and it should be demoted off the gate.**

The third prediction is a genuine control. Run 3 found every untouched dimension
drifting downward and could not separate variance from systematic drift. If they
hold steady while only the rebuilt dimension moves, the drift was an artefact of
the earlier phases; if they fall again, drift is real and has a cause worth
finding.

---

### Commit 1 — the intake asks for artefacts, not for a fraction

The obvious computation is *"what fraction of cases do your current rules or
reports already close?"* and it is the wrong question. `times_per_period` and
`data_sensitivity` work because they are **neutral facts a requester has no
reason to shade.** That one asks the requester to **price the alternative to
their own request, on the dimension that gates it** — the only field in the
intake with an adversarial incentive, in a pattern whose entire track record
comes from non-adversarial fields.

So the form asks **what exists**, and the level is derived from the list.
`existing_deterministic_artefacts` is a repeating entry of three fields:

- `name` — what it is, in the requester's words
- `what_it_does` — what it produces, in their words. The coverage rule reads this
  text, so a qualifier here ("about half the tickets") is load-bearing.
- `completes_without_judgement` — *after this runs, is the work done, or does
  someone still have to decide something?* The only field asking for an
  assessment, and it is a yes/no about what happens next in their own process.

**Three states, all distinct and all meaningful.** A populated list derives a
level; an **empty** list is a strong and reproducible signal that nothing exists;
**absent** means nobody was asked, and the dimension is recorded unknown rather
than estimated. Absent is the refusal branch, consistent with `business_value`.

### The exemplars, and where each entry came from

Entries were drawn only from a sentence the request already contains. Where a
request names no deterministic tooling the list is **empty**; nothing was
invented.

| Exemplar | List | Drawn from |
|---|---|---|
| `ticket_handover_summaries` | empty | "Handover notes are written by hand into the ticket in ServiceNow at the end of each shift." The team lead's written definition of a good note is quality criteria, not something that produces a note. |
| `hr_policy_questions` | empty | "we answer from the same handful of policy PDFs every time" — the PDFs are the source, not something that finishes the work. |
| `ticket_volume_by_team` | 1, completing | "My team lead exports it to Excel and pivots it by hand once a month." |
| `predict_laptop_failures` | empty | "The endpoint management agent could probably report some of that but it has never been switched on" — never switched on is not something that exists today. |
| `contract_renewal_drafting` | 1, not completing | "The buyers have a standard template for the summary" — it lays out the summary; the buyer still reads three sources and writes it. |
| `something_with_the_invoices` | **absent** | The request says nothing whatever about what exists today. Leaving it absent is the honest answer and it is the exemplar built to be unanswerable. |
| `ticket_routing_classifier` | 1, completing | "The keyword rules we set up years ago now cover maybe half of the tickets and they get worse every time a team is renamed or a new service is added." |

**One judgement call worth recording.** `hr_policy_questions` names a bundled
assistant that IT says already searches the same library. It is **not** in this
list, on two grounds: an LLM assistant is not a *deterministic* artefact, and
"nobody has tried it" means it is not doing the work today. That request is
caught by `existing_licensed_capability`, which is where a licence claim belongs.

**A cross-phase consequence, flagged rather than resolved.** ADR-029 justified
the two-part evidence test partly on the grounds that a licence claim which fails
Part B is "not lost — it is scored on `non_ai_alternative`, which carries the
already-licensed language at level 5". **That justification does not survive this
phase.** The rebuilt dimension measures what is *finished today*, so a licensed
capability nobody has switched on scores 1, not 5. The compensation argument is
void; the two-part test now stands or falls on its own merits. This was not
anticipated by either phase brief and is the kind of interaction only a
cross-phase read catches.

---

### Commit 2 — the dimension deleted and rebuilt

The body was **deleted and written fresh**, not edited. Three frames were laid
over each other and every previous repair addressed the top one:

1. Original anchors describing alternatives by **type** — a rule, a query, **a
   form field**, a template.
2. Phase 4's numeric bands describing **fraction of instances covered**.
3. Phase 5's axis sentence describing **whether an instance finishes without
   human judgement**.

**The sediment is gone and a test asserts it.** Level 1's *"no deterministic rule
can be written for it"* and level 5's *"a form field"* predate Phase 4, survived
two repairs each, and are what made the dimension answer two questions at once —
Scorer B hit the first (the zero band reachable by the number and contradicted by
the prose), Scorer A hit the second (a capture-time dropdown scoring 5 on an axis
demanding no human judgement). Neither string appears anywhere in the axis,
`scoring_rule`, description or anchors.

**Types now live in `notes`**, a new field on `Dimension` with the same role and
the same reason as `AntiPattern.notes`: it is not rendered into the prompt, so a
kind of thing can be named there without becoming a criterion. A rule, a query, a
report, a template — useful for prompting a requester whose list came back
suspiciously empty, never for scoring.

The new body: `axis` is one line, the `derivation` maps the list to a level, five
anchors restate those levels in artefact vocabulary, and no anchor names a type.
**60 lines → 53.**

### What is mechanical, and the one place it is not

| Artefact list | Level | Settled by |
|---|---|---|
| Absent | `null` → `incomplete` | code |
| Empty | 1 | code |
| Entries, none completing | 2 | code |
| ≥1 completing, part / most / all | 3 / 4 / 5 | **the reader, via `coverage_rule`** |

Three of the five outcomes and the refusal are settled in code. Levels 3–5 need
part / most / all, and **the three fields the intake asks for cannot separate
those without reading `what_it_does`**. So `coverage_rule` states the test in two
sentences — does the completing entries' own description cover the work
unqualified, with a stated remainder, or only a named subset — and the reader
applies it.

**This is a deviation from the phase plan's acceptance criterion 4**, which asked
that the dimension resolve by derivation whenever the list is present. It does not
for the top three levels, and the alternative was a fourth per-entry field asking
the requester what fraction their tool covers — **the adversarial question this
whole design exists to avoid.** Between a derivation with a narrow reader-applied
step and a fully mechanical one fed by a number the requester has an incentive to
shade, the first is the better trade. It is also exactly where ADR-026's residual
lives on `business_value`, and the phase's own interpretation table anticipates it:
70–90% agreement means the entry point is the residual problem.

Note what this means for the gate, which fires at ≥ 4: **the gating band is the
reader-applied one.** If the re-run lands above 90% the coverage rule is doing the
work; if it lands at 70–90% the gate is still resting on a judgement and
`requires_human_confirmation` should stay where ADR-028 put it.

### Exemplar results — no verdict changed, three reference scores now diverge

| Exemplar | Verdict | Total | `non_ai_alternative` |
|---|---|---|---|
| `ticket_handover_summaries` | `go` | 4.13 → **4.23** | ref 2 → **1** derived (empty list) |
| `hr_policy_questions` | `not_ai` | 3.17 → **3.47** | ref 4 → **1** derived (empty list) |
| `ticket_volume_by_team` | `not_ai` | 2.74 | 5, reader-applied — unchanged |
| `predict_laptop_failures` | `no_go` | 3.87 | 1 derived — matches its reference |
| `contract_renewal_drafting` | `no_go` | 3.08 | 2 derived — matches its reference |
| `something_with_the_invoices` | `incomplete` | — | ref 3 → **null**, field absent |
| `ticket_routing_classifier` | `go` | 4.57 | 3, reader-applied — unchanged |

`hr_policy_questions` is the interesting one. Its `non_ai_alternative` fell from 4
to 1 and `non_ai_alternative_suffices` no longer fires — only
`existing_capability_covers_it` does, which is its expected gate. **That is the
construct working**: nothing deterministic finishes HR policy answering today, and
the licensed-capability claim belongs to the anti-pattern gate rather than to this
dimension.

**The three divergent reference scores have not been re-authored.** The anchors'
meaning changed in this commit, which is the ADR-027 situation where re-scoring
fixtures to match a rule written in the same commit would make the reference set
circular. It is reported instead, and the divergence is inert because the
derivation is authoritative. Re-authoring them is a follow-up.

### A cross-phase interaction, and a caveat on the control

Recorded in Commit 1 and repeated here because it changes an earlier
justification: **ADR-029's fallback argument for the two-part evidence test is
void.** It held that a licence claim failing Part B was "not lost — it is scored
on `non_ai_alternative`, which carries the already-licensed language at level 5".
That language is gone, and the rebuilt dimension measures what is finished today,
so a licensed capability nobody has switched on scores 1. The two-part test now
stands on its own merits.

And the third registered prediction — that untouched dimensions stay within ±7 —
**is a weaker control than it looks**, for a reason worth stating before the
numbers arrive. The prompt changed again this phase: `non_ai_alternative` is
omitted from it whenever the derivation settles the level, so the prompt a scorer
reads is shorter on some cases and not others. ADR-029's drift candidates included
exactly that mechanism. If the untouched dimensions move again, prompt length
remains a live explanation and this phase did not eliminate it.

---

## ADR-031 — Measuring the system against the reference

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** one new script; no production file touched
**Reference:** `evals/scores_B_run5.yaml` + `evaluacion/scores_A_run5.yaml`, agreed slots only
**Evidence for the design:** `evaluacion/12_five_runs.md`

Five runs measured scorer against scorer. **The product has never been measured.**
The corpus now carries every intake field the engine reads, so this is finally
executable.

### Registered predictions, before the code

**(a) — as briefed, and it is wrong; the corrected version is registered instead.**

The brief asks me to state that the model now scores only three dimensions —
`adoption_risk`, `data_readiness`, `implementation_effort` — because the other
four derive from intake fields and the model never sees them. **That is not what
the code does**, and registering it uncorrected would misattribute every
`business_value` error to a derivation that never ran. Read from `assess.py` and
`scoring.py` before writing the measurement:

- `derive_scores()` skips any derivation with `is_fallback`, and
  `business_value`'s `MagnitudeDerivation` is exactly that. **`business_value` is
  always put to the model**, in every case; the derivation only fills it when the
  model returns null. It is model-scored with a computed safety net, not derived.
- `non_ai_alternative`'s `ArtefactDerivation` returns a level for `absent`,
  `empty` and `none_complete` — but returns `None` on the coverage branch, which
  leaves the dimension in the prompt. On the four v2 cases with a completing
  artefact, **the model scores it.**
- `process_frequency` and `data_governance` are omitted only where their intake
  field is populated. Six v2 cases have a blank frequency field and five a blank
  classification, so on those the model scores them too.

So the corrected statement, which is the one being tested: **the model scores
four dimensions on most cases** — the three judged ones plus `business_value` —
**and up to seven on the sparse ones.** Two dimensions are fully removed from the
model's work only where the requester filled the field. That is still the main
finding of the rubric work and it still has not been written down anywhere; it is
just less clean than briefed.

**(b) Model exact-match on the three judged dimensions will not much exceed 76%,
and if it does, suspect the reference.** The human-human figure on those three is
68 of 90. There is a bias worth naming in advance: **the reference contains only
slots where the two scorers already agreed**, so the model is being graded on the
subset of the corpus that is easiest to score. That biases model accuracy
upward relative to any full-corpus measure. A model result far above 76% is more
likely to be an artefact of that selection than a capability.

**(c) Verdict accuracy will be bounded by those dimensions plus the anti-pattern
matching.** The two scorers' anti-pattern matches already differ on six of thirty
cases — A-08, A-11, B-03, B-12, B-16, B-18 — so the anti-pattern arm is a second
uncontrolled input to the verdict, not just the dimension scores.

**(d) Median latency about 5 s, with a bimodal tail.** ADR-023 measured five of
six requests at roughly 5 s and one at 416 s, against a 30 s timeout. Expected
timeout rate on 30 cases: **0 to 5 (0–17%)**, with 1–2 the central guess.
Timeouts are an infrastructure outcome and are counted as their own class, never
as a wrong verdict.

### The reference, and what it costs

A slot enters the reference **only where both scorers recorded the same score.**
Disagreements are excluded — not averaged, not adjudicated. Built before the run:

| Dimension | In reference | Excluded (disagreed) | Both refused |
|---|---|---|---|
| `business_value` | 25 | 0 | 5 |
| `adoption_risk` | 25 | 5 | 0 |
| `data_readiness` | 22 | 8 | 0 |
| `process_frequency` | 24 | 1 | 5 |
| `implementation_effort` | 21 | 9 | 0 |
| `data_governance` | 27 | 2 | 1 |
| `non_ai_alternative` | 30 | 0 | 0 |
| **Total** | **174** | **25** | **11** |

**Twenty-five slots have no right answer** because the study never reconciled
them, and that is the honest cost of the design. Note where they are: 22 of the
25 are in the three judged dimensions. The model is therefore graded most
thinly exactly where it does the most work.

The eleven both-refused slots are reported separately. A null is not a score, so
they cannot enter a match count — but whether the engine also refuses there is
worth knowing, and it is a property of the derivations rather than of the model.

**Verdicts** are computed by running the production scorer over each scorer's
slot values with the real intake, so gates, completeness and bands all come from
`scoring.py` rather than from anything this script reimplements. A verdict enters
the reference where both scorers' computed verdicts agree.

### Rules for this phase

Nothing in `rubric.yaml`, `patterns.yaml`, `scoring.py`, `assess.py` or any other
production file is touched. **Nothing is tuned in response to the result.** If the
number is bad, that is the result, and ADR-024's rule holds: the verdict outcome
is reported as a confusion matrix with a stated cost ordering —
`false go > false not_ai > false no_go > spurious incomplete` — and never
collapsed to a scalar, because a scalar lets one severe error trade against two
mild ones and read as progress.

---

## ADR-032 — Distinctness belongs in the grammar, and a derived value must survive an unscorable outcome

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** `assess.py` schema construction, one `Outcome` field
**Cause:** the product measurement in `81fd155` did not measure the model

### The defect

`build_response_schema` pinned `dimension_assessments` to
`minItems = maxItems = len(asked)` and pinned `dimension_id` to an enum. It did
not require the entries to be **distinct**. `qwen2.5:7b` satisfied both
constraints by emitting `data_readiness` twice and omitting
`implementation_effort` — **on 29 of 30 cases, in both measurement passes.**
`_index_assessments` dropped the duplicate into `ignored_dimension_ids` and the
omitted dimension was simply unknown, so `implementation_effort` was null
everywhere, its 0% match was structural rather than inaccuracy, and the resulting
0.30 of unknown weight drove **15 of the 22 verdict errors**.

This is **ADR-019 recurring one level down**. That ADR's finding was that a schema
which does not demand the work does not get the work; this is a schema that does
not demand *distinctness* and does not get it. A constraint that can be moved into
the grammar is not enforced by leaving it implicit.

### It went into the grammar, and the belt-and-braces version defeats the belt

`uniqueItems: true` would **not** have caught this: two entries with the same
`dimension_id` and different `evidence` are distinct items, so the weaker
constraint accepts exactly the payload that caused the defect. A test records
that, so the weaker fix is not proposed later.

What works is `prefixItems`: position *i* is pinned to
`{"const": <dimension i>}`, which the decoder cannot violate. Stronger than
uniqueness — it also fixes the order the prompt already asks for.

Both facts below were **measured against Ollama 0.32.1 with qwen2.5:7b**, not
assumed:

- Told to put one id in every slot, the model emitted the pinned sequence
  instead. The converter honours `prefixItems` and `const`.
- **With `items` present alongside `prefixItems`, the converter honours `items`
  and ignores `prefixItems`**, and the model duplicated freely again. So `items`
  had to be **removed**, not kept as a fallback. Leaving it in as insurance
  silently disables the insurance. `minItems == maxItems == len(prefixItems)`
  already forbids extras.

No prose instruction was added, no retry path was needed, and nothing in
`rubric.yaml`, `patterns.yaml` or the anchors was touched.

### The second fix: `Outcome.resolved_scores`

Reconstructing what the system scored took three sources and was wrong twice, and
both errors produced plausible numbers. Reading `outcome.contributions` reported
**deterministic lookups at an 8% match**, because contributions are empty whenever
a case is gated or incomplete. Reading the merged `Assessment` reported
`business_value` at **0%**, because its fallback derivation is applied inside
`score()` on a private copy and never written back — `fallback_derived_dimensions`
named the dimension and discarded the number.

So on an unscorable case, the value a derivation computed was **unrecoverable from
the result**. `Outcome.resolved_scores` now records every dimension's
post-derivation value regardless of scorability. An 8% score on a deterministic
lookup is precisely the shape of measurement artefact ADR-024 exists to catch, and
it was caught by disbelieving the number rather than by any check in the code.

### Registered predictions for the re-measurement

Written before running it.

| Prediction | Basis |
|---|---|
| `implementation_effort` will be scored on most cases rather than none | it was null only because the grammar let the model drop it |
| Spurious incompletes will fall sharply from 15 | they were caused by 0.30 of unknown weight on the two dropped dimensions |
| Model exact-match on the judged dimensions will rise from 1% but stay **below** the 76% human-human ceiling; above it, suspect the reference | the reference contains only slots the two scorers already agreed on, so it is the easy subset |
| **Self-consistency will be the binding constraint on any accuracy figure** | two passes of the identical system already disagreed on 8 of 30 verdicts |

The last one decides how the rest may be read. **Self-consistency is reported
first, before any accuracy number**, because a system that disagrees with itself
on eight verdicts cannot be said to agree with a reference to any finer resolution
than that. The measurement is run **three times**, unchanged in every other
respect, and nothing is tuned in response to what it shows.

---

## ADR-033 — The same measurement with a larger model, to try to refute the mechanism finding

**Date:** 2026-07-26 · **Status:** accepted · **Scope:** one measurement run; no code, no config
**Refutes or confirms:** the claim in ADR-032's re-measurement that computation reproduces and judgement does not

### Why this run exists

The 7B result gives **5% exact and 33% slot-level self-consistency on
model-scored dimensions against 97% and 95% on derived ones**, and that contrast
is about to be written up as a general claim about mechanism. **A cheap
measurement could refute it.** If a larger model scores well on the same three
dimensions, the finding is about model size and the conclusion would be wrong.

So the same measurement runs again with `qwen2.5:14b` and **one variable
changed**: `OLLAMA_MODEL`. Same corpus, same rubric, same reference, same script,
same three passes. No dimension converted, no anchor touched, no prompt adjusted
for the larger model — adjusting the prompt would change two things at once and
forfeit the comparison.

### Registered predictions and decision thresholds, before running

**Model-scored exact-match on the three judged dimensions.** The 7B gave 5%
exact, 21% within ±1 pooled. Thresholds, adopted as briefed because they are
reasonable and pre-committing to someone else's line is stronger than inventing
my own:

| Outcome | Reading |
|---|---|
| **above 50% exact** | the mechanism finding is **refuted** — it was about model size |
| **25–50% exact** | **qualified** — mechanism matters, but so does capability |
| **below 25% exact** | **confirmed** |

My expectation: **10–20% exact, 35–50% within ±1.** Reasoning, so the guess is
falsifiable rather than vague. The three judged dimensions ask for things the
request text mostly does not contain — whether users were consulted, what
happened to the last tool, how many quarters an integration takes. ADR-021
measured that directly: those dimensions came back unknown on almost every
request *because the free text does not carry them*. A larger model reads the
same absent information. What I expect it to buy is fewer refusals and better
±1 banding, not exact agreement.

**Self-consistency, and it is the number that matters most.** The 7B gave 50% of
verdicts and 33% of judged slots identical across three passes. **A larger model
that is accurate but still unstable does not rescue the system**, because a
verdict that changes between runs cannot be defended to a requester whatever its
average accuracy. Expectation: **55–70% verdicts, 40–55% judged slots** — better,
because a stronger model has less reason to flip a marginal judgement, and still
far from usable. If self-consistency stays near 50% while exact-match rises, the
right conclusion is that accuracy figures for this system are not meaningful at
all, and that is a worse outcome than a low score.

**Latency, on a 12 GB card.** 14B at Q4_K_M is about 9 GB of weights against
~10.2 GB free, so the KV cache will be tight and some layers may spill to CPU.
The 7B ran at a 4.3 s median. Expectation: **12–25 s median, and I do expect
timeouts at the shipped 30 s setting — 2 to 8 of 90 requests.** If spill is worse
than expected the median could exceed 30 s and most of the run would time out,
which is itself a reportable result about the shipped default on this hardware.

**Refusal rate.** The 7B declined `adoption_risk` on 19–24 of 30 cases per pass
and `data_readiness` on 16–18; that, not wrong answers, drove the spurious
incompletes. Expectation: **refusals roughly halve** and spurious incompletes
fall with them. This is the prediction I hold most confidently, because refusing
is the behaviour most likely to be capability-bound rather than
information-bound.

### Rules

Nothing is tuned in response to the result. If the model does not fit or the run
is impractical, the run **stops and says so** rather than reducing the corpus or
the passes — a partial run is not comparable to the 7B numbers and would be worse
than no run at all.

### The result: qualified, not refuted, and not confirmed

**25% exact on the three judged dimensions** — 5% → 25% on the same corpus, same
rubric, same reference, one variable changed. That lands **exactly on the boundary
between "qualified" and "confirmed"**, and the honest reading of a threshold hit on
its edge is the weaker of the two claims: **qualified.**

| Registered | Expected | 7B | 14B | Verdict on the prediction |
|---|---|---|---|---|
| Model-scored exact, three judged dims | 10–20% | 5% | **25%** | above my range; on the qualify/confirm line |
| Model-scored within ±1 | 35–50% | 22% | **67%** | well above; I underestimated banding |
| Self-consistency, verdicts | 55–70% | 50% | **77%** | held, top of range |
| Self-consistency, judged slots | 40–55% | 33% | **34%** | **failed — no movement at all** |
| Latency median | 12–25 s | 4.3 s | **8.6 s** | below my range; the card held it |
| Timeouts at 30 s | 2–8 of 90 | 0 | **0 of 90** | failed; no spill penalty materialised |
| Refusals roughly halve | — | 19–24/30 | **0/30** | held far beyond the prediction |

**What a 3× larger model bought, precisely.** Refusals on `adoption_risk` went
19–24 of 30 to **zero**. Spurious incompletes went 41 to **3**. Verdict matches
went 25 of 84 to **52**. That is a real and large improvement, and every part of
it is the model *answering* rather than the model being *right*: within-±1 tripled
to 67% while exact match reached only 25%.

**What it did not buy, and this is the finding.** Slot-level self-consistency on
the judged dimensions is **34%, against the 7B's 33%.** Identical. The larger model
answers far more often and agrees with itself on those answers no more than the
small one did. Derived slots stayed at 94–95% for both. Two models a generation
apart in capability produce the same instability on the same three dimensions,
and near-perfect stability on the four that are computed.

**So the mechanism claim survives in a narrower form.** It cannot be stated as
"judgement does not reproduce, computation does" — 5% to 25% is too big a move to
attribute to mechanism alone, and capability clearly matters for whether the model
engages at all. It can be stated as: **a dimension resolved by computation is
stable across models and across runs; a dimension resolved by judgement is not,
and scaling the model 3× does not make it so.** The instability is in the
construct, not in the parameter count.

**One cost the improvement carried, and it is in the worst class.** False `go`
went 1 to **7** — 2, 3, 2 per pass, against 0, 0, 1 for the 7B. Under the stated
cost ordering that is the most expensive error type in the system, and it got
worse as the model got better. The reason is the same as the improvement: the 7B
mostly refused and fell into `incomplete`, which is the *cheapest* error class. A
model that answers can be wrong in the expensive direction. **This is the
clearest demonstration yet of why ADR-024 forbids the scalar** — collapse this to
one accuracy number and it reads as an unambiguous 2× improvement, when the worst
error class multiplied by seven.

Nothing was tuned in response to any of this, and the 7B remains the shipped
default: `DEFAULT_OLLAMA_MODEL` is untouched.

---

## ADR-034 — Phase 10: an intake agent, and the two things building it exposed

**Status:** accepted · **Date:** 2026-07-27

Phase 2 cut the conversational agent. That decision is reversed here, deliberately
and by the owner: the project's goal changed, and a portfolio piece for a role
building an AI Agent Hub that contains no agent is not one.

It is not a reversal of the *reasoning*, though, and that matters. Phase 2 cut a
conversational agent that would have **scored dimensions in conversation.** This
one cannot. The measurement programme between then and now settled what the model
is for — it finds and quotes evidence, kw = 0.97 for computed slots against
kappa = 0.04 for judged ones — and the agent implements that split rather than
ignoring it. `score_and_gate` takes a `RequestIntake` and a list of
quote-verified anti-pattern matches, and there is no parameter through which a
model-produced number could arrive. A test asserts the signature.

### The interview needs two things a form does not

**A gate must not fire on a field nobody has been asked about.**
`no_named_business_owner` fires on an empty `business_owner`, which is right for a
submitted form: the requester had their chance and left it blank. In an interview
an empty field means *not asked yet*, and honouring the gate at turn zero would
end every conversation with `no_go` before a word was exchanged. So gates whose
deciding field is still unasked are held back — and the loop tracks what it has
*asked*, not just what is *filled*, because a requester who cannot name an owner
has answered, and the gate must then fire. Asked-and-unanswerable and never-asked
look identical in the intake and mean opposite things.

**A question has to be able to change something.** A field earns a turn only if
it can decide a gate or resolve a dimension still unknown. Without that rule the
agent asked who does the work today — useful context on a form, a wasted turn in
a conversation — and reached the same verdict four questions later.

### The ceiling, stated rather than hidden

`adoption_risk`, `data_readiness` and `implementation_effort` carry 0.45 of the
rubric weight between them and no intake field supplies any of them. With the
model barred from scoring, **`go` is unreachable through the interview.** What is
reachable is `no_go` and `not_ai` by gate, both decided, and `incomplete` naming
exactly which dimensions no question can fix.

That is not a defect in the agent. It is the architecture rule's cost, made
visible, and the fix is the one ADR-031's write-up already recommended: convert
those three to intake fields. Building the agent did not create that debt, it
priced it.

### The live run found a defect the offline run could not

The scripted mock filled four fields. The live 7B filled one, and died on
`existing_deterministic_artefacts` — twice, with `Expecting property name enclosed
in double quotes`.

The extraction schema had asked for a JSON list **inside a JSON string**.
Grammar-constrained decoding cannot help with that: the grammar constrains the
outer string and has nothing whatever to say about its contents. So the hardest
extraction in the interview was the one piece running unconstrained, and the 7B
emitted unquoted keys.

`value` is now shaped per field — a real array for the artefact list, a real
object for volume, an enum for the classifications. **This is ADR-032 recurring
one level down**: a constraint that can be moved into the grammar is not enforced
by leaving it implicit. Twice now, in two different files, the same mistake has
cost a measurable failure.

A second live finding is recorded and **not** fixed: the 7B sometimes pastes the
whole internal prompt hint into its question, asks four things at once, and signs
off with emoji. That is a prompt-quality problem in exactly the place the model is
allowed to be weak — it affects how a question reads, never what is recorded or
decided — and this phase ships without tuning it, because tuning a prompt against
a single observation is how the earlier phases took a dimension from 70% to 30%.

---

## ADR-035 — Phase 11: converting the last three dimensions, and what that moved

**Status:** accepted · **Date:** 2026-07-27 · **Rubric v3.0.0**

Phase 10 priced the architecture rule: `adoption_risk`, `data_readiness` and
`implementation_effort` carry 0.45 of the rubric's weight, no intake field
supplied any of them, and with the model barred from scoring, `go` was
unreachable. This supplies them. A fully answered intake now reaches `go` at 4.49
with all seven dimensions derived and no model-produced number anywhere in the
approval.

The owner took this decision with the trade-off stated in advance: converting may
relocate the judgement to the requester rather than resolve it, exactly as §4.3
of the paper documents for `non_ai_alternative`. `docs/RELOCATION.md` records the
transfer field by field, and is a required deliverable rather than commentary.

### Rules before tables

Every field had to answer one question before it was written into the schema:
**could two requesters looking at the same real situation give different answers?**
Where the answer was yes, a numbered rule forces it. R1–R9 live in `rubric.yaml`
beside the anchors because they ARE the anchor semantics, and there is a test per
rule. A lookup table over an ambiguous field is a judgement with a number stapled
to it, which is the failure mode three prose repairs already taught this project.

**R1 is the load-bearing one.** `users_consulted` would otherwise be a question
about how collaborative the requester feels they were. So a user counts as
consulted only if the requester can quote something one of them said, and
`record_field` verifies that quote against what they actually typed — an invented
quote is dropped and the level demotes from 2 to 4. Same two-part evidence test
that took the anti-pattern checks from 0% agreement to full agreement (ADR-029).

**The worst signal governs, never the average.** The effort and adoption anchors
are disjunctive — "several integrations, OR a new platform component, OR
retraining a whole team" is already a 4 — so a maximum agrees with them and a
mean would quietly average a blocker away.

### Nothing published moved

Every derivation returns `None` when its evidence object is absent, which is
every intake in the measured corpus, so those dimensions return to model scoring
exactly as under v2.0.0. Verified rather than asserted: the reference is still
174 slots / 25 excluded / 11 both-null / 28 verdicts, and `tools/kappa_system.py`
reproduces `evals/kappa_system_results.json` byte-identically under v3.0.0. A
test pins all four counts.

### Two orderings the conversion exposed

**A decided verdict must not end the interview while a question could move it.**
`adoption_risk` weighs 0.17, which fits inside the 0.25 unknown-weight budget, so
a request could clear completeness with nobody having been asked who was
consulted — and the loop would stop and approve. An approval issued while a
question that could still change it went unasked is the one outcome this product
exists to prevent. A fired gate stays the exception, and a real one: nothing a
later answer could add outvotes a gate.

**The contract's baseline had nothing supplying it.** Every interview issued a
contract recording its baseline as unmeasured. `stated_baseline_value` is now a
`contract_field`: no dimension needs it, so it is asked only once the verdict is
heading for `go`.

### The finding that is not a conversion

**`adoption_risk` has no gate.** Nobody consulted, replacing a way of working the
users chose themselves, 900 people to change — `adoption_risk` derives to 5 and
the request is still approved at 3.68, because at weight 0.17 the other six
dimensions outvote it. This is pre-existing behaviour; under v2.0.0 a model
scoring 5 produced the same result. What changed is that it is now reachable
deterministically and therefore demonstrable.

The rubric's own reasoning about gates applies directly — *a weight small enough
to be fair to a normal case is too small to stop an extreme one* — and no gate
was ever written for the dimension this system says decides whether an internal
tool succeeds. Adding one would change verdicts, so it is left as an open
question for the owner and pinned by a test rather than decided inside a phase
whose brief forbids altering published numbers.

### What still resists

`non_ai_alternative` levels 3–5 need *part / most / all*, which requires reading
artefact descriptions against the work. The intake deliberately does not ask the
requester what fraction their existing tool covers: that is the one question in
the form with an adversarial incentive, since it asks them to price the
alternative to their own request on the dimension that gates it. So a request
whose artefacts complete part of the work still needs a human reader. That is the
honest boundary of this programme and it is left standing.

### ADR-035 addendum — what the live run of the approval path showed

The offline scripted run reaches `go` at 4.49 with all seven dimensions derived
and a contract carrying a measured baseline. The live 7B reached `go` at 3.74,
and the three ways it fell short are worth more than the success.

**Three unbounded corners of the grammar had to be closed first,** and each cost
a hung or broken run before it was found: arrays with no `maxItems` (the model
kept generating systems), and strings with no `maxLength` (the model kept
writing). Both matter more than they look, because a timeout frees the *caller*
and not the work — so one runaway generation keeps occupying the model and every
later call in the interview queues behind it. **That is the third and fourth time
in three phases that an unconstrained corner of a grammar has cost a measurable
failure**, after ADR-032 and ADR-034. The lesson keeps arriving by way of a
broken run rather than a review.

**The 7B extracted the adoption evidence backwards.** Given "The analysts asked
for this themselves. Marta said it sits in the wrong queue until someone
notices", it recorded `users_consulted: nobody` and an empty quote — deriving
`adoption_risk = 5` where the truth is 1. The hardest field to convert is also
the hardest to extract, and the two failures compound.

**And the request was approved anyway, at 3.74.** A live model producing the
worst possible adoption reading did not stop the verdict, because
`adoption_risk` has no gate. `docs/RELOCATION.md` §4 predicted exactly this from
a constructed example; the live run produced it by accident on the reference
`go` exemplar within an hour. That is the strongest argument available for
gating the dimension, and it is still the owner's decision rather than this
phase's.

Two barren answers on the baseline then ended the interview, so the live contract
records its baseline as unmeasured. Nothing was tuned in response to any of this.
