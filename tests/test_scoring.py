"""Tests for deterministic scoring. No live model, no network.

Every expected total below is hand-computed from the weights in rubric.yaml and
written out longhand in a comment, so a reader can check the arithmetic with a
calculator and catch a rubric edit that silently moved a verdict.

Weights as shipped:
    business_value        0.22 (higher)   adoption_risk         0.17 (lower)
    data_readiness        0.15 (higher)   process_frequency     0.13 (higher)
    implementation_effort 0.13 (lower)    data_governance       0.10 (lower)
    non_ai_alternative    0.10 (lower)
A `lower_is_better` raw score is flipped as 6 - raw before weighting.
"""

from __future__ import annotations

import pytest
import yaml

from config import RUBRIC_PATH, load_patterns, load_rubric
from schemas import (
    AntiPatternMatch,
    Assessment,
    Confidence,
    DimensionAssessment,
    RequestIntake,
)
from scoring import Verdict, match_band, score

PATTERNS = load_patterns()
RUBRIC = load_rubric()

# An intake that satisfies the owner gate, so tests of other gates are not
# accidentally testing this one.
# Every anti-pattern match in these tests quotes this phrase, and the intake
# below contains it — so matches verify and the tests exercise gate logic
# rather than the quote check. The quote check has its own tests.
QUOTABLE_PHRASE = "the platform team said the licence already covers it"

OWNED = RequestIntake(
    request_text=f"A request. {QUOTABLE_PHRASE}",
    requesting_area="Service Desk",
    business_owner="Ana Ruiz",
    process_description="Done by hand today.",
)

# SYNTHETIC ARITHMETIC FIXTURE — not a reference assessment of anything.
#
# These scores are chosen to exercise the arithmetic: both directions, a
# hand-verifiable total, and a result comfortably inside the `go` band. They are
# NOT an anchor-faithful reading of any real request and must not be reused as a
# few-shot exemplar — that would teach the model to inflate the
# heaviest-weighted dimension. The reference exemplars are the six files in
# examples/, scored against the anchors (see tests/test_examples.py).
#
# dimension              direction         raw -> norm  x weight = contribution
# business_value         higher_is_better    4 ->  4    x 0.22   = 0.88
# adoption_risk          lower_is_better     2 ->  4    x 0.17   = 0.68
# data_readiness         higher_is_better    4 ->  4    x 0.15   = 0.60
# process_frequency      higher_is_better    4 ->  4    x 0.13   = 0.52
# implementation_effort  lower_is_better     2 ->  4    x 0.13   = 0.52
# data_governance        lower_is_better     2 ->  4    x 0.10   = 0.40
# non_ai_alternative     lower_is_better     2 ->  4    x 0.10   = 0.40
#                                                         total  = 4.00 -> go
#
# Note non_ai_alternative: raw 2 normalizes to 4. A RAW 4 would fire the
# non_ai_alternative_suffices gate and the verdict would be not_ai, not go — so
# the raw/normalized distinction is load-bearing here, not cosmetic.
ARITHMETIC_SCORES = {
    "business_value": 4,
    "adoption_risk": 2,
    "data_readiness": 4,
    "process_frequency": 4,
    "implementation_effort": 2,
    "data_governance": 2,
    "non_ai_alternative": 2,
}
ARITHMETIC_TOTAL = 4.00

# Every dimension at its most favourable, used as the base for the gate tests:
# each then spoils exactly one dimension, so the gate is provably what changed
# the verdict and not the arithmetic.
BEST_SCORES = {
    "business_value": 5,
    "adoption_risk": 1,
    "data_readiness": 5,
    "process_frequency": 5,
    "implementation_effort": 1,
    "data_governance": 1,
    "non_ai_alternative": 1,
}


def make_assessment(
    scores: dict[str, int | None],
    anti_pattern_ids: list[str] | None = None,
    archetype_id: str | None = "classification",
) -> Assessment:
    """Build an Assessment from a {dimension_id: score} mapping."""
    return Assessment(
        archetype_id=archetype_id,
        anti_pattern_matches=[
            AntiPatternMatch(
                anti_pattern_id=i,
                quote=QUOTABLE_PHRASE,
                quote_confidence=Confidence.HIGH,
            )
            for i in (anti_pattern_ids or [])
        ],
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=dimension_id,
                score=value,
                evidence=f"Request evidence for {dimension_id}.",
                confidence=Confidence.HIGH,
            )
            for dimension_id, value in scores.items()
        ],
    )


def rubric_with(tmp_path, **changes):
    """Load a copy of the real rubric with top-level keys replaced."""
    data = yaml.safe_load(RUBRIC_PATH.read_text())
    data.update(changes)
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_rubric(path)


def permissive_rubric(tmp_path, **completeness):
    """A rubric with a relaxed completeness rule and NO gates.

    The gates must go too: config.py refuses a rubric whose gate dimensions are
    not in never_unknown, precisely because such a gate fails open. These
    fixtures exist to exercise the weight rule on its own, so they drop the
    gates rather than defeat that guard.
    """
    data = yaml.safe_load(RUBRIC_PATH.read_text())
    data["completeness"] = completeness
    data["blocking_gates"] = []
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_rubric(path)


def rubric_without_gate(tmp_path, gate_id: str):
    """Load a copy of the real rubric with one blocking gate deleted."""
    data = yaml.safe_load(RUBRIC_PATH.read_text())
    data["blocking_gates"] = [
        gate for gate in data["blocking_gates"] if gate["id"] != gate_id
    ]
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_rubric(path)


class TestDirectionNormalization:
    """If direction were ignored, this case would total 2.00 instead of 3.00."""

    def test_all_raw_twos_totals_3_00(self):
        # Raw 2 everywhere; no gate fires (data_readiness 2 > 1,
        # data_governance 2 < 5, non_ai_alternative 2 < 4).
        #  2 x 0.22 = 0.44 | (6-2)=4 x 0.17 = 0.68 | 2 x 0.15 = 0.30
        #  2 x 0.13 = 0.26 | 4 x 0.13 = 0.52 | 4 x 0.10 = 0.40 | 4 x 0.10 = 0.40
        #                                              total = 3.00
        outcome = score(
            make_assessment(dict.fromkeys(RUBRIC.dimension_ids, 2)),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.triggered_gates == []
        assert outcome.weighted_total == pytest.approx(3.00)
        assert outcome.verdict is Verdict.NO_GO

    def test_lower_is_better_dimensions_are_flipped_in_the_breakdown(self):
        outcome = score(make_assessment(ARITHMETIC_SCORES), RUBRIC, PATTERNS, OWNED)
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert (by_id["adoption_risk"].raw_score, by_id["adoption_risk"].normalized_score) == (2, 4)
        assert (by_id["business_value"].raw_score, by_id["business_value"].normalized_score) == (4, 4)


class TestVerdictBands:
    def test_weighted_total_arithmetic_with_synthetic_scores(self):
        """Verify the weighted sum against the hand-computed 4.00.

        The scores are a synthetic fixture chosen to exercise the arithmetic
        (see the longhand table at the top of this file). They are NOT a
        reference assessment of any request and carry no claim about how any
        real case should be scored against the anchors.
        """
        outcome = score(make_assessment(ARITHMETIC_SCORES), RUBRIC, PATTERNS, OWNED)
        assert outcome.weighted_total == pytest.approx(ARITHMETIC_TOTAL)
        assert outcome.verdict is Verdict.GO

    def test_exact_band_boundary_of_3_50_is_a_go(self):
        # 4 x 0.22 = 0.88 | (6-3)=3 x 0.17 = 0.51 | 4 x 0.15 = 0.60
        # 4 x 0.13 = 0.52 | 3 x 0.13 = 0.39 | 3 x 0.10 = 0.30 | 3 x 0.10 = 0.30
        #                                            total = exactly 3.50
        outcome = score(
            make_assessment(
                {
                    "business_value": 4,
                    "adoption_risk": 3,
                    "data_readiness": 4,
                    "process_frequency": 4,
                    "implementation_effort": 3,
                    "data_governance": 3,
                    "non_ai_alternative": 3,
                }
            ),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.weighted_total == pytest.approx(3.50)
        assert outcome.verdict is Verdict.GO

    def test_just_below_the_boundary_is_a_no_go(self):
        # As above but data_readiness 3 -> 3 x 0.15 = 0.45 (was 0.60)
        # 0.88 + 0.51 + 0.45 + 0.52 + 0.39 + 0.30 + 0.30 = 3.35
        outcome = score(
            make_assessment(
                {
                    "business_value": 4,
                    "adoption_risk": 3,
                    "data_readiness": 3,
                    "process_frequency": 4,
                    "implementation_effort": 3,
                    "data_governance": 3,
                    "non_ai_alternative": 3,
                }
            ),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.weighted_total == pytest.approx(3.35)
        assert outcome.verdict is Verdict.NO_GO

    @pytest.mark.parametrize(
        ("total", "expected"),
        [
            (1.0, Verdict.NO_GO),
            (3.499999, Verdict.NO_GO),
            (3.5, Verdict.GO),
            (5.0, Verdict.GO),
        ],
    )
    def test_band_edges_directly(self, total, expected):
        assert match_band(total, RUBRIC) is expected

    def test_total_off_the_scale_raises(self):
        with pytest.raises(ValueError, match="outside every verdict band"):
            match_band(5.5, RUBRIC)


class TestBlockingGates:
    """Each case scores every other dimension at its best, so the weighted
    total lands in the `go` band and only the gate can account for the verdict.
    """

    def test_no_usable_data_blocks_an_otherwise_perfect_request(self):
        # 5 x 0.22 = 1.10 | 5 x 0.17 = 0.85 | 1 x 0.15 = 0.15  <- the penalty
        # 5 x 0.13 = 0.65 | 5 x 0.13 = 0.65 | 5 x 0.10 = 0.50 | 5 x 0.10 = 0.50
        #                                            total = 4.40 -> go band
        outcome = score(
            make_assessment({**BEST_SCORES, "data_readiness": 1}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.weighted_total == pytest.approx(4.40)
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["no_usable_data"]
        assert "data_readiness scored 1" in outcome.triggered_gates[0].detail

    def test_unacceptable_data_governance_blocks_an_otherwise_perfect_request(self):
        # 1.10 + 0.85 + 0.75 + 0.65 + 0.65 + (6-5)=1 x 0.10 = 0.10 + 0.50
        #                                            total = 4.60 -> go band
        outcome = score(
            make_assessment({**BEST_SCORES, "data_governance": 5}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.weighted_total == pytest.approx(4.60)
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["unacceptable_data_governance"]

    def test_non_ai_alternative_threshold_fires_on_its_own(self):
        # 1.10 + 0.85 + 0.75 + 0.65 + 0.65 + 0.50 + (6-4)=2 x 0.10 = 0.20
        #                                            total = 4.70 -> go band
        outcome = score(
            make_assessment({**BEST_SCORES, "non_ai_alternative": 4}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.weighted_total == pytest.approx(4.70)
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == ["non_ai_alternative_suffices"]

    def test_existing_licensed_capability_fires_its_own_gate(self):
        outcome = score(
            make_assessment(BEST_SCORES, ["existing_licensed_capability"]),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.verdict is Verdict.NOT_AI
        # Attributed to the specific gate, not the general one — its
        # remediation (go and use the licence you already pay for) is the most
        # actionable thing the Hub can say.
        assert outcome.triggered_gate_ids == ["existing_capability_covers_it"]
        assert outcome.triggered_gates[0].matched_anti_pattern_ids == [
            "existing_licensed_capability"
        ]

    def test_other_hard_block_anti_patterns_fire_the_general_gate(self):
        outcome = score(
            make_assessment(BEST_SCORES, ["reporting_in_disguise"]),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == ["non_ai_alternative_suffices"]

    def test_no_named_business_owner_fires_from_intake(self):
        outcome = score(
            make_assessment(BEST_SCORES),
            RUBRIC,
            PATTERNS,
            RequestIntake(request_text=f"A request. {QUOTABLE_PHRASE}", business_owner="   "),
        )
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["no_named_business_owner"]
        assert "business_owner" in outcome.triggered_gates[0].detail

    def test_a_named_owner_does_not_fire_the_gate(self):
        outcome = score(make_assessment(BEST_SCORES), RUBRIC, PATTERNS, OWNED)
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO

    def test_intake_gate_cannot_fire_without_an_intake(self):
        """Absence of intake is not evidence that the field is empty."""
        outcome = score(make_assessment(BEST_SCORES), RUBRIC, PATTERNS, intake=None)
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO

    def test_advisory_anti_pattern_does_not_fire_any_gate(self):
        for advisory in (
            "chatbot_without_job_to_be_done",
            "data_does_not_exist_yet",
            "solution_first_no_measurable_problem",
            "single_user_workaround",
        ):
            outcome = score(
                make_assessment(BEST_SCORES, [advisory]), RUBRIC, PATTERNS, OWNED
            )
            assert outcome.triggered_gates == [], advisory
            assert outcome.verdict is Verdict.GO, advisory

    def test_precedence_lowest_number_decides_and_all_are_reported(self):
        outcome = score(
            make_assessment(
                {**BEST_SCORES, "data_readiness": 1, "non_ai_alternative": 4},
                ["existing_licensed_capability"],
            ),
            RUBRIC,
            PATTERNS,
            RequestIntake(request_text=f"A request. {QUOTABLE_PHRASE}", business_owner=""),
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == [
            "existing_capability_covers_it",
            "non_ai_alternative_suffices",
            "no_named_business_owner",
            "no_usable_data",
        ]
        precedences = [g.precedence for g in outcome.triggered_gates]
        assert precedences == sorted(precedences)

    def test_an_unknown_gate_dimension_yields_incomplete_not_a_silent_pass(self):
        """The fail-open guard.

        A gate whose dimension is null cannot fire. Before Phase 3.2 that
        request sailed through as a `go` with the blocking rule silently never
        run; now every gate dimension is in never_unknown, so the same input
        returns `incomplete` and names the reason.
        """
        outcome = score(
            make_assessment({**BEST_SCORES, "data_readiness": None}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.triggered_gates == []
        assert outcome.unknown_dimensions == ["data_readiness"]
        assert outcome.verdict is Verdict.INCOMPLETE
        assert "gate condition" in outcome.completeness_violation

    def test_gate_fires_even_when_the_request_is_too_sparse_to_score(self):
        outcome = score(
            make_assessment({"business_value": 5}, ["rpa_relabeled"]),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.weighted_total is None

    def test_deleting_a_gate_restores_band_behaviour(self, tmp_path):
        """Gates are config: removing one needs no Python edit."""
        no_data = make_assessment({**BEST_SCORES, "data_readiness": 1})
        assert score(no_data, RUBRIC, PATTERNS, OWNED).verdict is Verdict.NO_GO

        without = rubric_without_gate(tmp_path, "no_usable_data")
        outcome = score(no_data, without, PATTERNS, OWNED)
        assert outcome.triggered_gates == []
        assert outcome.weighted_total == pytest.approx(4.40)
        assert outcome.verdict is Verdict.GO

    def test_unknown_anti_pattern_id_is_reported_not_raised(self):
        outcome = score(
            make_assessment(BEST_SCORES, ["invented_by_the_model"]),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.ignored_anti_pattern_ids == ["invented_by_the_model"]
        assert outcome.verdict is Verdict.GO

    def test_gate_explanation_names_the_gate_and_its_reason(self):
        outcome = score(
            make_assessment({**BEST_SCORES, "data_governance": 5}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert "unacceptable_data_governance -> no_go" in outcome.explanation
        assert "data_governance scored 5" in outcome.explanation
        assert "cannot be processed" in outcome.explanation


class TestCompleteness:
    """Completeness is measured in WEIGHT, plus an absolute never_unknown list.

    Weights: business_value 0.22, adoption_risk 0.17, data_readiness 0.15,
    process_frequency 0.13, implementation_effort 0.13, data_governance 0.10,
    non_ai_alternative 0.10. Budget 0.25.
    """

    def test_one_unknown_within_budget_scores_with_renormalized_weights(self):
        # process_frequency unknown = 0.13 of weight, inside the 0.25 budget,
        # and not in never_unknown. Every remaining dimension normalizes to 4,
        # so renormalization must still produce exactly 4.00.
        scores = {
            "business_value": 4,
            "adoption_risk": 2,
            "data_readiness": 4,
            "process_frequency": None,
            "implementation_effort": 2,
            "data_governance": 2,
            "non_ai_alternative": 2,
        }
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS, OWNED)
        assert outcome.unknown_dimensions == ["process_frequency"]
        assert outcome.unknown_weight == pytest.approx(0.13)
        assert outcome.completeness_violation is None
        assert outcome.weighted_total == pytest.approx(4.00)
        assert outcome.verdict is Verdict.GO
        assert sum(c.effective_weight for c in outcome.contributions) == pytest.approx(1.0)

    def test_two_light_unknowns_within_budget_still_resolve(self, tmp_path):
        """The weight rule in isolation, with never_unknown reduced.

        Against the SHIPPED config no two dimensions can both be unknown: the
        three not in never_unknown weigh 0.17, 0.13 and 0.13, and every pair
        exceeds 0.25. That interaction is recorded in ADR-022; here the rule
        itself is exercised on its own.
        """
        permissive = permissive_rubric(
            tmp_path, max_unknown_weight=0.25, never_unknown=["business_value"]
        )
        # data_governance 0.10 + implementation_effort 0.13 = 0.23 <= 0.25
        scores = {**ARITHMETIC_SCORES, "data_governance": None,
                  "implementation_effort": None}
        outcome = score(make_assessment(scores), permissive, PATTERNS, OWNED)
        assert outcome.unknown_weight == pytest.approx(0.23)
        assert outcome.completeness_violation is None
        assert outcome.verdict is not Verdict.INCOMPLETE

    def test_two_unknowns_over_budget_return_incomplete(self, tmp_path):
        permissive = permissive_rubric(
            tmp_path, max_unknown_weight=0.25, never_unknown=["business_value"]
        )
        # adoption_risk 0.17 + implementation_effort 0.13 = 0.30 > 0.25
        scores = {**ARITHMETIC_SCORES, "adoption_risk": None,
                  "implementation_effort": None}
        outcome = score(make_assessment(scores), permissive, PATTERNS, OWNED)
        assert outcome.verdict is Verdict.INCOMPLETE
        assert outcome.unknown_weight == pytest.approx(0.30)
        assert "max_unknown_weight" in outcome.completeness_violation
        assert "0.30" in outcome.completeness_violation
        assert "0.25" in outcome.completeness_violation
        assert outcome.weighted_total is None

    def test_a_heavy_unknown_alone_can_exceed_the_budget(self, tmp_path):
        """The whole point of the unit change: one heavy slot > two light ones."""
        permissive = permissive_rubric(
            tmp_path, max_unknown_weight=0.15, never_unknown=[]
        )
        heavy = score(
            make_assessment({**ARITHMETIC_SCORES, "business_value": None}),
            permissive, PATTERNS, OWNED,
        )
        light = score(
            make_assessment({**ARITHMETIC_SCORES, "data_governance": None}),
            permissive, PATTERNS, OWNED,
        )
        assert heavy.unknown_weight == pytest.approx(0.22)
        assert heavy.verdict is Verdict.INCOMPLETE
        assert light.unknown_weight == pytest.approx(0.10)
        assert light.verdict is not Verdict.INCOMPLETE

    @pytest.mark.parametrize(
        "required", ["business_value", "data_readiness", "data_governance",
                     "non_ai_alternative"],
    )
    def test_a_never_unknown_dimension_always_forces_incomplete(self, required):
        """Whatever budget remains — 0.10 is well inside 0.25 and still fails."""
        outcome = score(
            make_assessment({**ARITHMETIC_SCORES, required: None}),
            RUBRIC, PATTERNS, OWNED,
        )
        assert outcome.verdict is Verdict.INCOMPLETE, required
        assert "never_unknown" in outcome.completeness_violation
        assert required in outcome.completeness_violation

    def test_the_gate_dimensions_say_why_they_are_required(self):
        """An unknown gate condition fails OPEN, which is the dangerous case."""
        outcome = score(
            make_assessment({**ARITHMETIC_SCORES, "data_readiness": None}),
            RUBRIC, PATTERNS, OWNED,
        )
        assert "gate condition" in outcome.completeness_violation
        assert "cannot fire" in outcome.completeness_violation

    def test_the_explanation_reports_the_rule_and_the_weight(self):
        outcome = score(
            make_assessment({**ARITHMETIC_SCORES, "business_value": None}),
            RUBRIC, PATTERNS, OWNED,
        )
        assert "Rule violated ->" in outcome.explanation
        assert "0.22 of weight" in outcome.explanation
        assert "budget 0.25" in outcome.explanation

    def test_a_dimension_absent_entirely_counts_as_unknown(self):
        scores = {k: v for k, v in ARITHMETIC_SCORES.items()
                  if k != "process_frequency"}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS, OWNED)
        assert outcome.unknown_dimensions == ["process_frequency"]
        assert outcome.verdict is Verdict.GO

    def test_everything_unknown_is_incomplete(self, tmp_path):
        """Guards the divide-by-zero when no dimension has a score."""
        permissive = permissive_rubric(
            tmp_path, max_unknown_weight=1.0, never_unknown=[]
        )
        outcome = score(
            make_assessment(dict.fromkeys(RUBRIC.dimension_ids, None)),
            permissive, PATTERNS, OWNED,
        )
        assert outcome.verdict is Verdict.INCOMPLETE
        assert outcome.weighted_total is None

    def test_unknown_scores_are_never_invented(self):
        scores = {**ARITHMETIC_SCORES, "process_frequency": None}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS, OWNED)
        assert "process_frequency" not in {c.dimension_id for c in outcome.contributions}


class TestMalformedAssessments:
    def test_unknown_dimension_id_is_ignored_and_reported(self):
        outcome = score(
            make_assessment({**ARITHMETIC_SCORES, "vibes": 5}),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert outcome.ignored_dimension_ids == ["vibes"]
        assert outcome.weighted_total == pytest.approx(ARITHMETIC_TOTAL)

    def test_duplicate_dimension_entries_keep_the_first(self):
        assessment = make_assessment(ARITHMETIC_SCORES)
        assessment.dimension_assessments.append(
            DimensionAssessment(
                dimension_id="business_value",
                score=1,
                evidence="a contradictory second opinion",
                confidence=Confidence.LOW,
            )
        )
        outcome = score(assessment, RUBRIC, PATTERNS, OWNED)
        assert outcome.ignored_dimension_ids == ["business_value"]
        assert outcome.weighted_total == pytest.approx(ARITHMETIC_TOTAL)


class TestConfigDrivesTheVerdict:
    """YAML edits change verdicts with no code change."""

    def test_moving_a_band_flips_the_fixture_to_no_go(self, tmp_path):
        stricter = rubric_with(
            tmp_path,
            verdict_bands=[
                {"verdict": "no_go", "lower": 1.0, "upper": 4.5, "upper_inclusive": False},
                {"verdict": "go", "lower": 4.5, "upper": 5.0, "upper_inclusive": True},
            ],
        )
        outcome = score(make_assessment(ARITHMETIC_SCORES), stricter, PATTERNS, OWNED)
        assert outcome.weighted_total == pytest.approx(ARITHMETIC_TOTAL)
        assert outcome.verdict is Verdict.NO_GO

    def test_reweighting_flips_the_fixture_to_no_go(self, tmp_path):
        # Shift weight onto adoption_risk, where this fixture scores worst
        # after normalization is undone... concretely:
        # 4 x 0.05 = 0.20 | (6-2)=4 x 0.10 = 0.40 | 4 x 0.05 = 0.20
        # 4 x 0.05 = 0.20 | 4 x 0.05 = 0.20 | 4 x 0.05 = 0.20 | 4 x 0.65 = 2.60
        # -> but with every normalized value equal to 4 the total is 4.00 for
        # ANY weighting, so instead drop one raw score and reweight onto it.
        data = yaml.safe_load(RUBRIC_PATH.read_text())
        new_weights = {
            "business_value": 0.05,
            "adoption_risk": 0.05,
            "data_readiness": 0.60,
            "process_frequency": 0.10,
            "implementation_effort": 0.10,
            "data_governance": 0.05,
            "non_ai_alternative": 0.05,
        }
        for dimension in data["dimensions"]:
            dimension["weight"] = new_weights[dimension["id"]]
        path = tmp_path / "rubric.yaml"
        path.write_text(yaml.safe_dump(data))
        reweighted = load_rubric(path)

        # data_readiness raw 2 now carries 0.60 of the weight:
        # 4 x 0.05 = 0.20 | 4 x 0.05 = 0.20 | 2 x 0.60 = 1.20 | 4 x 0.10 = 0.40
        # 4 x 0.10 = 0.40 | 4 x 0.05 = 0.20 | 4 x 0.05 = 0.20   total = 2.80
        scores = {**ARITHMETIC_SCORES, "data_readiness": 2}
        outcome = score(make_assessment(scores), reweighted, PATTERNS, OWNED)
        assert outcome.weighted_total == pytest.approx(2.80)
        assert outcome.verdict is Verdict.NO_GO


class TestEndToEnd:
    def test_full_outcome_of_the_arithmetic_fixture(self):
        outcome = score(make_assessment(ARITHMETIC_SCORES), RUBRIC, PATTERNS, OWNED)

        assert outcome.verdict is Verdict.GO
        assert outcome.weighted_total == pytest.approx(ARITHMETIC_TOTAL)
        assert outcome.triggered_gates == []
        assert outcome.unknown_dimensions == []
        assert outcome.ignored_dimension_ids == []
        assert outcome.ignored_anti_pattern_ids == []

        assert [c.dimension_id for c in outcome.contributions] == RUBRIC.dimension_ids
        assert [c.contribution for c in outcome.contributions] == pytest.approx(
            [0.88, 0.68, 0.60, 0.52, 0.52, 0.40, 0.40]
        )
        assert sum(c.contribution for c in outcome.contributions) == pytest.approx(
            ARITHMETIC_TOTAL
        )
        for contribution in outcome.contributions:
            assert contribution.effective_weight == pytest.approx(contribution.weight)

        assert "GO" in outcome.explanation
        assert "4.00" in outcome.explanation
        assert "Request evidence for business_value." in outcome.explanation

    def test_explanation_of_a_gated_case_names_the_alternative(self):
        outcome = score(
            make_assessment(ARITHMETIC_SCORES, ["existing_licensed_capability"]),
            RUBRIC,
            PATTERNS,
            OWNED,
        )
        assert "NOT_AI" in outcome.explanation
        assert "Gates triggered" in outcome.explanation
        assert "existing_capability_covers_it -> not_ai" in outcome.explanation
        assert "Instead:" in outcome.explanation

    def test_explanation_of_an_incomplete_case_lists_what_is_missing(self):
        scores = {**ARITHMETIC_SCORES, "data_readiness": None, "adoption_risk": None}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS, OWNED)
        assert "INCOMPLETE" in outcome.explanation
        assert "data_readiness" in outcome.explanation
        assert "adoption_risk" in outcome.explanation
