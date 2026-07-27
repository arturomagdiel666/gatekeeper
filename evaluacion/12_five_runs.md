---
tags: [evaluation, finding, rubric, gatekeeper]
runs: five, same 30 cases, same two scorers
status: v2 — eight corrections after independent review; headline restated
---

# Five runs: computation converges, judgement does not

Identical corpus of 30 requests, identical protocol, two independent scorers. The rubric changed three times; the corpus gained one stated field on the fifth run.

> **v2.** Eight corrections after review by Scorer B against the raw files. Three change a claim, including the headline number and the isolation of the decisive experiment. All are verified. The originals are preserved in §9.

---

## 1 · The result

**Dimensions resolved by computation from a stated field reproduce almost perfectly. Dimensions resolved by judgement do not.**

| Mechanism | Dimensions | Comparable slots | Agreement |
|---|---|---|---|
| **Derivation from a stated intake field** | `business_value`, `process_frequency`, `data_governance`, `non_ai_alternative` | 109 | **106 / 109 = 97%** |
| **Judgement against anchors** | `adoption_risk`, `data_readiness`, `implementation_effort` | 90 | **68 / 90 = 76%** |

### The denominator, and what it hides

Those four dimensions span 4 × 30 = **120 slots**. Eleven are null for both scorers and are genuinely uncomparable. **Three more are null for one scorer and scored by the other** — those are real disagreements, and the first version of this document excluded them, reporting 106/106 = 100%.

That exclusion is not a rounding matter. `business_value`'s refusal branch and `non_ai_alternative`'s `absent` branch exist **specifically to produce nulls**, and a metric that drops null-versus-score pairs cannot see the disagreement those branches invite. The honest figure counts them: **97%**.

The rule now stated explicitly: a slot is comparable when at least one scorer produced a score. Both-null pairs are excluded and reported separately (11). Null-versus-score pairs count as disagreements (3).

---

## 2 · Five runs

| Dimension | Run 1 | Run 2 | Run 3 | Run 4 | **Run 5** |
|---|---|---|---|---|---|
| `business_value` | 63% | 100% | 92% | 100% | **100%** |
| `process_frequency` | 100% | 88% | 100% | 100% | **100%** |
| `data_governance` | 100% | 96% | 100% | 100% | **100%** |
| `non_ai_alternative` | 70% | 61% | **30%** | 70% | **100%** |
| `adoption_risk` | 80% | 83% | 73% | 87% | 83% |
| `data_readiness` | 80% | 73% | 67% | 73% | 73% |
| `implementation_effort` | 77% | 80% | 70% | 80% | 70% |
| **Overall** | 81% | 83% | 74% | 86% | **89%** |
| **Verdict agreement** | 80% | 67% | 73% | 80% | **90%** |

Per-dimension figures exclude both-null pairs, as in earlier runs. The 97% in §1 is the corrected aggregate for the derived group.

---

## 3 · The decisive experiment, and why its isolation is not clean

`non_ai_alternative` is the only dimension that has been through every treatment:

| Run | Treatment | Agreement |
|---|---|---|
| 1 | Original anchors — type-based prose | 70% |
| 2 | Phase 4 added numeric coverage bands **beside** the prose | 61% |
| 3 | Phase 5 deleted one rule, added a clarifying sentence | **30%** |
| 4 | Phase 6 rebuilt it as a derivation — corpus had no field, so **both scorers constructed one** | 70% |
| 5 | Same derivation, same rubric, **field stated in the corpus** | **100%** |

The rubric was byte-identical between runs 4 and 5.

**But the scorer instruction was not.** Run 4 told both scorers to construct the artefact list from prose. Run 5 told them to take the stated list as given and not second-guess it. Verified against the raw files:

| | Slots changed between run 4 and run 5 |
|---|---|
| Scorer A, derived dimensions | 13 / 120 |
| Scorer B, derived dimensions | 11 / 120 |
| Scorer A, judged dimensions | 18 / 90 |
| **Scorer B, judged dimensions** | **0 / 90** |

**Both scorers moved onto the field**; Scorer B's `non_ai_alternative` changed on 11 of 30 cases, and its branch agreement between constructed and stated list was 19 of 30. This is not one scorer converging onto a stable other. It is both abandoning their own constructions.

Scorer B put the objection precisely: *supplying the field and forbidding second-guessing are the same treatment.* Run 4 asked for thirty construction judgements including the completion flag both scorers had named as the most consequential call in the instrument. Run 5 asked for **zero** of them, plus four coverage calls. Twenty-six of thirty levels then follow from three stated words per case.

**The conclusion survives; the isolation claim does not.** Computation over a supplied field reproduces. What the experiment cannot separate is how much came from *having* the field versus from being told not to argue with it. The missing arm — field supplied, scorer permitted to overrule — was never run.

---

## 4 · The 97% is largely degenerate, and that matters

Of Scorer B's 106 derived slots, **only 8 admit a different defensible answer** given the stated field:

- `business_value` A-04 and B-05, where the stated durations are ranges (40–120 minutes, 1–3 days) and midpoint versus low end crosses a band edge; A-08 at 1,040 hours, 4% over an edge
- `process_frequency` A-01 (96 against an edge at 100), A-09 (900 against 1,000), B-15 (9,600 against 10,000)
- `non_ai_alternative` A-08 and B-03, all-versus-most

Five more are refusals where nothing was computed. **The remaining 93 are form-reading.**

So §1 establishes that two scorers can read a form and apply a band table. That is real and worth publishing — it is the mechanism the whole study identifies — but **it is not evidence that the underlying constructs are well defined.** A construct with one defensible answer per case is reproducible whether or not it measures the right thing.

---

## 5 · The judged dimensions are not two independent readings

Scorer B's judged scores changed on **zero of 90 slots** between runs 4 and 5. Scorer B flagged this against its own interest: *"perfect stability is as consistent with carry-over as with consistency."* Scorer B ran both in one session; Scorer A was a fresh agent with no memory each run.

Two consequences.

**The 76% judged agreement is not a fresh-versus-fresh comparison.** It measures a newly-derived reading against a carried-forward one. Whether that inflates or deflates the figure is unknown; that it is not what the protocol claims is certain.

**The ±10 variance band is one rater's drift, not the instrument's noise.** `implementation_effort` 80% → 70% and `adoption_risk` 87% → 83% happened with zero movement from Scorer B. All of it is Scorer A.

And that exposes a circularity in the first version of this document: Phase 6 registered a control — untouched dimensions stay within ±7 — **and the control failed** (`adoption_risk` +10 against run 3, `implementation_effort` −10 against run 4). §8 then used that same movement as the variance band excusing the judged dimensions' figures. **The same data cannot both fail a control and establish the noise floor that forgives the failure.**

---

## 6 · What the residual is, and why it looks smaller than it is

Three verdict disagreements, none from a derived dimension:

| Case | A | B | Differs on |
|---|---|---|---|
| A-03 | `no_go` | `incomplete` | `data_readiness`, `implementation_effort` |
| B-01 | `go` 3.53 | `no_go` 3.38 | `data_readiness` |
| B-15 | `no_go` 3.43 | `go` 3.56 | `implementation_effort` |

Two are band flips of 0.13 and 0.15 across a hard 3.50 threshold. Arguably **one substantive verdict disagreement remains** — A-03, which is a gate.

But "every remaining problem is in an unconverted dimension" is **partly an artefact of what the converted dimension now decides.** Of Scorer B's eight `not_ai` verdicts, only three come from the `non_ai_alternative` threshold; five come from the anti-pattern arm of the same gate. Converting the dimension cut its verdict influence from *every* `not_ai` in run 3 to three in run 5, which mechanically reduces its chance of appearing in the residual.

**And the mechanism that took over — the two-part anti-patterns — has a measured agreement history of 0–50%.** They agreed this run. That is not the same as being reliable.

---

## 7 · Verdict agreement of 90% supports much less than it sounds like

It is 27 of 30. A 95% interval runs roughly **73–99%**.

Worse for the metric: **six of the nineteen band-decided cases sit within ±0.15 of the 3.50 threshold** — B-01 at 3.38, B-17 at 3.40, A-12 at 3.48, A-06 at 3.53, B-15 at 3.56, A-09 at 3.65. **Thirty-two percent of the banded corpus is one small scoring difference from flipping.**

The 80% → 90% move is three cases. It supports *"not wildly unreliable, and no worse than run 1."* It does not support 90% as the instrument's verdict reliability, and quoting it as a headline beside the 97% invites exactly that reading.

---

## 8 · The claim that survives everything

Reliability is now measured. **Validity is not**, and five runs made that gap larger rather than smaller.

The derived dimensions agree because both scorers read the same stated field and apply the same lookup. **A field answered wrongly by the requester produces perfect agreement on a wrong score**, and no agreement study can see it.

Both scorers reported this without being asked, recording the cases where they would have filled the field differently from how it was stated:

- **Scorer A: 8 of 30** recorded objections.
- **Scorer B: 9 recorded objections, but 11 measured divergences.** Its constructed list and the stated list produce different levels on eleven cases. The two it did not object to are A-03 — where it had listed intranet search as an artefact in run 4 and in run 5 wrote that the stated *nada* was consistent, adopting the field against its own prior reading — and B-03, logged as a coverage ambiguity rather than an objection.

**That gap between 11 divergences and 9 objections is itself the deference the run-5 instruction produced**, and it is a measurement of §3's confound.

Corrected split of Scorer B's eleven: **six one-level differences** — five passive stores plus A-11's completion-flag disagreement — and **three that cross the gate**.

The sharpest is **B-16**. The request states a complete six-category routing rule and says a person applies it to every request. The stated field says *nothing exists*. Scorer B reads level 5; the field produces level 1. Four levels, from a requester not recognising their own routing rule as deterministic because a human executes it.

> **Moving a judgement into the intake form does not eliminate it. It transfers it to the requester — who has less training in the rubric than the scorer, and an interest in the answer.**

Both scorers independently named the same root cause: `completes_without_judgement` asks *"after it runs, is the work done"* and never says **whose** work.

On B-16 the first version said the instrument *survived by accident*. That was wrong. `deterministic_rule_suffices` is designed for a stated rule with available inputs and matched on both parts as intended — the match is the design working. The accident is only that it is a hard block rather than advisory.

---

## 9 · Corrections in v2

**Changed a claim**

1. **The headline was 106/106 = 100%.** The denominator silently excluded three null-versus-score pairs — the exact disagreement type the refusal branches invite. Corrected to **106/109 = 97%**, with the comparability rule now stated. (§1)
2. **§3 claimed runs 4 and 5 differed only in the field being supplied.** The scorer instruction also changed, and Scorer B's own scores moved on 11 of 30 cases. Both scorers abandoned their constructions. The conclusion holds; the isolation does not, and the missing arm is named. (§3)
3. **§5 reported 9 divergences and a split of 5 + 3 = 8 against its own total of 9.** The measured divergence is 11; the recorded objections are 9; the split is six one-level and three gate-crossing. (§8)

**Qualified a claim**

4. The ±10 variance was one rater's drift, and was used circularly to excuse a control it had itself failed. (§5)
5. 97% is degenerate on 93 of 106 slots — form-reading, not construct validity. (§4)
6. The residual's attribution is partly an artefact of the converted dimension losing verdict influence to anti-patterns with a 0–50% history. (§6)
7. 90% verdict agreement is 27/30 with a 73–99% interval, and a third of banded cases sit within ±0.15 of the threshold. (§7)
8. B-16 was not survived "by accident". (§8)

---

## 10 · What follows

1. **Run the missing arm**: field supplied, scorer permitted to overrule. Without it, §3 cannot separate the field from the instruction.
2. **Fix `completes_without_judgement` to name whose work.** Both scorers named it as the whole residual ambiguity in the field, and it decides gate firings.
3. **Convert `data_readiness` and `implementation_effort`.** They are the entire verdict residual and `data_readiness` carries a gate.
4. **Use a fresh scorer on both sides.** Carry-over on 90 judged slots means the protocol's independence claim does not currently hold for those dimensions.
5. **Measure validity of the fields, not the scores.** Have a second party fill the intake fields from each request independently and measure agreement on the fields. That is where the system's weight now sits.
6. **Then run the system against this reference.** Five runs of scorer-versus-scorer, and the product itself has still never been measured.

---

## 11 · Method

Fourteen predictions registered across three phases; five held.

- Overall agreement went 81 → 83 → 74 → 86 → **89**. Verdicts 80 → 67 → 73 → 80 → **90**, on 27 of 30 cases with a wide interval.
- The single largest intervention was **not a rubric edit** — it was supplying a field the corpus lacked, with the rubric byte-identical across the two runs. It was also confounded with an instruction change, and that was not noticed until an independent reader checked.
- **Prose repair moved a dimension from 70% to 30% across three attempts.** Computation over the same construct moved it to 100%, on a metric that is 88% form-reading.
- **A study of reliability, run carefully enough, tells you where your validity problem is.** It is wherever agreement is perfect and the input was supplied by someone with a stake in the answer.

Three of the eight corrections in this version change a claim, and all three were found by a reviewer checking arithmetic and raw files — not by the author, in either version.
