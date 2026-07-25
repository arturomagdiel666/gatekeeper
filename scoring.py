"""Deterministic scoring: rubric plus assessment in, verdict out.

Pure functions only — no LLM calls, no file I/O, no clock, no randomness. The
model supplies per-dimension scores and evidence; every number in the result is
computed here, from weights that live in ``rubric.yaml``. That split is what
makes a verdict defensible: asked "why No-Go?", you can point at the exact line
of arithmetic and the exact sentence of evidence behind it.

The order of evaluation matters and is deliberate:

1. **Gates first.** A hard-block anti-pattern, or a high enough score on the
   gate dimension, produces ``not_ai`` and overrides everything. Gates are
   positive findings — learning that a SQL query already solves the problem is
   enough to stop, even mid-interview — so they are checked before the
   completeness rule.
2. **Completeness next.** Too many unknown dimensions yields ``incomplete``
   rather than a verdict computed from a mostly-empty interview.
3. **Bands last.** The weighted total is matched against the rubric's bands,
   which only ever produce ``go`` or ``no_go``.

A use case can therefore score 4.6 and still come out ``not_ai``. That is the
entire point of the product: if Not-AI were the bottom band, exactly the cases
Gatekeeper exists to catch would pass as Go.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from config import Patterns, Rubric
from schemas import Assessment, DimensionAssessment

__all__ = [
    "Verdict",
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
        triggered_gates: Ids of the Not-AI gates that fired, empty if none.
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
    triggered_gates: list[str] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    ignored_dimension_ids: list[str] = Field(default_factory=list)
    ignored_anti_pattern_ids: list[str] = Field(default_factory=list)
    explanation: str = ""


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
) -> tuple[list[str], list[str]]:
    """Evaluate the Not-AI gates.

    Returns the ids of the gates that fired, plus any matched anti-pattern ids
    that are not in the patterns file.
    """
    triggered: list[str] = []
    ignored_anti_patterns: list[str] = []

    for anti_pattern_id in assessment.anti_pattern_ids:
        anti_pattern = patterns.anti_pattern_by_id(anti_pattern_id)
        if anti_pattern is None:
            ignored_anti_patterns.append(anti_pattern_id)
            continue
        if rubric.not_ai_gate.hard_block_anti_patterns and anti_pattern.hard_block:
            triggered.append(f"anti_pattern:{anti_pattern_id}")

    gate = rubric.not_ai_gate
    gate_entry = indexed.get(gate.dimension_id)
    if gate_entry is not None and gate_entry.score is not None:
        if gate_entry.score >= gate.min_raw_score:
            triggered.append(f"{gate.dimension_id}>={gate.min_raw_score}")

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
    triggered_gates: list[str],
    unknown_dimensions: list[str],
    rubric: Rubric,
    patterns: Patterns,
    assessment: Assessment,
) -> str:
    """Assemble the human-readable account of how the verdict was reached."""
    lines: list[str] = []
    scale_max = rubric.scale.max

    if verdict is Verdict.NOT_AI:
        headline = (
            f"Verdict: NOT_AI — overridden by "
            f"{len(triggered_gates)} gate(s). This is not a low score; it is a "
            "finding that the problem should not be solved with AI."
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
        lines.append("Gates triggered:")
        for gate_id in triggered_gates:
            if gate_id.startswith("anti_pattern:"):
                anti_pattern = patterns.anti_pattern_by_id(
                    gate_id.split(":", 1)[1]
                )
                if anti_pattern is not None:
                    lines.append(f"  - {gate_id} — {anti_pattern.label}")
                    lines.append(f"      Instead: {anti_pattern.better_alternative}")
                    continue
            dimension = rubric.dimension_by_id(rubric.not_ai_gate.dimension_id)
            label = dimension.label if dimension else rubric.not_ai_gate.dimension_id
            lines.append(
                f"  - {gate_id} — {label} scored at or above the Not-AI "
                "threshold: a non-AI solution would do the job."
            )

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


def score(assessment: Assessment, rubric: Rubric, patterns: Patterns) -> Outcome:
    """Turn an interview assessment into an auditable verdict.

    Args:
        assessment: The structured output of a discovery interview.
        rubric: Validated rubric supplying weights, bands, and gates.
        patterns: Validated pattern library supplying anti-pattern definitions.

    Returns:
        An :class:`Outcome` whose ``weighted_total`` is reproducible by hand
        from the rubric's weights and whose ``explanation`` cites the evidence
        behind every line.
    """
    indexed, ignored_dimension_ids = _index_assessments(assessment, rubric)
    triggered_gates, ignored_anti_pattern_ids = _evaluate_gates(
        assessment, indexed, rubric, patterns
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
        verdict = Verdict.NOT_AI
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
