"""Tests for deterministic scoring. No live model, no network.

Every expected total below is hand-computed from the weights in rubric.yaml and
written out longhand in a comment, so a reader can check the arithmetic with a
calculator and catch a rubric edit that silently moved a verdict.

Weights as shipped:
    economic_impact 0.25 (higher)   process_frequency 0.15 (higher)
    data_maturity   0.20 (higher)   implementation_effort 0.15 (lower)
    regulatory_risk 0.10 (lower)    non_ai_alternative 0.15 (lower)
A `lower_is_better` raw score is flipped as 6 - raw before weighting.
"""

from __future__ import annotations

import pytest
import yaml

from config import RUBRIC_PATH, load_patterns, load_rubric
from schemas import Assessment, Confidence, DimensionAssessment
from scoring import Verdict, match_band, score

PATTERNS = load_patterns()
RUBRIC = load_rubric()

# The Phase 1.5/1.6 spike case, carried forward: a hospital wants discharge
# notes summarized, with five years of clean structured records.
GOLDEN_SCORES = {
    "economic_impact": 5,
    "process_frequency": 4,
    "data_maturity": 5,
    "implementation_effort": 3,
    "regulatory_risk": 4,
    "non_ai_alternative": 2,
}
#   5 x 0.25 = 1.25   |   4 x 0.15 = 0.60   |   5 x 0.20 = 1.00
#  (6-3)=3 x 0.15 = 0.45 | (6-4)=2 x 0.10 = 0.20 | (6-2)=4 x 0.15 = 0.60
#                                                     total = 4.10  -> go
GOLDEN_TOTAL = 4.10


def make_assessment(
    scores: dict[str, int | None],
    anti_pattern_ids: list[str] | None = None,
    archetype_id: str | None = "summarization",
) -> Assessment:
    """Build an Assessment from a {dimension_id: score} mapping."""
    return Assessment(
        archetype_id=archetype_id,
        anti_pattern_ids=anti_pattern_ids or [],
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=dimension_id,
                score=value,
                evidence=f"Interview evidence for {dimension_id}.",
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


def rubric_without_gate(tmp_path, gate_id: str):
    """Load a copy of the real rubric with one blocking gate deleted."""
    data = yaml.safe_load(RUBRIC_PATH.read_text())
    data["blocking_gates"] = [
        gate for gate in data["blocking_gates"] if gate["id"] != gate_id
    ]
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_rubric(path)


# Every dimension at its most favourable, used as the base for the gate tests:
# each one then spoils exactly one dimension, so the gate is provably what
# changed the verdict and not the arithmetic.
BEST_SCORES = {
    "economic_impact": 5,
    "process_frequency": 5,
    "data_maturity": 5,
    "implementation_effort": 1,
    "regulatory_risk": 1,
    "non_ai_alternative": 1,
}


class TestDirectionNormalization:
    """If direction were ignored, this case would total 2.00 instead of 2.80."""

    def test_all_raw_twos_totals_2_80(self):
        # Raw 2 everywhere. No gate fires (data_maturity 2 > 1,
        # regulatory_risk 2 < 5, non_ai_alternative 2 < 4), so this isolates
        # the arithmetic:
        #  2 x 0.25 = 0.50 | 2 x 0.15 = 0.30 | 2 x 0.20 = 0.40
        # (6-2)=4 x 0.15 = 0.60 | 4 x 0.10 = 0.40 | 4 x 0.15 = 0.60
        #                                            total = 2.80
        outcome = score(
            make_assessment(dict.fromkeys(RUBRIC.dimension_ids, 2)), RUBRIC, PATTERNS
        )
        assert outcome.triggered_gates == []
        assert outcome.weighted_total == pytest.approx(2.80)
        assert outcome.verdict is Verdict.NO_GO

    def test_lower_is_better_dimensions_are_flipped_in_the_breakdown(self):
        outcome = score(make_assessment(GOLDEN_SCORES), RUBRIC, PATTERNS)
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert (by_id["regulatory_risk"].raw_score, by_id["regulatory_risk"].normalized_score) == (4, 2)
        assert (by_id["economic_impact"].raw_score, by_id["economic_impact"].normalized_score) == (5, 5)


class TestVerdictBands:
    def test_golden_case_totals_4_10_and_goes(self):
        outcome = score(make_assessment(GOLDEN_SCORES), RUBRIC, PATTERNS)
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)
        assert outcome.verdict is Verdict.GO

    def test_exact_band_boundary_of_3_50_is_a_go(self):
        # 5 x 0.25 = 1.25 | 3 x 0.15 = 0.45 | 3 x 0.20 = 0.60
        # 3 x 0.15 = 0.45 | 3 x 0.10 = 0.30 | 3 x 0.15 = 0.45  -> exactly 3.50
        outcome = score(
            make_assessment(
                {
                    "economic_impact": 5,
                    "process_frequency": 3,
                    "data_maturity": 3,
                    "implementation_effort": 3,
                    "regulatory_risk": 3,
                    "non_ai_alternative": 3,
                }
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.weighted_total == pytest.approx(3.50)
        assert outcome.verdict is Verdict.GO

    def test_just_below_the_boundary_is_a_no_go(self):
        # As above but implementation_effort 4 -> (6-4)=2 x 0.15 = 0.30
        # 1.25 + 0.45 + 0.60 + 0.30 + 0.30 + 0.45 = 3.35
        outcome = score(
            make_assessment(
                {
                    "economic_impact": 5,
                    "process_frequency": 3,
                    "data_maturity": 3,
                    "implementation_effort": 4,
                    "regulatory_risk": 3,
                    "non_ai_alternative": 3,
                }
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.weighted_total == pytest.approx(3.35)
        assert outcome.verdict is Verdict.NO_GO

    @pytest.mark.parametrize(
        ("total", "expected"),
        [
            (1.0, Verdict.NO_GO),      # bottom of the scale, inclusive
            (3.499999, Verdict.NO_GO),  # just under the boundary
            (3.5, Verdict.GO),          # boundary belongs to the upper band
            (5.0, Verdict.GO),          # top of the scale, inclusive
        ],
    )
    def test_band_edges_directly(self, total, expected):
        assert match_band(total, RUBRIC) is expected

    def test_total_off_the_scale_raises(self):
        with pytest.raises(ValueError, match="outside every verdict band"):
            match_band(5.5, RUBRIC)


class TestNotAiGate:
    """not_ai is reachable only through gates — never through a band."""

    def test_hard_block_anti_pattern_overrides_an_otherwise_excellent_score(self):
        outcome = score(
            make_assessment(
                GOLDEN_SCORES, anti_pattern_ids=["deterministic_rule_suffices"]
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.verdict is Verdict.NOT_AI
        # The total is still reported, and still lands in the go band — which is
        # exactly the case that would slip through if not_ai were a low band.
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO
        assert outcome.triggered_gate_ids == ["not_ai_alternative_suffices"]
        assert outcome.triggered_gates[0].matched_anti_pattern_ids == [
            "deterministic_rule_suffices"
        ]

    def test_non_ai_alternative_threshold_fires_on_its_own(self):
        # No anti-patterns at all; only the dimension threshold (raw >= 4).
        # 1.25 + 0.60 + 1.00 + 0.45 + 0.20 + (6-4)=2 x 0.15 = 0.30 -> 3.80
        scores = {**GOLDEN_SCORES, "non_ai_alternative": 4}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.weighted_total == pytest.approx(3.80)
        assert outcome.triggered_gate_ids == ["not_ai_alternative_suffices"]
        assert outcome.triggered_gates[0].matched_anti_pattern_ids == []

    def test_non_ai_alternative_below_threshold_does_not_fire(self):
        scores = {**GOLDEN_SCORES, "non_ai_alternative": 3}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert outcome.triggered_gates == []
        assert outcome.verdict is not Verdict.NOT_AI

    def test_advisory_anti_pattern_does_not_force_not_ai(self):
        outcome = score(
            make_assessment(
                GOLDEN_SCORES, anti_pattern_ids=["chatbot_without_job_to_be_done"]
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO

    def test_data_does_not_exist_yet_is_advisory_not_a_hard_block(self):
        """It routes through the no_usable_data gate, not through not_ai."""
        outcome = score(
            make_assessment(
                GOLDEN_SCORES, anti_pattern_ids=["data_does_not_exist_yet"]
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO

    def test_gate_fires_even_when_the_interview_is_too_sparse_to_score(self):
        outcome = score(
            make_assessment(
                {"economic_impact": 5},
                anti_pattern_ids=["reporting_in_disguise"],
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.weighted_total is None

    def test_unknown_anti_pattern_id_is_reported_not_raised(self):
        outcome = score(
            make_assessment(GOLDEN_SCORES, anti_pattern_ids=["invented_by_the_model"]),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.ignored_anti_pattern_ids == ["invented_by_the_model"]
        assert outcome.verdict is Verdict.GO


class TestBlockingGates:
    """Phase 2.1: conditions too categorical for any weight to express.

    Each case scores every other dimension at its best, so the weighted total
    lands in the `go` band and only the gate can account for the verdict.
    """

    def test_no_usable_data_blocks_an_otherwise_perfect_case(self):
        # 5 x 0.25 = 1.25 | 5 x 0.15 = 0.75 | 1 x 0.20 = 0.20   <- the penalty
        # (6-1)=5 x 0.15 = 0.75 | 5 x 0.10 = 0.50 | 5 x 0.15 = 0.75
        #                                            total = 4.20 -> go band
        outcome = score(
            make_assessment({**BEST_SCORES, "data_maturity": 1}), RUBRIC, PATTERNS
        )
        assert outcome.weighted_total == pytest.approx(4.20)
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["no_usable_data"]
        assert "data_maturity scored 1" in outcome.triggered_gates[0].detail

    def test_unacceptable_regulatory_exposure_blocks_an_otherwise_perfect_case(self):
        # 1.25 + 0.75 + 1.00 + 0.75 + (6-5)=1 x 0.10 = 0.10 + 0.75
        #                                            total = 4.60 -> go band
        outcome = score(
            make_assessment({**BEST_SCORES, "regulatory_risk": 5}), RUBRIC, PATTERNS
        )
        assert outcome.weighted_total == pytest.approx(4.60)
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["unacceptable_regulatory_exposure"]

    def test_precedence_not_ai_outranks_no_go_and_both_are_reported(self):
        outcome = score(
            make_assessment(
                {**BEST_SCORES, "data_maturity": 1, "non_ai_alternative": 4}
            ),
            RUBRIC,
            PATTERNS,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == [
            "not_ai_alternative_suffices",
            "no_usable_data",
        ]
        assert outcome.triggered_gates[0].precedence < outcome.triggered_gates[1].precedence

    def test_a_gate_cannot_fire_on_an_unknown_dimension(self):
        outcome = score(
            make_assessment({**BEST_SCORES, "data_maturity": None}), RUBRIC, PATTERNS
        )
        assert outcome.triggered_gates == []
        assert outcome.unknown_dimensions == ["data_maturity"]
        # Every remaining dimension normalizes to 5, so renormalization gives 5.00.
        assert outcome.weighted_total == pytest.approx(5.00)
        assert outcome.verdict is Verdict.GO

    def test_deleting_a_gate_restores_band_behaviour(self, tmp_path):
        """Acceptance criterion 3 — config only, no Python edit."""
        no_data = make_assessment({**BEST_SCORES, "data_maturity": 1})
        assert score(no_data, RUBRIC, PATTERNS).verdict is Verdict.NO_GO

        without = rubric_without_gate(tmp_path, "no_usable_data")
        outcome = score(no_data, without, PATTERNS)
        assert outcome.triggered_gates == []
        assert outcome.weighted_total == pytest.approx(4.20)
        assert outcome.verdict is Verdict.GO

    def test_gate_explanation_names_the_gate_and_its_reason(self):
        outcome = score(
            make_assessment({**BEST_SCORES, "regulatory_risk": 5}), RUBRIC, PATTERNS
        )
        assert "unacceptable_regulatory_exposure -> no_go" in outcome.explanation
        assert "regulatory_risk scored 5" in outcome.explanation
        assert "compliance and legal path" in outcome.explanation


class TestCompleteness:
    def test_one_unknown_still_scores_with_renormalized_weights(self):
        # process_frequency unknown; every remaining dimension normalizes to 4,
        # so the renormalized weights must still produce exactly 4.00.
        scores = {
            "economic_impact": 4,
            "process_frequency": None,
            "data_maturity": 4,
            "implementation_effort": 2,  # -> 4
            "regulatory_risk": 2,  # -> 4
            "non_ai_alternative": 2,  # -> 4
        }
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert outcome.unknown_dimensions == ["process_frequency"]
        assert outcome.weighted_total == pytest.approx(4.00)
        assert outcome.verdict is Verdict.GO
        assert sum(c.effective_weight for c in outcome.contributions) == pytest.approx(1.0)

    def test_too_many_unknowns_refuses_to_produce_a_verdict(self):
        scores = {**GOLDEN_SCORES, "data_maturity": None, "regulatory_risk": None}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert outcome.verdict is Verdict.INCOMPLETE
        assert outcome.weighted_total is None
        assert outcome.contributions == []
        assert set(outcome.unknown_dimensions) == {"data_maturity", "regulatory_risk"}

    def test_a_dimension_absent_entirely_counts_as_unknown(self):
        scores = {k: v for k, v in GOLDEN_SCORES.items() if k != "data_maturity"}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert outcome.unknown_dimensions == ["data_maturity"]
        assert outcome.verdict is Verdict.GO  # one unknown is within the limit

    def test_everything_unknown_is_incomplete_even_if_the_limit_allows_it(
        self, tmp_path
    ):
        """Guards the divide-by-zero when no dimension has a score."""
        permissive = rubric_with(tmp_path, completeness={"max_unknown_dimensions": 6})
        outcome = score(
            make_assessment(dict.fromkeys(RUBRIC.dimension_ids, None)),
            permissive,
            PATTERNS,
        )
        assert outcome.verdict is Verdict.INCOMPLETE
        assert outcome.weighted_total is None

    def test_unknown_scores_are_never_invented(self):
        scores = {**GOLDEN_SCORES, "data_maturity": None}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert "data_maturity" not in {c.dimension_id for c in outcome.contributions}


class TestMalformedAssessments:
    def test_unknown_dimension_id_is_ignored_and_reported(self):
        assessment = make_assessment({**GOLDEN_SCORES, "vibes": 5})
        outcome = score(assessment, RUBRIC, PATTERNS)
        assert outcome.ignored_dimension_ids == ["vibes"]
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)

    def test_duplicate_dimension_entries_keep_the_first(self):
        assessment = make_assessment(GOLDEN_SCORES)
        assessment.dimension_assessments.append(
            DimensionAssessment(
                dimension_id="economic_impact",
                score=1,
                evidence="a contradictory second opinion",
                confidence=Confidence.LOW,
            )
        )
        outcome = score(assessment, RUBRIC, PATTERNS)
        assert outcome.ignored_dimension_ids == ["economic_impact"]
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)


class TestConfigDrivesTheVerdict:
    """Acceptance criterion 3: YAML edits change verdicts with no code change."""

    def test_moving_a_band_flips_the_golden_case_to_no_go(self, tmp_path):
        stricter = rubric_with(
            tmp_path,
            verdict_bands=[
                {"verdict": "no_go", "lower": 1.0, "upper": 4.5, "upper_inclusive": False},
                {"verdict": "go", "lower": 4.5, "upper": 5.0, "upper_inclusive": True},
            ],
        )
        outcome = score(make_assessment(GOLDEN_SCORES), stricter, PATTERNS)
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)
        assert outcome.verdict is Verdict.NO_GO

    def test_reweighting_flips_the_golden_case_to_no_go(self, tmp_path):
        # Shift weight onto regulatory_risk, where this case scores worst.
        # 5 x 0.05 = 0.25 | 4 x 0.10 = 0.40 | 5 x 0.15 = 0.75
        # 3 x 0.10 = 0.30 | 2 x 0.45 = 0.90 | 4 x 0.15 = 0.60  -> 3.20
        new_weights = {
            "economic_impact": 0.05,
            "process_frequency": 0.10,
            "data_maturity": 0.15,
            "implementation_effort": 0.10,
            "regulatory_risk": 0.45,
            "non_ai_alternative": 0.15,
        }
        data = yaml.safe_load(RUBRIC_PATH.read_text())
        for dimension in data["dimensions"]:
            dimension["weight"] = new_weights[dimension["id"]]
        path = tmp_path / "rubric.yaml"
        path.write_text(yaml.safe_dump(data))
        reweighted = load_rubric(path)

        outcome = score(make_assessment(GOLDEN_SCORES), reweighted, PATTERNS)
        assert outcome.weighted_total == pytest.approx(3.20)
        assert outcome.verdict is Verdict.NO_GO


class TestGoldenPathEndToEnd:
    def test_full_outcome_of_the_golden_case(self):
        outcome = score(make_assessment(GOLDEN_SCORES), RUBRIC, PATTERNS)

        assert outcome.verdict is Verdict.GO
        assert outcome.weighted_total == pytest.approx(GOLDEN_TOTAL)
        assert outcome.triggered_gates == []
        assert outcome.unknown_dimensions == []
        assert outcome.ignored_dimension_ids == []
        assert outcome.ignored_anti_pattern_ids == []

        assert [c.dimension_id for c in outcome.contributions] == RUBRIC.dimension_ids
        assert [c.contribution for c in outcome.contributions] == pytest.approx(
            [1.25, 0.60, 1.00, 0.45, 0.20, 0.60]
        )
        assert sum(c.contribution for c in outcome.contributions) == pytest.approx(
            GOLDEN_TOTAL
        )
        for contribution in outcome.contributions:
            assert contribution.effective_weight == pytest.approx(contribution.weight)

        assert "GO" in outcome.explanation
        assert "4.10" in outcome.explanation
        assert "Interview evidence for economic_impact." in outcome.explanation

    def test_explanation_of_a_gated_case_names_the_alternative(self):
        outcome = score(
            make_assessment(GOLDEN_SCORES, anti_pattern_ids=["rpa_relabeled"]),
            RUBRIC,
            PATTERNS,
        )
        assert "NOT_AI" in outcome.explanation
        assert "Gates triggered" in outcome.explanation
        assert "not_ai_alternative_suffices -> not_ai" in outcome.explanation
        assert "Instead:" in outcome.explanation

    def test_explanation_of_an_incomplete_case_lists_what_is_missing(self):
        scores = {**GOLDEN_SCORES, "data_maturity": None, "regulatory_risk": None}
        outcome = score(make_assessment(scores), RUBRIC, PATTERNS)
        assert "INCOMPLETE" in outcome.explanation
        assert "data_maturity" in outcome.explanation
        assert "regulatory_risk" in outcome.explanation
