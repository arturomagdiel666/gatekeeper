---
tags: [evaluation, finding, rubric, gatekeeper]
runs: four, same 30 cases, same two scorers
status: measured — mechanism hypothesis partially confirmed, and refined
---

# Four runs: does computation actually converge?

Identical corpus, identical protocol, identical scorers. The rubric changed three times.

---

## 1 · All four runs

| Dimension | Run 1 | Run 2 | Run 3 | **Run 4** | vs baseline |
|---|---|---|---|---|---|
| `process_frequency` | 100% | 88% | 100% | **100%** | = |
| `data_governance` | 100% | 96% | 100% | **100%** | = |
| `business_value` | 63% | 100% | 92% | **100%** | **+37** |
| `adoption_risk` | 80% | 83% | 73% | **87%** | +7 |
| `implementation_effort` | 77% | 80% | 70% | **80%** | +3 |
| `data_readiness` | 80% | 73% | 67% | **73%** | −7 |
| `non_ai_alternative` | 70% | 61% | **30%** | **70%** | = |
| **Overall** | 81% | 83% | 74% | **86%** | **+5** |
| **Verdict agreement** | 80% | 67% | 73% | **80%** | = |

**Run 4 is the best overall run.** Six of seven dimensions are at or above their run-1 baseline, and `business_value` is 37 points above it. The two-run detour through Phases 4 and 5 ends roughly where it started on verdicts, with one dimension permanently improved and one recovered.

---

## 2 · The registered prediction, and how it resolved

Phase 6 registered three outcomes with fixed interpretations:

| Outcome | Meaning | Result |
|---|---|---|
| `non_ai_alternative` **above 90%** | mechanism confirmed | — |
| **70–90%** | the derivation's **entry point** is the residual problem | ✅ **70%** |
| **below 70%** | computation does not rescue it; demote it off the gate | — |

An amendment registered after Scorer B pointed out that levels 3–5 remained reader-applied:

| Outcome | Meaning |
|---|---|
| >90% with most gating slots `derived` | mechanism confirmed |
| >90% with most gating slots `judged` | **mechanism refuted** — what worked was removing competing frames |

The dimension landed at **70%** — recovered from 30%, back to its original baseline, not above it. The middle case. And the branch data says something the prediction did not anticipate.

---

## 3 · Where the error actually is now

`non_ai_alternative` is now `derived` on **all 30 cases** for both scorers. The derivation itself never disagreed. Yet agreement is 70%.

| | Agreement |
|---|---|
| Cases where both scorers used a **mechanical** branch (`empty` / `none_complete`) | 16 / 22 = **73%** |
| Cases where either used the **reader-applied** coverage rule | 5 / 8 = **62%** |
| Exact **branch** agreement | 21 / 30 |

The mechanical branches are **not** more reliable than the reader-applied rule. At n=8 the 73–62 gap is noise. The amendment was designed to catch the coverage rule carrying the result; it is not carrying it, and neither is the derivation.

**All nine disagreements are disagreements about what belongs in the list**, not about how the derivation maps it:

- Five are `empty` versus `none_complete` — does a passive artefact (a contract template, a category catalogue, a five-year archive) "exist for this work" at all?
- Three are `none_complete` versus a coverage branch — does a thing finish an instance?
- One is the reverse.

Scorer B stated it precisely: *"The derivation itself never wavered; every remaining disagreement is in list construction."*

> **A derivation is only as reliable as the field it reads. Moving a judgement out of the scoring rule and into the intake field does not remove the judgement — it relocates it.**

There is an uncomfortable symmetry here. The rule Phase 5 deleted from this dimension said that *an alternative which relocates a judgement rather than removing it does not count*. Phase 6 then built a derivation that relocates a judgement rather than removing it.

---

## 4 · The confound that makes the mechanism hypothesis still untested

The three derivations that reach 97–100% read **fields that already exist in the corpus** — `times_per_period`, `data_sensitivity`, a stated magnitude. A scorer reads a number off the case and applies a lookup.

`non_ai_alternative`'s derivation reads a field **the corpus does not have**. Both scorers had to construct the artefact list from prose before any lookup could run.

So run 4 did not compare *computation against prose*. It compared **reading a stated field against constructing one**. Under that comparison the result is unsurprising and the mechanism hypothesis is neither confirmed nor refuted for this dimension.

**The clean test is cheap and specific:** author the artefact list once into all 30 cases as a stated field — as a requester would fill it — and re-run. If agreement jumps into the 90s, the mechanism holds and the entire deficit was the missing field. If it stays near 70, the field itself is not answerable reproducibly and the dimension should come off the gate.

That test also matches production reality: in use, the **requester** fills this field. Neither scorer would ever have to construct it.

---

## 5 · The gate is the weakest point, and it is worse than the dimension

The dimension agrees at 70%. **The gating decision agrees at 50%.**

| | Cases scored ≥ 4 |
|---|---|
| Scorer A | A-08, B-03, B-07 |
| Scorer B | A-05, A-08, B-03, B-07, B-14, B-16 |
| Agreement | **3 of 6** |

Scorer B doubled the gate firings. All three extra cases turn on one question the rubric does not answer: **does the artefact have to finish the requested job *well*?**

B-15 is the sharp version — first-in-first-out finishes 100% of lead assignments while doing exactly the wrong job. A-05's regional spreadsheets finish each region's view but leave four contested numbers. B-14's slide is the report but does not say what worked.

`completes_without_judgement` asks whether an instance is finished. It does not ask whether it is finished *correctly*. That single missing clause decides three of the six gate firings.

---

## 6 · The drift control

The third registered prediction was that untouched dimensions stay within ±7 of run 3. They did — and they moved **up**:

| Untouched in Phase 6 | Run 3 | Run 4 | |
|---|---|---|---|
| `adoption_risk` | 73% | 87% | +14 |
| `implementation_effort` | 70% | 80% | +10 |
| `data_readiness` | 67% | 73% | +6 |
| `business_value` | 92% | 100% | +8 |

Run 3 saw every untouched dimension fall; run 4 saw every untouched dimension rise. **That kills the systematic-drift reading.** Two runs moving in opposite directions on untouched dimensions is variance, not drift — and it puts run-to-run variance at roughly **±10 points**, wider than the ±7 estimated from run 3 alone.

That widened band matters. It means:

- `non_ai_alternative`'s recovery from 30% to 70% is real — it exceeds the band by a wide margin.
- `business_value`'s 63 → 100 is real.
- **Almost nothing else in four runs of this study is interpretable.** `data_readiness` 80 → 73 is within noise. Every 3-to-7-point movement previously discussed was noise.

Scorer B's warning still stands unresolved: the assessment prompt changed length again in Phase 6, and prompt length remains an unexcluded cause. The clean measurement — scoring one untouched dimension twice against an identical rubric — has not been run.

---

## 7 · What is now known about the instrument

> Four of seven dimensions reproduce at 87–100% between independent scorers. Three of those read a stated intake field and apply a lookup; the fourth carries no procedure at all. Two sit at 73–80%. `non_ai_alternative`, which controls a blocking gate, reproduces at 70% — and the **gating decision** it controls reproduces at **50%**.
>
> Reliability is measured. **Validity is not.** The two dimensions at 100% resolve by reading a form field, and a field in the wrong unit would be invisible to any agreement study.

---

## 8 · Next, in order

1. **Author the artefact field into all 30 cases and re-run.** The only clean test of the mechanism hypothesis, and the only one that matches how the field is filled in production.
2. **Add the missing clause to `completes_without_judgement`** — whether the artefact finishes the job *correctly*, not merely finishes it. Three of six gate firings turn on it.
3. **Measure pure run-to-run variance**: score one untouched dimension twice against an identical rubric. Until this exists, every number in this study carries a ±10 band derived from four confounded runs.
4. **Restore a signal for a licensed capability nobody switched on.** Phase 6 removed level 5's "already-licensed capability" language, and ADR-029's justification for the two-part evidence test rested on it. That case now scores 1 and is invisible.
5. **Add a positive `existing_licensed_capability` case to the corpus.** Its recall is still untested across four runs — zero matches in 120 case-readings.

---

## 9 · Method

Fourteen predictions registered across three phases; four held.

The value of that ratio is unchanged and worth restating. Overall agreement across four runs reads 81 → 83 → 74 → 86. Without registered predictions the summary is *"it went up and down and ended higher."* With them, four runs produced:

- **`business_value`: 63% → 100%**, by replacing an estimation instruction with a derivation. The single clearest result in the study.
- **A prose procedure is worse than no procedure** — 48% against 72% at dimension level in run 3.
- **A derivation relocates a judgement rather than removing it**, unless the field it reads is answerable as a fact.
- **Reliability at ceiling can conceal a validity failure** that no agreement study can see.
- **Run-to-run variance is ~±10 points**, which invalidates most of the fine-grained comparisons made in earlier documents — including several of my own.
