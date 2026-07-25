"""Review an approved agent against its Measurement Contract.

Pure policy. **No LLM anywhere in this module** — a function that recommends
decommissioning somebody's agent must be able to show its arithmetic, and be
reproducible by anyone who disagrees with it. Every threshold lives in
``review_policy.yaml``; the code here only computes indicators and applies the
declared conditions.

The four instrumentation layers exist because an agent can fail in four
independent ways and a usage chart hides three of them:

* **usage** — is anyone using it?
* **quality** — does it work when they do?
* **business** — did the number it was approved against actually move?
* **cost** — is it worth what it costs to run?

Two failure signatures get their own explicit triggers because both look like
success on an adoption dashboard:

* **high usage, low quality** — people use it because they must, and correct
  its output every time; the correction work never appears in usage numbers.
* **curiosity adoption** — lots of people tried it once. Interest, not value.

Missing telemetry is a finding, never a pass. Any field may be ``None``, and a
condition that cannot be evaluated returns ``insufficient_telemetry`` rather
than being read as "fine".
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from config import ConfigError
from contracts import add_months
from schemas import MeasurementContract

__all__ = [
    "Recommendation",
    "ObservedMetrics",
    "ReviewIndicators",
    "TriggeredCondition",
    "UnevaluatedCondition",
    "ReviewOutcome",
    "ReviewPolicy",
    "load_review_policy",
    "review",
    "EVALUATORS",
    "POLICY",
    "REVIEW_POLICY_PATH",
]

PROJECT_ROOT = Path(__file__).resolve().parent
REVIEW_POLICY_PATH = PROJECT_ROOT / "review_policy.yaml"

TriggerRecommendation = Literal["retire", "adjust"]

#: What an evaluator concluded. ``insufficient`` means the telemetry needed to
#: decide was missing — never conflate it with ``not_fired``.
Status = Literal["fired", "not_fired", "insufficient"]


class Recommendation(str, Enum):
    """What the review recommends doing with the agent."""

    CONTINUE = "continue"
    ADJUST = "adjust"
    RETIRE = "retire"
    INSUFFICIENT_TELEMETRY = "insufficient_telemetry"


class ObservedMetrics(BaseModel):
    """What was actually observed, across the four instrumentation layers.

    Every field is optional. A ``None`` is not zero and not "fine" — it means
    the telemetry was never emitted, which the review reports rather than
    guesses around.

    The two manual assertions at the bottom cannot be computed from telemetry.
    They are modelled as explicit booleans so a reviewer must answer them:
    leaving one as ``None`` blocks the review instead of quietly reading as
    "no".
    """

    model_config = ConfigDict(extra="forbid")

    # --- context -------------------------------------------------------------
    months_since_launch: int | None = None
    window_months: float = Field(default=1.0, gt=0)

    # --- usage ---------------------------------------------------------------
    active_users: int | None = None
    addressable_population: int | None = None
    sessions: int | None = None
    task_starts: int | None = None
    repeat_users: int | None = None
    time_to_first_value_days: float | None = None

    # --- quality -------------------------------------------------------------
    task_completion_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    override_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    mid_task_abandonment_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    # --- business ------------------------------------------------------------
    primary_metric_value: float | None = None

    # --- cost ----------------------------------------------------------------
    inference_cost: float | None = None
    licence_cost: float | None = None
    maintenance_hours: float | None = None
    maintenance_hourly_rate: float | None = None

    # --- manual assertions ---------------------------------------------------
    owner_absent: bool | None = None
    superseded_by_platform: bool | None = None
    #: Defaults to False rather than None: if nobody has said a fix is underway,
    #: the safe reading is that none is. This makes the quality trigger MORE
    #: likely to fire, which is the conservative direction.
    remediation_in_flight: bool = False

    @property
    def total_cost(self) -> float | None:
        """Total cost over the window, or ``None`` if no cost was reported."""
        parts = [self.inference_cost, self.licence_cost]
        maintenance = None
        if self.maintenance_hours is not None and self.maintenance_hourly_rate is not None:
            maintenance = self.maintenance_hours * self.maintenance_hourly_rate
        parts.append(maintenance)
        known = [p for p in parts if p is not None]
        return sum(known) if known else None


class ReviewIndicators(BaseModel):
    """The computed numbers behind the recommendation.

    Reported whether or not anything fired, so a reviewer can see what the
    policy saw.
    """

    model_config = ConfigDict(extra="forbid")

    adoption_rate: float | None = None
    repeat_usage_ratio: float | None = None
    successful_tasks: float | None = None
    total_cost: float | None = None
    cost_per_successful_task: float | None = None
    value_per_task: float | None = None


class TriggeredCondition(BaseModel):
    """One decommission condition that fired."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str
    recommendation: TriggerRecommendation
    detail: str
    observed: str


class UnevaluatedCondition(BaseModel):
    """One condition that could not be evaluated, and what was missing."""

    model_config = ConfigDict(extra="forbid")

    trigger_id: str
    missing: str


class ReviewOutcome(BaseModel):
    """The result of reviewing an agent against its contract."""

    model_config = ConfigDict(extra="forbid")

    recommendation: Recommendation
    triggered_conditions: list[TriggeredCondition] = Field(default_factory=list)
    unevaluated_conditions: list[UnevaluatedCondition] = Field(default_factory=list)
    indicators: ReviewIndicators = Field(default_factory=ReviewIndicators)
    next_review_date: date | None = None
    rationale: str = ""

    @property
    def triggered_ids(self) -> list[str]:
        """Ids of the conditions that fired."""
        return [c.trigger_id for c in self.triggered_conditions]


class Thresholds(BaseModel):
    """Policy thresholds."""

    model_config = ConfigDict(extra="forbid")

    adoption_floor: float
    ramp_months: int
    completion_rate_floor: float
    override_rate_ceiling: float
    repeat_usage_floor: float
    high_usage_adoption_floor: float


class NextReview(BaseModel):
    """How far ahead the next review is scheduled."""

    model_config = ConfigDict(extra="forbid")

    standard_interval_months: int = Field(gt=0)
    remediation_interval_months: int = Field(gt=0)


class TriggerPolicy(BaseModel):
    """One decommission condition's policy settings."""

    model_config = ConfigDict(extra="forbid")

    id: str
    recommendation: TriggerRecommendation
    enabled: bool = True
    detail: str


class ReviewPolicy(BaseModel):
    """The validated contents of ``review_policy.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: str
    thresholds: Thresholds
    next_review: NextReview
    monetary_conversions: dict[str, float]
    triggers: list[TriggerPolicy] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "ReviewPolicy":
        ids = [t.id for t in self.triggers]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate trigger ids in review_policy.yaml")
        return self

    @property
    def enabled_triggers(self) -> list[TriggerPolicy]:
        """Triggers that are switched on."""
        return [t for t in self.triggers if t.enabled]


def load_review_policy(path: Path | str | None = None) -> ReviewPolicy:
    """Load and validate the review policy.

    Args:
        path: File to load; defaults to the project's ``review_policy.yaml``.

    Returns:
        The validated :class:`ReviewPolicy`.

    Raises:
        ConfigError: If the file is missing, unparseable, or invalid.
    """
    resolved = Path(path) if path is not None else REVIEW_POLICY_PATH
    try:
        text = resolved.read_text()
    except OSError as exc:
        raise ConfigError(f"Could not read review policy {resolved}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{resolved} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{resolved} must contain a YAML mapping at the top level")
    try:
        return ReviewPolicy.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid review policy at {resolved}:\n{exc}") from exc


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def _compute_indicators(
    contract: MeasurementContract, observed: ObservedMetrics, policy: ReviewPolicy
) -> ReviewIndicators:
    """Compute the four indicators, leaving any that cannot be computed None."""
    adoption_rate = None
    if observed.active_users is not None and observed.addressable_population:
        adoption_rate = observed.active_users / observed.addressable_population

    repeat_usage_ratio = None
    if observed.repeat_users is not None and observed.active_users:
        repeat_usage_ratio = observed.repeat_users / observed.active_users

    successful_tasks = None
    if observed.task_starts is not None and observed.task_completion_rate is not None:
        successful_tasks = observed.task_starts * observed.task_completion_rate

    total_cost = observed.total_cost
    cost_per_successful_task = None
    if total_cost is not None and successful_tasks:
        cost_per_successful_task = total_cost / successful_tasks

    value_per_task = None
    conversion = policy.monetary_conversions.get(contract.primary_metric_unit)
    if (
        conversion is not None
        and observed.primary_metric_value is not None
        and observed.task_starts
    ):
        window_value = observed.primary_metric_value * conversion * observed.window_months
        value_per_task = window_value / observed.task_starts

    return ReviewIndicators(
        adoption_rate=adoption_rate,
        repeat_usage_ratio=repeat_usage_ratio,
        successful_tasks=successful_tasks,
        total_cost=total_cost,
        cost_per_successful_task=cost_per_successful_task,
        value_per_task=value_per_task,
    )


# ---------------------------------------------------------------------------
# Trigger evaluators
#
# Each returns (status, detail). Thresholds come from the policy; nothing here
# is hard-coded, so a threshold change is a YAML edit.
# ---------------------------------------------------------------------------

EvaluatorResult = tuple[Status, str]
Evaluator = Callable[
    [MeasurementContract, ObservedMetrics, ReviewIndicators, ReviewPolicy],
    EvaluatorResult,
]


def _usage_floor_not_met(contract, observed, indicators, policy) -> EvaluatorResult:
    if indicators.adoption_rate is None:
        return "insufficient", "active_users and addressable_population"
    if observed.months_since_launch is None:
        return "insufficient", "months_since_launch"
    floor = policy.thresholds.adoption_floor
    if observed.months_since_launch < policy.thresholds.ramp_months:
        return (
            "not_fired",
            f"still in ramp ({observed.months_since_launch} of "
            f"{policy.thresholds.ramp_months} months)",
        )
    if indicators.adoption_rate < floor:
        return (
            "fired",
            f"adoption {indicators.adoption_rate:.0%} is below the {floor:.0%} "
            f"floor, {observed.months_since_launch} months after launch",
        )
    return "not_fired", f"adoption {indicators.adoption_rate:.0%} meets the floor"


def _cost_exceeds_value(contract, observed, indicators, policy) -> EvaluatorResult:
    if indicators.cost_per_successful_task is None:
        return "insufficient", "cost fields, task_starts and task_completion_rate"
    if indicators.value_per_task is None:
        return (
            "insufficient",
            f"primary_metric_value, or no monetary conversion for unit "
            f"{contract.primary_metric_unit!r}",
        )
    if indicators.cost_per_successful_task > indicators.value_per_task:
        return (
            "fired",
            f"cost per successful task {indicators.cost_per_successful_task:.2f} "
            f"exceeds value per task {indicators.value_per_task:.2f}",
        )
    return (
        "not_fired",
        f"cost per successful task {indicators.cost_per_successful_task:.2f} is "
        f"within value per task {indicators.value_per_task:.2f}",
    )


def _quality_below_threshold(contract, observed, indicators, policy) -> EvaluatorResult:
    if observed.task_completion_rate is None and observed.override_rate is None:
        return "insufficient", "task_completion_rate and override_rate"
    if observed.remediation_in_flight:
        return "not_fired", "remediation is in flight"
    reasons = []
    floor = policy.thresholds.completion_rate_floor
    ceiling = policy.thresholds.override_rate_ceiling
    if observed.task_completion_rate is not None and observed.task_completion_rate < floor:
        reasons.append(
            f"completion {observed.task_completion_rate:.0%} below the {floor:.0%} floor"
        )
    if observed.override_rate is not None and observed.override_rate > ceiling:
        reasons.append(
            f"override {observed.override_rate:.0%} above the {ceiling:.0%} ceiling"
        )
    if reasons:
        return "fired", "; ".join(reasons)
    return "not_fired", "completion and override rates are within policy"


def _business_metric_missed(contract, observed, indicators, policy) -> EvaluatorResult:
    if observed.primary_metric_value is None:
        return "insufficient", f"primary_metric_value ({contract.primary_metric_id})"
    threshold = contract.success_threshold
    value = observed.primary_metric_value
    missed = (
        value < threshold
        if contract.primary_metric_direction == "higher_is_better"
        else value > threshold
    )
    comparison = "below" if contract.primary_metric_direction == "higher_is_better" else "above"
    if missed:
        return (
            "fired",
            f"{contract.primary_metric_label} is {value:g} "
            f"{contract.primary_metric_unit}, {comparison} the agreed threshold "
            f"of {threshold:g}",
        )
    return (
        "not_fired",
        f"{contract.primary_metric_label} is {value:g}, meeting the threshold "
        f"of {threshold:g}",
    )


def _high_usage_low_quality(contract, observed, indicators, policy) -> EvaluatorResult:
    if indicators.adoption_rate is None:
        return "insufficient", "active_users and addressable_population"
    if observed.override_rate is None:
        return "insufficient", "override_rate"
    high = policy.thresholds.high_usage_adoption_floor
    ceiling = policy.thresholds.override_rate_ceiling
    if indicators.adoption_rate >= high and observed.override_rate > ceiling:
        return (
            "fired",
            f"adoption {indicators.adoption_rate:.0%} looks healthy while the "
            f"override rate is {observed.override_rate:.0%}, above the "
            f"{ceiling:.0%} ceiling — people are correcting it every time",
        )
    return "not_fired", "usage and override rate are not in this pattern"


def _curiosity_adoption(contract, observed, indicators, policy) -> EvaluatorResult:
    if indicators.adoption_rate is None:
        return "insufficient", "active_users and addressable_population"
    if indicators.repeat_usage_ratio is None:
        return "insufficient", "repeat_users"
    high = policy.thresholds.high_usage_adoption_floor
    floor = policy.thresholds.repeat_usage_floor
    if indicators.adoption_rate >= high and indicators.repeat_usage_ratio < floor:
        return (
            "fired",
            f"adoption {indicators.adoption_rate:.0%} with only "
            f"{indicators.repeat_usage_ratio:.0%} of users returning, below the "
            f"{floor:.0%} floor — interest, not value",
        )
    return "not_fired", "repeat usage is not in this pattern"


def _owner_absent(contract, observed, indicators, policy) -> EvaluatorResult:
    if observed.owner_absent is None:
        return "insufficient", "owner_absent (a reviewer must assert this)"
    if observed.owner_absent:
        return "fired", f"the named owner ({contract.business_owner}) is no longer in place"
    return "not_fired", f"{contract.business_owner} remains the owner"


def _superseded_by_platform(contract, observed, indicators, policy) -> EvaluatorResult:
    if observed.superseded_by_platform is None:
        return "insufficient", "superseded_by_platform (a reviewer must assert this)"
    if observed.superseded_by_platform:
        return "fired", "a licensed platform capability now covers this natively"
    return "not_fired", "no licensed capability covers this yet"


#: Registry mapping trigger id to its evaluator. A test asserts these keys
#: match the trigger ids in review_policy.yaml exactly, so a trigger cannot be
#: declared and then silently never evaluated, nor evaluated without config.
EVALUATORS: dict[str, Evaluator] = {
    "usage_floor_not_met": _usage_floor_not_met,
    "cost_exceeds_value": _cost_exceeds_value,
    "quality_below_threshold": _quality_below_threshold,
    "business_metric_missed": _business_metric_missed,
    "high_usage_low_quality": _high_usage_low_quality,
    "curiosity_adoption": _curiosity_adoption,
    "owner_absent": _owner_absent,
    "superseded_by_platform": _superseded_by_platform,
}


def _build_rationale(
    recommendation: Recommendation,
    triggered: list[TriggeredCondition],
    unevaluated: list[UnevaluatedCondition],
    indicators: ReviewIndicators,
    contract: MeasurementContract,
    next_review_date: date | None,
) -> str:
    """Assemble the plain-language account of the recommendation."""
    lines: list[str] = []
    if recommendation is Recommendation.RETIRE:
        lines.append(
            f"Recommendation: RETIRE. {len(triggered)} condition(s) fired, at "
            "least one of which is sufficient on its own to decommission."
        )
    elif recommendation is Recommendation.ADJUST:
        lines.append(
            f"Recommendation: ADJUST. {len(triggered)} condition(s) fired, none "
            "of them fatal. Bounded remediation is expected before the next "
            f"review on {next_review_date}."
        )
    elif recommendation is Recommendation.INSUFFICIENT_TELEMETRY:
        lines.append(
            "Recommendation: INSUFFICIENT TELEMETRY. The instrumentation needed "
            "to decide is missing, so no judgement is offered. Missing telemetry "
            "is a finding in itself — it must be in place before "
            f"{next_review_date}."
        )
    else:
        lines.append(
            "Recommendation: CONTINUE. No decommission condition fired and "
            f"every condition could be evaluated. Next review {next_review_date}."
        )

    lines.append("")
    lines.append(
        f"Contract: {contract.primary_metric_label} "
        f"({contract.primary_metric_unit}), threshold "
        f"{contract.success_threshold:g}, owner {contract.business_owner}, "
        f"review date {contract.review_date}."
    )

    if triggered:
        lines.append("")
        lines.append("Conditions fired:")
        for condition in triggered:
            lines.append(
                f"  - {condition.trigger_id} [{condition.recommendation}] — "
                f"{condition.observed}"
            )
            lines.append(f"      {condition.detail}")

    if unevaluated:
        lines.append("")
        lines.append("Could not be evaluated (missing telemetry):")
        for condition in unevaluated:
            lines.append(f"  - {condition.trigger_id} — needs {condition.missing}")

    lines.append("")
    lines.append("Indicators:")
    for label, value, fmt in (
        ("adoption rate", indicators.adoption_rate, "{:.1%}"),
        ("repeat-usage ratio", indicators.repeat_usage_ratio, "{:.1%}"),
        ("successful tasks", indicators.successful_tasks, "{:.0f}"),
        ("total cost", indicators.total_cost, "{:.2f}"),
        ("cost per successful task", indicators.cost_per_successful_task, "{:.2f}"),
        ("value per task", indicators.value_per_task, "{:.2f}"),
    ):
        rendered = fmt.format(value) if value is not None else "not available"
        lines.append(f"  - {label}: {rendered}")

    return "\n".join(lines)


def review(
    contract: MeasurementContract,
    observed: ObservedMetrics,
    policy: ReviewPolicy | None = None,
) -> ReviewOutcome:
    """Evaluate an approved agent against its Measurement Contract.

    Args:
        contract: The contract the agent was approved under.
        observed: What the instrumentation actually reported.
        policy: Thresholds and trigger settings; defaults to the loaded
            ``review_policy.yaml``.

    Returns:
        A :class:`ReviewOutcome` whose ``rationale`` shows every indicator and
        every condition considered. The next review date is derived from the
        contract's own review date, so no system clock is consulted.
    """
    settings = policy or POLICY
    indicators = _compute_indicators(contract, observed, settings)

    triggered: list[TriggeredCondition] = []
    unevaluated: list[UnevaluatedCondition] = []
    for trigger in settings.enabled_triggers:
        evaluator = EVALUATORS.get(trigger.id)
        if evaluator is None:  # pragma: no cover - guarded by a test
            raise ConfigError(
                f"review_policy.yaml declares trigger {trigger.id!r} but "
                "review.py has no evaluator for it"
            )
        status, detail = evaluator(contract, observed, indicators, settings)
        if status == "fired":
            triggered.append(
                TriggeredCondition(
                    trigger_id=trigger.id,
                    recommendation=trigger.recommendation,
                    detail=" ".join(trigger.detail.split()),
                    observed=detail,
                )
            )
        elif status == "insufficient":
            unevaluated.append(
                UnevaluatedCondition(trigger_id=trigger.id, missing=detail)
            )

    # Precedence: a definite retire is actionable and more telemetry will not
    # unfire it, so it outranks everything. But an unevaluable condition must
    # never read as "fine" — it outranks adjust, because recommending a small
    # fix while blind to part of the picture is exactly the failure this
    # module exists to prevent.
    if any(c.recommendation == "retire" for c in triggered):
        recommendation = Recommendation.RETIRE
    elif unevaluated:
        recommendation = Recommendation.INSUFFICIENT_TELEMETRY
    elif triggered:
        recommendation = Recommendation.ADJUST
    else:
        recommendation = Recommendation.CONTINUE

    if recommendation is Recommendation.RETIRE:
        next_review_date = None
    elif recommendation is Recommendation.CONTINUE:
        next_review_date = add_months(
            contract.review_date, settings.next_review.standard_interval_months
        )
    else:
        next_review_date = add_months(
            contract.review_date, settings.next_review.remediation_interval_months
        )

    return ReviewOutcome(
        recommendation=recommendation,
        triggered_conditions=triggered,
        unevaluated_conditions=unevaluated,
        indicators=indicators,
        next_review_date=next_review_date,
        rationale=_build_rationale(
            recommendation,
            triggered,
            unevaluated,
            indicators,
            contract,
            next_review_date,
        ),
    )


#: Validated at import time so a broken policy fails immediately and loudly.
POLICY: ReviewPolicy = load_review_policy()
