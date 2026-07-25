"""Pydantic models for the LLM's structured output.

These are the models the interview hands to the provider as a
``response_schema``, so their field names are part of the prompt contract, not
merely internal naming. Two rules govern them, both bought with measurement:

**No verdict, no total.** :class:`Assessment` deliberately has no field for a
verdict or a score total. Python computes both (see ``scoring.py``) from the
rubric. Offering a model a verdict field invites it to pick the conclusion
first and reason the dimensions backwards to justify it — the same failure mode
that pre-registering thresholds is meant to prevent on the human side. It is
also what makes Gatekeeper auditable: every number in the outcome traces to a
weight in ``rubric.yaml`` and an evidence string here.

**Naming hygiene.** The Phase 1.6 matrix (``evals/spike_schema_shape_*.json``)
showed that prose in the prompt overrides schema key names: asking for "a
one-paragraph summary" made the model emit ``paragraph`` where the schema said
``summary``, in 6 of 10 trials, while the same nested schema with clean prose
scored 10 of 10 on key fidelity. So a prompt built on these models must refer
to fields by their exact names or not at all. Specifically, never write:

* for ``evidence`` — "justification", "rationale", "reasoning", "because"
* for ``score`` — "rating", "grade", "number", "level", "points"
* for ``confidence`` — "certainty", "sureness", "how sure"
* for ``dimension_id`` — "criterion", "factor", "category"
* for ``anti_pattern_ids`` — "red flags", "warnings", "problems"
* for ``archetype_id`` — "pattern", "type", "kind", "shape"

Since the payload travels through constrained JSON generation rather than
native tool arguments (Phase 1.6 decision), nesting is safe here and the models
are shaped for clarity.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Confidence",
    "DimensionAssessment",
    "Assessment",
    "SCORE_MIN",
    "SCORE_MAX",
]

#: Bounds for a raw dimension score. These must match ``scale`` in
#: ``rubric.yaml``; a test asserts they have not drifted apart. They are
#: repeated here because a JSON Schema handed to a model has to carry static
#: bounds, whereas the rubric's scale is runtime configuration.
SCORE_MIN = 1
SCORE_MAX = 5


class Confidence(str, Enum):
    """How firmly the interview established a dimension's score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DimensionAssessment(BaseModel):
    """One rubric dimension as assessed from the interview.

    Attributes:
        dimension_id: Id of the rubric dimension being scored, exactly as it
            appears in ``rubric.yaml``.
        score: Raw score on the rubric scale, or ``None`` when the interview
            could not establish it. Never guess a score to fill this in — an
            unknown recorded as unknown is what lets the scorer refuse to
            produce a verdict it cannot support.
        evidence: What in the interview justifies this score, quoted or closely
            paraphrased. This is what a reader is shown when they ask why the
            verdict came out the way it did, so it must point at something the
            interviewee actually said.
        confidence: How firmly the evidence establishes the score.
    """

    model_config = ConfigDict(extra="forbid")

    dimension_id: str
    score: int | None = Field(default=None, ge=SCORE_MIN, le=SCORE_MAX)
    evidence: str
    confidence: Confidence


class Assessment(BaseModel):
    """The complete structured output of a discovery interview.

    Carries no verdict and no total on purpose — those are computed in Python
    from the rubric so the arithmetic is auditable and the model cannot lead
    with a conclusion.

    Attributes:
        archetype_id: Id of the best-matching archetype from
            ``patterns.yaml``, or ``None`` if none fits.
        anti_pattern_ids: Ids of every matched anti-pattern. Those flagged
            ``hard_block`` in ``patterns.yaml`` force a ``not_ai`` verdict.
        dimension_assessments: One entry per rubric dimension.
    """

    model_config = ConfigDict(extra="forbid")

    archetype_id: str | None = None
    anti_pattern_ids: list[str] = Field(default_factory=list)
    dimension_assessments: list[DimensionAssessment] = Field(default_factory=list)
