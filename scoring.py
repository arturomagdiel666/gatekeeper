"""Deterministic scoring: rubric plus assessment in, verdict out.

Pure functions only — no LLM calls, no file I/O, no clock, no randomness. The
model supplies per-dimension scores and evidence; every number in the result is
computed here, from weights that live in ``rubric.yaml``. That split is what
makes a verdict defensible: asked "why No-Go?", you can point at the exact line
of arithmetic and the exact sentence of evidence behind it.

The order of evaluation matters and is deliberate:

1. **Gates first.** Any blocking gate declared in ``rubric.yaml`` that fires
   forces its verdict and overrides everything. Gates are positive findings —
   learning that a SQL query already solves the problem is enough to stop, even
   mid-interview — so they are checked before the completeness rule. A gate
   cannot fire on a dimension the interview left unknown.
2. **Completeness next.** Too many unknown dimensions yields ``incomplete``
   rather than a verdict computed from a mostly-empty interview.
3. **Bands last.** The weighted total is matched against the rubric's bands,
   which only ever produce ``go`` or ``no_go``.

Gates exist because some conditions are categorical rather than gradual, and no
weighted average can express "this is disqualifying": a weight small enough to
be fair to a normal case is too small to stop an extreme one. A use case can
therefore score 4.6 and still come out ``not_ai`` or ``no_go``. That is the
entire point of the product — if these conditions were merely low scores,
exactly the cases Gatekeeper exists to catch would pass as Go.

When several gates fire, the one with the lowest ``precedence`` decides the
verdict and every gate that fired is still reported.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from config import (
    AntiPatternCondition,
    DimensionThresholdCondition,
    IntakeFieldCondition,
    Patterns,
    Rubric,
)
from schemas import Assessment, DimensionAssessment, RequestIntake

__all__ = [
    "Verdict",
    "TriggeredGate",
    "DimensionContribution",
    "Outcome",
    "score",
    "match_band",
    "TOTAL_PRECISION",
]

#: Decimal places the weighted total is rounded to before it is compared to a
#: band boundary. Without this, a total that should be exactly 3.5 can land on
#: 3.4999999999999996 and fall into the wrong band — the arithmetic is a sum of
#: binary floats, and band edges are the one place that error is visible.
TOTAL_PRECISION = 6


class Verdict(str, Enum):
    """The outcome of a triage."""

    GO = "go"
    NO_GO = "no_go"
    NOT_AI = "not_ai"
    INCOMPLETE = "incomplete"


class TriggeredGate(BaseModel):
    """A blocking gate that fired, and what specifically fired it.

    Attributes:
        gate_id: The gate's id in ``rubric.yaml``.
        verdict: The verdict this gate forces.
        precedence: Lower decides when several gates fire.
        reason: The gate's human-readable explanation from the config.
        detail: What in this particular assessment met the condition — the
            dimension and score, or the anti-patterns matched.
        matched_anti_pattern_ids: Hard-blocking anti-patterns that contributed,
            empty unless this gate has an anti-pattern condition.
    """

    model_config = ConfigDict(extra="forbid")

    gate_id: str
    verdict: Verdict
    precedence: int
    reason: str
    detail: str
    matched_anti_pattern_ids: list[str] = Field(default_factory=list)


class DimensionContribution(BaseModel):
    """One dimension's line in the weighted total, fully explained.

    Attributes:
        dimension_id: Rubric dimension id.
        label: Human-readable dimension name.
        raw_score: The score as assessed, before direction handling.
        normalized_score: The score after direction handling, where higher
            always means better.
        weight: The dimension's declared weight in the rubric.
        effective_weight: The weight actually applied, after renormalizing
            across the known dimensions. Equal to ``weight`` when nothing is
            unknown.
        contribution: ``normalized_score * effective_weight`` — this line's
            share of the weighted total.
        evidence: The interview evidence behind the score.
        confidence: How firmly the evidence establishes the score.
    """

    model_config = ConfigDict(extra="forbid")

    dimension_id: str
    label: str
    raw_score: int
    normalized_score: int
    weight: float
    effective_weight: float
    contribution: float
    evidence: str
    confidence: str


class Outcome(BaseModel):
    """The complete, auditable result of scoring one assessment.

    Attributes:
        verdict: The decision.
        weighted_total: The weighted score on the rubric's scale, or ``None``
            when no score could be computed (an ``incomplete`` outcome, or a
            gate firing on an interview too sparse to score).
        contributions: Per-dimension breakdown; these sum to
            ``weighted_total``.
        triggered_gates: Every blocking gate that fired, ordered by precedence
            so the first is the one that decided the verdict. Empty if none.
        unknown_dimensions: Ids of dimensions the interview left unknown.
        ignored_dimension_ids: Assessed ids that are not in the rubric, or
            duplicate entries after the first. Reported rather than raised, so
            a model hallucinating an id degrades the outcome visibly instead of
            crashing the run.
        ignored_anti_pattern_ids: Matched anti-pattern ids not in
            ``patterns.yaml``.
        explanation: Human-readable account of how the verdict was reached.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    weighted_total: float | None
    contributions: list[DimensionContribution] = Field(default_factory=list)
    triggered_gates: list[TriggeredGate] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    ignored_dimension_ids: list[str] = Field(default_factory=list)
    ignored_anti_pattern_ids: list[str] = Field(default_factory=list)
    explanation: str = ""

    @property
    def triggered_gate_ids(self) -> list[str]:
        """Ids of the gates that fired, in precedence order."""
        return [gate.gate_id for gate in self.triggered_gates]


def match_band(weighted_total: float, rubric: Rubric) -> Verdict:
    """Map a weighted total onto the rubric's verdict bands.

    Bands match on ``lower <= total < upper``, or ``lower <= total <= upper``
    for the highest band. The rubric's own validation guarantees the bands tile
    the scale, so any total within it matches exactly one band.

    Args:
        weighted_total: A score on the rubric's scale.
        rubric: The validated rubric supplying the bands.

    Returns:
        The banded verdict, always :attr:`Verdict.GO` or :attr:`Verdict.NO_GO`.

    Raises:
        ValueError: If the total falls outside every band, which can only
            happen if it is off the rubric's scale entirely.
    """
    for band in rubric.verdict_bands:
        within_upper = (
            weighted_total <= band.upper
            if band.upper_inclusive
            else weighted_total < band.upper
        )
        if band.lower <= weighted_total and within_upper:
            return Verdict(band.verdict)
    raise ValueError(
        f"weighted total {weighted_total!r} falls outside every verdict band; "
        f"the rubric's scale is {rubric.scale.min}-{rubric.scale.max}"
    )


def _index_assessments(
    assessment: Assessment, rubric: Rubric
) -> tuple[dict[str, DimensionAssessment], list[str]]:
    """Index dimension assessments by id, first entry winning.

    Returns the index plus the ids that were ignored: unknown to the rubric, or
    duplicates of an id already seen.
    """
    indexed: dict[str, DimensionAssessment] = {}
    ignored: list[str] = []
    known_ids = set(rubric.dimension_ids)
    for entry in assessment.dimension_assessments:
        if entry.dimension_id not in known_ids or entry.dimension_id in indexed:
            ignored.append(entry.dimension_id)
            continue
        indexed[entry.dimension_id] = entry
    return indexed, ignored


def _evaluate_gates(
    assessment: Assessment,
    indexed: dict[str, DimensionAssessment],
    rubric: Rubric,
    patterns: Patterns,
    intake: RequestIntake | None,
) -> tuple[list[TriggeredGate], list[str]]:
    """Evaluate every blocking gate declared in the rubric.

    A gate fires when any one of its conditions is met. Two kinds of condition
    can never be met rather than being treated as false-by-default:

    * a dimension the assessment left unknown — an unknown is not evidence, and
      treating it as one would defeat the point of recording it;
    * an intake field when no ``intake`` was supplied, since the scorer then
      has no way to know whether the field was empty or simply not passed.

    Returns the gates that fired, ordered by precedence (so the first decides
    the verdict), plus any matched anti-pattern ids absent from the patterns
    file.
    """
    ignored_anti_patterns: list[str] = []
    matched_all: list[str] = []
    matched_hard_blocks: list[str] = []
    for anti_pattern_id in assessment.anti_pattern_ids:
        anti_pattern = patterns.anti_pattern_by_id(anti_pattern_id)
        if anti_pattern is None:
            ignored_anti_patterns.append(anti_pattern_id)
            continue
        matched_all.append(anti_pattern_id)
        if anti_pattern.hard_block:
            matched_hard_blocks.append(anti_pattern_id)

    triggered: list[TriggeredGate] = []
    for gate in rubric.gates_by_precedence:
        details: list[str] = []
        contributing_anti_patterns: list[str] = []
        for condition in gate.any_of:
            if isinstance(condition, DimensionThresholdCondition):
                entry = indexed.get(condition.dimension)
                if entry is None or entry.score is None:
                    continue
                if condition.is_met(entry.score):
                    details.append(condition.describe(entry.score))
            elif isinstance(condition, AntiPatternCondition):
                hits = condition.matches(matched_hard_blocks, matched_all)
                if hits:
                    contributing_anti_patterns.extend(hits)
                    details.append(
                        "anti-pattern(s) matched: " + ", ".join(hits)
                    )
            elif isinstance(condition, IntakeFieldCondition):
                if intake is None:
                    continue
                if condition.is_met(getattr(intake, condition.field, None)):
                    details.append(condition.describe())
        if details:
            triggered.append(
                TriggeredGate(
                    gate_id=gate.id,
                    verdict=Verdict(gate.verdict),
                    precedence=gate.precedence,
                    reason=" ".join(gate.reason.split()),
                    detail="; ".join(details),
                    matched_anti_pattern_ids=contributing_anti_patterns,
                )
            )
    return triggered, ignored_anti_patterns


def _compute_contributions(
    indexed: dict[str, DimensionAssessment], rubric: Rubric
) -> tuple[list[DimensionContribution], float]:
    """Build the per-dimension breakdown and the weighted total.

    Weights are renormalized across the dimensions that have a score, so the
    total always lands on the rubric's scale even when something is unknown.
    """
    scored = [
        (dimension, indexed[dimension.id])
        for dimension in rubric.dimensions
        if dimension.id in indexed and indexed[dimension.id].score is not None
    ]
    weight_sum = sum(dimension.weight for dimension, _ in scored)

    contributions: list[DimensionContribution] = []
    for dimension, entry in scored:
        assert entry.score is not None  # guaranteed by the filter above
        normalized = rubric.normalize(dimension, entry.score)
        effective_weight = dimension.weight / weight_sum
        contributions.append(
            DimensionContribution(
                dimension_id=dimension.id,
                label=dimension.label,
                raw_score=entry.score,
                normalized_score=normalized,
                weight=dimension.weight,
                effective_weight=round(effective_weight, TOTAL_PRECISION),
                contribution=round(normalized * effective_weight, TOTAL_PRECISION),
                evidence=entry.evidence,
                confidence=entry.confidence.value,
            )
        )
    total = round(sum(c.contribution for c in contributions), TOTAL_PRECISION)
    return contributions, total


def _build_explanation(
    verdict: Verdict,
    weighted_total: float | None,
    contributions: list[DimensionContribution],
    triggered_gates: list[TriggeredGate],
    unknown_dimensions: list[str],
    rubric: Rubric,
    patterns: Patterns,
    assessment: Assessment,
) -> str:
    """Assemble the human-readable account of how the verdict was reached."""
    lines: list[str] = []
    scale_max = rubric.scale.max

    if triggered_gates:
        headline = (
            f"Verdict: {verdict.value.upper()} — forced by "
            f"{len(triggered_gates)} blocking gate(s). This is not a low score; "
            "it is a categorical finding that the bands do not get to overrule."
        )
        if weighted_total is not None:
            headline += (
                f" The weighted total ({weighted_total:.2f} of "
                f"{scale_max:.2f}) is shown below for transparency but did not "
                "determine the verdict."
            )
    elif verdict is Verdict.INCOMPLETE:
        headline = (
            f"Verdict: INCOMPLETE — {len(unknown_dimensions)} of "
            f"{len(rubric.dimensions)} dimensions are unknown, above the limit "
            f"of {rubric.completeness.max_unknown_dimensions}. No score was "
            "computed; the missing information is listed below."
        )
    else:
        headline = (
            f"Verdict: {verdict.value.upper()} — weighted total "
            f"{weighted_total:.2f} of {scale_max:.2f}."
        )
    lines.append(headline)

    if assessment.archetype_id:
        archetype = patterns.archetype_by_id(assessment.archetype_id)
        label = archetype.label if archetype else "unrecognized archetype"
        lines.append(f"Archetype: {assessment.archetype_id} ({label})")

    if triggered_gates:
        lines.append("")
        lines.append("Gates triggered (the first decided the verdict):")
        for gate in triggered_gates:
            lines.append(
                f"  - {gate.gate_id} -> {gate.verdict.value} ({gate.detail})"
            )
            lines.append(f"      {gate.reason}")
            for anti_pattern_id in gate.matched_anti_pattern_ids:
                anti_pattern = patterns.anti_pattern_by_id(anti_pattern_id)
                if anti_pattern is not None:
                    lines.append(f"      {anti_pattern.label}.")
                    lines.append(f"      Instead: {anti_pattern.better_alternative}")

    if unknown_dimensions:
        lines.append("")
        lines.append(f"Unknown dimensions: {', '.join(unknown_dimensions)}")

    if contributions:
        lines.append("")
        lines.append(
            "Dimension detail (normalized score x effective weight = contribution):"
        )
        for item in contributions:
            lines.append(
                f"  - {item.label}: raw {item.raw_score} -> normalized "
                f"{item.normalized_score} x {item.effective_weight:.3f} = "
                f"{item.contribution:.3f}  [confidence: {item.confidence}]"
            )
            lines.append(f"      Evidence: {item.evidence}")

    return "\n".join(lines)


def score(
    assessment: Assessment,
    rubric: Rubric,
    patterns: Patterns,
    intake: RequestIntake | None = None,
) -> Outcome:
    """Turn an assessment into an auditable verdict.

    Args:
        assessment: The structured output of a single-shot assessment.
        rubric: Validated rubric supplying weights, bands, and gates.
        patterns: Validated pattern library supplying anti-pattern definitions.
        intake: The originating request, required only by gates with
            ``intake_field`` conditions. When omitted, those gates cannot fire —
            the scorer will not infer that a field is empty from its absence.

    Returns:
        An :class:`Outcome` whose ``weighted_total`` is reproducible by hand
        from the rubric's weights and whose ``explanation`` cites the evidence
        behind every line.
    """
    indexed, ignored_dimension_ids = _index_assessments(assessment, rubric)
    triggered_gates, ignored_anti_pattern_ids = _evaluate_gates(
        assessment, indexed, rubric, patterns, intake
    )

    unknown_dimensions = [
        dimension.id
        for dimension in rubric.dimensions
        if dimension.id not in indexed or indexed[dimension.id].score is None
    ]

    # A total is only meaningful when enough of the interview came back, and
    # only computable when at least one dimension has a score to weight.
    scorable = (
        len(unknown_dimensions) <= rubric.completeness.max_unknown_dimensions
        and len(unknown_dimensions) < len(rubric.dimensions)
    )

    if scorable:
        contributions, weighted_total = _compute_contributions(indexed, rubric)
    else:
        contributions, weighted_total = [], None

    if triggered_gates:
        # Gates arrive in precedence order, so the first one decides.
        verdict = triggered_gates[0].verdict
    elif not scorable:
        verdict = Verdict.INCOMPLETE
    else:
        assert weighted_total is not None  # scorable guarantees a total
        verdict = match_band(weighted_total, rubric)

    return Outcome(
        verdict=verdict,
        weighted_total=weighted_total,
        contributions=contributions,
        triggered_gates=triggered_gates,
        unknown_dimensions=unknown_dimensions,
        ignored_dimension_ids=ignored_dimension_ids,
        ignored_anti_pattern_ids=ignored_anti_pattern_ids,
        explanation=_build_explanation(
            verdict,
            weighted_total,
            contributions,
            triggered_gates,
            unknown_dimensions,
            rubric,
            patterns,
            assessment,
        ),
    )
