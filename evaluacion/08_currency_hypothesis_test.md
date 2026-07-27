---
tags: [evaluation, finding, rubric, gatekeeper]
status: hypothesis refuted — replacement finding recorded
inputs: scores_A.yaml, scores_B.yaml (no re-run)
---

# Currency hypothesis: refuted

## The hypothesis

`business_value` anchors state thresholds in USD; every figure in the corpus is in Mexican pesos; no conversion basis is stated. At ~17–20 MXN/USD, reading a peso figure against a USD threshold lands **exactly one level high** — which is the shape of the observed one-directional skew (A higher than B in 11 of 30, lower in none).

**Prediction:** the disagreement concentrates on cases whose evidence is a currency figure, and vanishes on cases scored by hours or volume.

## The test

Both scorers' `business_value` quotes and notes were classified by whether the cited evidence contains a currency figure. No re-run was required.

| | n | With currency evidence |
|---|---|---|
| Cases where scorers **disagreed** | 11 | 3 — **27%** |
| Cases where scorers **agreed** | 19 | 5 — **26%** |

**Refuted.** Currency evidence is present at the same rate in agreements and disagreements. It has no explanatory power over the skew.

Confirming detail: of the five agreements with currency evidence — A-06, A-07, B-03, B-11, B-18 — **all five agree exactly**, and each cites an explicit peso figure. If the currency mismatch drove disagreement, these are the cases where it would show, and it does not.

The currency gap remains a real defect. It is an objective definitional hole and should be closed. But closing it **will not improve agreement**, and `business_value` still needs the harder anchor work. That is exactly what the test was for.

---

## What actually explains the skew

The disagreements concentrate at the **bottom of the scale**, not on any denomination:

| Levels in conflict | Cases |
|---|---|
| 1 vs 2 | **6** |
| 1 vs 3 | 1 |
| 2 vs 3 | 2 |
| 3 vs 4 | 1 |
| 4 vs 5 | 1 |

Seven of eleven disagreements sit at level 1–3, and six are the single boundary between 1 and 2.

And the predictor is clean:

| | n | At least one scorer marked `confidence: low` |
|---|---|---|
| Disagreements | 11 | **11 — 100%** |
| Agreements | 19 | 13 — 68% |

**Every single disagreement is a case where at least one scorer marked low confidence.** Low confidence does not guarantee disagreement — 13 low-confidence cases still agreed — but its absence guarantees agreement. In this corpus, `confidence: high` or `medium` on both sides never once produced a disagreement.

### The mechanism, and it is an instruction rather than an anchor

`business_value`'s description contains this rule:

> *If the request names no figure, estimate the order of magnitude from the process described and record `confidence: low`. A missing number must never pull this score down.*

That instruction was added deliberately, in Phase 2.1, to stop the heaviest-weighted dimension from degenerating into a measure of how well the requester writes a business case. **It fixed the bias it was aimed at, and introduced a reproducibility problem in its place.**

Both scorers followed it. Both marked low confidence. And then they estimated differently — because "estimate the order of magnitude from the process described" is an instruction to perform a judgement the anchors give no procedure for. Scorer A estimated up; Scorer B estimated down; neither is wrong under the text.

The cases where this bites are exactly the vague ones: A-01, A-03, B-07, B-12, B-14, B-16 — requests with no stated magnitude at all. Those are also the requests a real Hub receives most often.

### Why this matters more than the currency gap

The currency gap is a hole in a definition: state a conversion basis and it closes, permanently, for everyone.

This is a hole in a **procedure**. The rubric asks for an estimate and supplies no method, so the estimate carries the scorer rather than the instrument. No amount of anchor rewriting fixes it, because the anchors are not the problem — the missing step is *how to estimate a magnitude from a process description when no figure is given*.

Three candidate repairs, in ascending cost:

1. **Make the estimation procedure explicit** — e.g. "multiply the stated volume by a stated per-instance time or cost; if neither is stated, use the intake `people_affected` and `times_per_period` fields; if those are blank, score `null`." Turns a judgement into a derivation, which §2 of the agreement study showed is the only thing that reliably produces convergence.
2. **Refuse rather than estimate.** Make `business_value` return `null` when no magnitude can be computed. Honest, and it would push many cases to `incomplete` — which the corpus produced **zero** of and arguably should produce more.
3. **Split the dimension** into stated magnitude and estimated magnitude, scored separately. Most faithful, most expensive, and it changes the weight structure.

Option 1 is consistent with the strongest evidence in the study: the two dimensions that reached 100% agreement did so because a derivation table replaced a judgement.

---

## Method note

This test cost two queries against files that already existed. It refuted the leading hypothesis about the worst dimension in the rubric, and replaced it with one that has a cleaner signal — 100% versus 27%.

It is worth naming why it was cheap: **both scorers were required to record a confidence value and a verbatim quote per score.** Neither field was requested for this purpose. The confidence field is what made the real mechanism visible, and the quote field is what made the currency classification possible at all.

Instrumenting *why* a judgement was made, not only what it was, is what allowed a wrong hypothesis to be discarded in minutes instead of surviving into an anchor rewrite that would not have helped.
