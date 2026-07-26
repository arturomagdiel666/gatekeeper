"""Loading and validation of Gatekeeper's YAML configuration.

``rubric.yaml`` and ``patterns.yaml`` are the tunable source of truth for how a
request is scored: weights, anchors, verdict bands, and the blocking gates all
live there so a domain expert can retune the Hub's intake criteria without
touching Python, and so the same request can be run against several rubric
configurations without a code change. The assessment prompt is generated from
these files too, so there is no second copy of the anchors to drift.

That flexibility is only safe if a malformed config can never reach the scorer,
so this module validates aggressively at load time and fails with a specific,
actionable message. Enforced invariants:

* dimension, archetype, anti-pattern, and gate ids are unique
* dimension weights sum to 1.0 (within ``WEIGHT_EPSILON``)
* every dimension has exactly one anchor per level on the declared scale, and
  declares the single ``axis`` it measures
* ``direction`` is one of the two known values
* verdict bands tile the scale exactly — no gap, no overlap, full coverage —
  and only the highest band may include its upper bound
* verdict bands contain only ``go`` and ``no_go``; ``not_ai`` is a gate and
  ``incomplete`` is a refusal to score, so neither may be reached by a band
* every gate condition names a dimension, an anti-pattern, or an intake field
  that actually exists, and every threshold lies on the scale
* a blocking gate forces only ``no_go`` or ``not_ai`` — never ``go``
* the unknown-dimension limit cannot exceed the number of dimensions

``RUBRIC`` and ``PATTERNS`` are loaded, validated, and cross-checked against
each other at import time, so a broken config breaks loudly and immediately
rather than halfway through an assessment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = [
    "ConfigError",
    "Scale",
    "Dimension",
    "VerdictBand",
    "VolumeDerivation",
    "SensitivityDerivation",
    "MagnitudeBand",
    "MagnitudeDenomination",
    "MagnitudeDerivation",
    "DimensionThresholdCondition",
    "AntiPatternCondition",
    "IntakeFieldCondition",
    "BlockingGate",
    "Completeness",
    "Rubric",
    "Archetype",
    "AntiPattern",
    "Patterns",
    "load_rubric",
    "load_patterns",
    "validate_cross_references",
    "RUBRIC",
    "PATTERNS",
    "RUBRIC_PATH",
    "PATTERNS_PATH",
]

PROJECT_ROOT = Path(__file__).resolve().parent
RUBRIC_PATH = PROJECT_ROOT / "rubric.yaml"
PATTERNS_PATH = PROJECT_ROOT / "patterns.yaml"

#: Tolerance for the "weights must sum to 1.0" check, so that a config written
#: with ordinary decimals is not rejected over binary floating-point error.
WEIGHT_EPSILON = 1e-6

Direction = Literal["higher_is_better", "lower_is_better"]

#: A blocking gate may only stop a request, never wave one through.
GateVerdict = Literal["no_go", "not_ai"]

Comparison = Literal["at_least", "at_most"]

#: Predicates available to an intake-field gate condition.
IntakePredicate = Literal["is_empty", "is_present"]

#: Intake fields a gate is allowed to test. Kept explicit so a typo in the
#: config is caught at load time rather than silently never firing.
INTAKE_GATE_FIELDS = frozenset(
    {
        "business_owner",
        "requesting_area",
        "process_description",
        "stated_benefit",
        "request_text",
    }
)


class ConfigError(RuntimeError):
    """Raised when a configuration file is missing, unparseable, or invalid."""


def _duplicates(values: list[str]) -> list[str]:
    """Return the values that appear more than once, in first-seen order."""
    seen: set[str] = set()
    dupes: list[str] = []
    for value in values:
        if value in seen and value not in dupes:
            dupes.append(value)
        seen.add(value)
    return dupes


class Scale(BaseModel):
    """The integer range every dimension is scored on."""

    model_config = ConfigDict(extra="forbid")

    min: int
    max: int

    @model_validator(mode="after")
    def _check_order(self) -> "Scale":
        if self.max <= self.min:
            raise ValueError(
                f"scale.max ({self.max}) must be greater than scale.min ({self.min})"
            )
        return self

    @property
    def levels(self) -> list[int]:
        """Every valid score on this scale, ascending."""
        return list(range(self.min, self.max + 1))


class VolumeBand(BaseModel):
    """One band of the annualized-volume to score mapping."""

    model_config = ConfigDict(extra="forbid")

    below_per_year: float
    score: int


class VolumeDerivation(BaseModel):
    """Derive a score from the intake's stated process volume."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["intake_volume"]
    bands: list[VolumeBand] = Field(min_length=1)
    otherwise: int

    #: Authoritative: this derivation replaces the model's score outright, and
    #: the dimension is not put to the model at all.
    is_fallback: bool = False

    def derive(self, instances_per_year: float | None) -> int | None:
        """Score for an annualized volume, or ``None`` if none was stated."""
        if instances_per_year is None:
            return None
        for band in sorted(self.bands, key=lambda b: b.below_per_year):
            if instances_per_year < band.below_per_year:
                return band.score
        return self.otherwise

    def describe(self, instances_per_year: float) -> str:
        """Explain the derivation for the outcome."""
        return (
            f"Derived from the intake form: {instances_per_year:,.0f} instances "
            "a year."
        )


class SensitivityDerivation(BaseModel):
    """Derive a score from the intake's declared data classification."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["intake_sensitivity"]
    mapping: dict[str, int]

    is_fallback: bool = False

    def derive(self, sensitivity: str | None) -> int | None:
        """Score for a classification, or ``None`` if unmapped or unknown."""
        if sensitivity is None:
            return None
        return self.mapping.get(sensitivity)

    def describe(self, sensitivity: str) -> str:
        """Explain the derivation for the outcome."""
        return f"Derived from the intake form: data classified {sensitivity!r}."


#: Which intake quantity feeds a magnitude denomination. ``volume_only`` needs
#: no second field: it scores the count of instances itself, which is the
#: weakest of the three denominations and is why it carries low confidence.
MagnitudeSource = Literal["minutes_per_instance", "cost_per_instance", "volume_only"]


class MagnitudeBand(BaseModel):
    """One band of an annualized-magnitude to score mapping."""

    model_config = ConfigDict(extra="forbid")

    below: float
    score: int


class MagnitudeDenomination(BaseModel):
    """One denomination a magnitude may be expressed and banded in.

    ``unit`` is descriptive and appears in the evidence string; ``from`` names
    the intake quantity that feeds it, and is the only part Python switches on.
    """

    model_config = ConfigDict(extra="forbid")

    unit: str
    from_: MagnitudeSource = Field(alias="from")
    confidence: Literal["low", "medium", "high"]
    bands: list[MagnitudeBand] = Field(min_length=1)
    otherwise: int

    def score_for(self, annualized_value: float) -> int:
        """The level whose band contains this annualized value."""
        for band in sorted(self.bands, key=lambda b: b.below):
            if annualized_value < band.below:
                return band.score
        return self.otherwise


class MagnitudeDerivation(BaseModel):
    """Compute an annualized magnitude from the intake, when none was stated.

    A **fallback** derivation, and the only one of the three. The other two
    replace the model's score outright because the intake states the fact
    directly — a volume is a volume. A magnitude is not stated directly by any
    single field: it is the product of two, and only where the request itself
    named no figure does computing it beat reading it. So this derivation
    applies ``when_unknown`` and never overwrites a score the assessment made.

    Denominations are tried in declaration order and the first that can be
    computed wins, so the priority is visible in ``rubric.yaml`` rather than
    encoded here (ADR-026).
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["intake_magnitude"]
    applies: Literal["when_unknown"]
    currency_code: str = "USD"
    denominations: list[MagnitudeDenomination] = Field(min_length=1)

    @property
    def is_fallback(self) -> bool:
        """Always true — see the class docstring."""
        return True

    def derive(
        self,
        *,
        instances_per_year: float | None,
        minutes_per_instance: float | None,
        cost_per_instance: float | None,
    ) -> tuple[int, str, str] | None:
        """Compute ``(score, evidence, confidence)``, or ``None`` if it cannot.

        Returning ``None`` is the fourth branch of the resolution order in the
        dimension's ``scoring_rule``: no magnitude was stated, and the intake
        does not carry enough to compute one. The caller leaves the dimension
        unknown, which for a ``never_unknown`` dimension yields ``incomplete``.

        The evidence string carries the arithmetic in full, so the level can be
        re-derived by hand from the request form without reading any code.
        """
        if instances_per_year is None:
            return None
        for denomination in self.denominations:
            if denomination.from_ == "minutes_per_instance":
                if minutes_per_instance is None:
                    continue
                value = instances_per_year * minutes_per_instance / 60.0
                arithmetic = (
                    f"{instances_per_year:,.0f} instances a year x "
                    f"{minutes_per_instance:g} minutes each / 60 = "
                    f"{value:,.0f} person-hours a year"
                )
            elif denomination.from_ == "cost_per_instance":
                if cost_per_instance is None:
                    continue
                value = instances_per_year * cost_per_instance
                arithmetic = (
                    f"{instances_per_year:,.0f} instances a year x "
                    f"{cost_per_instance:g} {self.currency_code} each = "
                    f"{value:,.0f} {self.currency_code} a year"
                )
            else:  # volume_only
                value = instances_per_year
                arithmetic = (
                    f"{value:,.0f} instances a year, counted as cases affected "
                    "— the intake stated neither a per-instance duration nor a "
                    "per-instance cost, so this is a count of instances rather "
                    "than a measure of benefit"
                )
            score_value = denomination.score_for(value)
            return (
                score_value,
                (
                    "Computed from the intake form because the request stated no "
                    f"magnitude: {arithmetic} -> level {score_value} on the "
                    f"{denomination.unit} denomination."
                ),
                denomination.confidence,
            )
        return None


DimensionDerivation = Annotated[
    VolumeDerivation | SensitivityDerivation | MagnitudeDerivation,
    Field(discriminator="source"),
]


class Dimension(BaseModel):
    """One scored dimension of the rubric.

    ``axis`` states the single construct this dimension measures. It exists to
    make "one dimension, one axis" checkable by a reader rather than a matter
    of trust: a dimension whose anchors drift into a second construct will
    visibly contradict its own axis line.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    axis: str
    #: Optional procedure for arriving at a score, rendered into the assessment
    #: prompt directly beneath the axis. It exists because ``description`` is
    #: NOT rendered — it is documentation for whoever tunes the rubric — so a
    #: rule the model has to follow had nowhere prompt-visible to live except
    #: ``axis``, which must stay a statement of the single construct measured if
    #: "one dimension, one axis" is to remain checkable by a reader (ADR-026).
    scoring_rule: str | None = None
    description: str
    weight: float = Field(gt=0.0, le=1.0)
    direction: Direction
    #: Optional rule for computing this dimension from a structured intake
    #: field instead of asking the model. Present only where the intake carries
    #: the fact directly; the mapping lives here beside the anchors because it
    #: IS the anchor semantics.
    derivation: DimensionDerivation | None = None
    anchors: dict[int, str]


class VerdictBand(BaseModel):
    """A range of weighted totals mapping to a verdict.

    Matches when ``lower <= total < upper``, or ``lower <= total <= upper`` when
    ``upper_inclusive`` is set (permitted only on the highest band).

    Only ``go`` and ``no_go`` are accepted here: ``not_ai`` must be reachable
    solely through a gate, and ``incomplete`` is a refusal to score rather than
    a band. Widening this ``Literal`` would silently break that guarantee.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["go", "no_go"]
    lower: float
    upper: float
    upper_inclusive: bool = False

    @model_validator(mode="after")
    def _check_order(self) -> "VerdictBand":
        if self.upper <= self.lower:
            raise ValueError(
                f"verdict band {self.verdict!r}: upper ({self.upper}) must be "
                f"greater than lower ({self.lower})"
            )
        return self


class DimensionThresholdCondition(BaseModel):
    """A gate condition on one dimension's raw score."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["dimension_threshold"]
    dimension: str
    comparison: Comparison
    threshold: int

    def is_met(self, raw_score: int) -> bool:
        """Return whether a raw score satisfies this condition."""
        if self.comparison == "at_least":
            return raw_score >= self.threshold
        return raw_score <= self.threshold

    def describe(self, raw_score: int) -> str:
        """Explain, for the outcome, why this condition fired."""
        comparison = "at least" if self.comparison == "at_least" else "at most"
        return f"{self.dimension} scored {raw_score}, {comparison} {self.threshold}"


class AntiPatternCondition(BaseModel):
    """A gate condition met when particular anti-patterns were matched.

    Either ``hard_block_any`` (any anti-pattern flagged ``hard_block`` in
    ``patterns.yaml``, minus ``exclude_ids``) or an explicit
    ``anti_pattern_ids`` list — exactly one of the two.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["anti_pattern"]
    hard_block_any: bool = False
    anti_pattern_ids: list[str] = Field(default_factory=list)
    exclude_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_exactly_one_form(self) -> "AntiPatternCondition":
        if self.hard_block_any and self.anti_pattern_ids:
            raise ValueError(
                "an anti_pattern condition sets both hard_block_any and "
                "anti_pattern_ids; use exactly one (add exclude_ids to "
                "hard_block_any if you need to carve ids out)"
            )
        if not self.hard_block_any and not self.anti_pattern_ids:
            raise ValueError(
                "an anti_pattern condition must set either hard_block_any: "
                "true or a non-empty anti_pattern_ids list"
            )
        if self.exclude_ids and not self.hard_block_any:
            raise ValueError(
                "exclude_ids only applies to hard_block_any conditions"
            )
        return self

    def matches(self, matched_hard_blocks: list[str], matched_all: list[str]) -> list[str]:
        """Return the matched anti-pattern ids that satisfy this condition."""
        if self.hard_block_any:
            excluded = set(self.exclude_ids)
            return [i for i in matched_hard_blocks if i not in excluded]
        wanted = set(self.anti_pattern_ids)
        return [i for i in matched_all if i in wanted]


class IntakeFieldCondition(BaseModel):
    """A gate condition on request metadata rather than on a scored dimension.

    Needed for facts about the request form itself — most importantly whether a
    business owner was named — which are not judgements and so have no place on
    a 1-5 scale.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["intake_field"]
    field: str
    predicate: IntakePredicate

    def is_met(self, value: object) -> bool:
        """Evaluate the predicate against an intake field's value."""
        present = value is not None and str(value).strip() != ""
        return not present if self.predicate == "is_empty" else present

    def describe(self) -> str:
        """Explain, for the outcome, why this condition fired."""
        wording = "is empty or absent" if self.predicate == "is_empty" else "is present"
        return f"intake field {self.field} {wording}"


GateCondition = Annotated[
    DimensionThresholdCondition | AntiPatternCondition | IntakeFieldCondition,
    Field(discriminator="type"),
]


class BlockingGate(BaseModel):
    """A categorical condition that forces a verdict, overriding the bands.

    Fires when *any* of its conditions is met. A gate can never force a ``go``:
    gates exist to stop a request, not to wave one through. When several fire,
    the lowest ``precedence`` decides the verdict and every gate that fired is
    still reported; ties are broken by declaration order in the config.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    verdict: GateVerdict
    precedence: int
    reason: str
    any_of: list[GateCondition] = Field(min_length=1)


class Completeness(BaseModel):
    """How much of the assessment may be missing and still yield a verdict.

    Measured in WEIGHT, not in a count of dimensions: the uncertainty of a
    verdict is proportional to the weight that is missing, not to the number of
    empty slots. See ADR-022.

    ``never_unknown`` is a separate, absolute rule. It exists mainly because a
    gate whose dimension is null cannot fire — an unknown there silently
    disables a blocking rule and FAILS OPEN.
    """

    model_config = ConfigDict(extra="forbid")

    max_unknown_weight: float = Field(ge=0.0, le=1.0)
    never_unknown: list[str] = Field(default_factory=list)


class Rubric(BaseModel):
    """The validated contents of ``rubric.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: str
    scale: Scale
    dimensions: list[Dimension] = Field(min_length=1)
    verdict_bands: list[VerdictBand] = Field(min_length=1)
    #: May be empty: removing every gate leaves pure band behaviour.
    blocking_gates: list[BlockingGate] = Field(default_factory=list)
    completeness: Completeness

    @model_validator(mode="after")
    def _validate_rubric(self) -> "Rubric":
        dupes = _duplicates([d.id for d in self.dimensions])
        if dupes:
            raise ValueError(f"duplicate dimension ids: {dupes}")

        total = sum(d.weight for d in self.dimensions)
        if abs(total - 1.0) > WEIGHT_EPSILON:
            raise ValueError(
                f"dimension weights must sum to 1.0 but sum to {total!r} "
                f"(off by {total - 1.0:+.6f}). Weights: "
                + ", ".join(f"{d.id}={d.weight}" for d in self.dimensions)
            )

        expected_levels = set(self.scale.levels)
        for dimension in self.dimensions:
            actual = set(dimension.anchors)
            if actual != expected_levels:
                missing = sorted(expected_levels - actual)
                extra = sorted(actual - expected_levels)
                raise ValueError(
                    f"dimension {dimension.id!r} must have exactly one anchor "
                    f"per level {sorted(expected_levels)}; "
                    f"missing={missing}, unexpected={extra}"
                )

        self._validate_bands()
        self._validate_gates(known_levels=expected_levels)

        known_dimension_ids = {d.id for d in self.dimensions}
        unknown_required = set(self.completeness.never_unknown) - known_dimension_ids
        if unknown_required:
            raise ValueError(
                f"completeness.never_unknown names dimensions that do not "
                f"exist: {sorted(unknown_required)}"
            )

        # A dimension used as a gate condition MUST be in never_unknown, or the
        # gate fails open when the model leaves it null.
        gated = {
            condition.dimension
            for gate in self.blocking_gates
            for condition in gate.any_of
            if isinstance(condition, DimensionThresholdCondition)
        }
        unguarded = gated - set(self.completeness.never_unknown)
        if unguarded:
            raise ValueError(
                f"dimension(s) {sorted(unguarded)} are gate conditions but are "
                "not in completeness.never_unknown. A gate whose dimension is "
                "unknown cannot fire, so this would silently disable a "
                "blocking rule — it fails open."
            )

        # NOT enforced here: "a dimension with a fallback derivation must be in
        # never_unknown". It is true of the shipped config and it is what makes
        # an uncomputable magnitude surface as `incomplete` rather than
        # renormalize away — but as a load-time invariant it forbids a rubric
        # with `never_unknown: []`, which is exactly the configuration the
        # completeness tests need in order to exercise the WEIGHT rule on its
        # own (ADR-022). The property is pinned by a test against the shipped
        # rubric instead, where it costs no expressiveness.
        return self

    def _validate_gates(self, known_levels: set[int]) -> None:
        """Require every gate to name real dimensions and in-scale thresholds."""
        dupes = _duplicates([g.id for g in self.blocking_gates])
        if dupes:
            raise ValueError(f"duplicate blocking gate ids: {dupes}")

        known_ids = {d.id for d in self.dimensions}
        for gate in self.blocking_gates:
            for condition in gate.any_of:
                if isinstance(condition, DimensionThresholdCondition):
                    if condition.dimension not in known_ids:
                        raise ValueError(
                            f"blocking gate {gate.id!r} names dimension "
                            f"{condition.dimension!r}, which is not a declared "
                            f"dimension. Known ids: {sorted(known_ids)}"
                        )
                    if condition.threshold not in known_levels:
                        raise ValueError(
                            f"blocking gate {gate.id!r} has threshold "
                            f"{condition.threshold}, outside the scale "
                            f"{sorted(known_levels)}"
                        )
                elif isinstance(condition, IntakeFieldCondition):
                    if condition.field not in INTAKE_GATE_FIELDS:
                        raise ValueError(
                            f"blocking gate {gate.id!r} tests intake field "
                            f"{condition.field!r}, which is not a gateable "
                            f"intake field. Known: {sorted(INTAKE_GATE_FIELDS)}"
                        )

    def _validate_bands(self) -> None:
        """Require the bands to tile the scale with no gap or overlap."""
        bands = sorted(self.verdict_bands, key=lambda b: b.lower)
        if bands[0].lower != float(self.scale.min):
            raise ValueError(
                f"the lowest verdict band starts at {bands[0].lower} but the "
                f"scale starts at {self.scale.min}; totals below that would "
                "match no band"
            )
        for previous, current in zip(bands, bands[1:]):
            if current.lower < previous.upper:
                raise ValueError(
                    f"verdict bands overlap: {previous.verdict!r} ends at "
                    f"{previous.upper} but {current.verdict!r} starts at "
                    f"{current.lower}"
                )
            if current.lower > previous.upper:
                raise ValueError(
                    f"verdict bands leave a gap: {previous.verdict!r} ends at "
                    f"{previous.upper} but {current.verdict!r} starts at "
                    f"{current.lower}; totals in between would match no band"
                )
            if previous.upper_inclusive:
                raise ValueError(
                    f"only the highest verdict band may set upper_inclusive, "
                    f"but {previous.verdict!r} does; it would overlap "
                    f"{current.verdict!r} at exactly {previous.upper}"
                )
        highest = bands[-1]
        if highest.upper != float(self.scale.max):
            raise ValueError(
                f"the highest verdict band ends at {highest.upper} but the "
                f"scale ends at {self.scale.max}; totals above that would "
                "match no band"
            )
        if not highest.upper_inclusive:
            raise ValueError(
                f"the highest verdict band ({highest.verdict!r}) must set "
                f"upper_inclusive: true, otherwise a perfect total of "
                f"{self.scale.max} would match no band"
            )

    def dimension_by_id(self, dimension_id: str) -> Dimension | None:
        """Return the dimension with this id, or ``None`` if there is none."""
        return next((d for d in self.dimensions if d.id == dimension_id), None)

    @property
    def gates_by_precedence(self) -> list[BlockingGate]:
        """Gates ordered by precedence, ties broken by declaration order."""
        return sorted(self.blocking_gates, key=lambda gate: gate.precedence)

    @property
    def dimension_ids(self) -> list[str]:
        """Every dimension id, in declared order."""
        return [d.id for d in self.dimensions]

    def normalize(self, dimension: Dimension, raw_score: int) -> int:
        """Convert a raw score so that higher always means better.

        A ``lower_is_better`` dimension is flipped about the scale
        (``min + max - raw``), so that on a 1-5 scale a raw 1 becomes 5. This
        is the step that makes weighting meaningful across dimensions that
        point in opposite directions.
        """
        if dimension.direction == "higher_is_better":
            return raw_score
        return self.scale.min + self.scale.max - raw_score


class Archetype(BaseModel):
    """A canonical shape an internal AI agent can take."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    typical_data_needs: str
    typical_risks: list[str]
    signals: list[str]
    notes_on_roi: str


class AntiPattern(BaseModel):
    """A signal that a request is not an AI problem."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    #: Things a reader can point at IN THE REQUEST TEXT. Not descriptions of
    #: the domain: resemblance to a category is not evidence, and treating it
    #: as evidence is what caused the false positives measured in ADR-020.
    signals: list[str]
    hard_block: bool
    better_alternative: str
    #: Reviewer guidance that is deliberately NOT a signal — background used to
    #: judge a match after one of the signals has already fired.
    notes: str | None = None


class Patterns(BaseModel):
    """The validated contents of ``patterns.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: str
    archetypes: list[Archetype] = Field(min_length=1)
    anti_patterns: list[AntiPattern] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_patterns(self) -> "Patterns":
        for label, values in (
            ("archetype", [a.id for a in self.archetypes]),
            ("anti-pattern", [a.id for a in self.anti_patterns]),
        ):
            dupes = _duplicates(values)
            if dupes:
                raise ValueError(f"duplicate {label} ids: {dupes}")
        return self

    def archetype_by_id(self, archetype_id: str) -> Archetype | None:
        """Return the archetype with this id, or ``None`` if there is none."""
        return next((a for a in self.archetypes if a.id == archetype_id), None)

    def anti_pattern_by_id(self, anti_pattern_id: str) -> AntiPattern | None:
        """Return the anti-pattern with this id, or ``None`` if there is none."""
        return next((a for a in self.anti_patterns if a.id == anti_pattern_id), None)

    @property
    def archetype_ids(self) -> list[str]:
        """Every archetype id, in declared order."""
        return [a.id for a in self.archetypes]

    @property
    def hard_block_ids(self) -> list[str]:
        """Ids of every anti-pattern that fires a hard-block gate condition."""
        return [a.id for a in self.anti_patterns if a.hard_block]


def validate_cross_references(rubric: Rubric, patterns: Patterns) -> None:
    """Check references that span the two config files.

    A gate naming an anti-pattern that does not exist would simply never fire —
    a silent failure of exactly the kind this project refuses to ship.

    Raises:
        ConfigError: If a gate references an unknown anti-pattern id.
    """
    known = {a.id for a in patterns.anti_patterns}
    for gate in rubric.blocking_gates:
        for condition in gate.any_of:
            if not isinstance(condition, AntiPatternCondition):
                continue
            for anti_pattern_id in [
                *condition.anti_pattern_ids,
                *condition.exclude_ids,
            ]:
                if anti_pattern_id not in known:
                    raise ConfigError(
                        f"blocking gate {gate.id!r} references anti-pattern "
                        f"{anti_pattern_id!r}, which is not defined in "
                        f"patterns.yaml. Known ids: {sorted(known)}"
                    )


def _load_yaml(path: Path) -> dict:
    """Read and parse a YAML file into a dict, or raise :class:`ConfigError`."""
    try:
        text = path.read_text()
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path} must contain a YAML mapping at the top level, got "
            f"{type(data).__name__}"
        )
    return data


def load_rubric(path: Path | str | None = None) -> Rubric:
    """Load and validate a rubric file.

    Args:
        path: Rubric to load; defaults to the project's ``rubric.yaml``. Pass an
            alternative here to score the same request against a different
            rubric configuration without changing any code.

    Returns:
        The validated :class:`Rubric`.

    Raises:
        ConfigError: If the file is missing, unparseable, or violates any
            invariant. The message names the file and the specific problem.
    """
    resolved = Path(path) if path is not None else RUBRIC_PATH
    data = _load_yaml(resolved)
    try:
        return Rubric.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid rubric config at {resolved}:\n{exc}") from exc


def load_patterns(path: Path | str | None = None) -> Patterns:
    """Load and validate a patterns file.

    Args:
        path: Patterns file to load; defaults to the project's
            ``patterns.yaml``.

    Returns:
        The validated :class:`Patterns`.

    Raises:
        ConfigError: If the file is missing, unparseable, or invalid.
    """
    resolved = Path(path) if path is not None else PATTERNS_PATH
    data = _load_yaml(resolved)
    try:
        return Patterns.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid patterns config at {resolved}:\n{exc}") from exc


#: Validated at import time so a broken config fails immediately and loudly.
RUBRIC: Rubric = load_rubric()
PATTERNS: Patterns = load_patterns()
validate_cross_references(RUBRIC, PATTERNS)
