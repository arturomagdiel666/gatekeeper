---
tags: [evaluation, finding, rubric, gatekeeper]
runs: three, same 30 cases, same two scorers, rubric changed twice
status: v2 — six corrections after independent review; central finding restated
---

# Three runs: what repairing a rubric actually did

Identical corpus, identical protocol, identical scorers. One variable changed between runs: the rubric.

> **v2.** Six corrections after review by Scorer B against the raw score files. One was an arithmetic slip that concealed the study's central result; the rest qualify claims that were overstated. The original readings are preserved in §8.

---

## 1 · The central finding

Group the seven dimensions by **how a score is arrived at**, not by what was done to them:

| Mechanism | Dimensions | Agreement (run 3) | Mean |
|---|---|---|---|
| **Derivation** — computed from an intake field | `process_frequency`, `data_governance`, `business_value` | 100 · 100 · 92 | **97%** |
| **Nothing** — anchors only | `adoption_risk`, `implementation_effort` | 73 · 70 | **72%** |
| **`scoring_rule` without derivation** — a procedure written in prose | `data_readiness`, `non_ai_alternative` | 67 · 30 | **48%** |

The partition is clean and has no overlap. Every dimension resolved by computation is ≥ 92%. Every dimension carrying a prose procedure and no computation is ≤ 67%.

> **A procedure written in prose is 24 points worse than writing no procedure at all.**

The same result at the level of individual scores, across all 196 scoreable slots in run 3:

| Both scorers resolved by | Agreement |
|---|---|
| Derivation | **64 / 66 = 97%** |
| Judgement | **73 / 121 = 60%** |

This is a property of the mechanism, not of any particular dimension.

---

## 2 · The three runs

| Dimension | Run 1 | Run 2 (Phase 4) | Run 3 (Phase 5) | What was done |
|---|---|---|---|---|
| `process_frequency` | 100% | 88% | **100%** | P4 added a unit definition · P5 fixed the intake question instead |
| `data_governance` | 100% | 96% | **100%** | Never touched |
| `business_value` | 63% | **100%** | 92% | P4 replaced a judgement with a derivation |
| `adoption_risk` | 80% | 83% | 73% | Never touched |
| `implementation_effort` | 77% | 80% | 70% | Never touched |
| `data_readiness` | 80% | 73% | 67% | P4 added a `min()` rule in prose |
| `non_ai_alternative` | 70% | 61% | **30%** | P4 added numeric bands · P5 deleted a rule, added a sentence |
| **Overall** | 81% | 83% | 74% | |
| **Verdict agreement** | 80% | 67% | 73% | |

---

## 3 · What worked

**`process_frequency` returned to 100%.** Phase 5 did not arbitrate between the axis and the derivation — it changed what the intake field asks, so the question and the rule finally refer to the same thing.

**`business_value` went from 63% to the low-90s** and stayed there. Phase 4 *replaced* its estimation instruction with a derivation rather than adding guidance beside it.

**Both dimensions moved into the computation class**, and that is the whole of the improvement in this study.

### The residual 3%, and where it lives

`business_value`'s two run-3 disagreements — A-08 and B-05 — are cases **both scorers marked `derived`**. They applied a procedure and still differed, at the point where the procedure is entered: which denomination counts as a stated magnitude, and whether "un equipo de tres personas" is a stated person-hours figure. That is a three-level swing on the heaviest-weighted dimension, decided by an unwritten rule about which branch fires.

> **Computation converges once the scorers agree which computation applies.** The entry point to a derivation is still a judgement, and it is where the remaining error lives.

---

## 4 · What failed: `non_ai_alternative`, 70% → 61% → 30%

Three successive evidence-driven repairs made the same dimension **monotonically worse**. It is now the least reproducible thing in the rubric by a wide margin, and it gates.

Both scorers diagnosed the same cause independently, from different directions:

- **Scorer B**: level 1's prose says *"no deterministic rule can be written for it"*, but the numeric band says zero instances finished. For a job-description template a rule plainly *can* be written — it just finishes nothing. *"The zero band is reachable by the number and contradicted by the prose."*
- **Scorer A**: level 5 lists *"a form field"* as a qualifying alternative, while the axis requires the alternative to finish *"with no human judgement added"*. A capture-time dropdown finishes nearly every instance — but only by making the capturer do the classifying.

The dimension carries **three frames laid over each other**:

1. Original anchors describe alternatives by **type** — a rule, a query, a form field, a template.
2. Phase 4 added numeric bands describing them by **fraction of instances covered**.
3. Phase 5 added an axis sentence describing them by **whether an instance finishes without human judgement**.

Layer 1 was never removed. Phase 5 deleted a Phase 4 addition and left the prose that predates both. Each repair addressed the most recent layer and left the sediment beneath it.

**The sediment is specific**: level 1's prose and level 5's "a form field". Neither was added by Phase 4 or Phase 5. Any further prose attempt starts there or repeats the cycle.

---

## 5 · Six qualifications that limit the numbers above

### 5.1 `existing_licensed_capability` is precision only; recall is untested

Both scorers matched it **zero times in 30 cases**. There is no positive case in the corpus, so the two-part test is shown **not to fire** — it is not shown to admit a true positive.

And the near-miss split, **3 for Scorer B against 10 for Scorer A**, says the two still read Part A very differently. The decision collapsed to agreement because Part B is unquotable in all 30 cases, not because the readings converged.

The honest claim: *the test eliminated a false-positive mechanism that decided five verdicts in run 2; its behaviour on a genuine licence claim is unmeasured.* A positive case exists and is cheap to add — `examples/02_hr_policy_questions.yaml` contains *"IT mentioned that the assistant bundled with our current licence tier can already search and answer over that same document library"*.

### 5.2 It is drift, not variance, and the distinction changes the remedy

Every dimension not repaired in Phase 5 moved **down**: `adoption_risk` −7, `implementation_effort` −7, `data_readiness` −13, `business_value` −8. The two that were repaired went to ceiling. Symmetric noise scatters; this does not. Four of four in the same direction is a 1-in-16 coincidence — suggestive at n = 4, not conclusive.

"±7 run-to-run variance" and "systematic downward drift across untouched dimensions" have different remedies: the first is answered by repetition, the second by finding the cause. Two testable candidates:

- Each run's scorers declared **fresh conventions** in their own file headers — how to treat a zero share, whether a stated headcount is a magnitude — and those conventions changed between runs.
- The rubric's **accumulating rationale prose** reframes neighbouring dimensions even where their anchors are untouched.

Either way, movements under ~7 points are not interpretable. What survives: `non_ai_alternative` −40, `process_frequency` +12 to ceiling, and the mechanism partition in §1, whose spread is 49 points.

### 5.3 The "untouched" dimensions were not a clean control

`data_readiness` received a `min()` rule in Phase 4. The assessment prompt changed length in all three runs. Calling these a control group is generous, and the drift estimate inherits that.

### 5.4 Both 100% dimensions are reliability at ceiling with untested validity

`process_frequency`'s 100% is 24 reads of a form field. It measures whether two scorers can read a number, **not whether the number is right**. B-03 scores level 1 for a process worth ~80k USD a year because the field says *"anual"*; B-05 counts 15 questionnaires where the agent would answer ~1,200 questions. Both are the field being in a defensible-but-arguably-wrong unit, and **no amount of agreement can see that.**

This is the same masking structure identified in the previous document — a reliable rule concealing a wrong one — now applying to the two dimensions this study leads with.

The honest framing: **Phase 5 converted a reliability problem into a validity problem, which is progress**, and validity needs a different instrument than an agreement study.

### 5.5 The verdict distributions have diverged

Eight verdict disagreements, and **six of the eight have different `non_ai_alternative` scores**. Scorer A returns 15 `no_go` and 3 `go`; Scorer B returns 11 `no_go` and 7 `go`. Two scorers applying the same instrument to the same corpus disagree about **more than twice as many approvals**.

### 5.6 Neither scorer is human, and n = 30, once

Unchanged from the first study and still the outer limit on everything here.

---

## 6 · What to publish about the instrument

> Three of seven dimensions are reproducible at 92–100% between independent scorers, **and all three resolve by computation from an intake field rather than by judgement.** Two more, scored by anchors alone, sit at 70–73%. Two carry a procedure written in prose and sit at 30–67% — worse than the dimensions with no procedure at all. `non_ai_alternative`, which controls a blocking gate, is the worst of them, and three attempts to repair it by rewriting its criteria each made it worse.
>
> Reliability is measured. **Validity is not**, and the two dimensions with perfect agreement are the ones where a wrong unit would be invisible.

No ROI rubric in circulation publishes either number.

---

## 7 · What to do about `non_ai_alternative`

**Rebuild it as a computation — but not by asking for the number.**

The obvious form of option 1 — *"what fraction of cases do your current rules or reports already close?"* — has an incentive problem the working derivations do not. `times_per_period` and `data_sensitivity` are neutral facts a requester has no reason to shade. That question asks the requester to **price the alternative to their own request, on the dimension that gates it.** It would be the only field in the intake with an adversarial incentive, and the derivation pattern's entire track record comes from non-adversarial fields.

The mitigation keeps the computation and removes the incentive: **ask for the artefacts, not the fraction.** *List the rules, reports, queries and templates you run today for this, and what each one covers.* Derive the fraction from the list.

That also addresses §3's residual: a list of artefacts has a much narrower entry point than a self-reported percentage.

The alternatives, for the record: rewrite all three frames at once starting from level 1's prose and level 5's "a form field" (one more prose attempt, but the first that removes the sediment); or demote the dimension, take the gate off it, and accept a compensable error where an unreproducible one now decides verdicts.

---

## 8 · Corrections made in v2, preserved

1. **§6 miscounted the bands** as "four of seven at 92–100%, two more at 70–73%". The run-3 column gives three and three. The correction is not cosmetic: it changes *three of four reproducible dimensions resolve by computation* into **all three of them do**, and it exposed the clean three-way partition in §1. The study's central result was hidden by an arithmetic slip in my own summary.
2. **`existing_licensed_capability` "total agreement"** was precision only. See 5.1.
3. **`business_value` 100% → 92% was attributed to drift.** Both disagreements are derived-vs-derived, at the branch-selection step. See §3.
4. **§4 called the movement variance.** The sign pattern says drift. See 5.2.
5. **Option 1 was recommended without its incentive problem.** See §7.
6. **Both 100% dimensions were reported as successes** without noting that agreement cannot see a wrong unit. See 5.4.

---

## 9 · Method

Across Phases 4 and 5, **eleven predictions were registered before the changes; three held.**

Overall agreement across the three runs reads 81 → 83 → 74. Without pre-registration the natural summary is *"we tried some fixes, one run was better, one was worse."* What actually happened is specific, directional, and generalisable:

- **Computation converges at 97%. Judgement converges at 60%. Prose procedure converges at 48% — worse than no procedure.**
- A dimension can be made monotonically worse by three consecutive repairs, each locally reasonable and evidence-driven.
- Reliability at ceiling can conceal a validity failure that no agreement study can detect.

And the central finding of this document was found by a reviewer checking my arithmetic against the raw files — not by the author, and not by care.
