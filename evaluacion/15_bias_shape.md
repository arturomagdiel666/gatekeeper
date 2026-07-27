---
tags: [evaluation, statistics, bias, gatekeeper]
scope: re-analysis only — no new scoring runs, no rubric changes, no prompt changes, no new cases
inputs: evals/measure_ref_v2_pass{1,2,3}.json · evals/measure_ref_14b_pass{1,2,3}.json · scores_A_run5.yaml · scores_B_run5.yaml
status: PRE-REGISTRATION ONLY — committed before any statistic below it was computed
---

# What shape is the error?

Phase 7 measured that on judged slots the system reproduces its own answers
about four times better than it matches the reference — κw ≈ 0.37 against
κ ≈ 0.04. A model that were merely noisy would agree with itself and with the
reference about equally badly. This one does not, so its dominant error is a
**bias**: a stable position that is not the rubric's.

A bias has a direction and a shape. Neither has been measured. Phase 7 reported
that the model is reproducibly wrong; it did not report *wrong in which
direction*, *wrong by how much*, or *wrong on which cases*. Those are three
different defects with three different explanations, and κ cannot separate them —
a model that scores everything one level too high and a model that scores at
random can produce the same κ.

No new runs. No rubric change. No prompt change. No new cases.

---

## 0 · Pre-registration

**This section was committed before any statistic in this document was
computed.** Commit `eb78758` placed `evaluacion/` under version control; the
commit carrying this section contains sections 0 and 1 and nothing below them.
That makes Phase 8 the first pre-registration in this project whose priority
over its own results is verifiable rather than asserted.

- **P1** — The system's judged scores are more concentrated than the
  reference's: the Shannon entropy of the system's score distribution is lower
  on at least two of the three judged dimensions, for both models.
- **P2** — The signed error has a non-zero median on at least two judged
  dimensions, and its sign is the same for both model sizes.
- **P3** — Between 7B and 14B the *direction* of the bias is preserved even
  where its magnitude changes: the sign of the median signed error agrees on at
  least 2 of 3 judged dimensions.
- **P4** — On the derived block the signed error is zero at every percentile,
  for both models. **This is the control.** If it fails, the analysis has a
  defect and not a finding, and the run stops there.

### What would make each prediction wrong

P1 fails if the system's entropy equals or exceeds the reference's on two or
more judged dimensions — which would mean the model is spreading across the
scale at least as widely as the assessors, and its disagreement is not a
collapse onto favoured levels.

P2 fails if the median signed error is zero on two or more judged dimensions, or
if it is non-zero with opposite signs between models. A zero median with wide
spread is the signature of noise rather than bias, and would contradict Phase 7's
reading of the self-consistency gap.

P3 fails if the sign of the median signed error agrees on fewer than 2 of 3
dimensions. That would mean model size changes not just how far the system is
from the rubric but which way, and the bias would be a property of the model
rather than of the construct.

P4 fails if any derived slot shows non-zero signed error. Phase 7 measured the
derived block at κw = +1.000 self-consistency and κ = 1.000 against the
reference on three of four dimensions, with `business_value · derived` at 88%
exact — so P4 is expected to fail *as stated* on `business_value`, and holds only
on the three dimensions that are unconditionally derived. Stating this in advance
rather than discovering it: the control is the three exact dimensions; a non-zero
error anywhere among them stops the analysis.

---

## 1 · What will be computed

For each model, each judged dimension, pooled over three passes, with the
derived block computed identically as a control.

**A · Marginal distributions.** System score distribution against the
reference's, on the same slots, as counts over levels 1–5, plus Shannon entropy
of each in bits. A judge that has collapsed onto one or two levels shows here
and nowhere else.

**B · Signed error.** `system − reference` per slot: full distribution, median,
interquartile range, and the proportion at each of −4 … +4. This separates *the
model scores everything too high* from *the model scores at random*.

**C · The confusion matrix, unsummarised.** 5×5, reference level against system
level, per judged dimension per model, printed in full. No collapse to a scalar.

**D · Case-borne or slot-borne?** Per case, the count of judged slots that miss
the reference, compared against what independent misses at the observed base
rate would produce. Clustering means some requests are hard; an even spread
means the criterion is.

**E · The system against each assessor separately** (§2 of the brief), on all
slots that assessor scored rather than only the agreed ones. κ and κw for
system-vs-A and system-vs-B beside system-vs-reference. If the system agrees
noticeably better with one assessor, the reference is doing more work than a
reference should. If it agrees equally badly with both, the reference is not the
explanation. Both outcomes are reportable; neither will be argued for.

### Guardrails

Every table carries n and slots dropped for missingness on the same row as the
statistic. Undefined statistics print `undefined` with the marginals that caused
them. Nothing is repaired, tuned or reworded; a number that looks wrong is
reported as computed and called wrong. The derived control is checked first.
Section 4 is findings — there is no section proposing fixes.

---

## 2 · The control, first

| dimensions | slots | non-zero signed errors |
|---|---|---|
| `process_frequency`, `data_governance`, `non_ai_alternative` · derived | 225 per model | **0** |

Zero at every percentile, both models, all six passes. The control holds and the
analysis proceeds.

**P4 as literally written fails, exactly where the pre-registration said it
would.** The full derived *block* is not zero: `business_value · derived` carries
9 non-zero errors of 72 slots per model. Those 9 are three cases, each wrong the
same way in all three passes:

| case | reference | derivation | error |
|---|---|---|---|
| `A-08` | 3 | 4 | +1 |
| `B-03` | 3 | 1 | −2 |
| `B-05` | 2 | 1 | −1 |

**Identical on both models and all six passes.** So `business_value`'s 88% is not
instability — it is three specific disagreements between the lookup table and the
two assessors, reproduced perfectly every time. That is a *validity* gap in the
derivation, not a reliability one, and it is the only place in the derived block
where one exists.

Everything below is therefore trustworthy in the sense P4 was meant to test: the
deterministic path contributes no error of its own to the judged-block figures.

---

## 3 · A · Marginals and entropy

Counts over levels 1–5 on the same slots, and Shannon entropy in bits. Maximum
over five levels is 2.322.

### 3.1 · 7B

| block / dimension | n | reference 1·2·3·4·5 | H | system 1·2·3·4·5 | H |
|---|---|---|---|---|---|
| **derived** | 297 | 63 · 84 · 99 · 30 · 21 | 2.122 | 69 · 81 · 93 · 33 · 21 | 2.147 |
| **judged** | 88 | 1 · 23 · 34 · 20 · 10 | 1.952 | 15 · 21 · 23 · 13 · 16 | **2.289** |
| `implementation_effort` · judged | 30 | 0 · 13 · 14 · 3 · 0 | 1.368 | 3 · 8 · 6 · 11 · 2 | **2.096** |
| `data_readiness` · judged | 28 | 1 · 2 · 16 · 5 · 4 | 1.750 | 4 · 6 · 8 · 2 · 8 | **2.182** |
| `adoption_risk` · judged | 20 | 0 · 8 · 0 · 12 · 0 | 0.971 | 4 · 5 · 5 · 0 · 6 | **1.985** |

### 3.2 · 14B

| block / dimension | n | reference 1·2·3·4·5 | H | system 1·2·3·4·5 | H |
|---|---|---|---|---|---|
| **derived** | 297 | 63 · 84 · 99 · 30 · 21 | 2.122 | 69 · 81 · 93 · 33 · 21 | 2.147 |
| **judged** | 222 | 3 · 73 · 65 · 66 · 15 | 1.913 | 73 · 87 · 42 · 20 · 0 | 1.825 |
| `implementation_effort` · judged | 63 | 0 · 27 · 30 · 6 · 0 | 1.357 | 18 · 36 · 9 · 0 · 0 | **1.379** |
| `data_readiness` · judged | 64 | 3 · 4 · 27 · 24 · 6 | 1.833 | 14 · 14 · 24 · 12 · 0 | **1.943** |
| `adoption_risk` · judged | 75 | 0 · 42 · 0 · 33 · 0 | 0.990 | 35 · 30 · 7 · 3 · 0 | **1.547** |

**P1 predicted the system would be more concentrated than the reference. It is
less concentrated, on all six comparisons.** Not one dimension of one model went
the predicted way. The system's entropy exceeds the reference's every time, by as
much as a full bit (`adoption_risk`, 7B: 0.971 → 1.985).

Two things this exposes, and the second matters more than the first.

**Entropy did not measure what P1 was reaching for.** Look at the 14B's
`adoption_risk`: the reference uses two levels and the system uses four, so the
system scores higher on entropy — and §5 shows the system's four levels carry
almost no information about which reference level a slot belongs to. A judge can
be *spread* and *undiscriminating* at once. Entropy answers "how many levels does
it use", and P1 was asking "does it discriminate". Those came apart here.

**The reference's own marginals are narrow, and structurally so.** On
`adoption_risk` the two assessors agreed only on levels **2 and 4** — never 1,
never 3, never 5, across all 25 agreed cases. On `implementation_effort` they
agreed only on 2, 3 and 4. The agreed subset is not a sample of the scale; it is
the levels where two people anchor the same way. **A reference built from
agreement is systematically narrower than the construct it stands for**, and
every κ computed against it inherits that.

---

## 4 · B · Signed error, `system − reference`

### 4.1 · Summary

| model | block / dimension | offered | n | dropped | median | IQR | mean | too high | too low |
|---|---|---|---|---|---|---|---|---|---|
| 7B | **derived** | 297 | 297 | 0 | +0.00 | 0.00 | −0.020 | 1% | 2% |
| 7B | **judged** | 225 | 88 | **137** | +0.00 | 3.00 | −0.239 | 40% | 47% |
| 7B | `implementation_effort` | 63 | 30 | 33 | **+1.00** | 2.75 | +0.367 | 53% | 30% |
| 7B | `data_readiness` | 66 | 28 | 38 | +0.00 | 2.00 | −0.179 | 36% | 46% |
| 7B | `adoption_risk` | 75 | 20 | 55 | **−0.50** | 3.00 | −0.250 | 45% | 50% |
| 14B | **derived** | 297 | 297 | 0 | +0.00 | 0.00 | −0.020 | 1% | 2% |
| 14B | **judged** | 225 | 222 | 3 | **−1.00** | 2.00 | −1.036 | 9% | **67%** |
| 14B | `implementation_effort` | 63 | 63 | 0 | **−1.00** | 1.00 | −0.810 | 3% | 60% |
| 14B | `data_readiness` | 66 | 64 | 2 | **−1.00** | 2.00 | −0.875 | 14% | 66% |
| 14B | `adoption_risk` | 75 | 75 | 0 | **−1.00** | 2.00 | −1.173 | 12% | 69% |

### 4.2 · Full distributions

| model | block / dimension | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +4 |
|---|---|---|---|---|---|---|---|---|---|---|
| 7B | derived | 0 | 0 | 3 | 3 | **288** | 3 | 0 | 0 | 0 |
| 7B | judged | 3 | 4 | 18 | 16 | 12 | 19 | 12 | 4 | 0 |
| 7B | `implementation_effort` | 0 | 0 | 4 | 5 | 5 | 8 | 8 | 0 | 0 |
| 7B | `data_readiness` | 1 | 0 | 5 | 7 | 5 | 5 | 4 | 1 | 0 |
| 7B | `adoption_risk` | 0 | 3 | 4 | 3 | 1 | 6 | 0 | 3 | 0 |
| 14B | derived | 0 | 0 | 3 | 3 | **288** | 3 | 0 | 0 | 0 |
| 14B | judged | 5 | 23 | 44 | **76** | 54 | 17 | 3 | 0 | 0 |
| 14B | `implementation_effort` | 0 | 2 | 11 | 25 | 23 | 2 | 0 | 0 | 0 |
| 14B | `data_readiness` | 1 | 3 | 14 | 24 | 13 | 9 | 0 | 0 | 0 |
| 14B | `adoption_risk` | 0 | 16 | 16 | 20 | 14 | 6 | 3 | 0 | 0 |

**The 14B has a clean directional bias: it scores judged dimensions about one
level below the assessors.** Median −1.00 on every judged dimension, 67% of
errors negative against 9% positive, mean −1.036. That is not noise around a
correct centre; it is a displaced centre.

**The 7B does not have that bias, and on one dimension has the opposite one.**
Its pooled judged median is 0.00 with an IQR of 3.00 — a distribution centred
correctly and spread across the whole scale, which is what noise looks like. On
`implementation_effort` its median is **+1.00** where the 14B's is **−1.00**.

That comparison has a confound and it is severe: **the 7B's median is computed on
the 39% of slots it did not refuse.** 137 of 225 judged slots are missing. Its
distribution describes the cases it chose to answer, and Phase 7 established that
those are not a random sample. This is stated rather than corrected, because
there is no correction available from data already on disk.

### 4.3 · What the predictions did

**P2 fails.** It required a non-zero median on ≥2 judged dimensions *with the
same sign in both models*. Only `adoption_risk` satisfies both (−0.50 and −1.00).
`implementation_effort` is non-zero in both and **opposite in sign**;
`data_readiness` is zero on the 7B.

**P3 fails.** The sign of the median agrees on **1 of 3** dimensions, not 2.

| dimension | 7B median | 14B median | signs agree? |
|---|---|---|---|
| `implementation_effort` | +1.00 | −1.00 | **no — opposite** |
| `data_readiness` | 0.00 | −1.00 | no — 7B has no sign |
| `adoption_risk` | −0.50 | −1.00 | yes |

This is the finding of the phase and it cuts against the reading Phase 7 gave.
`13_system_measurement.md` §3 placed the instability "in the construct, not the
parameter count". At the level of *magnitude* that survives — both models are
near chance. At the level of *direction* it does not: on the same dimension, the
same cases and the same rubric, one model sits a level high and the other a level
low. **The bias has a direction, and the direction belongs to the model.**

---

## 5 · C · The confusion matrices, unsummarised

Reference level down the rows, system level across the columns. `·` marks a
reference level no agreed slot occupies.

### 5.1 · 14B — where the shape is clearest

**`adoption_risk`** · n=75, dropped 0

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 · | 0 | 0 | 0 | 0 | 0 |
| **2** | **19** | 14 | 6 | 3 | 0 |
| 3 · | 0 | 0 | 0 | 0 | 0 |
| **4** | **16** | 16 | 1 | 0 | 0 |
| 5 · | 0 | 0 | 0 | 0 | 0 |

This is the single most informative table in the phase. The reference
distinguishes two groups of cases — 42 slots at level 2 and 33 at level 4, two
levels apart. **The system's response to both is the same.** Reference-2 slots
get a mean system score of ≈1.8; reference-4 slots get ≈1.5. The system is not
biased low on `adoption_risk` so much as **nearly constant**: it answers 1 or 2
whatever the case, and the direction it does move is *backwards* — it scores the
high-risk group slightly lower than the low-risk group.

**`implementation_effort`** · n=63, dropped 0

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 · | 0 | 0 | 0 | 0 | 0 |
| **2** | 6 | **19** | 2 | 0 | 0 |
| **3** | 10 | **16** | 4 | 0 | 0 |
| **4** | 2 | 1 | 3 | 0 | 0 |
| 5 · | 0 | 0 | 0 | 0 | 0 |

Same shape, less extreme. Levels 4 and 5 are **never used by the system** across
63 slots. The reference's level-4 cases are answered 1 or 2 five times out of six.

**`data_readiness`** · n=64, dropped 2

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| **1** | 0 | 3 | 0 | 0 | 0 |
| **2** | 2 | 1 | 1 | 0 | 0 |
| **3** | 8 | 5 | **9** | 5 | 0 |
| **4** | 3 | 5 | **13** | 3 | 0 |
| **5** | 1 | 0 | 1 | **4** | 0 |

The only judged dimension with any diagonal structure. Level 5 is never used.

### 5.2 · 7B — the same dimensions, before refusal is accounted for

**`adoption_risk`** · n=20, **55 of 75 dropped**

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 · | 0 | 0 | 0 | 0 | 0 |
| **2** | 1 | 1 | 3 | 0 | 3 |
| 3 · | 0 | 0 | 0 | 0 | 0 |
| **4** | 3 | 4 | 2 | 0 | 3 |
| 5 · | 0 | 0 | 0 | 0 | 0 |

**`implementation_effort`** · n=30, **33 of 63 dropped**

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1 · | 0 | 0 | 0 | 0 | 0 |
| **2** | 0 | 3 | 3 | **7** | 0 |
| **3** | 3 | 4 | 2 | 4 | 1 |
| **4** | 0 | 1 | 1 | 0 | 1 |
| 5 · | 0 | 0 | 0 | 0 | 0 |

**`data_readiness`** · n=28, **38 of 66 dropped**

| ref \ sys | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| **1** | 0 | 1 | 0 | 0 | 0 |
| **2** | 1 | 0 | 0 | 0 | 1 |
| **3** | 2 | 5 | 4 | 1 | 4 |
| **4** | 0 | 0 | 1 | 1 | 3 |
| **5** | 1 | 0 | 3 | 0 | 0 |

The 7B's matrices are scattered rather than displaced. Where the 14B's
`implementation_effort` fills columns 1–2, the 7B's fills column 4 for
reference-2 cases — the source of its +1.00 median. On 30 of 63 slots.

**Two different failure modes, both landing at κ ≈ 0.** The 7B answers a minority
of slots and answers them without pattern. The 14B answers nearly all of them
with a compressed, downward-shifted response that barely varies with the case.
No scalar distinguishes these, and κ did not.

---

## 6 · D · Is the error case-borne or slot-borne?

Judged misses per case, pooled over three passes, against the exact
Poisson-binomial expectation for independent misses at the observed base rate.
Each case contributes its own binomial because each had a different number of
slots the system was willing to score.

### 6.1 · 7B — 26 cases, 76 misses of 88 scored slots, base rate 86%

| misses in a case | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| observed cases | **0** | 6 | 5 | 5 | 6 | 3 | 1 | 0 |
| expected if independent | 0.8 | 5.8 | 5.4 | 3.6 | 5.5 | 2.8 | 1.6 | 0.4 |

Observed variance 2.234 · expected 2.813 · **ratio 0.794**

### 6.2 · 14B — 30 cases, 168 misses of 222 scored slots, base rate 76%

| misses in a case | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| observed cases | **0** | 0 | 3 | 3 | 5 | 3 | 6 | 5 | 0 | 4 | 0 | 1 | 0 |
| expected if independent | 0.0 | 0.5 | 1.7 | 3.0 | 3.9 | 5.6 | 5.2 | 4.3 | 3.4 | 1.6 | 0.5 | 0.3 | 0.1 |

Observed variance 5.490 · expected 4.401 · **ratio 1.247**

**The misses are slot-borne.** A variance ratio of 1.0 is what independent misses
produce. The 7B's 0.794 is *below* independence — misses spread more evenly than
chance would spread them. The 14B's 1.247 is mild over-dispersion, nowhere near
the pattern a hard-cases explanation needs; concentrating the same 168 misses
into half the cases would put the ratio above 3.

And the flattest fact in the table: **no case, on either model, had zero judged
misses.** 0 of 26 and 0 of 30, against 0.8 and 0.03 expected. There is no subset
of requests the system handles correctly. There is no hard tail to remove.

---

## 7 · E · The system against each assessor separately

The reference is the subset where two assessors agreed, so it is both the easier
slots and a construct built from those same two people. Scoring against each
assessor's **full** slot set — every slot that assessor recorded, agreed or not —
tests how much work the reference is doing.

| model | comparison | offered | n | dropped | exact | κ | κw |
|---|---|---|---|---|---|---|---|
| 7B | judged vs **reference** (agreed) | 225 | 88 | 137 | 14% | −0.107 | −0.114 |
| 7B | judged vs **assessor A** | 291 | 123 | 168 | 14% | −0.116 | −0.093 |
| 7B | judged vs **assessor B** | 300 | 124 | 176 | 19% | −0.064 | −0.071 |
| 7B | derived vs assessor A | 297 | 297 | 0 | 97% | +0.960 | +0.968 |
| 7B | derived vs assessor B | 297 | 297 | 0 | 97% | +0.960 | +0.968 |
| 14B | judged vs **reference** (agreed) | 225 | 222 | 3 | 24% | +0.035 | +0.086 |
| 14B | judged vs **assessor A** | 291 | 281 | 10 | 22% | +0.014 | +0.059 |
| 14B | judged vs **assessor B** | 300 | 282 | 18 | 28% | +0.053 | +0.089 |
| 14B | derived vs assessor A | 297 | 297 | 0 | 97% | +0.960 | +0.968 |
| 14B | derived vs assessor B | 297 | 297 | 0 | 97% | +0.960 | +0.968 |

Per judged dimension:

| model | dimension | vs A: n / κ / κw | vs B: n / κ / κw |
|---|---|---|---|
| 7B | `implementation_effort` | 47 / −0.155 / −0.199 | 47 / −0.149 / −0.135 |
| 7B | `data_readiness` | 39 / −0.085 / +0.050 | 39 / −0.043 / +0.017 |
| 7B | `adoption_risk` | 27 / −0.073 / −0.118 | 27 / +0.078 / −0.012 |
| 14B | `implementation_effort` | 89 / +0.049 / +0.034 | 89 / +0.055 / +0.030 |
| 14B | `data_readiness` | 82 / −0.065 / +0.045 | 82 / −0.046 / +0.084 |
| 14B | `adoption_risk` | 90 / −0.074 / −0.078 | 90 / −0.076 / −0.090 |

**The outcome is the second one the brief described: the reference is not the
explanation.** Agreement with each assessor's full slot set — 291 and 300 slots
against the reference's 225, including every slot the two disagreed on — is
within 0.05 κ of agreement with the reference, on both models. The chance-level
result does not come from having tested only the easy agreed subset. It stands on
the assessors' complete individual judgements.

Two smaller observations, reported without argument:

- **The system agrees marginally better with B than with A**, in 5 of the 6
  dimension-model cells, and on the pooled judged block for both models
  (κ gap 0.052 on the 7B, 0.039 on the 14B). The direction is consistent; the
  magnitude is roughly a tenth of the distance to either. **Disclosure: assessor
  B's scores were produced by this assistant, assessor A's by a separate
  session.** The lean is toward the assessor sharing the system's model family.
  On this data the effect is too small to separate from noise, and no test here
  can settle it.

- **The two assessors agreed on 99 of 99 derived-mechanism slots** and disagreed
  on 25 judged ones. All 25 reference exclusions and all 11 both-null slots fall
  on judged dimensions. Where the intake form decides, two independent people
  reach the same answer every time; where judgement decides, they do not — the
  same split the system shows, in the humans.

---

## 8 · Findings

1. **The control holds and locates one validity gap.** Zero error on the three
   unconditionally derived dimensions, all six passes, both models.
   `business_value · derived` is wrong on exactly three cases — `A-08`, `B-03`,
   `B-05` — identically every pass on both models. Its 88% is a fixed
   disagreement between the lookup table and the assessors, not instability.

2. **The system is more spread than the reference, not less.** Six of six
   comparisons. P1 predicted the opposite. Entropy measures how many levels are
   used and P1 needed to know whether they discriminate; on the 14B's
   `adoption_risk` the system uses twice as many levels as the reference and
   carries almost no information about it.

3. **A reference built from agreement is narrower than the construct.** On
   `adoption_risk` the two assessors agreed only on levels 2 and 4 across 25
   cases — never 1, 3 or 5. Every κ computed against that reference inherits its
   range.

4. **The 14B has a uniform downward bias of about one level.** Median −1.00 on
   all three judged dimensions, 67% of errors negative against 9% positive.

5. **The bias direction is not preserved across model sizes.** On
   `implementation_effort` the medians are +1.00 (7B) and −1.00 (14B). P3
   required agreement on 2 of 3 dimensions and got 1. The magnitude of the failure
   belongs to the construct; the direction belongs to the model. The 7B figure
   rests on the 39% of slots it did not refuse, which is a confound and not a
   correctable one.

6. **Two different failure modes reach the same κ.** The 7B answers a minority of
   slots without pattern (median 0.00, IQR 3.00). The 14B answers nearly all of
   them with a compressed response that barely varies with the case — on
   `adoption_risk` it scores the reference's level-4 group *lower* than its
   level-2 group. κ ≈ 0 for both.

7. **The misses are slot-borne, not case-borne.** Variance ratios 0.794 and
   1.247 against 1.0 for independence. **No case on either model had zero judged
   misses** — 0 of 26 and 0 of 30. There is no hard tail; there is a criterion the
   system does not track.

8. **The reference is not doing the work.** Scored against each assessor's full
   slot set, including every slot the two disagreed on, κ moves by less than 0.05
   on both models. Phase 7's chance-level result survives the test that could have
   overturned it.

---

## 9 · The predictions

| | prediction | result | |
|---|---|---|---|
| **P1** | system entropy lower on ≥2 of 3 judged dimensions, both models | lower on **0 of 6** — system is more spread everywhere | **failed** |
| **P2** | non-zero median on ≥2 dimensions with the same sign in both models | only `adoption_risk` satisfies both | **failed** |
| **P3** | median sign agrees on ≥2 of 3 dimensions | agrees on **1 of 3**; `implementation_effort` is opposite | **failed** |
| **P4** | derived signed error zero at every percentile | **0 errors** on the three unconditional dimensions; 9 on `business_value · derived`, as pre-registered | **held on the control** |

Three of four failed, and P1 failed in the reverse of its predicted direction.

Project total: **thirty predictions registered, twelve held.**

---

## 10 · Method notes

**Section D shipped wrong the first time.** The expected-miss distribution
multiplied an already-summed Poisson-binomial PMF by the case count, printing
"152 expected cases" for a sample of 26. It looked like a finding — a wild excess
of expected misses over observed — and it was an arithmetic error. Caught by
noticing that expected cases exceeded existing cases. The assertion that expected
counts sum to the case count is now in the code and in the tests. **That is the
third measurement in this project to be wrong and plausible at the same time**,
after the contributions field and the response schema.

**One instrument choice is worth recording as a limitation.** Entropy was
pre-registered as the test for concentration and answered a different question
than the one P1 was asking. The confusion matrices in §5 answer the intended
question and were pre-registered too, so the phase recovered — but P1 could have
been written to test discrimination directly and was not.

**`tools/bias_shape.py` rebuilds the reference rather than importing it.**
`build_reference()` in `scripts/measure_against_reference.py` hardcodes an
absolute path to a Windows mount, so importing it makes a clean checkout fail.
The slot rule is four lines and reimplemented identically; verdicts are not used
by any analysis here, so the production scorer is not invoked. That hardcoded
path is a defect in the older script and was **not repaired** — this phase
changes nothing outside its own deliverables.

**Pre-registration.** Sections 0 and 1 were committed as `d82f2a1` before
`tools/bias_shape.py` existed. This is the first phase in the project whose
registration precedes its analysis in the version history rather than in a file
mtime.
