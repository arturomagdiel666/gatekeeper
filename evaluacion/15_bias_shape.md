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
