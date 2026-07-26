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
    MagnitudeDerivation,
    Patterns,
    Rubric,
    SensitivityDerivation,
    VolumeDerivation,
)
from schemas import Assessment, Confidence, DimensionAssessment, RequestIntake

__all__ = [
    "Verdict",
    "TriggeredGate",
    "FiredCondition",
    "UnsupportedAntiPattern",
    "normalize_for_quote_check",
    "quote_is_supported",
    "derive_scores",
    "derive_fallback_scores",
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


def normalize_for_quote_check(text: str) -> str:
    """Lower-case and collapse all whitespace, for verbatim-quote comparison.

    Deliberately forgiving about presentation and strict about words: a model
    that re-wraps a line or changes capitalisation is still quoting, while one
    that swaps a word is paraphrasing and must not pass.
    """
    return " ".join(text.lower().split())


def quote_is_supported(quote: str, source: str) -> bool:
    """Whether ``quote`` appears verbatim in ``source``.

    Whitespace- and case-insensitive substring check. An empty or whitespace-only
    quote is never supported — "I found this pattern but cannot show you where"
    is precisely the claim this check exists to reject.
    """
    if not quote or not quote.strip():
        return False
    return normalize_for_quote_check(quote) in normalize_for_quote_check(source)


class UnsupportedAntiPattern(BaseModel):
    """An anti-pattern match whose quote could not be found in the request.

    Reported rather than silently dropped: a fabricated quote is a finding
    about the model, and hiding it would make the same failure invisible next
    time.
    """

    model_config = ConfigDict(extra="forbid")

    anti_pattern_id: str
    quote: str
    reason: str


class FiredCondition(BaseModel):
    """One condition inside a gate that was actually met.

    Recorded individually because confirmation is a property of the CONDITION,
    not of the gate (ADR-028): a gate can hold a reproducible condition and an
    unreliable one in the same ``any_of``, and which of them fired is what
    decides whether the verdict stands on its own.

    Attributes:
        kind: The condition's ``type`` from the config.
        detail: What in this assessment met it.
        requires_human_confirmation: Resolved from the condition's own flag, or
            from its type's default when the config leaves it unset.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    detail: str
    requires_human_confirmation: bool


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
    #: Every condition in this gate that was met, in declaration order.
    fired_conditions: list[FiredCondition] = Field(default_factory=list)
    #: True when at least one condition that fired was a dimension threshold or
    #: an intake-field predicate — both deterministic given the assessment.
    #:
    #: INFORMATIONAL ONLY since ADR-028. This used to decide whether the verdict
    #: needed human confirmation, on the reasoning that a threshold is
    #: deterministic given the assessment. It is — and the agreement study showed
    #: that deterministic is not the same as reliable: the threshold gate this
    #: flag waved through was the least reproducible decision in the system.
    #: Confirmation now follows :attr:`FiredCondition.requires_human_confirmation`
    #: on the conditions that actually fired.
    deterministic_basis: bool = False
    #: The verbatim quotes the anti-pattern conditions relied on, so a human
    #: confirming the verdict can see the evidence without opening the payload.
    supporting_quotes: list[str] = Field(default_factory=list)


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
    #: Anti-pattern matches discarded because their quote was not found in the
    #: request. Visible rather than silent — a fabricated quote is a finding.
    unsupported_anti_patterns: list[UnsupportedAntiPattern] = Field(
        default_factory=list
    )
    #: Dimensions computed from a structured intake field rather than scored by
    #: the model. Reported so a reader can see which numbers were judgements.
    derived_dimensions: list[str] = Field(default_factory=list)
    #: Dimensions the assessment left unknown and the intake form was able to
    #: compute — the fallback branch. Kept separate from ``derived_dimensions``
    #: because the two answer different questions: that list is "the model was
    #: never asked", this one is "the model refused and the form covered it".
    fallback_derived_dimensions: list[str] = Field(default_factory=list)
    #: Total rubric weight sitting on unknown dimensions — the unit the
    #: completeness budget is actually measured in.
    unknown_weight: float = 0.0
    #: Which completeness rule was violated, or ``None`` if the assessment was
    #: complete enough to score.
    completeness_violation: str | None = None
    #: True when the verdict rests on a hard-block anti-pattern gate and nothing
    #: deterministic. Such a verdict is a RECOMMENDATION awaiting human
    #: confirmation, not a rejection.
    requires_human_confirmation: bool = False
    confirmation_reason: str | None = None
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


def derive_scores(
    rubric: Rubric, intake: RequestIntake | None
) -> dict[str, tuple[int, str]]:
    """Dimensions this intake determines outright, as ``id -> (score, why)``.

    Pure and side-effect free, so ``assess.py`` can ask the same question
    before building the prompt that ``score()`` answers afterwards. A dimension
    that appears here is not asked of the model at all — neither its anchors
    nor its schema entry are sent.

    **Authoritative derivations only.** A fallback derivation
    (:class:`~config.MagnitudeDerivation`) is deliberately absent: it fires only
    where the assessment left the dimension unknown, so the dimension must
    still be put to the model and must still appear in the prompt. Excluding it
    here is what keeps those two facts from contradicting each other — see
    :func:`derive_fallback_scores`.
    """
    if intake is None:
        return {}
    derived: dict[str, tuple[int, str]] = {}
    for dimension in rubric.dimensions:
        rule = dimension.derivation
        if rule is None or rule.is_fallback:
            continue
        if isinstance(rule, VolumeDerivation):
            source_value = intake.instances_per_year
        elif isinstance(rule, SensitivityDerivation):
            source_value = getattr(intake.data_sensitivity, "value", None)
        else:  # pragma: no cover - the union is closed
            continue
        score_value = rule.derive(source_value)
        if score_value is not None:
            derived[dimension.id] = (score_value, rule.describe(source_value))
    return derived


def derive_fallback_scores(
    rubric: Rubric, intake: RequestIntake | None
) -> dict[str, tuple[int, str, Confidence]]:
    """Dimensions this intake can compute, as ``id -> (score, why, confidence)``.

    The complement of :func:`derive_scores`: these derivations do NOT replace an
    assessed score, they fill one the assessment left unknown. The motivating
    case is ``business_value``, where the rubric used to instruct the model to
    "estimate the order of magnitude from the process described" — an
    instruction two independent scorers followed to two different answers on 11
    of 30 cases (ADR-026). The instruction is now to refuse; this is what
    catches the refusal and turns it into arithmetic where the intake form
    carries the numbers.

    Unlike an authoritative derivation the confidence varies, because the
    denominations are not equally good: hours or currency computed from a stated
    per-instance figure is ``medium``, a bare count of instances is ``low``.
    """
    if intake is None:
        return {}
    derived: dict[str, tuple[int, str, Confidence]] = {}
    for dimension in rubric.dimensions:
        rule = dimension.derivation
        if rule is None or not rule.is_fallback:
            continue
        if not isinstance(rule, MagnitudeDerivation):  # pragma: no cover
            continue
        computed = rule.derive(
            instances_per_year=intake.instances_per_year,
            minutes_per_instance=intake.minutes_per_instance,
            cost_per_instance=intake.cost_per_instance,
        )
        if computed is not None:
            score_value, why, confidence = computed
            derived[dimension.id] = (score_value, why, Confidence(confidence))
    return derived


def _apply_intake_derivations(
    indexed: dict[str, DimensionAssessment],
    rubric: Rubric,
    intake: RequestIntake | None,
) -> list[str]:
    """Replace model scores with deterministic ones where the intake states the fact.

    Some dimensions are not judgement calls once the requester has answered a
    direct question. If the intake form says the process runs three times a
    week, ``process_frequency`` is arithmetic, not assessment — and asking a
    model to re-infer it can only introduce error. The mapping lives in
    ``rubric.yaml`` beside the anchors, because it IS the anchor semantics.

    A derivation that yields ``None`` — the field was left blank, or the
    classification is ``unknown`` — leaves the model's score in place. The form
    is never mandatory, so a blank simply returns the dimension to model
    scoring.

    Mutates ``indexed`` in place and returns the ids that were derived.
    """
    derived: list[str] = []
    for dimension_id, (score_value, why) in derive_scores(rubric, intake).items():
        indexed[dimension_id] = DimensionAssessment(
            dimension_id=dimension_id,
            score=score_value,
            evidence=why,
            confidence=Confidence.HIGH,
        )
        derived.append(dimension_id)
    return derived


def _apply_fallback_derivations(
    indexed: dict[str, DimensionAssessment],
    rubric: Rubric,
    intake: RequestIntake | None,
) -> list[str]:
    """Fill unknown dimensions the intake can compute, leaving assessed ones alone.

    The asymmetry with :func:`_apply_intake_derivations` is the whole point. An
    authoritative derivation overwrites: if the form says the process runs 180
    times a day, the model's opinion about frequency is noise. A fallback
    derivation defers: a magnitude the request actually states is better
    evidence than one computed from two form fields, so this only runs where the
    assessment recorded ``score: None``.

    Mutates ``indexed`` in place and returns the ids that were filled.
    """
    filled: list[str] = []
    for dimension_id, (score_value, why, confidence) in derive_fallback_scores(
        rubric, intake
    ).items():
        existing = indexed.get(dimension_id)
        if existing is not None and existing.score is not None:
            continue
        indexed[dimension_id] = DimensionAssessment(
            dimension_id=dimension_id,
            score=score_value,
            evidence=why,
            confidence=confidence,
        )
        filled.append(dimension_id)
    return filled


def _evaluate_gates(
    assessment: Assessment,
    indexed: dict[str, DimensionAssessment],
    rubric: Rubric,
    patterns: Patterns,
    intake: RequestIntake | None,
) -> tuple[list[TriggeredGate], list[str], list[UnsupportedAntiPattern]]:
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
    unsupported: list[UnsupportedAntiPattern] = []
    matched_all: list[str] = []
    matched_hard_blocks: list[str] = []
    quote_by_id: dict[str, str] = {}

    # The evidentiary bar for an anti-pattern is higher than for a dimension
    # score, because the cost of the error is higher: a wrong dimension moves
    # the total by tenths and is compensable, a wrong anti-pattern fires a gate
    # and cannot be outvoted. Every match must carry a quote that actually
    # appears in the request, or it is discarded. See ADR-020.
    source_text = ""
    if intake is not None:
        source_text = "\n".join(
            part
            for part in (
                intake.request_text,
                intake.process_description,
                intake.stated_benefit or "",
            )
            if part
        )

    for match in assessment.anti_pattern_matches:
        anti_pattern = patterns.anti_pattern_by_id(match.anti_pattern_id)
        if anti_pattern is None:
            ignored_anti_patterns.append(match.anti_pattern_id)
            continue
        if intake is None:
            unsupported.append(
                UnsupportedAntiPattern(
                    anti_pattern_id=match.anti_pattern_id,
                    quote=match.quote,
                    reason=(
                        "no intake was supplied, so the quote could not be "
                        "verified against the request"
                    ),
                )
            )
            continue
        if not quote_is_supported(match.quote, source_text):
            unsupported.append(
                UnsupportedAntiPattern(
                    anti_pattern_id=match.anti_pattern_id,
                    quote=match.quote,
                    reason=(
                        "empty quote"
                        if not match.quote.strip()
                        else "quote does not appear in the request text"
                    ),
                )
            )
            continue
        matched_all.append(match.anti_pattern_id)
        quote_by_id[match.anti_pattern_id] = match.quote
        if anti_pattern.hard_block:
            matched_hard_blocks.append(match.anti_pattern_id)

    triggered: list[TriggeredGate] = []
    for gate in rubric.gates_by_precedence:
        fired: list[FiredCondition] = []
        contributing_anti_patterns: list[str] = []
        deterministic_basis = False
        for condition in gate.any_of:
            detail: str | None = None
            if isinstance(condition, DimensionThresholdCondition):
                entry = indexed.get(condition.dimension)
                if entry is None or entry.score is None:
                    continue
                if condition.is_met(entry.score):
                    detail = condition.describe(entry.score)
                    deterministic_basis = True
            elif isinstance(condition, AntiPatternCondition):
                hits = condition.matches(matched_hard_blocks, matched_all)
                if hits:
                    contributing_anti_patterns.extend(hits)
                    detail = "anti-pattern(s) matched: " + ", ".join(hits)
            elif isinstance(condition, IntakeFieldCondition):
                if intake is None:
                    continue
                if condition.is_met(getattr(intake, condition.field, None)):
                    detail = condition.describe()
                    deterministic_basis = True
            if detail is not None:
                fired.append(
                    FiredCondition(
                        kind=condition.type,
                        detail=detail,
                        requires_human_confirmation=condition.confirmation_required,
                    )
                )
        if fired:
            triggered.append(
                TriggeredGate(
                    gate_id=gate.id,
                    verdict=Verdict(gate.verdict),
                    precedence=gate.precedence,
                    reason=" ".join(gate.reason.split()),
                    detail="; ".join(c.detail for c in fired),
                    matched_anti_pattern_ids=contributing_anti_patterns,
                    fired_conditions=fired,
                    deterministic_basis=deterministic_basis,
                    supporting_quotes=[
                        quote_by_id[i]
                        for i in contributing_anti_patterns
                        if i in quote_by_id
                    ],
                )
            )
    return triggered, ignored_anti_patterns, unsupported


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
    unknown_weight: float,
    violation: str | None,
    unsupported: list[UnsupportedAntiPattern],
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
            f"Verdict: INCOMPLETE — {violation or 'the assessment is not complete enough to score'}. No score was computed; the missing information is listed below."
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
            lines.append(f"  - {gate.gate_id} -> {gate.verdict.value}")
            for condition in gate.fired_conditions:
                basis = (
                    "needs human confirmation"
                    if condition.requires_human_confirmation
                    else "stands on its own"
                )
                lines.append(
                    f"      condition {condition.kind} [{basis}]: {condition.detail}"
                )
            lines.append(f"      {gate.reason}")
            for quote in gate.supporting_quotes:
                lines.append(f'      Quoted from the request: "{quote}"')
            for anti_pattern_id in gate.matched_anti_pattern_ids:
                anti_pattern = patterns.anti_pattern_by_id(anti_pattern_id)
                if anti_pattern is not None:
                    lines.append(f"      {anti_pattern.label}.")
                    lines.append(f"      Instead: {anti_pattern.better_alternative}")

    if unknown_dimensions:
        lines.append("")
        lines.append(
            f"Unknown dimensions: {', '.join(unknown_dimensions)} "
            f"({unknown_weight:.2f} of weight, budget "
            f"{rubric.completeness.max_unknown_weight:.2f})"
        )
        if violation:
            lines.append(f"  Rule violated -> {violation}")

    if unsupported:
        lines.append("")
        lines.append(
            "Anti-pattern matches DISCARDED — the quote was not found in the "
            "request, so no gate fired on them:"
        )
        for item in unsupported:
            lines.append(f'  - {item.anti_pattern_id}: "{item.quote}" ({item.reason})')

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
    # Deterministic derivations run BEFORE the gates, so a gate that keys on a
    # derived dimension sees the derived value rather than the model's guess.
    derived_dimensions = _apply_intake_derivations(indexed, rubric, intake)
    # Fallbacks run next, and still before the gates and the completeness rule:
    # a magnitude computed from the form is a score like any other, and the
    # dimension must be known or unknown before anything reads it.
    fallback_dimensions = _apply_fallback_derivations(indexed, rubric, intake)
    triggered_gates, ignored_anti_pattern_ids, unsupported = _evaluate_gates(
        assessment, indexed, rubric, patterns, intake
    )

    unknown_dimensions = [
        dimension.id
        for dimension in rubric.dimensions
        if dimension.id not in indexed or indexed[dimension.id].score is None
    ]

    # Completeness is measured in WEIGHT, not in a count of dimensions: the
    # uncertainty of a verdict is proportional to the weight that is missing,
    # not to the number of empty slots (ADR-022). A second, absolute rule
    # covers dimensions that must never be unknown — chiefly the gate
    # conditions, where an unknown silently disables a blocking rule.
    unknown_set = set(unknown_dimensions)
    unknown_weight = round(
        sum(d.weight for d in rubric.dimensions if d.id in unknown_set),
        TOTAL_PRECISION,
    )
    budget = rubric.completeness.max_unknown_weight
    missing_required = [
        i for i in rubric.completeness.never_unknown if i in unknown_set
    ]

    completeness_violation: str | None = None
    if missing_required:
        completeness_violation = (
            "never_unknown: "
            + ", ".join(missing_required)
            + " must always carry a score"
            + (
                " (each is a gate condition, and a gate whose dimension is "
                "unknown cannot fire)"
                if any(i != "business_value" for i in missing_required)
                else ""
            )
        )
    elif unknown_weight > budget + 1e-9:
        completeness_violation = (
            f"max_unknown_weight: {unknown_weight:.2f} of weight is unknown, "
            f"above the budget of {budget:.2f}"
        )
    elif not unknown_set:
        pass
    if len(unknown_dimensions) >= len(rubric.dimensions):
        completeness_violation = "every dimension is unknown; nothing to weight"

    scorable = completeness_violation is None

    if scorable:
        contributions, weighted_total = _compute_contributions(indexed, rubric)
    else:
        contributions, weighted_total = [], None

    requires_confirmation = False
    confirmation_reason: str | None = None
    if triggered_gates:
        # Gates arrive in precedence order, so the first one decides.
        deciding = triggered_gates[0]
        verdict = deciding.verdict
        # Confirmation follows the CONDITIONS THAT FIRED, not the gate (ADR-028).
        # ALL of them must require it: one condition that stands on its own is
        # sufficient basis for the verdict, even where another that also fired
        # would need review. `all()` over a non-empty list, and the list is
        # non-empty by construction — a gate with no fired condition is not in
        # this list.
        needing = [c for c in deciding.fired_conditions if c.requires_human_confirmation]
        if len(needing) == len(deciding.fired_conditions):
            requires_confirmation = True
            described = "; ".join(f"{c.kind} ({c.detail})" for c in needing)
            quoted = "; ".join(f'"{q}"' for q in deciding.supporting_quotes)
            confirmation_reason = (
                f"{verdict.value} rests on {len(needing)} condition(s) of gate "
                f"{deciding.gate_id} that are judgements rather than settled "
                f"facts about the request: {described}. "
                + (f"Quoted from the request: {quoted}. " if quoted else "")
                + "Confirm the finding before refusing the request."
            )
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
        unsupported_anti_patterns=unsupported,
        derived_dimensions=derived_dimensions,
        fallback_derived_dimensions=fallback_dimensions,
        unknown_weight=unknown_weight,
        completeness_violation=completeness_violation,
        requires_human_confirmation=requires_confirmation,
        confirmation_reason=confirmation_reason,
        explanation=_build_explanation(
            verdict,
            weighted_total,
            contributions,
            triggered_gates,
            unknown_dimensions,
            unknown_weight,
            completeness_violation,
            unsupported,
            rubric,
            patterns,
            assessment,
        ),
    )
