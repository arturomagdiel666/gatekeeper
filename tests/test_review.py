"""Tests for the review and sunset recommender. Pure policy, no model, no clock."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from schemas import MeasurementContract
from review import (
    EVALUATORS,
    POLICY,
    REVIEW_POLICY_PATH,
    ObservedMetrics,
    Recommendation,
    load_review_policy,
    review,
)

# A contract on an hours-based metric, so value per task is computable
# (hours_per_month has a monetary conversion in review_policy.yaml).
CONTRACT = MeasurementContract(
    primary_metric_id="hours_reclaimed_per_month",
    primary_metric_label="Hours reclaimed per month",
    primary_metric_unit="hours_per_month",
    primary_metric_direction="higher_is_better",
    measurement_method="Sampled time study.",
    baseline_value=None,
    baseline_is_measured=False,
    success_threshold=40.0,
    review_date=date(2026, 6, 30),
    business_owner="Ana Ruiz",
    decommission_trigger_ids=list(EVALUATORS),
    archetype_id="summarization",
    approval_date=date(2026, 3, 31),
)

# A healthy agent: adopted, completing work, cheap, and hitting its number.
# Cost: 200 + 300 + 5h x 100 = 1000 over the window.
# Successful tasks: 500 starts x 0.90 = 450.  Cost per successful task = 2.22
# Value: 60 hours x 45/hour x 1 month = 2700; / 500 starts = 5.40 per task.
HEALTHY = ObservedMetrics(
    months_since_launch=6,
    window_months=1.0,
    active_users=60,
    addressable_population=100,
    sessions=800,
    task_starts=500,
    repeat_users=45,
    time_to_first_value_days=1.0,
    task_completion_rate=0.90,
    override_rate=0.10,
    escalation_rate=0.05,
    mid_task_abandonment_rate=0.05,
    primary_metric_value=60.0,
    inference_cost=200.0,
    licence_cost=300.0,
    maintenance_hours=5.0,
    maintenance_hourly_rate=100.0,
    owner_absent=False,
    superseded_by_platform=False,
)


def observed(**overrides) -> ObservedMetrics:
    """The healthy baseline with specific fields overridden."""
    return HEALTHY.model_copy(update=overrides)


def policy_with(tmp_path, mutate):
    """Load a copy of the real policy after mutating its raw dict."""
    data = yaml.safe_load(REVIEW_POLICY_PATH.read_text())
    mutate(data)
    path = tmp_path / "review_policy.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_review_policy(path)


class TestPolicyAndRegistry:
    def test_every_declared_trigger_has_an_evaluator_and_vice_versa(self):
        """A trigger cannot be declared and then silently never evaluated."""
        assert {t.id for t in POLICY.triggers} == set(EVALUATORS)

    def test_the_required_triggers_are_present(self):
        assert {
            "usage_floor_not_met",
            "cost_exceeds_value",
            "quality_below_threshold",
            "owner_absent",
            "superseded_by_platform",
            "business_metric_missed",
        } <= {t.id for t in POLICY.triggers}

    def test_review_module_contains_no_llm_import(self):
        """The retirement decision must be reproducible, so no model may touch it."""
        source = (REVIEW_POLICY_PATH.parent / "review.py").read_text()
        for forbidden in ("provider", "ollama", "openai", "LLMProvider", "chat("):
            assert forbidden not in source


class TestIndicatorArithmetic:
    def test_cost_per_successful_task_is_hand_verifiable(self):
        # (200 + 300 + 5 x 100) / (500 x 0.90) = 1000 / 450 = 2.2222
        outcome = review(CONTRACT, HEALTHY)
        assert outcome.indicators.total_cost == pytest.approx(1000.0)
        assert outcome.indicators.successful_tasks == pytest.approx(450.0)
        assert outcome.indicators.cost_per_successful_task == pytest.approx(1000 / 450)

    def test_value_per_task_is_hand_verifiable(self):
        # 60 hours x 45 per hour x 1 month = 2700; / 500 task starts = 5.40
        outcome = review(CONTRACT, HEALTHY)
        assert outcome.indicators.value_per_task == pytest.approx(5.40)

    def test_adoption_and_repeat_usage(self):
        outcome = review(CONTRACT, HEALTHY)
        assert outcome.indicators.adoption_rate == pytest.approx(0.60)
        assert outcome.indicators.repeat_usage_ratio == pytest.approx(0.75)

    def test_window_months_scales_value(self):
        outcome = review(CONTRACT, observed(window_months=3.0))
        assert outcome.indicators.value_per_task == pytest.approx(5.40 * 3)


class TestHealthyAgentContinues:
    def test_recommendation_is_continue(self):
        outcome = review(CONTRACT, HEALTHY)
        assert outcome.recommendation is Recommendation.CONTINUE
        assert outcome.triggered_conditions == []
        assert outcome.unevaluated_conditions == []

    def test_next_review_is_the_standard_interval_after_the_contract_date(self):
        outcome = review(CONTRACT, HEALTHY)
        assert outcome.next_review_date == date(2026, 12, 30)  # +6 months

    def test_rationale_shows_the_indicators(self):
        rationale = review(CONTRACT, HEALTHY).rationale
        assert "CONTINUE" in rationale
        assert "cost per successful task" in rationale
        assert "Ana Ruiz" in rationale


class TestEachTriggerFiresIndependently:
    def test_usage_floor_not_met(self):
        outcome = review(CONTRACT, observed(active_users=10))  # 10% adoption
        assert outcome.recommendation is Recommendation.RETIRE
        assert "usage_floor_not_met" in outcome.triggered_ids
        assert outcome.next_review_date is None

    def test_usage_floor_does_not_fire_during_ramp(self):
        outcome = review(
            CONTRACT, observed(active_users=10, months_since_launch=1)
        )
        assert "usage_floor_not_met" not in outcome.triggered_ids

    def test_cost_exceeds_value(self):
        # Raise cost rather than lowering the metric, so this isolates the
        # trigger instead of also missing the business threshold:
        # (3000 + 300 + 500) / 450 = 8.44 per successful task, against an
        # unchanged 5.40 of value per task.
        outcome = review(CONTRACT, observed(inference_cost=3000.0))
        assert outcome.indicators.cost_per_successful_task == pytest.approx(3800 / 450)
        assert outcome.indicators.value_per_task == pytest.approx(5.40)
        assert outcome.triggered_ids == ["cost_exceeds_value"]
        assert outcome.recommendation is Recommendation.RETIRE

    def test_quality_below_threshold_on_completion(self):
        outcome = review(CONTRACT, observed(task_completion_rate=0.50))
        assert "quality_below_threshold" in outcome.triggered_ids

    def test_quality_below_threshold_on_override(self):
        outcome = review(CONTRACT, observed(override_rate=0.45, active_users=40))
        assert "quality_below_threshold" in outcome.triggered_ids

    def test_quality_does_not_fire_when_remediation_is_in_flight(self):
        outcome = review(
            CONTRACT, observed(task_completion_rate=0.50, remediation_in_flight=True)
        )
        assert "quality_below_threshold" not in outcome.triggered_ids

    def test_business_metric_missed_higher_is_better(self):
        outcome = review(CONTRACT, observed(primary_metric_value=39.0))
        assert "business_metric_missed" in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.RETIRE

    def test_business_metric_missed_lower_is_better(self):
        lower_better = CONTRACT.model_copy(
            update={
                "primary_metric_id": "first_response_time_minutes",
                "primary_metric_unit": "minutes",
                "primary_metric_direction": "lower_is_better",
                "success_threshold": 30.0,
            }
        )
        # 45 minutes is worse than a 30-minute target.
        outcome = review(lower_better, observed(primary_metric_value=45.0))
        assert "business_metric_missed" in outcome.triggered_ids

    def test_owner_absent(self):
        outcome = review(CONTRACT, observed(owner_absent=True))
        assert "owner_absent" in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.RETIRE

    def test_superseded_by_platform(self):
        outcome = review(CONTRACT, observed(superseded_by_platform=True))
        assert "superseded_by_platform" in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.RETIRE


class TestTheTwoFailureSignatures:
    """Both look like success on an adoption chart, which is why they are explicit."""

    def test_high_usage_low_quality(self):
        # Adoption 60% (healthy-looking) with a 45% override rate.
        outcome = review(CONTRACT, observed(override_rate=0.45))
        assert "high_usage_low_quality" in outcome.triggered_ids
        detail = next(
            c for c in outcome.triggered_conditions
            if c.trigger_id == "high_usage_low_quality"
        )
        assert "correcting it every time" in detail.observed

    def test_curiosity_adoption(self):
        # Adoption 60% but only 20% of users ever came back.
        outcome = review(CONTRACT, observed(repeat_users=12))
        assert "curiosity_adoption" in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.ADJUST

    def test_curiosity_adoption_does_not_fire_at_low_usage(self):
        """The signature requires usage to look healthy first."""
        outcome = review(CONTRACT, observed(active_users=30, repeat_users=6))
        assert "curiosity_adoption" not in outcome.triggered_ids


class TestInsufficientTelemetry:
    def test_missing_manual_assertion_blocks_the_review(self):
        outcome = review(CONTRACT, observed(owner_absent=None))
        assert outcome.recommendation is Recommendation.INSUFFICIENT_TELEMETRY
        assert "owner_absent" in [c.trigger_id for c in outcome.unevaluated_conditions]

    def test_missing_usage_telemetry_blocks_the_review(self):
        outcome = review(CONTRACT, observed(active_users=None))
        assert outcome.recommendation is Recommendation.INSUFFICIENT_TELEMETRY

    def test_a_unit_with_no_monetary_conversion_cannot_be_valued(self):
        """percent has no conversion, so cost_exceeds_value is unevaluable."""
        percent_contract = CONTRACT.model_copy(
            update={"primary_metric_unit": "percent", "success_threshold": 20.0}
        )
        outcome = review(percent_contract, observed(primary_metric_value=25.0))
        unevaluated = {c.trigger_id for c in outcome.unevaluated_conditions}
        assert "cost_exceeds_value" in unevaluated
        assert outcome.recommendation is Recommendation.INSUFFICIENT_TELEMETRY

    def test_missing_telemetry_never_reads_as_success(self):
        blind = ObservedMetrics()
        outcome = review(CONTRACT, blind)
        assert outcome.recommendation is Recommendation.INSUFFICIENT_TELEMETRY
        assert outcome.recommendation is not Recommendation.CONTINUE
        assert len(outcome.unevaluated_conditions) == len(POLICY.enabled_triggers)

    def test_insufficient_gets_a_short_next_review(self):
        outcome = review(CONTRACT, observed(owner_absent=None))
        assert outcome.next_review_date == date(2026, 9, 30)  # +3 months


class TestPrecedence:
    def test_retire_outranks_adjust(self):
        outcome = review(CONTRACT, observed(active_users=10, override_rate=0.45))
        assert outcome.recommendation is Recommendation.RETIRE

    def test_retire_outranks_insufficient(self):
        """A definite retire is actionable; more telemetry will not unfire it."""
        outcome = review(CONTRACT, observed(owner_absent=True, active_users=None))
        assert outcome.recommendation is Recommendation.RETIRE

    def test_insufficient_outranks_adjust(self):
        """Never recommend a small fix while blind to part of the picture."""
        outcome = review(
            CONTRACT, observed(repeat_users=12, superseded_by_platform=None)
        )
        assert "curiosity_adoption" in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.INSUFFICIENT_TELEMETRY


class TestAdjustOutcome:
    def test_adjust_sets_a_next_review_and_names_the_remediation(self):
        outcome = review(CONTRACT, observed(repeat_users=12))
        assert outcome.recommendation is Recommendation.ADJUST
        assert outcome.next_review_date == date(2026, 9, 30)  # +3 months
        assert "ADJUST" in outcome.rationale
        assert "remediation" in outcome.rationale.lower()
        assert "Interest, not value" in outcome.rationale


class TestPolicyDrivesTheRecommendation:
    """A policy change flips a recommendation with no Python edit."""

    def test_flipping_a_trigger_recommendation_changes_the_outcome(self, tmp_path):
        low_adoption = observed(active_users=10)
        assert review(CONTRACT, low_adoption).recommendation is Recommendation.RETIRE

        def make_it_advisory(data):
            for trigger in data["triggers"]:
                if trigger["id"] == "usage_floor_not_met":
                    trigger["recommendation"] = "adjust"

        lenient = policy_with(tmp_path, make_it_advisory)
        assert (
            review(CONTRACT, low_adoption, lenient).recommendation
            is Recommendation.ADJUST
        )

    def test_lowering_a_threshold_stops_a_trigger_firing(self, tmp_path):
        low_adoption = observed(active_users=10)  # 10% adoption
        assert "usage_floor_not_met" in review(CONTRACT, low_adoption).triggered_ids

        def lower_the_floor(data):
            data["thresholds"]["adoption_floor"] = 0.05

        lenient = policy_with(tmp_path, lower_the_floor)
        outcome = review(CONTRACT, low_adoption, lenient)
        assert "usage_floor_not_met" not in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.CONTINUE

    def test_disabling_a_trigger_removes_it_entirely(self, tmp_path):
        def disable_owner_check(data):
            for trigger in data["triggers"]:
                if trigger["id"] == "owner_absent":
                    trigger["enabled"] = False

        without = policy_with(tmp_path, disable_owner_check)
        outcome = review(CONTRACT, observed(owner_absent=True), without)
        assert "owner_absent" not in outcome.triggered_ids
        assert outcome.recommendation is Recommendation.CONTINUE

    def test_changing_the_next_review_interval(self, tmp_path):
        def stretch(data):
            data["next_review"]["standard_interval_months"] = 12

        stretched = policy_with(tmp_path, stretch)
        outcome = review(CONTRACT, HEALTHY, stretched)
        assert outcome.next_review_date == date(2027, 6, 30)


class TestGoldenPathsToEachRecommendation:
    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, Recommendation.CONTINUE),
            ({"repeat_users": 12}, Recommendation.ADJUST),
            ({"active_users": 10}, Recommendation.RETIRE),
            ({"owner_absent": None}, Recommendation.INSUFFICIENT_TELEMETRY),
        ],
    )
    def test_all_four_recommendations_are_reachable(self, overrides, expected):
        outcome = review(CONTRACT, observed(**overrides))
        assert outcome.recommendation is expected
        assert outcome.rationale
        assert outcome.indicators is not None
