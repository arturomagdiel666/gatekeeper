"""Data models for the assessment: what goes in, and what the model returns.

:class:`RequestIntake` is the input — the request form a business area fills
in. It is *not* LLM output and is never passed as a ``response_schema``; it is
here because it is a first-class data model of the Hub's intake, and because
``rubric.yaml`` gates on some of its fields.

:class:`Assessment` and its parts are the model's structured output, handed to
the provider as a ``response_schema``. Their field names are part of the prompt
contract, not merely internal naming, and two rules govern them — both bought
with measurement:

**No verdict, no total.** :class:`Assessment` deliberately has no field for a
verdict or a score total. Python computes both (see ``scoring.py``) from the
rubric. Offering a model a verdict field invites it to pick the conclusion
first and reason the dimensions backwards to justify it — the same failure mode
that pre-registering thresholds is meant to prevent on the human side. It is
also what makes the Hub's decisions auditable: every number in the outcome
traces to a weight in ``rubric.yaml`` and an evidence string here.

**Naming hygiene.** The Phase 1.6 matrix (``evals/spike_schema_shape_*.json``)
showed that prose in the prompt overrides schema key names: asking for "a
one-paragraph summary" made the model emit ``paragraph`` where the schema said
``summary``, in 6 of 10 trials, while the same nested schema with clean prose
scored 10 of 10 on key fidelity. So a prompt built on these models must refer
to fields by their exact names or not at all. :data:`BANNED_PROMPT_SYNONYMS` is
that rule as data rather than as prose, and a test asserts the generated
assessment prompt contains none of them.

Since the payload travels through constrained JSON generation rather than
native tool arguments (Phase 1.6 decision), nesting is safe here and the models
are shaped for clarity.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Confidence",
    "AntiPatternMatch",
    "DeterministicArtefact",
    "DataEvidence",
    "EffortEvidence",
    "AdoptionEvidence",
    "SampleCheck",
    "Procurement",
    "UserConsultation",
    "WorkflowFit",
    "RequestIntake",
    "Period",
    "PriorTool",
    "DataSensitivity",
    "DimensionAssessment",
    "Assessment",
    "InstrumentationPlan",
    "MeasurementContract",
    "BANNED_PROMPT_SYNONYMS",
    "banned_synonyms",
    "SCORE_MIN",
    "SCORE_MAX",
]

#: Bounds for a raw dimension score. These must match ``scale`` in
#: ``rubric.yaml``; a test asserts they have not drifted apart. They are
#: repeated here because a JSON Schema handed to a model has to carry static
#: bounds, whereas the rubric's scale is runtime configuration.
SCORE_MIN = 1
SCORE_MAX = 5

#: Words a prompt must never use in place of a schema field name, keyed by the
#: field they endanger. Curated deliberately: only terms that could plausibly
#: be mistaken for a *key name* are listed. Common English that merely appears
#: near a field ("because", "level", "criteria", "type") is excluded — banning
#: it would make the check unpassable without making the prompt any safer, and
#: "level" in particular is load-bearing in the rubric anchors.
BANNED_PROMPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "evidence": ("justification", "rationale", "reasoning", "justify"),
    "score": ("rating", "grade", "mark out of"),
    "confidence": ("certainty", "sureness", "how sure"),
    "dimension_id": ("criterion name", "factor id"),
    "anti_pattern_matches": ("red flag", "warning sign", "smells"),
    # "citation" is deliberately NOT banned here: it appears legitimately in
    # the rag_qa archetype's risk text ("answers with no citation"), which is
    # domain prose rather than an instruction naming a field. Banning it would
    # make the check unpassable without making the prompt any safer — the same
    # curation rule as "level" and "criteria" above.
    "quote": ("excerpt", "snippet", "verbatim span"),
    "archetype_id": ("use case category", "pattern name"),
    "proposed_metric_id": ("kpi", "success measure name"),
}


def banned_synonyms() -> tuple[str, ...]:
    """Every banned near-synonym, flattened and lower-cased."""
    return tuple(
        synonym.lower()
        for synonyms in BANNED_PROMPT_SYNONYMS.values()
        for synonym in synonyms
    )


class Confidence(str, Enum):
    """How firmly the request established a dimension's score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Period(str, Enum):
    """The unit ``times_per_period`` is counted in."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"

    @property
    def per_year(self) -> float:
        """How many of this period fall in a year."""
        return {"day": 260.0, "week": 52.0, "month": 12.0, "year": 1.0}[self.value]


class PriorTool(str, Enum):
    """What happened to the last tool built for these same users."""

    NONE = "none"
    ADOPTED = "adopted"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class SampleCheck(str, Enum):
    """Whether anyone has opened a real sample of the data and said what they saw.

    Not "is the data good" — that is the judgement this replaces. It asks what
    happened: did somebody look, and did they report a problem. R3 in
    ``rubric.yaml`` settles the boundary between the last two.
    """

    NOT_LOOKED = "not_looked"
    LOOKED_USABLE = "looked_usable"
    LOOKED_PROBLEMS = "looked_problems"


class Procurement(str, Enum):
    """What has to be bought before this can run.

    Ordered by how far outside the team's control the purchase sits, which is
    what the effort anchors actually grade — a licence bought off an existing
    contract is a form, a new vendor is a negotiation.
    """

    NONE = "none"
    EXISTING_LICENCE = "existing_licence"
    NEW_LICENCE_EXISTING_VENDOR = "new_licence_existing_vendor"
    NEW_VENDOR = "new_vendor"


class UserConsultation(str, Enum):
    """How far the intended users were involved.

    The boundary between `TOLD_NOT_ASKED` and `CONSULTED` is forced by evidence,
    not by the requester's sense of how collaborative they were: R1 in
    ``rubric.yaml`` says a user counts as consulted only if the requester can
    quote something one of them said about this work. No quote, no consultation.
    That is the same two-part evidence test that took the anti-pattern checks
    from 0% agreement to full agreement (ADR-029).
    """

    NOBODY = "nobody"
    TOLD_NOT_ASKED = "told_not_asked"
    CONSULTED = "consulted"
    REQUESTED_IT = "requested_it"


class WorkflowFit(str, Enum):
    """Where the output lands relative to what people already do."""

    EXISTING_STEP = "existing_step"
    EXISTING_STEP_MODIFIED = "existing_step_modified"
    NEW_STEP = "new_step"
    REPLACES_CHOSEN_WAY = "replaces_chosen_way"


class DataSensitivity(str, Enum):
    """Classification of the data the agent would process."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    REGULATED = "regulated"
    UNKNOWN = "unknown"


class DeterministicArtefact(BaseModel):
    """One deterministic thing that already exists today for this work.

    The input to ``non_ai_alternative``'s derivation, and the reason that
    dimension is a computation rather than a judgement (ADR-030).

    **Why this and not a percentage.** The obvious computation would be to ask
    the requester what fraction of cases their current rules already close. That
    is the one question in the intake with an adversarial incentive: it asks them
    to price the alternative to their own request, on the dimension that gates
    it. Every derivation that works in this rubric — ``times_per_period``,
    ``data_sensitivity`` — draws on a fact the requester has no reason to shade.
    So the form asks what EXISTS and the level is derived from the list.

    Attributes:
        name: What it is, in the requester's words.
        what_it_does: What it produces, in the requester's words. The coverage
            rule in ``rubric.yaml`` reads this text against the work the request
            describes, so a qualifier here ("about half the tickets") is
            load-bearing rather than decorative.
        completes_without_judgement: After this runs, is the work done, or does
            someone still have to decide something? The only field that asks for
            an assessment, and it is a yes/no about what happens next in the
            requester's own process — not a claim about the value of their
            request.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    what_it_does: str
    completes_without_judgement: bool


class DataEvidence(BaseModel):
    """What is known about the data, as facts rather than as a readiness opinion.

    Feeds ``data_readiness``, which scores ``min(availability, evaluability)``.
    Both halves are computed from the counts and enums here; the numbered rules
    that settle what each one means live in ``rubric.yaml`` beside the anchors,
    because they ARE the anchor semantics (ADR-035).

    Attributes:
        systems: The named systems the data lives in **today**. An empty list is
            a real answer meaning it is not in any system — in people's heads,
            on paper, or not collected. The count is what the derivation reads;
            the names are what makes it auditable. R2 settles what counts.
        sample_checked: Whether anyone has opened a real sample and said what
            they found.
        correct_examples: How many existing examples of a correct output there
            are. For a predictive request these are labelled outcomes; for a
            generative one, outputs somebody has agreed are good. Zero is a real
            answer and the common one.
        quality_criteria_agreed: Whether a written statement of what makes an
            output correct exists and has been agreed. R4 forbids counting an
            intention to write one.
    """

    model_config = ConfigDict(extra="forbid")

    systems: list[str]
    sample_checked: SampleCheck
    correct_examples: int = Field(ge=0)
    quality_criteria_agreed: bool


class EffortEvidence(BaseModel):
    """What has to be built, bought and approved, counted rather than estimated.

    Feeds ``implementation_effort``. The three inputs are scored separately and
    the **worst** governs, because the anchors are disjunctive: "several system
    integrations, OR a new platform component, OR retraining a whole team" is
    already a level 4 whichever one of them is true.

    Attributes:
        systems_to_integrate: The systems code must read from or write to. R5
            excludes a system a human exports a file from — that is a manual
            step, not an integration.
        procurement: What must be bought before this can run.
        approving_teams: The teams that can block this by withholding approval.
            R6 excludes teams that are merely informed.
    """

    model_config = ConfigDict(extra="forbid")

    systems_to_integrate: list[str]
    procurement: Procurement
    approving_teams: list[str]


class AdoptionEvidence(BaseModel):
    """What is known about the people who would have to change, and what they said.

    Feeds ``adoption_risk``, the dimension most likely to smuggle a judgement
    through — which is why its central field is settled by a quote rather than by
    a self-assessment. ``prior_tool_for_these_users`` is read from the intake
    alongside this, since it was already there and is the single most informative
    fact about adoption.

    Attributes:
        users_consulted: How far the intended users were involved.
        user_quote: Something one of the intended users said about this work,
            copied word for word. R1 makes this load-bearing: without it the
            consultation level is capped at `told_not_asked` however the
            requester describes it.
        workflow_fit: Where the output lands relative to what people already do.
        people_who_must_change: How many distinct people must change what they
            actually do. R8 excludes people who merely receive a different-
            looking report.
    """

    model_config = ConfigDict(extra="forbid")

    users_consulted: UserConsultation
    user_quote: str | None = None
    workflow_fit: WorkflowFit
    people_who_must_change: int = Field(ge=0)


class RequestIntake(BaseModel):
    """A request submitted to the AI Agent Hub.

    Input, not model output. ``business_owner`` is gated in ``rubric.yaml``:
    the Hub will not approve an agent with nobody accountable for its adoption
    or for its Measurement Contract, so an empty value forces ``no_go`` rather
    than being scored.

    **Why the structured fields exist.** The live run showed `adoption_risk`,
    `data_governance` and `non_ai_alternative` coming back unknown on almost
    every request — not because the model failed, but because **the free text
    does not contain them.** Nobody writes in a request whether a previous tool
    for the same users was adopted or abandoned. With seven dimensions and a
    limit of one unknown, `incomplete` became the default outcome. The fix is a
    short structured form, not a conversational agent: the single constrained
    call stays, it simply receives richer input.

    **Every structured field is optional on purpose.** A mandatory form
    pre-qualifies requests and teaches people to write what the form wants to
    hear. A blank field simply returns that dimension to model scoring, or to
    unknown.

    Attributes:
        request_text: What the requester wrote, in their own words.
        requesting_area: The business area or team making the request.
        business_owner: The named person accountable for this agent.
        process_description: How the work is done today.
        stated_benefit: The benefit the requester claims, if they named one.
        who_does_this_today: Who performs the work now, and roughly how many.
        people_affected: How many people the process touches.
        times_per_period: How many times the task would be done END TO END,
            with ``period``. Not how often the process runs: if one submission
            contains many items the agent would handle separately, this counts
            the items. The two are not the same question and asking the first
            one while scoring the second cost 12 points of agreement (ADR-029).
            When given, ``process_frequency`` is computed from it in code rather
            than inferred by the model.
        period: The unit ``times_per_period`` is counted in.
        minutes_per_instance: How long one instance takes a person today. With
            the volume above this is what makes ``business_value`` computable
            instead of estimated — the two fields multiply into annual
            person-hours (ADR-026).
        cost_per_instance: What one instance costs today, in the rubric's
            currency. The alternative denomination for the same computation,
            for processes whose benefit is cash rather than time.
        prior_tool_for_these_users: What happened to the last tool built for
            these users — the single most informative fact about adoption risk,
            and one that never appears in free text.
        where_the_data_lives: The systems holding the data.
        data_sensitivity: Classification of that data. When given,
            ``data_governance`` is computed from it in code.
        existing_deterministic_artefacts: The deterministic things that exist
            today for this work — see :class:`DeterministicArtefact`.
            ``non_ai_alternative`` is derived from this list, and the three
            states are distinct: an EMPTY list is a strong, reproducible signal
            that nothing exists, while ``None`` means nobody was asked and the
            dimension is recorded unknown rather than estimated (ADR-030).
    """

    model_config = ConfigDict(extra="forbid")

    request_text: str
    requesting_area: str = ""
    business_owner: str = ""
    process_description: str = ""
    stated_benefit: str | None = None

    # --- structured supplements, all optional --------------------------------
    who_does_this_today: str = ""
    people_affected: int | None = None
    times_per_period: int | None = None
    period: Period | None = None
    minutes_per_instance: float | None = Field(default=None, gt=0.0)
    cost_per_instance: float | None = Field(default=None, gt=0.0)
    prior_tool_for_these_users: PriorTool = PriorTool.UNKNOWN
    where_the_data_lives: str | None = None
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    #: ``None`` and ``[]`` mean different things here and the derivation reads
    #: both: None is "not asked", [] is "asked, nothing exists".
    existing_deterministic_artefacts: list[DeterministicArtefact] | None = None
    #: The three dimensions no field used to supply. Each is ``None`` when
    #: nobody was asked, which returns its dimension to model scoring exactly as
    #: before — that is what keeps every figure measured under rubric v2.0.0
    #: reproducible from a corpus whose intakes do not carry these (ADR-035).
    data_evidence: DataEvidence | None = None
    effort_evidence: EffortEvidence | None = None
    adoption_evidence: AdoptionEvidence | None = None

    @property
    def instances_per_year(self) -> float | None:
        """Annualized process volume, or ``None`` if not stated."""
        if self.times_per_period is None or self.period is None:
            return None
        return self.times_per_period * self.period.per_year


class AntiPatternMatch(BaseModel):
    """One matched anti-pattern, with the text that justifies the match.

    An anti-pattern match is held to a **higher evidentiary standard than a
    dimension score**, and this class is where that asymmetry lives. The reason
    is the same non-compensability that makes gates correct in the first place:
    an error in a weighted dimension moves the total by tenths and can be
    absorbed by the other six, while an error in a gate decides the verdict and
    cannot be outvoted by anything. See ADR-020.

    ``quote`` must be text copied **verbatim** from the request.
    ``scoring.py`` checks it as a substring of the request text before letting
    any gate fire on it; a quote that is not in the source is a fabrication, and
    the match is discarded and reported rather than silently honoured.

    Attributes:
        anti_pattern_id: Id from ``patterns.yaml``.
        quote: Text copied word for word from the request. Not a paraphrase,
            not a summary, not an inference.
        second_quote: A second span copied word for word, for the anti-patterns
            whose signals name two parts that must BOTH hold. Where
            ``patterns.yaml`` marks an anti-pattern ``two_part_evidence``, a
            match without this is discarded exactly as a fabricated quote is:
            half the test is not the test. ``None`` for every other
            anti-pattern, where it is neither wanted nor read.
        quote_confidence: How well that quote establishes the anti-pattern.
    """

    model_config = ConfigDict(extra="forbid")

    anti_pattern_id: str
    quote: str
    second_quote: str | None = None
    quote_confidence: Confidence


class DimensionAssessment(BaseModel):
    """One rubric dimension as assessed from the request.

    Attributes:
        dimension_id: Id of the rubric dimension being scored, exactly as it
            appears in ``rubric.yaml``.
        score: Raw score on the rubric scale, or ``None`` when the request does
            not establish it. Never guess a score to fill this in — an unknown
            recorded as unknown is what lets the scorer refuse to produce a
            verdict it cannot support.
        evidence: What in the request justifies this score, quoted or closely
            paraphrased. This is what a requester is shown when they ask why
            the verdict came out the way it did, so it must point at something
            actually present in the request.

            Deliberately held to a LOWER standard than
            :class:`AntiPatternMatch.quote`: free-form prose, not verified
            against the source. A wrong dimension score shifts the weighted
            total by tenths and is compensable by the other dimensions; a wrong
            anti-pattern match fires a gate and decides the verdict outright.
            The evidentiary bar follows the cost of the error (ADR-020).
        confidence: How firmly the request establishes the score.
    """

    model_config = ConfigDict(extra="forbid")

    dimension_id: str
    #: Required but nullable: the model must decide explicitly between a score
    #: and "the request does not establish this". Giving it a default would let
    #: the field be omitted, which is not the same statement.
    score: int | None = Field(ge=SCORE_MIN, le=SCORE_MAX)
    evidence: str
    confidence: Confidence


class Assessment(BaseModel):
    """The complete structured output of a single-shot assessment.

    Carries no verdict and no total on purpose — those are computed in Python
    from the rubric so the arithmetic is auditable and the model cannot lead
    with a conclusion.

    The two metric fields are the model's *only* role in the Measurement
    Contract: proposing which candidate metric fits and reporting a baseline if
    the request states one. The contract skeleton is assembled deterministically
    in ``contracts.py``.

    Attributes:
        archetype_id: Id of the best-matching archetype from
            ``patterns.yaml``, or ``None`` if none fits.
        anti_pattern_matches: Every matched anti-pattern, each carrying the
            verbatim quote that justifies it. Those flagged ``hard_block`` in
            ``patterns.yaml`` fire a gate — but only if their quote verifies
            against the request text.
        dimension_assessments: One entry per rubric dimension.
        proposed_metric_id: The candidate metric from ``contracts.yaml`` that
            best fits this request, or ``None`` to accept the archetype default.
        stated_baseline_value: The current value of that metric if the request
            states it, else ``None``. Do not estimate — an unmeasured baseline
            is a finding, and the contract records it as such.
    """

    model_config = ConfigDict(extra="forbid")

    # These three are REQUIRED — deliberately, and the reason is measured.
    # Pydantic omits any field with a default from the JSON Schema's `required`
    # list, and grammar-constrained decoding will then happily satisfy the
    # schema with `{}`. The first live run of the six examples returned
    # `{"archetype_id": "summarization", "proposed_metric_id": "..."}` and
    # nothing else: the model identified the archetype correctly and stopped,
    # because the schema told it everything else was optional. A schema that
    # does not demand the work does not get the work.
    archetype_id: str | None = Field(description="Null if no archetype fits.")
    anti_pattern_matches: list[AntiPatternMatch] = Field(
        description=(
            "Every anti-pattern the request matches, each with a verbatim "
            "quote from the request. Empty list if none. Never omit the key."
        )
    )
    dimension_assessments: list[DimensionAssessment] = Field(
        min_length=1,
        description="One entry per rubric dimension.",
    )
    # Genuinely optional: omitting these accepts the archetype's default metric
    # and records the baseline as unmeasured, both of which are valid outcomes.
    proposed_metric_id: str | None = None
    stated_baseline_value: float | None = None


class InstrumentationPlan(BaseModel):
    """What must be emitted for an agent to be reviewable at all.

    Four layers, because an agent can fail in four independent ways and a
    usage chart hides three of them.
    """

    model_config = ConfigDict(extra="forbid")

    usage: list[str] = Field(default_factory=list)
    quality: list[str] = Field(default_factory=list)
    business: list[str] = Field(default_factory=list)
    cost: list[str] = Field(default_factory=list)


class MeasurementContract(BaseModel):
    """The terms an agent is approved under — and will be reviewed against.

    An agent may only be approved together with the definition of its own
    failure. This is what makes retirement a scheduled, unemotional event
    rather than a political one.

    Attributes:
        primary_metric_id: Exactly one metric. Not a list — a contract with
            three metrics has none, because there is no single number anyone
            can be held to.
        primary_metric_label: Human-readable name of that metric.
        primary_metric_unit: Its unit, used by the reviewer to convert value.
        measurement_method: How the value is actually observed.
        baseline_value: The metric's value today, if it has been measured.
        baseline_is_measured: Whether that baseline was actually measured. A
            contract against an unmeasured baseline is still issued, but the
            fact is recorded — it is a finding, not a formality.
        success_threshold: The value that constitutes success at review.
        review_date: Approval date plus the horizon for this effort band.
        business_owner: The named person accountable, carried from intake.
        decommission_trigger_ids: References into the triggers catalogue.
        instrumentation_plan: What must be emitted, by layer.
        archetype_id: The archetype whose template produced this contract.
        approval_date: The date the agent was approved.
    """

    model_config = ConfigDict(extra="forbid")

    primary_metric_id: str
    primary_metric_label: str
    primary_metric_unit: str
    #: Whether a higher or lower value of the metric is better. Carried on the
    #: contract so the reviewer can compare value against threshold without
    #: reloading the metric catalogue — the contract must be self-contained
    #: enough to be evaluated on its own terms.
    primary_metric_direction: str
    measurement_method: str
    baseline_value: float | None = None
    baseline_is_measured: bool = False
    success_threshold: float
    review_date: date
    business_owner: str
    decommission_trigger_ids: list[str] = Field(default_factory=list)
    instrumentation_plan: InstrumentationPlan = Field(
        default_factory=InstrumentationPlan
    )
    archetype_id: str
    approval_date: date
