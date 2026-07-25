"""Deterministic assembly of a Measurement Contract.

> An agent may only be approved together with the definition of its own
> failure.

A ``go`` verdict is incomplete without pre-agreed success criteria. This module
turns an approved assessment into a :class:`~schemas.MeasurementContract`,
using the archetype template, the implementation-effort band, and the intake
metadata from ``contracts.yaml``.

**The skeleton is code; only the selection is model output.** The model
proposes which candidate metric fits and reports a baseline if the request
states one. Everything else — the measurement method, the success threshold,
the review date, the instrumentation plan, the decommission triggers — is
assembled here, from config, deterministically. A model that proposes a metric
outside the archetype's candidate list is overridden with the archetype default
and the proposal is recorded, the same way a hallucinated dimension id is
handled in ``scoring.py``.

Contracts are issued **only** on ``go``. Every other verdict returns ``None``:
there is nothing to measure an agent against if it was not approved.

The approval date is always **injected**, never read from the system clock, so
contract generation is pure and its date arithmetic is testable.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from config import ConfigError
from schemas import (
    Assessment,
    InstrumentationPlan,
    MeasurementContract,
    RequestIntake,
)
from scoring import Outcome, Verdict

__all__ = [
    "MetricTemplate",
    "ArchetypeContractTemplate",
    "ReviewHorizon",
    "DecommissionTrigger",
    "ContractsConfig",
    "ContractResult",
    "load_contracts_config",
    "issue_contract",
    "add_months",
    "CONTRACTS",
    "CONTRACTS_PATH",
]

PROJECT_ROOT = Path(__file__).resolve().parent
CONTRACTS_PATH = PROJECT_ROOT / "contracts.yaml"

ThresholdBasis = Literal["absolute", "relative_improvement"]
MetricDirection = Literal["higher_is_better", "lower_is_better"]


def add_months(start: date, months: int) -> date:
    """Return ``start`` advanced by ``months``, clamping the day of month.

    Written out rather than pulled from a dependency so the arithmetic is
    visible and testable: 31 January plus one month is 28 (or 29) February,
    not an error and not 3 March.
    """
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)
    days_in_month = (next_month_start - date(year, month, 1)).days
    return date(year, month, min(start.day, days_in_month))


class MetricTemplate(BaseModel):
    """One candidate primary metric."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    unit: str
    direction: MetricDirection
    threshold_basis: ThresholdBasis
    default_absolute_threshold: float
    default_target_improvement_pct: float
    typical_ramp_months: int
    measurement_method: str

    def success_threshold(self, baseline: float | None) -> float:
        """Compute the value that constitutes success.

        An ``absolute`` metric is a gain measured from nothing, so its target
        does not depend on a baseline. A ``relative_improvement`` metric
        improves on a measured baseline in its own improving direction, and
        falls back to the absolute default when no baseline was measured.
        """
        if self.threshold_basis == "absolute" or baseline is None:
            return self.default_absolute_threshold
        factor = self.default_target_improvement_pct / 100.0
        if self.direction == "higher_is_better":
            return round(baseline * (1.0 + factor), 4)
        return round(baseline * (1.0 - factor), 4)


class ArchetypeContractTemplate(BaseModel):
    """Which metrics are candidates for an archetype, and what else to emit."""

    model_config = ConfigDict(extra="forbid")

    id: str
    default_metric_id: str
    candidate_metric_ids: list[str] = Field(min_length=1)
    instrumentation_extra: dict[str, list[str]] = Field(default_factory=dict)


class ReviewHorizon(BaseModel):
    """Months from approval to first review, for one effort band."""

    model_config = ConfigDict(extra="forbid")

    id: str
    effort_min: int
    effort_max: int
    months: int = Field(gt=0)

    def covers(self, effort: int) -> bool:
        """Whether this band contains the given raw effort score."""
        return self.effort_min <= effort <= self.effort_max


class DecommissionTrigger(BaseModel):
    """One condition under which an approved agent is retired or adjusted."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    manual_assertion: bool
    description: str


class ContractsConfig(BaseModel):
    """The validated contents of ``contracts.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: str
    metrics: list[MetricTemplate] = Field(min_length=1)
    archetypes: list[ArchetypeContractTemplate] = Field(min_length=1)
    review_horizons: list[ReviewHorizon] = Field(min_length=1)
    instrumentation_baseline: dict[str, list[str]]
    decommission_triggers: list[DecommissionTrigger] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "ContractsConfig":
        metric_ids = {m.id for m in self.metrics}
        if len(metric_ids) != len(self.metrics):
            raise ValueError("duplicate metric ids in contracts.yaml")

        for template in self.archetypes:
            unknown = set(template.candidate_metric_ids) - metric_ids
            if unknown:
                raise ValueError(
                    f"archetype {template.id!r} lists candidate metrics that do "
                    f"not exist: {sorted(unknown)}"
                )
            if template.default_metric_id not in template.candidate_metric_ids:
                raise ValueError(
                    f"archetype {template.id!r} has default_metric_id "
                    f"{template.default_metric_id!r}, which is not one of its "
                    "own candidate_metric_ids"
                )
            for layer in template.instrumentation_extra:
                if layer not in self.instrumentation_baseline:
                    raise ValueError(
                        f"archetype {template.id!r} adds instrumentation for "
                        f"unknown layer {layer!r}; known layers are "
                        f"{sorted(self.instrumentation_baseline)}"
                    )

        bands = sorted(self.review_horizons, key=lambda h: h.effort_min)
        for previous, current in zip(bands, bands[1:]):
            if current.effort_min != previous.effort_max + 1:
                raise ValueError(
                    f"review_horizons must tile the effort scale with no gap or "
                    f"overlap, but {previous.id!r} ends at {previous.effort_max} "
                    f"and {current.id!r} starts at {current.effort_min}"
                )

        trigger_ids = {t.id for t in self.decommission_triggers}
        if len(trigger_ids) != len(self.decommission_triggers):
            raise ValueError("duplicate decommission trigger ids in contracts.yaml")
        return self

    def metric_by_id(self, metric_id: str) -> MetricTemplate | None:
        """Return the metric template with this id, or ``None``."""
        return next((m for m in self.metrics if m.id == metric_id), None)

    def archetype_by_id(self, archetype_id: str) -> ArchetypeContractTemplate | None:
        """Return the archetype contract template with this id, or ``None``."""
        return next((a for a in self.archetypes if a.id == archetype_id), None)

    def horizon_months(self, effort: int | None) -> int:
        """Months to the first review for a raw implementation-effort score.

        An unknown effort gets the SHORTEST horizon: reviewing too early is
        recoverable, reviewing too late is not.
        """
        if effort is None:
            return min(h.months for h in self.review_horizons)
        for horizon in self.review_horizons:
            if horizon.covers(effort):
                return horizon.months
        return min(h.months for h in self.review_horizons)

    @property
    def trigger_ids(self) -> list[str]:
        """Every decommission trigger id, in declared order."""
        return [t.id for t in self.decommission_triggers]

    def build_instrumentation(
        self, template: ArchetypeContractTemplate
    ) -> InstrumentationPlan:
        """Merge the archetype's extra instrumentation onto the baseline."""
        layers = {
            layer: list(items)
            for layer, items in self.instrumentation_baseline.items()
        }
        for layer, items in template.instrumentation_extra.items():
            layers.setdefault(layer, []).extend(items)
        return InstrumentationPlan(**layers)


class ContractResult(BaseModel):
    """A contract issue attempt and what was discarded on the way.

    ``ignored_metric_ids`` mirrors the hallucinated-id handling in
    ``scoring.py``: a model proposing a metric that is not a candidate for the
    archetype does not fail the request, but the proposal is not silently
    honoured either. It lives here rather than on :class:`~scoring.Outcome`
    because ``Outcome`` is produced by the pure scorer, which knows nothing
    about contracts.
    """

    model_config = ConfigDict(extra="forbid")

    contract: MeasurementContract | None = None
    ignored_metric_ids: list[str] = Field(default_factory=list)


def load_contracts_config(path: Path | str | None = None) -> ContractsConfig:
    """Load and validate the contract templates.

    Args:
        path: File to load; defaults to the project's ``contracts.yaml``.

    Returns:
        The validated :class:`ContractsConfig`.

    Raises:
        ConfigError: If the file is missing, unparseable, or invalid.
    """
    resolved = Path(path) if path is not None else CONTRACTS_PATH
    try:
        text = resolved.read_text()
    except OSError as exc:
        raise ConfigError(f"Could not read contracts config {resolved}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{resolved} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{resolved} must contain a YAML mapping at the top level")
    try:
        return ContractsConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid contracts config at {resolved}:\n{exc}") from exc


def _effort_score(outcome: Outcome) -> int | None:
    """Raw implementation_effort score from the outcome, or ``None``."""
    for contribution in outcome.contributions:
        if contribution.dimension_id == "implementation_effort":
            return contribution.raw_score
    return None


def issue_contract(
    outcome: Outcome,
    assessment: Assessment,
    intake: RequestIntake,
    approval_date: date,
    config: ContractsConfig | None = None,
    default_archetype_id: str = "summarization",
) -> ContractResult:
    """Assemble the Measurement Contract for an approved request.

    Args:
        outcome: The scored outcome. A contract is issued only for ``go``.
        assessment: The model's assessment, supplying the archetype and the
            metric proposal.
        intake: The originating request, supplying the business owner.
        approval_date: The date of approval. Injected, never read from the
            clock, so the review-date arithmetic stays testable.
        config: Contract templates; defaults to the loaded ``contracts.yaml``.
        default_archetype_id: Template to fall back on when the assessment
            names no archetype or an unrecognized one.

    Returns:
        A :class:`ContractResult`. Its ``contract`` is ``None`` for every
        verdict other than ``go``.
    """
    settings = config or CONTRACTS
    if outcome.verdict is not Verdict.GO:
        return ContractResult(contract=None)

    ignored_metric_ids: list[str] = []

    template = (
        settings.archetype_by_id(assessment.archetype_id)
        if assessment.archetype_id
        else None
    )
    if template is None:
        template = settings.archetype_by_id(default_archetype_id)
    if template is None:  # pragma: no cover - config validation prevents this
        raise ConfigError(
            f"no contract template for archetype {assessment.archetype_id!r} and "
            f"no fallback template {default_archetype_id!r}"
        )

    metric_id = template.default_metric_id
    proposed = assessment.proposed_metric_id
    if proposed:
        if proposed in template.candidate_metric_ids:
            metric_id = proposed
        else:
            ignored_metric_ids.append(proposed)

    metric = settings.metric_by_id(metric_id)
    if metric is None:  # pragma: no cover - config validation prevents this
        raise ConfigError(f"metric {metric_id!r} is not defined in contracts.yaml")

    baseline = assessment.stated_baseline_value
    horizon = settings.horizon_months(_effort_score(outcome))

    contract = MeasurementContract(
        primary_metric_id=metric.id,
        primary_metric_label=metric.label,
        primary_metric_unit=metric.unit,
        measurement_method=" ".join(metric.measurement_method.split()),
        baseline_value=baseline,
        baseline_is_measured=baseline is not None,
        success_threshold=metric.success_threshold(baseline),
        review_date=add_months(approval_date, horizon),
        business_owner=intake.business_owner,
        decommission_trigger_ids=settings.trigger_ids,
        instrumentation_plan=settings.build_instrumentation(template),
        archetype_id=template.id,
        approval_date=approval_date,
    )
    return ContractResult(contract=contract, ignored_metric_ids=ignored_metric_ids)


#: Validated at import time so a broken config fails immediately and loudly.
CONTRACTS: ContractsConfig = load_contracts_config()
