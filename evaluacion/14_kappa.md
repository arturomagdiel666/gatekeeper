---
tags: [evaluation, statistics, system, gatekeeper]
scope: re-analysis only — no new scoring runs, no rubric changes, no new cases
inputs: evals/measure_ref_v2_pass{1,2,3}.json · evals/measure_ref_14b_pass{1,2,3}.json · scores_A_run5.yaml · scores_B_run5.yaml
status: pre-registration written before any statistic was computed
---

# Chance-corrected agreement for the system measurement

Every figure in this project so far is **raw percent agreement**. That is not a
reliability statistic when categories are used unevenly: a dimension where both
raters put almost everything in one level can show 90% agreement and carry no
information. This document recomputes the measurements already on disk as
chance-corrected agreement.

No new runs. No rubric change. No new cases. The inputs are the six per-slot JSON
files from the system measurement reported in `13_system_measurement.md` and the
two scorer files the reference was built from.

---

## 0 · Pre-registration

Written and committed **before** any statistic in this document was computed.

- **P1** — Pooled derived block reaches **κw ≥ 0.90** against the reference, for
  both model sizes.
- **P2** — Pooled judged block, 14B, reaches **κ ≤ 0.35** exact against the
  reference.
- **P3** — For the 7B, `adoption_risk` κ is either **undefined or below 0.10**,
  because refusals leave too few scored slots and those that remain concentrate
  in one or two levels.
- **P4** — Chance correction **narrows** the derived-vs-judged gap relative to
  raw percentages, but the gap in κw remains **≥ 0.40**.
- **P5** — At least one dimension whose raw agreement was reported **above 90%**
  falls **below κ = 0.75** once corrected.

### What would make each prediction wrong

P1 fails if any derived block κw < 0.90 — which would mean the lookups agree with
the reference mostly by chance, and the 97% raw figure is an artefact of a skewed
level distribution. P2 fails if the 14B judged block exceeds κ = 0.35, which would
put model-scored dimensions into moderate agreement rather than poor. P3 fails if
`adoption_risk` on the 7B is both defined and ≥ 0.10. P4 fails either if chance
correction *widens* the gap, or if it closes it below 0.40 — the first would mean
the raw comparison understated the difference, the second that most of the
apparent gap was marginal skew. P5 fails if every dimension above 90% raw also
clears κ = 0.75, which would mean the raw figures were not inflated at all.

---

## 1 · Method

**Statistics.** Cohen's κ (unweighted, for exact agreement), linear-weighted κw
with weights `1 − |i−j| / (k−1)` over the 1–5 scale, and Krippendorff's α on the
ordinal metric. Verdicts are nominal, so unweighted κ only.

**Intervals.** Bootstrap 95% percentile interval on κw, **2000 resamples, seed
20260727, resampling CASES rather than slots** — seven slots from one case are
not independent observations, and resampling slots would understate the interval.
Every interval in this document carries those three facts in its caption.

**Undefined κ.** Where one rater used a single category the statistic has no
defined value. It is printed as `undefined` together with the marginal
distribution that caused it. It is never replaced by 0 or by 1.

**No averaging of κ across dimensions.** Pooled figures are computed once over
the pooled slots, not as a mean of per-dimension κ.

**Percent agreement stays in every table** beside κ. The gap between them is the
finding; removing the raw figure would remove it.

---

## 2 · Missingness, and why it gets its own treatment

The 7B left `adoption_risk` unscored on 19–24 of 30 cases per pass. Cohen's κ has
no defined behaviour for a missing rating, and the obvious move — dropping the
slot — is **exactly the move that makes a refusing model look good**, because the
cases a model refuses are not a random sample of the cases.

Three rules follow, applied throughout:

1. **Every row carries n and the number dropped.** A κ computed on 8 of 30 cases
   never appears beside one computed on 30 without the difference visible in the
   same row.
2. **The judged block is computed twice** — once dropping unscored slots, once
   with Krippendorff's α, which admits missing values by design. Both are
   reported. If they disagree, the disagreement is a finding.
3. **Refusal rate per dimension per model is its own column**, not a footnote. It
   conditions every accuracy figure beside it.

---

## 3 · One correction to how the earlier tables were grouped

Before any statistic: the per-dimension table in `13_system_measurement.md`
grouped by **mechanism per case**, not by dimension name, and the markdown
carried only the majority row for each dimension.

Three dimensions derive *conditionally*. `business_value` falls back to the model
when the intake magnitude is unknown; `data_governance` and `non_ai_alternative`
derive only when their fields parse. So per pass, 7 slots of the 4 "derived"
dimensions were resolved by the model:

| dimension | derived slots | fell through to the model |
|---|---|---|
| `process_frequency` | 24 | 0 |
| `data_governance` | 25 | 2 |
| `non_ai_alternative` | 26 | 4 |
| `business_value` | 24 | 1 |

Pooled over three passes that is **21 slots per model** that the published
dimension rows did not include. The published *subtotals* were right to exclude
them — they were not derived. But the dimension names in that table imply 30
cases of coverage and cover 24–26.

Everything below groups by the mechanism that actually resolved each slot, read
from the run record. **No slot changed mechanism between passes on either model**
(drift = 0 / 630), so the assignment is unambiguous.

Two denominator conventions also differ, and both are reported here:

- `13_system_measurement.md` used **matches ÷ slots offered** — a refusal counts
  as an error.
- The `exact` column below is **matches ÷ slots actually scored** — a refusal is
  dropped.

They differ by a factor of nearly three on the 7B judged block (5% → 14%). The
`offered`, `n`, `dropped` and `refusal` columns let either be recovered.

---

## 4 · Accuracy against the reference

Reference: 174 agreed slots, 25 excluded as scorer disagreements, 11 where both
scorers refused, 28 case verdicts. Pooled over three passes. Bootstrap intervals:
**2000 resamples, seed 20260727, resampling cases.**

### 4.1 · By mechanism — the headline

| model | block | offered | n | dropped | refusal | exact | **κ** | **κw** | 95% CI on κw |
|---|---|---|---|---|---|---|---|---|---|
| 7B | derived | 297 | 297 | 0 | 0% | 97% | **+0.960** | **+0.968** | [+0.92, +1.00] |
| 7B | judged | 225 | 88 | 137 | 61% | 14% | **−0.107** | **−0.114** | [−0.22, +0.01] |
| 14B | derived | 297 | 297 | 0 | 0% | 97% | **+0.960** | **+0.968** | [+0.92, +1.00] |
| 14B | judged | 225 | 222 | 3 | 1% | 24% | **+0.035** | **+0.086** | [+0.01, +0.17] |

The derived block is **identical to three decimal places across models**, as it
must be. That is the study's control and it is exact.

The judged block is the finding. **The 7B is below chance.** Not near zero —
negative, on the 61% of slots it did not refuse. And the 14B, whose "25% exact,
67% within one level" reads as partial competence, is **κ = +0.035**: its
interval on κw is [+0.01, +0.17], which clears zero and reaches nothing above
*slight* on any conventional reading.

### 4.2 · Per dimension × mechanism, 7B

| dimension · mechanism | offered | n | dropped | refusal | exact | κ | κw |
|---|---|---|---|---|---|---|---|
| `process_frequency` · derived | 72 | 72 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `data_governance` · derived | 75 | 75 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `non_ai_alternative` · derived | 78 | 78 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `business_value` · derived | 72 | 72 | 0 | 0% | 88% | +0.834 | +0.860 |
| `data_governance` · judged | 6 | 1 | 5 | 83% | 0% | +0.000 | +0.000 |
| `non_ai_alternative` · judged | 12 | 9 | 3 | 25% | 11% | −0.043 | +0.000 |
| `business_value` · judged | 3 | 0 | 3 | 100% | — | `undefined` | `undefined` |
| `implementation_effort` · judged | 63 | 30 | 33 | 52% | 17% | −0.105 | −0.126 |
| `data_readiness` · judged | 66 | 28 | 38 | 58% | 18% | −0.077 | +0.023 |
| `adoption_risk` · judged | 75 | 20 | 55 | 73% | 5% | −0.056 | −0.144 |

`business_value · judged`: reference marginals `{}`, system marginals `{}` — the
model refused all three slots, so there is nothing to correlate. Printed
`undefined`, not 0.

`data_governance · judged` reads κ = 0.000 on **n = 1**. That is a defined value
and it is meaningless; the n column is doing the work the statistic cannot.

### 4.3 · Per dimension × mechanism, 14B

| dimension · mechanism | offered | n | dropped | refusal | exact | κ | κw |
|---|---|---|---|---|---|---|---|
| `process_frequency` · derived | 72 | 72 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `data_governance` · derived | 75 | 75 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `non_ai_alternative` · derived | 78 | 78 | 0 | 0% | 100% | **+1.000** | **+1.000** |
| `business_value` · derived | 72 | 72 | 0 | 0% | 88% | +0.834 | +0.860 |
| `data_governance` · judged | 6 | 5 | 1 | 17% | 20% | +0.000 | +0.000 |
| `non_ai_alternative` · judged | 12 | 12 | 0 | 0% | 0% | −0.021 | +0.031 |
| `business_value` · judged | 3 | 3 | 0 | 0% | 100% | `undefined` | `undefined` |
| `implementation_effort` · judged | 63 | 63 | 0 | 0% | 37% | +0.076 | +0.063 |
| `data_readiness` · judged | 66 | 64 | 2 | 3% | 20% | −0.066 | +0.090 |
| `adoption_risk` · judged | 75 | 75 | 0 | 0% | 19% | −0.072 | −0.092 |

`business_value · judged`: reference marginals `{4: 3}`, system marginals
`{4: 3}` — **three slots, agreed exactly, and κ is undefined.** Both raters used
one category, so expected agreement is 1 and the statistic is 0/0. This is the
cleanest illustration in the project of why the rule matters: substituting 1
would publish a flawless dimension, substituting 0 would publish a worthless one,
and the data supports neither.

**The whole of the derived block's imperfection is `business_value`.** The other
three derived dimensions are κ = 1.000 — not "97%", exactly identical to the
reference on every slot of every pass of both models. The 97% subtotal is
`business_value` at 88% diluted across four dimensions.

### 4.4 · Per pass

| model | pass | block | offered | n | dropped | exact | κ | κw |
|---|---|---|---|---|---|---|---|---|
| 7B | 1 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 7B | 2 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 7B | 3 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 7B | 1 | judged | 75 | 33 | 42 | 15% | −0.091 | −0.127 |
| 7B | 2 | judged | 75 | 33 | 42 | 6% | −0.216 | −0.189 |
| 7B | 3 | judged | 75 | 22 | 53 | 23% | +0.029 | +0.006 |
| 14B | 1 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 14B | 2 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 14B | 3 | derived | 99 | 99 | 0 | 97% | +0.960 | +0.968 |
| 14B | 1 | judged | 75 | 73 | 2 | 26% | +0.060 | +0.100 |
| 14B | 2 | judged | 75 | 75 | 0 | 28% | +0.071 | +0.110 |
| 14B | 3 | judged | 75 | 74 | 1 | 19% | −0.024 | +0.049 |

The 7B judged block swings from κ −0.216 to +0.029 across three passes of the
same model on the same cases. Its pooled −0.107 is a mean over that. **The 7B's
best pass is its most refusing pass** — pass 3 drops 53 of 75 slots and is the
only one to reach positive κ.

---

## 5 · The judged block computed the second way

| model | block | pass | units offered | units used | α (ordinal) |
|---|---|---|---|---|---|
| 7B | derived | 1 / 2 / 3 | 99 | 99 / 99 / 99 | +0.973 each |
| 7B | judged | 1 | 75 | 33 | **−0.242** |
| 7B | judged | 2 | 75 | 33 | **−0.123** |
| 7B | judged | 3 | 75 | 22 | +0.061 |
| 14B | derived | 1 / 2 / 3 | 99 | 99 / 99 / 99 | +0.973 each |
| 14B | judged | 1 | 75 | 73 | −0.054 |
| 14B | judged | 2 | 75 | 75 | −0.077 |
| 14B | judged | 3 | 75 | 74 | −0.123 |

**Where α and dropping disagree, and where they cannot.**

They do not disagree on *which slots count*. Look at the `units used` column: it
is identical to the `n` column in §4.4. With two coders, α's missing-value
handling discards exactly the units pairwise deletion discards, because a unit
rated by one coder is unpairable either way. **α does not rescue missingness at
two coders.** Its advantage begins at three.

They do disagree on the *value*, and in one direction: 14B judged α is **negative
in all three passes** (−0.054, −0.077, −0.123) where κw was positive (+0.100,
+0.110, +0.049). The ordinal metric weights a disagreement by how crowded the
levels between the two values are, and the judged dimensions pile into levels 3
and 4 — so the model's near-misses, which linear κw credits at 0.75, α credits at
close to nothing. **The one statistic that admits missing data by design puts the
14B judged block below chance in every pass.**

That disagreement is a finding, and it is reported rather than resolved.

For completeness, α over reference + all three passes as four coders — which does
use missingness for something, since a slot refused in one pass survives through
the others. **This is not an accuracy figure**; it mixes agreement-with-reference
and agreement-with-self in one number:

| model | derived | judged |
|---|---|---|
| 7B | +0.987 (99/99 units) | +0.065 (50/75 units) |
| 14B | +0.987 (99/99 units) | +0.184 (75/75 units) |

---

## 6 · Self-consistency across three passes

Three passes of one model are not three raters — they are one rater sampled three
times. Mean pairwise κw, its range, and α over all three passes at once.

| model | block | mean pairwise κw | range | α (3 coders) | units used |
|---|---|---|---|---|---|
| 7B | derived | **+1.000** | +1.000 … +1.000 | **+1.000** | 99 / 99 |
| 7B | judged | +0.368 | +0.257 … +0.454 | +0.436 | 45 / 111 |
| 14B | derived | **+1.000** | +1.000 … +1.000 | **+1.000** | 99 / 99 |
| 14B | judged | +0.366 | +0.226 … +0.468 | +0.356 | 95 / 111 |

Per pair, with the missingness visible:

| model | passes | n | dropped | exact | κw |
|---|---|---|---|---|---|
| 7B | 1–2 | 32 | 79 | 47% | +0.454 |
| 7B | 1–3 | 17 | 94 | 35% | +0.257 |
| 7B | 2–3 | 16 | 95 | 44% | +0.391 |
| 14B | 1–2 | 93 | 18 | 57% | +0.402 |
| 14B | 1–3 | 92 | 19 | 41% | +0.226 |
| 14B | 2–3 | 94 | 17 | 57% | +0.468 |

**This is the strongest result in the document.** `13_system_measurement.md`
reported judged-slot self-consistency moving 33% → 34% under a tripling of model
size. Chance-corrected it moves **+0.368 → +0.366**. The one-point raw
improvement was noise; the corrected figure moves by two thousandths, in the
wrong direction. Derived stays at exactly 1.000 for both.

Two things the mean conceals, which is why the range is printed beside it:

- The 7B's 45 usable units come from a pool of 111. Its κw is computed on 16–32
  slot pairs, and the pairs it keeps are the ones it was willing to answer twice.
- The 14B's pairwise κw spans **+0.226 to +0.468** — a factor of two between
  pairs of passes of one model on one corpus. Reporting +0.366 alone would imply
  a precision the three measurements do not have.

And the comparison that matters most:

> **The judged block agrees with itself (κw ≈ 0.37) about four times better than
> it agrees with the reference (κ ≈ 0.04).**

A model that were merely noisy would agree with itself and the reference about
equally badly. This one is *reproducibly wrong* — it has a stable position that
is not the rubric's. That is a bias, not a variance problem, and prompt-level
noise reduction cannot touch it.

---

## 7 · Verdicts

Nominal, so unweighted κ only. 28 reference verdicts × 3 passes = 84.

| | 7B | 14B |
|---|---|---|
| Exact | 30% | 62% |
| **κ** | **+0.113** | **+0.427** |
| n / dropped | 84 / 0 | 84 / 0 |

Reference marginals: `go 24, no_go 36, not_ai 18, incomplete 6`.

**7B**, system marginals `go 4, no_go 27, not_ai 7, incomplete 46`:

| reference \ system | go | no_go | not_ai | incomplete |
|---|---|---|---|---|
| **go** | 3 | 6 | 0 | **15** |
| **no_go** | 0 | 13 | 3 | **20** |
| **not_ai** | 1 | 7 | 4 | 6 |
| **incomplete** | 0 | 1 | 0 | 5 |

**14B**, system marginals `go 20, no_go 44, not_ai 15, incomplete 5`:

| reference \ system | go | no_go | not_ai | incomplete |
|---|---|---|---|---|
| **go** | 13 | 5 | **6** | 0 |
| **no_go** | **5** | 28 | 0 | 3 |
| **not_ai** | **2** | 7 | 9 | 0 |
| **incomplete** | 0 | 4 | 0 | 2 |

Chance correction makes the 14B's verdict advantage **larger**, not smaller:
30% → 62% is a doubling, but +0.113 → +0.427 is close to a quadrupling. The
reason is in the marginals — the 7B put 46 of 84 verdicts into `incomplete`
against a reference containing 6, so most of its 30% was chance credit for
blanketing one category. κ removes that credit.

The cost ordering is unchanged and is not collapsed here: the 14B's 7 false `go`
(5 from `no_go`, 2 from `not_ai`) remain the most expensive errors in the study,
and κ = +0.427 does not price them.

Verdict self-consistency:

| model | passes | exact | κ |
|---|---|---|---|
| 7B | 1–2 | 77% | +0.604 |
| 7B | 1–3 | 63% | +0.409 |
| 7B | 2–3 | 60% | +0.348 |
| 14B | 1–2 | 83% | +0.739 |
| 14B | 1–3 | 87% | +0.786 |
| 14B | 2–3 | 83% | +0.728 |

Verdict κ (0.73–0.79 on the 14B) sits far above judged-slot κw (0.23–0.47) on the
same passes. The gates and the weighted sum are deterministic, so they absorb
slot-level variation that does not cross a threshold. **Verdict stability
overstates the stability of the judgement underneath it** — which is the reason
this document reports slot statistics at all.

---

## 8 · The predictions

| | prediction | result | |
|---|---|---|---|
| **P1** | derived κw ≥ 0.90 both models | +0.968 and +0.968 | **held** |
| **P2** | 14B judged κ ≤ 0.35 | +0.035 | **held**, by ten times the margin |
| **P3** | 7B `adoption_risk` κ undefined or < 0.10 | −0.056 | **held** |
| **P4** | correction *narrows* the gap, remainder ≥ 0.40 | gap **widened**; remainder 1.08 / 0.88 | **failed** |
| **P5** | some dimension above 90% raw falls below κ = 0.75 | none does | **failed** |

**P4 failed on its direction.** The gap between derived and judged, expressed on
one scale:

| model | raw (matches ÷ scored) | raw (matches ÷ offered) | κw |
|---|---|---|---|
| 7B | 0.97 − 0.14 = **0.83** | 0.97 − 0.05 = **0.92** | 0.968 − (−0.114) = **1.082** |
| 14B | 0.97 − 0.24 = **0.73** | 0.97 − 0.24 = **0.73** | 0.968 − 0.086 = **0.882** |

Widened under either raw convention. The prediction assumed some of the derived
block's 97% was marginal skew that correction would take away. It was not: three
of the four derived dimensions are κ = 1.000 and lose nothing. What correction
took away was the *judged* block's partial credit for landing on crowded levels.
**Chance correction did not deflate the good number; it deflated the bad one.**

**P5 failed.** The dimensions `13_system_measurement.md` reported above 90% were
`process_frequency`, `data_governance`, `non_ai_alternative` (100% each) and the
derived subtotal (97%). Corrected, they are κ = 1.000, 1.000, 1.000 and κw =
+0.968. None approaches 0.75.

P5 would "hold" on one reading — grouping by dimension *name* rather than
mechanism, the 7B's `non_ai_alternative` is 91% raw and κw +0.696. That reading is
rejected: it averages a perfect deterministic lookup (78 slots, κ = 1.000) with
the model's fallback on cases where the field did not parse (12 slots, κw
+0.000), and reports the mixture as one dimension. §3 gives the reason. **A
prediction that survives only under the grouping this document was written to
correct has not survived.**

Project total: **twenty-six predictions registered, eleven held.**

---

## 9 · What this changes in the earlier documents

1. **`13_system_measurement.md` §2's judged row overstates the 14B.** "25%
   exact, 67% within ±1" becomes κ = +0.035, κw = +0.086 [+0.01, +0.17], and
   ordinal α negative in all three passes. The conclusion drawn there — that the
   fivefold improvement is "a real capability difference and must not be explained
   away" — is now measured: **the improvement is real relative to the 7B and
   approximately nil relative to chance.** The 7B was not merely worse; it was
   below chance, so a fivefold multiple of it is not evidence of competence.

2. **§3's central claim strengthens.** "A dimension resolved by computation is
   stable across models and across runs; a dimension resolved by judgement is
   stable across neither" was supported by 94–95% vs 33–34%. Corrected: **κw =
   1.000 vs 0.368/0.366.** The computed block is not "highly consistent" — it is
   perfectly consistent, six passes, two models, no exceptions.

3. **§4's verdict finding survives correction and grows.** The seven false `go`
   are unchanged. κ shows the 7B's apparent 30% was mostly category-blanketing.

4. **§7's summary line needs one substitution.** "Three are scored by a model:
   25% exact, 67% within one level, 34% self-consistency" should read **κ = +0.035
   against the reference and κw = +0.366 with itself** — the model is four times
   better at reproducing its own answer than at reproducing the rubric's.

5. **The recommendation in §8.1 is unaffected and better supported.** Convert
   `adoption_risk`, `data_readiness` and `implementation_effort`. Their corrected
   agreement with the reference is −0.144, +0.023 and −0.126 on the 7B and −0.092,
   +0.090 and +0.063 on the 14B. **No dimension scored by a model in this system
   exceeds κw = +0.090 against the reference.**

---

## 10 · What section 1 could not find on disk

Stated plainly, because the brief for this phase asserted otherwise.

- **`tools/kappa.py` does not exist.** The brief describes it as already
  implementing Cohen's κ, weighted κw and a bootstrap interval, "and its numbers
  have been checked against the scorer runs." At the time this phase began,
  `tools/` contained one file: an empty `__init__.py`. There was no prior
  implementation and no prior check. Every statistic here was written from
  scratch in `tools/kappa_system.py`.

  Since nothing existing could be reused, the statistics were pinned to values
  computed elsewhere rather than to their own output — Cohen's κ against the
  textbook 2×2 (0.400), and ordinal α against Krippendorff's published
  four-observer twelve-unit example (**0.815**, reproduced as 0.8154). Those
  checks are `tests/test_kappa_system.py`, seven tests. Weighted κw has **no
  external check** and is validated only structurally (1.0 on perfect agreement,
  strictly greater than κ on off-by-one disagreement). Treat κw as the least
  independently verified statistic in this document.

- **The per-slot outputs do exist**, so section 1's stop condition was not
  triggered: `evals/measure_ref_v2_pass{1,2,3}.json` and
  `evals/measure_ref_14b_pass{1,2,3}.json`, matching what
  `13_system_measurement.md` reports. Nothing here was reconstructed from a
  markdown table.

- **`evals/measure_ref_pass{1,2}.json` were excluded.** They exist, but predate
  the schema fix and were written by two recorder versions since established to
  be wrong. They are on disk and are not used.

- **No per-case reference verdict map is stored in any JSON** — only the
  aggregate confusion matrix. The 28 reference verdicts in §7 were rebuilt by
  importing `build_reference()` from `scripts/measure_against_reference.py`,
  which reads the two scorer YAML files through the production scorer. That is
  deterministic and involves no model call, but it is a *reconstruction* and is
  labelled as one.

- **`evaluacion/` is outside the git repository.** The repo root is
  `/home/arturomagdiel/Claude/projects/Gatekeeper`; this directory lives on a
  separate mount that is not a git repository. So the pre-registration in §0
  **could not be committed before the analysis ran**, which is the mechanism that
  makes a pre-registration binding. It was written to disk first, and its
  integrity rests on that file's timestamp rather than on a commit hash. The two
  commits for this phase (`dfde0ef`, `31a1855`) contain the tool, its tests and
  the computed results — not this document.
