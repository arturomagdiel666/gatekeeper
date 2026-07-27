---
tags: [evaluation, agreement, gatekeeper]
scorers: A (isolated agent) · B (Claude Code)
corpus: 30 cases, Spanish pilot run
status: pilot measured — v2, central attribution corrected after review
---

# Inter-rater agreement study — pilot run

Two independent scorers applied `rubric.yaml` v2.0.0 to the same 30 requests, blind to each other and to the design notes. Neither is human; see Limitations.

> **This is a pilot.** The corpus is in Spanish and the project standardised on English after this run. The findings hold, but the numbers are re-run on the English corpus before being quoted as final.

> **v2 correction.** The first version of §4 attributed the verdict disagreements to a divergent reading of the `existing_licensed_capability` anti-pattern. **That was wrong**, and it was wrong in a specific way worth recording: the evidence for it was assembled by naming the two dimension-threshold gates that supported the conclusion and omitting the one that contradicts it. Scorer B caught it. The corrected analysis is in §4, and it points the opposite way. The original error is preserved in §9 rather than deleted.

---

## 1 · Headline

| Measure | Result |
|---|---|
| Exact agreement, per dimension | **81%** (165 / 204 scoreable slots) |
| Agreement within ±1 level | **99.5%** (203 / 204) |
| Verdict agreement | **80%** (24 / 30) |
| Archetype agreement | 87% (26 / 30) |
| Largest single disagreement | 2 levels, once, in `business_value` |

No disagreement exceeded two levels. For a first application by two scorers who never spoke, that reads as a defensible instrument — and the aggregate is not the finding.

---

## 2 · Agreement by dimension

| Dimension | Weight | n | Exact | ±1 | Mean abs. diff | Distribution (A − B) |
|---|---|---|---|---|---|---|
| `process_frequency` | 0.13 | 25 | 100% | 100% | 0.00 | 0:25 |
| `data_governance` | 0.10 | 29 | 100% | 100% | 0.00 | 0:29 |
| `adoption_risk` | 0.17 | 30 | 80% | 100% | 0.20 | −1:2 · 0:24 · +1:4 |
| `data_readiness` | 0.15 | 30 | 80% | 100% | 0.20 | −1:3 · 0:24 · +1:3 |
| `implementation_effort` | 0.13 | 30 | 77% | 100% | 0.23 | −1:1 · 0:23 · +1:6 |
| `non_ai_alternative` | 0.10 | 30 | **70%** | 100% | 0.30 | −1:3 · 0:21 · +1:6 |
| `business_value` | **0.22** | 30 | **63%** | 97% | 0.40 | 0:19 · +1:10 · **+2:1** |

**The two dimensions at 100% are the two with `derivation` blocks in the rubric** — `process_frequency` derives from the intake volume field (line 221), `data_governance` from the intake sensitivity mapping (line 297). For most of those slots **no anchor judgement occurred at all**: both scorers applied the same lookup table. That agreement measures the derivation table, not the anchors, and must not be read as evidence that observable anchors make scorers converge.

The narrower claim the data does support: on the handful of `data_governance` slots where the intake field was blank and judgement was actually required (A-09, A-11, B-08, B-14), the scorers still converged. That is evidence for **deriving rather than inferring wherever a field exists** — a design lever, not a property of good anchor prose.

**The worst dimension carries the heaviest weight.** `business_value` at 63% is simultaneously the least reproducible and the most consequential.

**The skew is systematic, not noise.** In `business_value`, A scored higher than B in 11 of 30 and lower in none. The same one-directional skew appears in `implementation_effort` (6 higher, 1 lower) and `non_ai_alternative` (6 higher, 3 lower). Random disagreement scatters both ways. See §6 for a mechanical hypothesis that would explain the `business_value` case entirely.

**Nulls converged.** Both scorers left the same five `process_frequency` slots unscored, on the same five cases, for the same stated reason. B additionally left `data_governance` null on A-03. That "unscoreable" converges where "which level" does not is itself informative.

---

## 3 · Verdict disagreements

Six cases produced different verdicts.

| Case | A | B | Mechanism |
|---|---|---|---|
| A-06 | `no_go` 3.38 | `go` 3.53 | Band boundary — 0.15 apart across 3.50 |
| B-09 | `no_go` 3.46 | `go` 3.59 | Band boundary — 0.13 apart across 3.50 |
| A-09 | `not_ai` | `no_go` | `non_ai_alternative` A=4 / B=3 |
| A-10 | `not_ai` | `no_go` | `non_ai_alternative` A=4 / B=3 |
| B-05 | `not_ai` | `no_go` | `non_ai_alternative` A=4 / B=3 |
| B-12 | `not_ai` | `no_go` | `non_ai_alternative` A=4 / B=3 |

---

## 4 · Every verdict disagreement traces to one dimension

**All six.** Two are band flips on totals driven by the same dimension's weight; four are gate flips at the 3/4 boundary of `non_ai_alternative`, the dimension with the second-worst agreement in the study and a gate at ≥ 4.

**Zero verdict disagreements were caused by anti-pattern reading.** Verified against both score files:

- On A-09, A-10 and B-05, **neither scorer matched any anti-pattern.** The flip is purely the 3-versus-4 score.
- On B-12, A matched only `data_does_not_exist_yet`, which is advisory and does not gate.
- Across the whole run, hard-block anti-pattern matches were **verdict-redundant in 16 of 17 instances** — they landed on cases already gated by the threshold. A: 8 redundant, 1 decisive. B: 8 redundant, 0 decisive.

So the disagreement that looked most dramatic — `existing_licensed_capability`, matched 4 times by A and 0 by B — **changed no verdict at all.**

**And the one case where it could have, it was cancelled by an opposite disagreement.** On A-01, A scored `non_ai_alternative` = 3 and reached `not_ai` through the anti-pattern; B scored 4 and reached `not_ai` through the threshold. Same verdict, opposite routes, two disagreements hiding inside one apparent agreement. Verdict-level agreement conceals this entirely.

### The threshold gate is the least reproducible thing in the system

`non_ai_alternative_suffices` fired every `not_ai` in this run for Scorer B, and it rests on a dimension where two careful scorers disagree 30% of the time, at exactly the boundary the gate uses. Five of thirty cases cross the 3/4 line between scorers — **one case in six.**

This inverts the conclusion the first version of this document reached. Phase 3.1 marked anti-pattern gates `requires_human_confirmation` and left dimension-threshold gates final, on the reasoning that a threshold gate is "deterministic given the assessment". That reasoning conflates two different things:

> **Deterministic is not the same as reliable.** A dimension-threshold gate is perfectly deterministic in code and can still be the least reproducible decision in the system, because its input is a human-or-model judgement at a boundary the anchors do not operationally define.

On this evidence, `requires_human_confirmation` is currently attached to the condition class that decided nothing, and withheld from the one that decided everything.

### A structural blocker for fixing it

`rubric.yaml:442-456` puts **both condition types inside a single `any_of`** on `non_ai_alternative_suffices`: the `dimension_threshold` at 4, and `hard_block_any` over the remaining anti-patterns. Confirmation is currently a per-gate flag. The A/B split runs per **condition class**, so the flag has to move to the condition, not the gate — otherwise either the threshold condition inherits a confirmation it may not need, or the anti-pattern condition escapes one it does.

This is a design change, not an anchor rewrite, and it is blocked on nothing except deciding it.

---

## 5 · What the anti-pattern split still shows

The anti-pattern reading disagreement decided no verdicts *in this corpus*, but it is a real and clean division and it will decide verdicts in a corpus where the threshold does not shadow it.

| Anti-pattern | A | B | Agreement |
|---|---|---|---|
| `reporting_in_disguise` | 5 | 5 | 100% |
| `solution_first_no_measurable_problem` | 3 | 3 | 100% |
| `chatbot_without_job_to_be_done` | 2 | 2 | 100% |
| `rpa_relabeled` | 2 | 2 | 100% |
| `deterministic_rule_suffices` | 4 | 2 | 50% |
| `data_does_not_exist_yet` | 1 | 0 | 0% |
| `existing_licensed_capability` | 4 | 0 | 0% |

> Anti-patterns whose signals describe what the requester **said** agree perfectly. Anti-patterns requiring a judgement about the **world** diverge completely.

"Asks for a dashboard" is in the text or it is not. "A licensed platform already covers this" requires deciding whether a platform named as a data source is also a capability that already does the job. B read the signals narrowly, citing the `patterns.yaml` warning that firing on resemblance was the defect being corrected; A read them broadly. **Both readings are defensible from the text**, which is the defect.

---

## 6 · Confirmed anchor defects

Both scorers named the same three anchor sets as most ambiguous, in the same order, without contact.

**`business_value` — denominations are not commensurable.** Person-hours, currency and cases are joined with "or" and declared alternative denominations of the same magnitude. B-10 is level 3 by hours (~1,800) and level 5 by volume (108,000 movements); A-09 is 1 by hours, 3 by cases, 5 via the regulatory clause. Both scorers produced the same list of divergent cases.

**`business_value` — levels 4 and 5 smuggle in a second axis.** "Direct influence on revenue or on a regulatory obligation the company already reports" is a categorical fact about strategic salience on a dimension declared magnitude-only. This is the one-axis-per-dimension violation named and supposedly fixed in Phase 2.1, surviving in anchors rewritten *after* the rule was written down.

**`business_value` — currency mismatch, and it may explain the skew.** Every figure in the corpus is in Mexican pesos; every anchor threshold is in USD, with no conversion basis stated. At ~17–20 MXN/USD, reading a peso figure against a USD threshold lands **exactly one level high** — which is the shape of the observed one-directional skew (A higher in 11 of 30, never lower). This is a testable hypothesis, not a conclusion: it predicts the skew concentrates on cases whose evidence is a currency figure and vanishes on cases scored by hours or volume. **That is checkable against the existing score files without re-running anything**, and it should be checked before any anchor is rewritten, because if it holds, most of the worst dimension's disagreement is a definitional gap rather than an anchor problem.

**`non_ai_alternative` — the 3/4 boundary decides verdicts and has no operational test.** "Roughly half the cases" versus "most of it". Both are phrased as coverage *of cases*, but real non-AI alternatives cover *part of the problem across all cases* — a template fixes tone but not writing effort. B-09 states exactly 60% and sits between the two words. **Scorer B flagged the 3/4 boundary specifically on 14 of 30 cases, and the dimension overall on 19.** Given §4, this is the single highest-priority repair in the rubric.

**`non_ai_alternative` — level 1 demands impossible evidence.** It requires that "rule-based attempts have been tried and are known to fail". A maximally rule-immune request — machine translation — cannot satisfy that test, because nobody would attempt rules. The anchor requires proof that only exists when someone has already wasted effort.

**`data_readiness` — bundles two constructs, and gates on the ambiguity.** "Does the data exist" and "can you evaluate the output" are answered differently by the same case: B-12 has retrievable NDAs but no record of which required negotiation, so the corpus reads level 2–3 while the labels read level 1 — and **level 1 fires `no_usable_data`**. Level 4's "quality has been checked on a real sample" is almost never stated, capping well-instrumented requests at 3 by construction; level 5's access-owner clause caps perfect-label cases at 4 on a point about paperwork.

**`process_frequency` — the instance unit is undefined.** B-06: 45 tenders a year, or ~4,500 requirement responses? Level 2 versus level 4. Yet this dimension scored 100% agreement where scoreable — because the derivation table shadowed the anchors. The defect is **latent, not active**, and would surface the moment a case arrives without a volume field.

---

## 7 · Unplanned finding: the verdict distribution

| Verdict | Designed intent | Scorer A | Scorer B |
|---|---|---|---|
| `not_ai` | 9 | 19 | 15 |
| `no_go` | 8 | 8 | 10 |
| `go` | 7 | 3 | 5 |
| `incomplete` | 6 | **0** | **0** |

The corpus targeted ~23% `go` and ~20% `incomplete`. It produced 10–17% `go` and zero `incomplete`, under both scorers independently. Totals compress between 2.2 and 3.5.

`incomplete` has a mechanical explanation: gates evaluate before completeness, so a case that would be `incomplete` for missing information gets gated first. That ordering is deliberate — but it means a Hub expecting to route requests back for more information will rarely get the chance.

Recorded now so that a later rise in `go` rate is not mistaken for progress when it was threshold movement.

---

## 8 · Sequence

1. **Test the currency hypothesis** (§6) against the existing score files. Cheap, needs no re-run, and may explain most of the worst dimension's disagreement.
2. **State the conversion basis in the rubric.** This is a definitional gap, not an anchor rewrite — a different class of change, testable independently, and it should be decided deliberately rather than swept into the anchor pass by default.
3. **Move `requires_human_confirmation` from the gate to the condition** (§4), so the flag can follow the reliability of each condition class rather than the gate that happens to contain both.
4. **Translate corpus and artefacts to English; re-run both scorers** under the unchanged protocol.
5. **Compare runs.** Agreement surviving translation is a property of the instrument; agreement that changes is a property of the language — worth knowing before running this rubric in a bilingual organisation.
6. **Then** rewrite anchors in one documented pass, `non_ai_alternative` 3/4 first, `business_value` second.
7. Only after the corrected rubric is stable, run the system against the reconciled reference and measure per-dimension accuracy.

---

## 9 · The error this document made, preserved

v1 of §4 claimed the verdict disagreements were caused by divergent readings of `existing_licensed_capability`, and argued that this validated Phase 3.1's decision to mark anti-pattern gates as needing confirmation while leaving threshold gates final.

Every part of that was wrong. The anti-pattern disagreement changed no verdict; all six disagreements trace to a threshold gate; and the design decision the data supposedly validated is the one the data most undermines.

**The mechanism of the error is worth more than the correction.** v1 supported its claim by naming the two dimension-threshold gates whose dimensions agreed at 80% and 100%, and omitting `non_ai_alternative_suffices` — the threshold gate that fired every `not_ai` in the run and rests on the second-worst dimension. The omission was not deliberate, which is the point: the conclusion was reached first and the supporting set assembled around it.

That is precisely the failure mode this project designs against everywhere else — pre-registering thresholds before seeing data, removing the verdict field from the model's schema so it cannot pick a conclusion and reason backwards. **The same bias appeared in the analysis of the study built to detect bias**, and it was caught by an independent reader with access to the raw data, not by the author.

The countermeasure that worked was not care. It was a second party who could check the claim against the files.
