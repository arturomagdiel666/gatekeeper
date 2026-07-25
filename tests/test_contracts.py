"""Tests for Measurement Contract assembly. No live model, no clock."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from config import ConfigError, load_patterns, load_rubric
from contracts import (
    CONTRACTS,
    CONTRACTS_PATH,
    add_months,
    issue_contract,
    load_contracts_config,
)
from schemas import Assessment, Confidence, DimensionAssessment, RequestIntake
from scoring import Verdict, score

RUBRIC = load_rubric()
PATTERNS = load_patterns()
APPROVAL = date(2026, 1, 31)

OWNED = RequestIntake(
    request_text="A request.",
    requesting_area="Service Desk",
    business_owner="Ana Ruiz",
)

GO_SCORES = {
    "business_value": 4,
    "adoption_risk": 2,
    "data_readiness": 4,
    "process_frequency": 4,
    "implementation_effort": 2,
    "data_governance": 2,
    "non_ai_alternative": 2,
}


def make_assessment(scores=None, archetype_id="summarization", **kwargs) -> Assessment:
    """Build an Assessment with the given scores and metric proposal."""
    return Assessment(
        archetype_id=archetype_id,
        anti_pattern_ids=[],
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=key,
                score=value,
                evidence=f"Evidence for {key}.",
                confidence=Confidence.HIGH,
            )
            for key, value in (scores or GO_SCORES).items()
        ],
        **kwargs,
    )


def issue(assessment, intake=OWNED, approval=APPROVAL):
    """Score an assessment and issue its contract in one step."""
    outcome = score(assessment, RUBRIC, PATTERNS, intake)
    return outcome, issue_contract(outcome, assessment, intake, approval)


class TestAddMonths:
    @pytest.mark.parametrize(
        ("start", "months", "expected"),
        [
            (date(2026, 1, 31), 1, date(2026, 2, 28)),  # clamps, does not overflow
            (date(2024, 1, 31), 1, date(2024, 2, 29)),  # leap year
            (date(2026, 1, 15), 3, date(2026, 4, 15)),
            (date(2026, 11, 30), 3, date(2027, 2, 28)),  # crosses the year
            (date(2026, 12, 1), 1, date(2027, 1, 1)),  # December wraps
            (date(2026, 6, 30), 9, date(2027, 3, 30)),
        ],
    )
    def test_month_arithmetic(self, start, months, expected):
        assert add_months(start, months) == expected


class TestContractsConfig:
    def test_shipped_config_loads(self):
        assert CONTRACTS.metrics and CONTRACTS.archetypes
        assert CONTRACTS.decommission_triggers

    def test_every_rubric_archetype_has_a_contract_template(self):
        """A go on any archetype must be able to issue a contract."""
        template_ids = {a.id for a in CONTRACTS.archetypes}
        assert set(PATTERNS.archetype_ids) <= template_ids

    def test_the_required_triggers_are_catalogued(self):
        assert {
            "usage_floor_not_met",
            "cost_exceeds_value",
            "quality_below_threshold",
            "owner_absent",
            "superseded_by_platform",
            "business_metric_missed",
            "high_usage_low_quality",
            "curiosity_adoption",
        } <= set(CONTRACTS.trigger_ids)

    def test_owner_and_platform_triggers_are_manual_assertions(self):
        manual = {t.id for t in CONTRACTS.decommission_triggers if t.manual_assertion}
        assert manual == {"owner_absent", "superseded_by_platform"}

    def test_horizons_by_effort_band(self):
        assert CONTRACTS.horizon_months(1) == 3
        assert CONTRACTS.horizon_months(2) == 3
        assert CONTRACTS.horizon_months(3) == 6
        assert CONTRACTS.horizon_months(4) == 9
        assert CONTRACTS.horizon_months(5) == 9

    def test_unknown_effort_gets_the_shortest_horizon(self):
        """Reviewing too early is recoverable; too late is not."""
        assert CONTRACTS.horizon_months(None) == 3

    def test_default_metric_must_be_a_candidate(self, tmp_path):
        data = yaml.safe_load(CONTRACTS_PATH.read_text())
        data["archetypes"][0]["default_metric_id"] = "hours_reclaimed_per_month"
        data["archetypes"][0]["candidate_metric_ids"] = ["rework_rate_pct"]
        path = tmp_path / "contracts.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(ConfigError, match="not one of its own"):
            load_contracts_config(path)

    def test_candidate_metric_must_exist(self, tmp_path):
        data = yaml.safe_load(CONTRACTS_PATH.read_text())
        data["archetypes"][0]["candidate_metric_ids"].append("invented_metric")
        path = tmp_path / "contracts.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(ConfigError, match="do not exist"):
            load_contracts_config(path)

    def test_gapped_review_horizons_are_rejected(self, tmp_path):
        data = yaml.safe_load(CONTRACTS_PATH.read_text())
        data["review_horizons"][0]["effort_max"] = 1  # leaves 2 uncovered
        path = tmp_path / "contracts.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(ConfigError, match="tile the effort scale"):
            load_contracts_config(path)


class TestContractIsIssuedOnlyOnGo:
    def test_go_issues_a_contract(self):
        outcome, result = issue(make_assessment())
        assert outcome.verdict is Verdict.GO
        assert result.contract is not None

    def test_no_go_issues_nothing(self):
        outcome, result = issue(make_assessment({**GO_SCORES, "business_value": 1,
                                                 "adoption_risk": 5,
                                                 "process_frequency": 1}))
        assert outcome.verdict is Verdict.NO_GO
        assert result.contract is None

    def test_not_ai_issues_nothing(self):
        assessment = make_assessment({**GO_SCORES, "non_ai_alternative": 5})
        outcome, result = issue(assessment)
        assert outcome.verdict is Verdict.NOT_AI
        assert result.contract is None

    def test_incomplete_issues_nothing(self):
        assessment = make_assessment(
            {**GO_SCORES, "data_readiness": None, "adoption_risk": None}
        )
        outcome, result = issue(assessment)
        assert outcome.verdict is Verdict.INCOMPLETE
        assert result.contract is None

    def test_gated_no_go_issues_nothing_even_with_a_go_band_total(self):
        assessment = make_assessment({**GO_SCORES, "data_governance": 5})
        outcome, result = issue(assessment)
        assert outcome.verdict is Verdict.NO_GO
        assert result.contract is None


class TestContractContents:
    def test_exactly_one_primary_metric(self):
        """A contract with three metrics has none."""
        _, result = issue(make_assessment())
        contract = result.contract
        assert isinstance(contract.primary_metric_id, str)
        assert contract.primary_metric_id
        assert contract.primary_metric_label
        assert contract.primary_metric_unit
        assert contract.measurement_method

    def test_archetype_default_metric_is_used_when_none_proposed(self):
        _, result = issue(make_assessment(archetype_id="rag_qa"))
        assert result.contract.primary_metric_id == "search_success_rate_pct"

    def test_a_valid_proposal_is_honoured(self):
        _, result = issue(
            make_assessment(
                archetype_id="rag_qa", proposed_metric_id="tickets_deflected_per_month"
            )
        )
        assert result.contract.primary_metric_id == "tickets_deflected_per_month"
        assert result.ignored_metric_ids == []

    def test_unknown_metric_id_falls_back_and_is_recorded(self):
        _, result = issue(
            make_assessment(
                archetype_id="rag_qa", proposed_metric_id="metric_i_made_up"
            )
        )
        assert result.contract.primary_metric_id == "search_success_rate_pct"
        assert result.ignored_metric_ids == ["metric_i_made_up"]

    def test_a_metric_valid_for_another_archetype_is_still_rejected(self):
        """Candidate lists are per archetype, not a global pool."""
        _, result = issue(
            make_assessment(
                archetype_id="rag_qa", proposed_metric_id="alert_precision_pct"
            )
        )
        assert result.ignored_metric_ids == ["alert_precision_pct"]

    def test_business_owner_is_carried_from_intake(self):
        _, result = issue(make_assessment())
        assert result.contract.business_owner == "Ana Ruiz"

    def test_all_four_instrumentation_layers_are_populated(self):
        _, result = issue(make_assessment(archetype_id="classification"))
        plan = result.contract.instrumentation_plan
        assert plan.usage and plan.quality and plan.business and plan.cost

    def test_archetype_instrumentation_is_merged_onto_the_baseline(self):
        _, result = issue(make_assessment(archetype_id="rag_qa"))
        quality = " ".join(result.contract.instrumentation_plan.quality).lower()
        assert "citation" in quality  # the rag_qa extra
        assert "completion rate" in quality  # the baseline

    def test_every_catalogued_trigger_is_attached(self):
        _, result = issue(make_assessment())
        assert result.contract.decommission_trigger_ids == CONTRACTS.trigger_ids


class TestBaselineAndThreshold:
    def test_unmeasured_baseline_is_recorded_as_such(self):
        _, result = issue(make_assessment())
        assert result.contract.baseline_value is None
        assert result.contract.baseline_is_measured is False

    def test_stated_baseline_is_recorded_as_measured(self):
        _, result = issue(
            make_assessment(
                archetype_id="summarization",
                proposed_metric_id="first_response_time_minutes",
                stated_baseline_value=60.0,
            )
        )
        assert result.contract.baseline_value == 60.0
        assert result.contract.baseline_is_measured is True

    def test_relative_threshold_improves_a_lower_is_better_baseline(self):
        # first_response_time_minutes: lower is better, 30% target
        # 60 minutes -> 60 * (1 - 0.30) = 42.0
        _, result = issue(
            make_assessment(
                proposed_metric_id="first_response_time_minutes",
                stated_baseline_value=60.0,
            )
        )
        assert result.contract.success_threshold == pytest.approx(42.0)

    def test_relative_threshold_improves_a_higher_is_better_baseline(self):
        # routing_accuracy_pct: higher is better, 15% target
        # 80 -> 80 * 1.15 = 92.0
        _, result = issue(
            make_assessment(
                archetype_id="classification",
                proposed_metric_id="routing_accuracy_pct",
                stated_baseline_value=80.0,
            )
        )
        assert result.contract.success_threshold == pytest.approx(92.0)

    def test_absolute_metric_ignores_the_baseline(self):
        """A gain measured from nothing has no baseline to improve on."""
        _, result = issue(
            make_assessment(proposed_metric_id="hours_reclaimed_per_month")
        )
        metric = CONTRACTS.metric_by_id("hours_reclaimed_per_month")
        assert result.contract.success_threshold == metric.default_absolute_threshold

    def test_relative_metric_without_a_baseline_falls_back_to_absolute(self):
        _, result = issue(
            make_assessment(proposed_metric_id="first_response_time_minutes")
        )
        metric = CONTRACTS.metric_by_id("first_response_time_minutes")
        assert result.contract.success_threshold == metric.default_absolute_threshold
        assert result.contract.baseline_is_measured is False


class TestReviewDate:
    @pytest.mark.parametrize(
        ("effort", "expected"),
        [
            (1, date(2026, 4, 30)),  # light  -> 3 months from 31 Jan, clamped
            (2, date(2026, 4, 30)),
            (3, date(2026, 7, 31)),  # moderate -> 6 months
            (4, date(2026, 10, 31)),  # heavy -> 9 months
            (5, date(2026, 10, 31)),
        ],
    )
    def test_review_date_follows_the_effort_band(self, effort, expected):
        # Keep the total in the go band while varying effort: raise
        # business_value as effort rises.
        scores = {**GO_SCORES, "implementation_effort": effort, "business_value": 5}
        outcome, result = issue(make_assessment(scores))
        assert outcome.verdict is Verdict.GO
        assert result.contract.review_date == expected

    def test_approval_date_is_recorded_and_injected(self):
        _, result = issue(make_assessment(), approval=date(2026, 3, 15))
        assert result.contract.approval_date == date(2026, 3, 15)
        assert result.contract.review_date == date(2026, 6, 15)

    def test_unknown_effort_uses_the_shortest_horizon(self):
        scores = {**GO_SCORES, "implementation_effort": None}
        outcome, result = issue(make_assessment(scores))
        assert outcome.verdict is Verdict.GO
        assert "implementation_effort" in outcome.unknown_dimensions
        assert result.contract.review_date == date(2026, 4, 30)
