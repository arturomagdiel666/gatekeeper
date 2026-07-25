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
    "RequestIntake",
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
    "anti_pattern_ids": ("red flag", "warning sign", "smells"),
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


class RequestIntake(BaseModel):
    """A request submitted to the AI Agent Hub.

    Input, not model output. ``business_owner`` is gated in ``rubric.yaml``:
    the Hub will not approve an agent with nobody accountable for its adoption
    or for its Measurement Contract, so an empty value forces ``no_go`` rather
    than being scored.

    Attributes:
        request_text: What the requester wrote, in their own words.
        requesting_area: The business area or team making the request.
        business_owner: The named person accountable for this agent.
        process_description: How the work is done today.
        stated_benefit: The benefit the requester claims, if they named one.
    """

    model_config = ConfigDict(extra="forbid")

    request_text: str
    requesting_area: str = ""
    business_owner: str = ""
    process_description: str = ""
    stated_benefit: str | None = None


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
        anti_pattern_ids: Ids of every matched anti-pattern. Those flagged
            ``hard_block`` in ``patterns.yaml`` fire a gate.
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
    anti_pattern_ids: list[str] = Field(
        description="Empty list if none match. Never omit the key."
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
