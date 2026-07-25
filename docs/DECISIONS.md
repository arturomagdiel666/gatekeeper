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
