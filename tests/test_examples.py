"""Offline tests of the six reference exemplars.

These test the scoring ENGINE, not the model: each example carries a
hand-authored, anchor-faithful assessment, and the assertion is that the engine
turns it into the expected verdict. No provider is involved.
"""

from __future__ import annotations

from datetime import date

import pytest

from config import PATTERNS, RUBRIC
from contracts import issue_contract
from examples import load_examples
from scoring import Verdict, match_band, score

EXAMPLES = load_examples()
APPROVAL = date(2026, 4, 1)


def ids(examples):
    return [e.id for e in examples]


class TestTheExampleSetItself:
    def test_there_are_six_examples(self):
        assert len(EXAMPLES) == 6

    def test_the_required_verdicts_are_all_covered(self):
        verdicts = {e.expected_verdict for e in EXAMPLES}
        assert verdicts == {"go", "not_ai", "no_go", "incomplete"}

    def test_the_required_gates_are_all_demonstrated(self):
        gates = {e.expected_gate for e in EXAMPLES if e.expected_gate}
        assert gates == {
            "existing_capability_covers_it",
            "non_ai_alternative_suffices",
            "no_usable_data",
            "no_named_business_owner",
        }

    def test_every_example_scores_every_dimension_or_records_it_unknown(self):
        for example in EXAMPLES:
            scored = {
                entry.dimension_id
                for entry in example.reference_assessment.dimension_assessments
            }
            assert scored == set(RUBRIC.dimension_ids), example.id

    def test_every_scored_dimension_quotes_the_anchor_level_it_satisfies(self):
        """The exemplars must be defensible, not merely plausible."""
        for example in EXAMPLES:
            for entry in example.reference_assessment.dimension_assessments:
                if entry.score is not None:
                    assert f"Level {entry.score}" in entry.evidence, (
                        example.id,
                        entry.dimension_id,
                    )

    def test_unknown_scores_carry_low_confidence_and_say_what_is_missing(self):
        for example in EXAMPLES:
            for entry in example.reference_assessment.dimension_assessments:
                if entry.score is None:
                    assert entry.confidence.value == "low", example.id
                    assert entry.evidence.strip()

    def test_every_referenced_id_exists_in_the_config(self):
        archetypes = set(PATTERNS.archetype_ids)
        anti_patterns = {a.id for a in PATTERNS.anti_patterns}
        for example in EXAMPLES:
            assessment = example.reference_assessment
            if assessment.archetype_id:
                assert assessment.archetype_id in archetypes, example.id
            matched = {m.anti_pattern_id for m in assessment.anti_pattern_matches}
            assert matched <= anti_patterns, example.id

    def test_every_anti_pattern_match_quotes_the_request_verbatim(self):
        """The exemplars must satisfy the same evidentiary bar as the model."""
        from scoring import quote_is_supported

        for example in EXAMPLES:
            source = "\n".join(
                [
                    example.intake.request_text,
                    example.intake.process_description,
                    example.intake.stated_benefit or "",
                ]
            )
            for match in example.reference_assessment.anti_pattern_matches:
                assert quote_is_supported(match.quote, source), (
                    example.id,
                    match.anti_pattern_id,
                    match.quote,
                )


@pytest.mark.parametrize("example", EXAMPLES, ids=ids(EXAMPLES))
class TestEachExampleProducesItsExpectedVerdict:
    """Acceptance criterion: every example produces its expected verdict offline."""

    def test_verdict_matches(self, example):
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        assert outcome.verdict.value == example.expected_verdict

    def test_expected_gate_decides_the_verdict(self, example):
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        if example.expected_gate is None:
            assert outcome.triggered_gates == []
        else:
            # The first gate is the one that decided, by precedence.
            assert outcome.triggered_gate_ids[0] == example.expected_gate

    def test_a_contract_is_issued_only_for_go(self, example):
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        result = issue_contract(
            outcome, example.reference_assessment, example.intake, APPROVAL
        )
        if example.expected_verdict == "go":
            assert result.contract is not None
            assert result.contract.primary_metric_id
            assert result.contract.business_owner == example.intake.business_owner
        else:
            assert result.contract is None

    def test_the_explanation_is_populated(self, example):
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        assert outcome.explanation.strip()
        assert example.expected_verdict.upper() in outcome.explanation


class TestGatesDoTheWorkNotTheArithmetic:
    def test_the_data_gate_overrides_a_score_that_would_have_passed(self):
        """predict_laptop_failures is the clean demonstration: strong on every
        dimension except the one that is disqualifying."""
        example = next(e for e in EXAMPLES if e.id == "predict_laptop_failures")
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.weighted_total >= 3.5, (
            "this example demonstrates a gate overriding a passing score, but "
            f"it only totals {outcome.weighted_total}"
        )
        assert match_band(outcome.weighted_total, RUBRIC) is Verdict.GO

    def test_the_owner_gate_changes_the_reason_not_only_the_verdict(self):
        """contract_renewal_drafting scores 3.08, which would band as no_go
        anyway. The gate is still load-bearing: without it the requester is
        told "you scored 3.08", and with it they are told the one thing they
        can actually act on. Scored honestly rather than inflated to make the
        override dramatic."""
        example = next(e for e in EXAMPLES if e.id == "contract_renewal_drafting")
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        assert outcome.verdict is Verdict.NO_GO
        assert outcome.triggered_gate_ids == ["no_named_business_owner"]
        assert "no_named_business_owner" in outcome.explanation
        assert "named business owner" in outcome.explanation

    def test_the_incomplete_example_names_what_is_missing(self):
        example = next(e for e in EXAMPLES if e.expected_verdict == "incomplete")
        outcome = score(
            example.reference_assessment, RUBRIC, PATTERNS, example.intake
        )
        assert len(outcome.unknown_dimensions) > RUBRIC.completeness.max_unknown_dimensions
        assert outcome.weighted_total is None
