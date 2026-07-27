---
tags: [evaluation, finding, system, gatekeeper]
runs: system measured against reference, two models, three passes each
status: definitive for this corpus
---

# Measuring the system: what a rubric is for, and what a model is for

Five runs measured scorer against scorer. This one measures the product. Same 30 cases, same rubric, same reference — built only from slots where two independent scorers agreed, with disagreements excluded rather than adjudicated.

Two models, three passes each, one variable between them.

---

## 1 · Self-consistency, first, because it bounds everything after it

|  | 7B | 14B |
|---|---|---|
| Verdict identical across three passes | 15 / 30 = **50%** | 23 / 30 = **77%** |
| Slot identical — **four derived** dimensions | 114 / 120 = **95%** | 113 / 120 = **94%** |
| Slot identical — **three judged** dimensions | 30 / 90 = **33%** | 31 / 90 = **34%** |

**Tripling the model moved judged-slot stability by one percentage point.**

Verdict stability rose from 50% to 77%, but not because the model decided more consistently — because it *refused* less. `adoption_risk` went from unscored on 19–24 of 30 cases to unscored on none. The system reached a verdict more often; it did not reach the same verdict more reliably at the level where the judgement happens.

No accuracy figure below can be read to a finer resolution than these numbers permit.

---

## 2 · Accuracy against the reference

Pooled over three passes, agreed slots only.

| | Dimension | n | 7B exact | 7B ±1 | 14B exact | 14B ±1 |
|---|---|---|---|---|---|---|
| **Derived** | `process_frequency` | 72 | 100% | 100% | **100%** | 100% |
| | `data_governance` | 75 | 100% | 100% | **100%** | 100% |
| | `non_ai_alternative` | 78 | 100% | 100% | **100%** | 100% |
| | `business_value` | 72 | 88% | 96% | **88%** | 96% |
| | **subtotal** | 297 | **97%** | 99% | **97%** | 99% |
| **Judged** | `implementation_effort` | 63 | 8% | 29% | **37%** | 79% |
| | `data_readiness` | 66 | 8% | 26% | **20%** | 70% |
| | `adoption_risk` | 75 | 1% | 13% | **19%** | 53% |
| | **subtotal** | 204 | **5%** | 22% | **25%** | 67% |

The derived block is **byte-identical across models**, as it must be — the model never touches it. That identity is the study's control, and it is exact.

The judged block improved fivefold on exact match and tripled within ±1. That is a real capability difference and it must not be explained away.

---

## 3 · The claim that survives, stated precisely

The result cannot be stated as *"judgement does not reproduce, computation does."* A five-fold move from 5% to 25% is too large to attribute to mechanism alone. **Capability plainly governs whether the model engages with the task at all.**

What the data does support:

> **A dimension resolved by computation is stable across models and across runs. A dimension resolved by judgement is stable across neither, and tripling the model does not make it so.**

The evidence is the pair of controls. On identical constructs, judged-slot self-consistency went 33% → 34% while both models held 94–95% on the computed ones. That places the instability **in the construct, not in the parameter count**.

A larger model answers more often and is right more often. It is not more consistent with itself where the judgement lives.

---

## 4 · The improvement produced the most expensive error

Verdicts, pooled, against the reference. Cost ordering: **false go > false not_ai > false no_go > spurious incomplete.**

| | 7B | 14B |
|---|---|---|
| Matching | 25 / 84 | **52 / 84** |
| **False `go`** | **1** | **7** |
| False `not_ai` | 3 | 6 |
| False `no_go` | 14 | 16 |
| Spurious `incomplete` | 41 | **3** |

Collapsed to a single accuracy number, this reads as a clean doubling: 30% to 62%. **The most costly error class multiplied by seven.**

The 7B's near-zero on false `go` was not a safety property. It was purchased by refusing so often that the system rarely reached the approval band at all. A model that answers can be wrong expensively; a model that refuses is only ever wrong cheaply.

This is the sharpest vindication the project has produced of the rule forbidding a scalar verdict metric — a rule adopted on principle, several phases before there was data to support it.

---

## 5 · Latency and refusal

|  | 7B | 14B |
|---|---|---|
| Median / max | 4.3 s / 6.1 s | 8.6 s / 12.0 s |
| Timeouts | 0 / 90 | 0 / 90 |
| Retries | 0 / 90 | 0 / 90 |
| `adoption_risk` unscored | 19–24 of 30 | **0 of 30** |
| `data_readiness` unscored | 16–18 | 2–3 |
| `implementation_effort` unscored | 12–17 | 0–1 |

The 14B fits in 12 GB (11.2 used) and doubles latency without approaching the timeout. The pathological 416-second tail recorded earlier has not recurred across 180 requests.

---

## 6 · Applying the rubric to itself

Gatekeeper's `non_ai_alternative` dimension asks how completely a non-AI solution would solve the same problem, and gates at level 4.

Applied to Gatekeeper's own scoring function, using this project's own measurements:

- The non-AI solution — an intake form with lookup tables and deterministic gates — resolves **four of seven dimensions at 97% accuracy and 94% self-consistency.**
- The AI solution resolves the other three at **25% accuracy and 34% self-consistency**, with seven false approvals.
- All three remaining dimensions ask for facts a requester could state — whether users were consulted, whether the data has been checked, which integrations are needed — so they are convertible in principle, though that is a prediction and not yet a measurement.

That is level 4 at minimum: *things that exist finish most of this work on their own.* The gate fires. **The verdict is `Not-AI`.**

The instrument, applied to itself, says do not build this with AI.

### And the qualification that keeps it honest

That conclusion applies to **scoring**, not to the whole product. One task in this system has measured evidence in the model's favour: **reading free text and quoting the sentence that supports an anti-pattern.**

Anti-patterns whose signals describe what the requester *said* reached 100% agreement between independent scorers. Those requiring a judgement about the world reached 0%, until a two-part evidence test converted them into a search for a quotable sentence — after which they also reached agreement. That is language work, and no lookup table does it.

So the architecture the evidence supports is not *no AI*. It is:

> **The model finds and quotes the evidence. The form and the tables decide.**

A `Not-AI` verdict on the scoring function is not a failed build. It is the tool doing exactly what it was made to do, on the hardest possible case, and reporting an answer its author did not want.

---

## 7 · What is now known, end to end

> Four of seven dimensions reach **97% accuracy** against a two-scorer reference and **94% self-consistency**, and are identical across two model sizes because no model touches them. Three are scored by a model: **25% exact, 67% within one level, 34% self-consistency**, and tripling model size moved that last figure by one point.
>
> Verdict agreement with the reference is **52 of 84 case-passes**. Seven of those errors are false approvals — the most expensive class — and they appeared *because* the larger model stopped refusing.
>
> Reliability is measured across six runs. **Validity is not.** The four accurate dimensions depend on fields a requester fills, and two independent scorers would have filled 8 and 11 of those 30 fields differently from how they are stated.

---

## 8 · What follows

1. **Convert `adoption_risk`, `data_readiness` and `implementation_effort`.** They are the entire residual and the evidence for how is now unambiguous. Convert them and the model leaves the scoring path.
2. **Keep the model for evidence extraction**, and measure that separately. It has never been measured on its own; it has only ever been measured inside a scoring task it was bad at.
3. **Measure the validity of the intake fields.** Have a second party fill them independently and measure agreement on the fields rather than the scores. That is where the system's weight now sits, and no work so far has touched it.
4. **Do not tune the prompt for the judged dimensions.** Two models, six passes and a fivefold capability difference all point at the constructs. Prompt work would be the fourth attempt to fix a construct by rewriting words around it, and the first three took a dimension from 70% to 30%.

---

## 9 · Method

Seven registered predictions on this run; three held, three failed, one held far past its bound. Across the project: **twenty-one predictions registered, eight held.**

Two things this measurement produced that no single number could have:

**The schema defect.** The first system measurement returned 1% accuracy on model-scored dimensions. That was not the model — the response schema pinned the *count* of dimension entries without requiring them to be *distinct*, so the model satisfied it by emitting one dimension twice and omitting another, on 29 of 30 cases. Fixing it in the grammar (`prefixItems` with `const`, and removing the `items` key that silently overrode it) took the affected dimension from a structural zero to a measurable 37%. **A constraint that can be moved into the grammar is not enforced by leaving it implicit** — the same lesson this project learned two phases earlier, recurring one level down.

**The measurement instrument was wrong twice before it was right**, and both wrong versions produced plausible numbers — an 8% match rate on a deterministic lookup, which reads as a devastating result and was entirely an artefact of reading the wrong field. It was caught because the person running it reported it unprompted.

Which is the whole method in one line: **a number that looks like a finding is a finding about your instrument until you have checked which.**
