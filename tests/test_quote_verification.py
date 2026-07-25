"""Tests for the evidentiary bar on anti-pattern matches. No model involved.

A gate is non-compensable: an error in a weighted dimension moves the total by
tenths and is absorbed by the other six, while an error in a gate decides the
verdict and cannot be outvoted. So a hard-block gate may not fire on a match
the model cannot show you in the request text (ADR-020).
"""

from __future__ import annotations

import pytest

from config import PATTERNS, RUBRIC
from schemas import (
    AntiPatternMatch,
    Assessment,
    Confidence,
    DimensionAssessment,
    RequestIntake,
)
from scoring import Verdict, quote_is_supported, score

REQUEST = (
    "We keep answering the same policy questions by email.\n"
    "IT told us the assistant bundled with our current licence tier\n"
    "already searches this document library, but nobody has tried it."
)

INTAKE = RequestIntake(
    request_text=REQUEST,
    requesting_area="HR",
    business_owner="Marcos Pena",
    process_description="Answered by hand from PDFs.",
)

GOOD_SCORES = {
    "business_value": 4,
    "adoption_risk": 2,
    "data_readiness": 4,
    "process_frequency": 4,
    "implementation_effort": 2,
    "data_governance": 2,
    "non_ai_alternative": 2,
}


def assessment_with(quote: str, anti_pattern_id="existing_licensed_capability"):
    """A would-be `go` carrying one anti-pattern match with the given quote."""
    return Assessment(
        archetype_id="rag_qa",
        anti_pattern_matches=[
            AntiPatternMatch(
                anti_pattern_id=anti_pattern_id,
                quote=quote,
                quote_confidence=Confidence.HIGH,
            )
        ],
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=key,
                score=value,
                evidence=f"Evidence for {key}.",
                confidence=Confidence.HIGH,
            )
            for key, value in GOOD_SCORES.items()
        ],
    )


class TestQuoteIsSupported:
    """The predicate itself, in isolation."""

    def test_exact_match(self):
        assert quote_is_supported("already searches this document library", REQUEST)

    def test_case_differences_still_match(self):
        assert quote_is_supported("ALREADY SEARCHES THIS DOCUMENT LIBRARY", REQUEST)

    def test_whitespace_and_line_wrapping_differences_still_match(self):
        # The source wraps between "tier" and "already"; the quote does not.
        assert quote_is_supported(
            "our current licence tier already searches", REQUEST
        )

    def test_a_paraphrase_does_not_match(self):
        assert not quote_is_supported(
            "the licensed tool can already search the documents", REQUEST
        )

    def test_a_single_swapped_word_does_not_match(self):
        assert not quote_is_supported(
            "already indexes this document library", REQUEST
        )

    @pytest.mark.parametrize("empty", ["", "   ", "\n\t "])
    def test_an_empty_quote_never_matches(self, empty):
        assert not quote_is_supported(empty, REQUEST)

    def test_a_fabricated_quote_does_not_match(self):
        assert not quote_is_supported(
            "we already pay for a platform that does exactly this", REQUEST
        )


class TestGateFiringRequiresASupportedQuote:
    """Acceptance criteria 2 and 3, end to end through score()."""

    def test_a_verbatim_quote_fires_the_gate(self):
        outcome = score(
            assessment_with("already searches this document library"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == ["existing_capability_covers_it"]
        assert outcome.unsupported_anti_patterns == []

    def test_a_case_and_whitespace_variant_still_fires(self):
        outcome = score(
            assessment_with("OUR CURRENT LICENCE TIER   already searches"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.unsupported_anti_patterns == []

    def test_a_paraphrase_does_not_fire_and_is_reported(self):
        outcome = score(
            assessment_with("the licensed tool can already do this"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO
        assert [u.anti_pattern_id for u in outcome.unsupported_anti_patterns] == [
            "existing_licensed_capability"
        ]
        assert "does not appear" in outcome.unsupported_anti_patterns[0].reason

    def test_an_empty_quote_does_not_fire_and_is_reported(self):
        outcome = score(assessment_with("   "), RUBRIC, PATTERNS, INTAKE)
        assert outcome.triggered_gates == []
        assert outcome.unsupported_anti_patterns[0].reason == "empty quote"

    def test_a_fabricated_quote_never_fires_a_gate(self):
        """Acceptance criterion 2."""
        outcome = score(
            assessment_with("we already pay for a platform that does exactly this"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO
        assert len(outcome.unsupported_anti_patterns) == 1
        assert (
            outcome.unsupported_anti_patterns[0].quote
            == "we already pay for a platform that does exactly this"
        )

    def test_the_discarded_match_is_named_in_the_explanation(self):
        outcome = score(
            assessment_with("a completely invented sentence"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert "DISCARDED" in outcome.explanation
        assert "a completely invented sentence" in outcome.explanation

    def test_a_quote_may_come_from_the_process_description(self):
        outcome = score(
            assessment_with("Answered by hand from PDFs."), RUBRIC, PATTERNS, INTAKE
        )
        assert outcome.verdict is Verdict.NOT_AI

    def test_without_an_intake_no_quote_can_be_verified(self):
        """Absence of a request is not evidence that a quote is genuine."""
        outcome = score(
            assessment_with("already searches this document library"),
            RUBRIC,
            PATTERNS,
            intake=None,
        )
        assert outcome.triggered_gates == []
        assert "could not be verified" in outcome.unsupported_anti_patterns[0].reason


class TestDimensionEvidenceKeepsTheLowerBar:
    """The asymmetry is the point: dimension evidence is NOT verified."""

    def test_free_form_dimension_evidence_is_accepted(self):
        assessment = assessment_with("already searches this document library")
        for entry in assessment.dimension_assessments:
            entry.evidence = "A paraphrase that appears nowhere in the request."
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        # Scored normally: every dimension still contributes.
        assert len(outcome.contributions) == len(RUBRIC.dimension_ids)


class TestRequiresHumanConfirmation:
    """Acceptance criterion 4."""

    def test_a_hard_block_anti_pattern_gate_requires_confirmation(self):
        outcome = score(
            assessment_with("already searches this document library"),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.requires_human_confirmation is True
        assert "already searches this document library" in outcome.confirmation_reason
        assert "existing_licensed_capability" in outcome.confirmation_reason

    def test_a_dimension_threshold_gate_does_not_require_confirmation(self):
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "data_readiness":
                entry.score = 1
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.triggered_gate_ids == ["no_usable_data"]
        assert outcome.requires_human_confirmation is False
        assert outcome.confirmation_reason is None

    def test_an_intake_field_gate_does_not_require_confirmation(self):
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        ownerless = INTAKE.model_copy(update={"business_owner": ""})
        outcome = score(assessment, RUBRIC, PATTERNS, ownerless)
        assert outcome.triggered_gate_ids == ["no_named_business_owner"]
        assert outcome.requires_human_confirmation is False

    def test_a_clean_go_requires_no_confirmation(self):
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.verdict is Verdict.GO
        assert outcome.requires_human_confirmation is False

    def test_a_gate_with_both_bases_does_not_require_confirmation(self):
        """non_ai_alternative >= 4 is deterministic even when an anti-pattern
        also contributed, so the verdict stands on its own."""
        assessment = assessment_with(
            "already searches this document library",
            anti_pattern_id="reporting_in_disguise",
        )
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "non_ai_alternative":
                entry.score = 5
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        deciding = outcome.triggered_gates[0]
        assert deciding.gate_id == "non_ai_alternative_suffices"
        assert deciding.deterministic_basis is True
        assert outcome.requires_human_confirmation is False
