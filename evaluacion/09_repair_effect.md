---
tags: [evaluation, finding, rubric, gatekeeper]
runs: run 1 (rubric v2.0.0) vs run 2 (Phase 4 repair)
corpus: identical, 30 cases, unchanged
status: measured — repair partially reverted the improvement it aimed for
---

# Did the repair work?

Same 30 cases, same protocol, same two scorers, one variable changed: the rubric. Phase 4 repaired four dimensions and moved the confirmation flag to the condition.

**Predictions were registered before implementation.** One of five held.

---

## 1 · Against the registered predictions

| Prediction | Registered | Result | |
|---|---|---|---|
| `business_value` agreement rises | 63% → ? | **63% → 100%** | ✅ |
| `non_ai_alternative` agreement rises | 70% → ? | **70% → 61%** | ❌ fell |
| Verdict agreement rises | 80% → ? | **80% → 67%** | ❌ fell |
| `incomplete` rises above zero | 0 / 30 | 0 (A) · 1 (B) | ~ barely |
| `go` may fall | 3–5 / 30 | A 3 → 3 · B 5 → **7** | ❌ rose |

**Overall dimension agreement moved 81% → 83%.** Without the registered predictions, that two-point rise is the number that would have been reported, and it would have been reported as success. The pre-registration is what makes this readable as what it is: **a targeted fix that worked completely, inside a repair that made the system worse.**

---

## 2 · Per dimension

| Dimension | Run 1 | Run 2 | Δ | What Phase 4 did |
|---|---|---|---|---|
| `business_value` | 63% | **100%** | **+37** | Replaced a judgement with a derivation |
| `implementation_effort` | 77% | 80% | +3 | *(untouched)* |
| `adoption_risk` | 80% | 83% | +3 | *(untouched)* |
| `data_governance` | 100% | 96% | −4 | *(untouched — collateral)* |
| `data_readiness` | 80% | 73% | −7 | Added a `min()` rule over two sub-assessments |
| `non_ai_alternative` | 70% | **61%** | **−9** | Added numeric coverage bands |
| `process_frequency` | 100% | **88%** | **−12** | Added an instance-unit definition |

**One repair succeeded and three regressed**, including both dimensions that had been at 100%.

`business_value` reached **perfect agreement**, with its slot count dropping 30 → 25 because five cases now refuse rather than estimate. That is the mechanism working exactly as designed: derive, or refuse — never estimate.

---

## 3 · Why the three regressions failed the same way

All three failed identically, and Scorer A named it without being asked.

**`non_ai_alternative`.** The repair added numeric coverage bands. It did not remove the prose rule already there. Scorer A: *"the numeric bands helped, but nothing tells you whether a coarse deterministic output finishes an instance or merely half-does it, and the 'moves a judgement upstream' rule and the 'finishes it' rule pull opposite ways."* Two rules, no precedence between them. It flagged the 3/4 boundary **25 times**, up from 14.

**`process_frequency`.** The repair added an instance-unit definition to the `axis` — asked for because the unit was undefined and the defect was latent. But the dimension already had a `derivation` that reads the intake volume field literally. Scorer A: *"the axis defines the unit but the derivation reads the field literally, and the two disagree by two bands."* B-06 is 45 tenders by the field and ~5,400 requirement responses by the axis.

**`data_readiness`.** The repair added a `min()` over availability and evaluability. The two sub-assessments still come from anchors that were not themselves repaired, so the rule made the combination mechanical while leaving both inputs judgemental.

> **Replacing a judgement with a procedure works. Adding a rule alongside a judgement makes it worse.**

`business_value` is the only one of the four where the procedure *replaced* the judgement — the estimation instruction was deleted, not supplemented. It is also the only one that improved.

### The two 100% dimensions were fragile, and clarifying them is what broke them

`process_frequency` and `data_governance` scored 100% in run 1 **because a derivation shadowed the anchors** — for most slots, no anchor judgement happened at all. Run 1's analysis said so explicitly and called the underlying defect *latent rather than active*.

Phase 4 defined the instance unit correctly. In doing so it gave scorers a reason to override the derivation — and they overrode it differently. **The clarification activated the latent defect.**

`data_governance` fell 4 points without being touched at all, which is the same effect arriving as collateral.

---

## 4 · The verdict result, and the deepest finding in the study

Verdict agreement fell from 80% to 67%. Ten cases now disagree, up from six. But the *cause* has completely changed hands.

| | Run 1 | Run 2 |
|---|---|---|
| Disagreements caused by `non_ai_alternative` threshold | **6 of 6** | 2 of 10 |
| Disagreements caused by `existing_capability_covers_it` | **0 of 6** | **5 of 10** |
| Band-boundary flips | 2 of 6 | 2 of 10 |

In run 1, the `existing_licensed_capability` disagreement — the most dramatic-looking number in the whole study, matched 4 times by A and 0 by B — **decided nothing**. Hard-block matches were verdict-redundant in 16 of 17 instances, because the threshold gate had already fired.

In run 2 it decides half the disagreements. Scorer A matched it **10 times**; Scorer B, zero. Agreement on that anti-pattern: **0%, in both runs.**

Nothing about that anti-pattern changed in Phase 4.

> **The repair did not create the unreliable mechanism. It removed the thing that was hiding it.**

Fixing the threshold gate reduced how often it fires, which stopped it shadowing the anti-pattern gate that sits above it in precedence. The worst-agreeing decision rule in the system was always there, doing nothing visible, waiting for the rule in front of it to stop covering it.

This generalises past this project:

> A repair that improves one mechanism can degrade the system, when the mechanism it improved was masking a worse one. Measuring only the repaired component will report success.

Run 1's own analysis contained the warning and neither scorer nor author read it as one: on A-01, the two scorers reached the same verdict by *opposite routes*, one via anti-pattern and one via threshold. That was redundancy visible in the data, described as a curiosity. It was the load-bearing structure.

---

## 5 · Nulls, and a gate that fails open

| | Run 1 | Run 2 |
|---|---|---|
| Scorer A nulls | 5 | **14** |
| Scorer B nulls | 6 | **11** |

Refusal nearly tripled, as intended for `business_value`. But nulls also appeared in `data_governance` and `non_ai_alternative` — both `never_unknown`, both gate conditions.

Scorer A flagged four of them explicitly: **a null on a gate condition means the gate cannot fire.** `never_unknown` forces `incomplete` rather than a silent pass, so the system behaves correctly — but only one case in thirty actually returned `incomplete`, because a *different* gate fired first. The ordering is right; the effect is that a refusal on a gated dimension is frequently invisible in the outcome.

---

## 6 · What follows

**Keep `business_value` exactly as it is.** It is the only demonstrated success in the repair and the only one that replaced rather than supplemented.

**For `process_frequency` and `non_ai_alternative`, delete a rule — do not add a third.** Each now carries two rules that disagree. Pick one and remove the other:
- `process_frequency`: either the derivation reads the intake field and the axis is rewritten to match it, or the axis's unit is authoritative and the derivation must recount. Not both.
- `non_ai_alternative`: either "finishes an instance end to end" or "moves the judgement upstream". Not both.

**`data_readiness` needs its sub-anchors repaired, not its combination rule.** The `min()` is sound; its inputs are not.

**`existing_capability_covers_it` is now the highest-priority repair in the system** — 0% agreement across both runs, on the highest-precedence gate, now deciding half of all disagreements. Scorer A applied an explicit, self-invented rule ("the request names a platform the company runs *and* that platform is the natural home of the requested capability") and called it *"the least reproducible call in the set"*. That rule, or a better one, belongs in `patterns.yaml` — no anti-pattern should require a scorer to invent its own decision procedure.

**Do not translate the corpus yet.** Two variables have now moved separately, which is what made this readable. Translation is a third and it should stay separate.

---

## 7 · What this run cost and what it bought

Two scorer runs over 30 cases. It bought:

- A confirmed, complete fix on the heaviest-weighted dimension — 63% to 100%
- A measured refutation of three of the four repairs, before any of them reached the paper as improvements
- A general rule about instrument repair that neither scorer nor author held before: **replace judgements, do not supplement them**
- The discovery that the system's least reliable decision rule had been invisible for two phases because a more frequent rule was covering it

And it is worth naming what made all of that legible: **five predictions written down before the change.** Overall agreement rose two points. Without the registered predictions, that is the sentence that would have been written, and every finding in this document would have been missed.
