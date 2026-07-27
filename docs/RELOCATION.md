# The relocation ledger

Rubric v3.0.0 converted the three dimensions a model used to score —
`data_readiness`, `implementation_effort`, `adoption_risk` — into derivations
over intake fields. Every measured figure this project has published says that
was the right move: computed slots reach κw = 0.97 against a two-assessor
reference and are identical across a doubling of model size, while model-scored
slots reach κ = 0.04, which is chance.

**But a conversion is not automatically a gain.** §4.3 of the paper says it
plainly: converting a dimension can look like a reliability improvement while
actually being a *transfer* — the judgement does not disappear, it moves to
whoever fills the field. `non_ai_alternative` is the worked example. Its
agreement went from 30% to 100% between scorers, and what that measures is that
two scorers reading the same authored list agree; it says nothing about whether
the list is right.

The only defence against passing off a transfer as a resolution is to name the
transfer at the moment it is made. That is what this file is. It is written to
be read by someone deciding whether to trust a Gatekeeper verdict, not as an
appendix.

One thing to hold onto while reading: **every judgement below used to be made by
a language model whose agreement with the reference was indistinguishable from
chance.** The comparison is not "expert scorer versus requester". It is
"requester with a written rule versus a model at κ = 0.04". That does not make a
relocation harmless; it does mean the alternative was not better.

---

## 1 · `data_readiness`

**Weight 0.15. Level 1 fires the `no_usable_data` gate, so this one can decide a
verdict on its own.**

**The judgement that used to sit with the scorer.** Whether the data is good
enough and whether you could tell a good output from a bad one — read off a
prose description of the process, against five anchors, by someone who had never
seen the data.

**Who makes it now.** Split four ways, and the split is the point:

| Sub-judgement | Who now decides | How it is forced |
|---|---|---|
| Where the data lives | The requester, by naming systems | R2. A count of named systems, not an adjective. "Scattered" is three or more; "centralized" is one |
| Whether the quality is known | Whoever opened the data | R3. `looked_usable` requires a person to have opened real records and reported no problems. An opinion formed without opening the data is `not_looked` |
| Whether an output can be judged | The requester, by counting | R4b. Examples that exist **now**, not records that could be labelled one day |
| Whether criteria are settled | The requester, by pointing at a document | R4. A **written** statement, **agreed** by the people who would apply it. An intention to write one is `false` |

**What would make it wrong.**

- **`sample_checked` is the soft spot.** R3 asks what happened, but the person
  reporting is usually the person who wants the project. "We looked and it was
  fine" is cheap to say and nothing in the system can contradict it. A requester
  who glanced at ten tidy rows and one who ran a profiling job give the same
  answer.
- `correct_examples` is a number, and a number invites rounding in the direction
  of the answer you want. R4b narrows what counts but cannot audit the count.
- R2 undercounts by construction: a requester who thinks of "the CRM" as one
  system when it is three tables in two databases states one system and lands at
  availability 5. The rule asks for systems, and system boundaries are the
  requester's own mental model of their estate.
- The 5/4 boundary rests on the difference between one system and two. That
  threshold is authored, not derived from the anchors, and a request sitting on
  it moves a whole level on a distinction nobody would defend as principled.

**Checkable against anything?** **Partly.** The named systems are checkable by
anyone with access to the estate — a wrong system name is falsifiable. The
example count is checkable in principle by looking. `sample_checked` and
`quality_criteria_agreed` are checkable only by asking to see the sample report
or the criteria document, which nothing in the system requires. Nobody checks
today.

---

## 2 · `implementation_effort`

**Weight 0.13. No gate. The most straightforwardly convertible of the three, and
the one with the least to say for itself.**

**The judgement that used to sit with the scorer.** How long the whole path to
production would take, in weeks-to-years bands, estimated from a paragraph.

**Who makes it now.** The requester, by producing three lists and one enum.

| Sub-judgement | Who now decides | How it is forced |
|---|---|---|
| What must be integrated | The requester, by naming systems | R5. Only systems **code** must read from or write to. A file a person exports by hand is a manual step, not an integration |
| What must be bought | The requester | R7. Ordered by distance from the team's control: an existing licence is a form, a new vendor is a negotiation |
| Who can block it | The requester, by naming teams | R6. Only teams that can **stop** this by withholding approval. Informed, consulted, or merely affected does not count |

**What would make it wrong.**

- **The requester is the worst-placed person in the organisation to count
  integrations.** They know their process; they do not know that the reporting
  system reads from a warehouse that would need a new feed. This field is
  systematically biased *low*, and `implementation_effort` is `lower_is_better`,
  so the bias runs toward approval. This is the clearest instance in the ledger
  of a relocation making a number easier to produce and no more likely to be
  right.
- R6 asks who can block, which is political knowledge. A requester who has never
  tried to ship anything through this organisation will name their own team and
  stop.
- The bands are authored thresholds. Three integrations is a 3 and four is a 4,
  and nothing in the anchors says where that line goes.

**Checkable against anything?** **In principle, by the people who would build
it, and that is exactly what nobody does before triage.** A delivery team could
correct every one of these fields in ten minutes. The rubric does not ask them.
The whole point of an intake gate is to decide before spending that ten minutes,
which means this dimension is now an unverified claim by an interested party
where it used to be an unverified guess by a model. **Neither is evidence.**

---

## 3 · `adoption_risk`

**Weight 0.17 — the second-heaviest dimension. No gate. The hardest of the three
and the one most likely to smuggle a judgement through.**

**The judgement that used to sit with the scorer.** Whether the intended users
will actually change how they work — inferred from prose, on a dimension where
the request almost never contains the relevant facts.

**Who makes it now.** The requester, and the design fights that as hard as it can.

| Sub-judgement | Who now decides | How it is forced |
|---|---|---|
| Whether users were consulted | **The users, indirectly** | R1. A user counts as consulted only if the requester can quote something one of them said about this work. `record_field` verifies the quote against what the requester actually typed. No quote → demoted to `told_not_asked` → level 4 |
| Where the output lands | The requester | R8. `existing_step` only if the output arrives somewhere they already open, at the cadence they already open it |
| How many must change | The requester, by counting | R9. People whose **own actions** change. Receiving a different-looking report does not count |
| What happened last time | The requester | Pre-existing field. `unknown` contributes nothing — the absence of a fact is not evidence adoption will go badly |

**R1 is the load-bearing part of this whole phase.** Without it,
`users_consulted` is a question about how collaborative the requester feels they
were, which is precisely the judgement the conversion was supposed to remove. The
quote requirement is the same two-part evidence test that took the anti-pattern
checks from 0% agreement between scorers to full agreement (ADR-029): a claim
about the world, made checkable by requiring the sentence it rests on.

**What would make it wrong.**

- **A requester can quote a user who agrees and not the three who did not.** The
  quote makes consultation *evidenced*; it does not make it *representative*.
  Selection is entirely unconstrained and the system cannot see it.
- R1 verifies the quote against the requester's own answer, not against the user.
  Someone willing to invent a sentence and type it in defeats the check
  completely. What the check actually stops is the softer and far commoner
  failure: claiming consultation happened without being able to produce anything
  anyone said.
- R8's `existing_step` is the field most likely to be answered optimistically.
  Every requester believes their thing fits naturally into what people already
  do; that belief is most of why the request exists.
- The headcount band is the one threshold not taken from the anchors' own
  wording. It does not invent a scale — it only refuses to let a change reaching
  hundreds of people score better than 3, on the grounds that anchor 3 already
  describes adoption that "depends on a manager asking people to use it". That
  reasoning is defensible and it is still authored.

**Checkable against anything?** **The quote is checkable in the weakest possible
sense** — present or absent, and verbatim against the answer it came in. Nothing
verifies that a user said it, that the user is representative, or that anyone was
asked. `prior_tool_for_these_users` is checkable by anyone with a memory of the
last two years. Everything else rests entirely on the requester's word.

**This is the relocation with the largest gap between how rigorous it looks and
how rigorous it is.** It has numbered rules, an evidence requirement, a
verification step and a demotion path, and a determined requester can still walk
a hopeless project to `adoption_risk = 1` by typing a sentence.

---

## 4 · Two things this exposed, neither of them a conversion

**`adoption_risk` has no gate, and at weight 0.17 it cannot stop anything.** A
request where nobody was consulted, which replaces a way of working the users
chose themselves, affecting 900 people, derives `adoption_risk = 5` — and is
still approved, at a weighted total of 3.68. The other six dimensions outvote it.

This is not new behaviour and the conversion did not cause it: under v2.0.0 a
model scoring this dimension 5 produced exactly the same result. What changed is
that it is now reachable deterministically, so it can be demonstrated instead of
argued about. The rubric's own reasoning about gates applies directly — *"a
weight small enough to be fair to a normal case is too small to stop an extreme
one"* — and no gate was ever written for the dimension the whole system says
decides whether an internal tool succeeds.

Adding one would change verdicts, so it is left here as an open question for the
owner rather than decided inside a phase whose brief forbids altering published
numbers. `tests/test_conversion.py::test_the_worst_possible_adoption_profile_still_reaches_go`
pins the current behaviour so the decision is made deliberately rather than
discovered.

**`non_ai_alternative` still resists, exactly where ADR-030 said it would.** Its
derivation settles the empty list, the nothing-completes case, and the absent
field. Levels 3–5 need *part / most / all*, which requires reading the artefact
descriptions against the work — and the intake deliberately does not ask the
requester what fraction their existing tool covers, because that is the one
question in the whole form with an adversarial incentive: it asks them to price
the alternative to their own request, on the dimension that gates it.

So a request whose existing artefacts complete part of the work still cannot be
resolved without a human reader. **That is the honest boundary of this
programme,** and it is left standing rather than papered over with a table.

---

## 5 · The summary a reader should leave with

| Dimension | Relocated to | Checkable | Direction of the likely error |
|---|---|---|---|
| `data_readiness` | Requester, plus whoever opened the data | Partly — systems and examples are falsifiable | Optimistic on quality |
| `implementation_effort` | Requester | In principle by a delivery team; nobody does | **Low**, and lower means approve |
| `adoption_risk` | Requester, with one quote from one user | Barely | Optimistic on fit and on consultation |

Three judgements moved from a model at chance agreement to a requester with
written rules. Two of the three are biased toward approval, and none of the three
is verified by anyone before a verdict is issued.

**What would make this ledger obsolete is not a better rule. It is a second
party** — a delivery team confirming the integration count, a data owner
confirming the sample was opened, one of the named users confirming they were
asked. Until then these fields are auditable, which is a real gain over a model
score, and unaudited, which is the thing to remember when reading a verdict built
on them.
