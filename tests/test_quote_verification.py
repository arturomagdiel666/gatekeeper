"""Tests for the evidentiary bar on anti-pattern matches. No model involved.

A gate is non-compensable: an error in a weighted dimension moves the total by
tenths and is absorbed by the other six, while an error in a gate decides the
verdict and cannot be outvoted. So a hard-block gate may not fire on a match
the model cannot show you in the request text (ADR-020).
"""

from __future__ import annotations

import pytest
import yaml

from config import PATTERNS, RUBRIC, RUBRIC_PATH, load_rubric
from schemas import (
    DataSensitivity,
    DeterministicArtefact,
    Period,
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
    # non_ai_alternative is derived from this list (ADR-030). One COMPLETING
    # entry means the derivation defers to the reader for levels 3-5, so each
    # fixture's own non_ai_alternative score stands and these tests keep
    # exercising what they were written for. The absent/empty/none-completing
    # branches have their own tests.
    existing_deterministic_artefacts=[
        DeterministicArtefact(
            name="A weekly report",
            what_it_does="closes out some of these cases on its own",
            completes_without_judgement=True,
        )
    ],
)

#: A verbatim Part B span from REQUEST: somebody has already said the licensed
#: tool covers this job. Part A — naming the licence tier — is the other half.
PART_B = "already searches this document library"

GOOD_SCORES = {
    "business_value": 4,
    "adoption_risk": 2,
    "data_readiness": 4,
    "process_frequency": 4,
    "implementation_effort": 2,
    "data_governance": 2,
    "non_ai_alternative": 2,
}


def assessment_with(
    quote: str,
    anti_pattern_id="existing_licensed_capability",
    second_quote: str | None = PART_B,
):
    """A would-be `go` carrying one anti-pattern match with the given quote.

    ``second_quote`` defaults to a verbatim Part B span, because
    existing_licensed_capability is a two-part test and a match quoting
    only Part A is discarded (ADR-029). Pass ``None`` to exercise that.
    """
    return Assessment(
        archetype_id="rag_qa",
        anti_pattern_matches=[
            AntiPatternMatch(
                anti_pattern_id=anti_pattern_id,
                quote=quote,
                second_quote=second_quote,
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

    def test_a_dimension_threshold_on_a_judged_dimension_now_requires_it(self):
        """INVERTED by ADR-028, and this is the test that used to say otherwise.

        It asserted that a threshold gate never needs confirmation, because a
        threshold is deterministic given the assessment. It is — and the
        agreement study showed that deterministic is not the same as reliable.
        `data_readiness` agreed at 80%, and level 1, the gated value, is exactly
        where the dimension was found answering two questions with one number.
        """
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "data_readiness":
                entry.score = 1
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.triggered_gate_ids == ["no_usable_data"]
        assert outcome.requires_human_confirmation is True
        assert "data_readiness scored 1" in outcome.confirmation_reason
        assert "dimension_threshold" in outcome.confirmation_reason

    def test_the_flag_is_reported_per_condition_not_per_gate(self):
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "data_governance":
                entry.score = 5
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        gate = outcome.triggered_gates[0]
        assert gate.gate_id == "unacceptable_data_governance"
        assert [c.kind for c in gate.fired_conditions] == ["dimension_threshold"]
        # Set false in the config, against the type default of true, because the
        # dimension agreed at 100% — with the objection recorded in rubric.yaml
        # that the derivation cannot produce the gated value of 5 at all.
        assert gate.fired_conditions[0].requires_human_confirmation is False
        assert outcome.requires_human_confirmation is False

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

    def test_a_gate_whose_two_fired_conditions_both_need_review_needs_review(self):
        """Also INVERTED by ADR-028.

        This case — `non_ai_alternative` at 5 with a hard-block anti-pattern
        alongside it — used to be waved through because the threshold was
        "deterministic". Both conditions are now judgements: the threshold fired
        every `not_ai` in the study on a dimension that agreed 70% of the time,
        and the anti-pattern is a reading of the world. `deterministic_basis` is
        still true and is now purely informational.
        """
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
        assert deciding.deterministic_basis is True, "still reported, no longer decisive"
        assert [c.kind for c in deciding.fired_conditions] == [
            "dimension_threshold",
            "anti_pattern",
        ]
        assert all(c.requires_human_confirmation for c in deciding.fired_conditions)
        assert outcome.requires_human_confirmation is True
        assert "non_ai_alternative scored 5" in outcome.confirmation_reason
        assert "reporting_in_disguise" in outcome.confirmation_reason


class TestDeterministicDerivation:
    """Acceptance criterion 5: stated facts are computed, not re-inferred."""

    def _assessment(self, **overrides):
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id in overrides:
                entry.score = overrides[entry.dimension_id]
        return assessment

    def test_process_frequency_is_derived_when_volume_is_stated(self):
        # 3 times a week = 156 a year, which is the level 3 band — regardless
        # of the model saying 4.
        intake = INTAKE.model_copy(
            update={"times_per_period": 3, "period": Period.WEEK}
        )
        outcome = score(
            self._assessment(process_frequency=4), RUBRIC, PATTERNS, intake
        )
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert by_id["process_frequency"].raw_score == 3
        assert "process_frequency" in outcome.derived_dimensions
        assert "156 instances a year" in by_id["process_frequency"].evidence

    def test_process_frequency_is_model_scored_when_volume_is_absent(self):
        outcome = score(self._assessment(process_frequency=4), RUBRIC, PATTERNS, INTAKE)
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert by_id["process_frequency"].raw_score == 4
        assert "process_frequency" not in outcome.derived_dimensions

    @pytest.mark.parametrize(
        ("sensitivity", "expected"),
        [
            (DataSensitivity.PUBLIC, 1),
            (DataSensitivity.INTERNAL, 2),
            (DataSensitivity.CONFIDENTIAL, 3),
            (DataSensitivity.REGULATED, 4),
        ],
    )
    def test_data_governance_is_derived_from_the_classification(
        self, sensitivity, expected
    ):
        intake = INTAKE.model_copy(update={"data_sensitivity": sensitivity})
        outcome = score(self._assessment(data_governance=5), RUBRIC, PATTERNS, intake)
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert by_id["data_governance"].raw_score == expected
        assert "data_governance" in outcome.derived_dimensions

    def test_unknown_classification_returns_the_dimension_to_the_model(self):
        outcome = score(self._assessment(data_governance=3), RUBRIC, PATTERNS, INTAKE)
        by_id = {c.dimension_id: c for c in outcome.contributions}
        assert by_id["data_governance"].raw_score == 3
        assert "data_governance" not in outcome.derived_dimensions

    def test_a_derived_score_can_stop_a_gate_the_model_would_have_fired(self):
        """The model said 5 (may not be processed); the form says internal."""
        intake = INTAKE.model_copy(
            update={"data_sensitivity": DataSensitivity.INTERNAL}
        )
        assert (
            score(self._assessment(data_governance=5), RUBRIC, PATTERNS, INTAKE)
            .triggered_gate_ids == ["unacceptable_data_governance"]
        )
        outcome = score(self._assessment(data_governance=5), RUBRIC, PATTERNS, intake)
        assert outcome.triggered_gates == []
        assert outcome.verdict is Verdict.GO

    def test_derivations_are_skipped_entirely_without_an_intake(self):
        outcome = score(self._assessment(), RUBRIC, PATTERNS, intake=None)
        assert outcome.derived_dimensions == []


class TestConfirmationFollowsTheConditionThatFired:
    """ADR-028: the flag moved from the gate to the condition.

    These build temp rubrics, so they also demonstrate the point of moving it:
    the reliability of a gate is now retunable in YAML, with no Python edit.
    """

    def rubric_with(self, tmp_path, mutate) -> object:
        """The shipped rubric with one gate condition altered."""
        data = yaml.safe_load(RUBRIC_PATH.read_text())
        mutate({gate["id"]: gate for gate in data["blocking_gates"]})
        path = tmp_path / "rubric.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        return load_rubric(path)

    def gated_assessment(self):
        """A would-be `go` spoiled only by non_ai_alternative, which gates."""
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "non_ai_alternative":
                entry.score = 4
        return assessment

    def test_as_shipped_the_non_ai_threshold_needs_confirmation(self):
        outcome = score(self.gated_assessment(), RUBRIC, PATTERNS, INTAKE)
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.triggered_gate_ids == ["non_ai_alternative_suffices"]
        assert outcome.requires_human_confirmation is True

    def test_flipping_one_line_of_yaml_changes_the_outcome(self, tmp_path):
        """No Python edit. The whole reason the flag lives in config."""

        def mutate(gates):
            for condition in gates["non_ai_alternative_suffices"]["any_of"]:
                if condition["type"] == "dimension_threshold":
                    condition["requires_human_confirmation"] = False

        relaxed = self.rubric_with(tmp_path, mutate)
        outcome = score(self.gated_assessment(), relaxed, PATTERNS, INTAKE)
        assert outcome.verdict is Verdict.NOT_AI, "the verdict is unaffected"
        assert outcome.requires_human_confirmation is False
        assert outcome.confirmation_reason is None

    def test_one_self_standing_condition_carries_a_mixed_gate(self, tmp_path):
        """Two conditions fire; only one needs review, so the verdict stands.

        This is the case a per-GATE flag could not express, and the reason the
        move was structurally blocked before it was made.
        """

        def mutate(gates):
            gates["no_usable_data"]["any_of"].append(
                {
                    "type": "intake_field",
                    "requires_human_confirmation": False,
                    "field": "business_owner",
                    "predicate": "is_present",
                }
            )

        mixed = self.rubric_with(tmp_path, mutate)
        assessment = assessment_with("already searches this document library")
        assessment.anti_pattern_matches = []
        for entry in assessment.dimension_assessments:
            if entry.dimension_id == "data_readiness":
                entry.score = 1
        # INTAKE names an owner, so both conditions of the mutated gate fire.
        outcome = score(assessment, mixed, PATTERNS, INTAKE)
        gate = outcome.triggered_gates[0]
        assert [c.requires_human_confirmation for c in gate.fired_conditions] == [
            True,
            False,
        ]
        assert outcome.requires_human_confirmation is False

    def test_an_unset_flag_takes_the_type_default(self, tmp_path):
        """Cautious by type: a threshold on a judged dimension defaults to true."""

        def mutate(gates):
            for condition in gates["non_ai_alternative_suffices"]["any_of"]:
                condition.pop("requires_human_confirmation", None)

        defaulted = self.rubric_with(tmp_path, mutate)
        condition = next(
            c
            for g in defaulted.blocking_gates
            if g.id == "non_ai_alternative_suffices"
            for c in g.any_of
            if c.type == "dimension_threshold"
        )
        assert condition.requires_human_confirmation is None
        assert condition.confirmation_required is True
        outcome = score(self.gated_assessment(), defaulted, PATTERNS, INTAKE)
        assert outcome.requires_human_confirmation is True

    def test_the_shipped_config_sets_every_gate_condition_explicitly(self):
        """Each entry is a measured decision, so none of them should be implicit."""
        for gate in RUBRIC.blocking_gates:
            for condition in gate.any_of:
                assert condition.requires_human_confirmation is not None, gate.id


class TestTwoPartEvidence:
    """ADR-029: half a two-part test is not evidence.

    existing_licensed_capability agreed 0% across BOTH scorer runs, on the
    highest-precedence gate. In run 1 it decided nothing because the threshold
    gate shadowed it; in run 2, after that gate stopped firing so often, it
    decided half of all verdict disagreements. One scorer matched it 10 times
    under a rule it invented for itself; the other, zero times. Both readings
    were supported by the old signals.
    """

    def test_a_platform_named_only_as_a_data_source_does_not_match(self):
        """The exact error being ruled out, and the cause of the 10-versus-0 split."""
        intake = RequestIntake(
            request_text=(
                "We want an agent to summarise the weekly pipeline. "
                "The data all lives in Salesforce."
            ),
            requesting_area="Sales",
            business_owner="Ana Ruiz",
            process_description="A manager builds it by hand each Monday.",
        )
        assessment = assessment_with(
            "The data all lives in Salesforce", second_quote=None
        )
        outcome = score(assessment, RUBRIC, PATTERNS, intake)
        assert outcome.triggered_gate_ids == [], "no gate may fire on Part A alone"
        discarded = outcome.unsupported_anti_patterns[0]
        assert discarded.anti_pattern_id == "existing_licensed_capability"
        assert "second_quote is missing" in discarded.reason

    def test_a_quoted_claim_that_the_tool_covers_it_does_match(self):
        """Part B present and verbatim: the gate fires, as it should."""
        outcome = score(
            assessment_with("our current licence tier", second_quote=PART_B),
            RUBRIC,
            PATTERNS,
            INTAKE,
        )
        assert outcome.triggered_gate_ids[0] == "existing_capability_covers_it"
        assert outcome.verdict is Verdict.NOT_AI
        assert outcome.unsupported_anti_patterns == []

    def test_a_fabricated_second_quote_is_rejected_like_a_fabricated_first(self):
        assessment = assessment_with(
            "already searches this document library",
            second_quote="the vendor confirmed it is covered",
        )
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.triggered_gates == []
        assert "not in the request text" in outcome.unsupported_anti_patterns[0].reason

    def test_a_one_part_anti_pattern_still_needs_only_one_quote(self):
        """The four anti-patterns at 100% agreement are untouched."""
        assessment = assessment_with(
            "already searches this document library",
            anti_pattern_id="reporting_in_disguise",
            second_quote=None,
        )
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.unsupported_anti_patterns == []
        assert outcome.triggered_gate_ids == ["non_ai_alternative_suffices"]

    def test_the_discarded_match_leaves_the_case_scored_on_its_dimensions(self):
        """Nothing is lost: the signal moves to a compensable dimension.

        non_ai_alternative already carries "an already-licensed capability solves
        it" at its top level, so a request whose licence claim cannot be quoted
        is scored there like any other rather than gated on an unreproducible
        judgement.
        """
        assessment = assessment_with("our current licence tier", second_quote=None)
        outcome = score(assessment, RUBRIC, PATTERNS, INTAKE)
        assert outcome.verdict is Verdict.GO, "GOOD_SCORES with no gate firing"
        assert len(outcome.contributions) == len(RUBRIC.dimension_ids)
        assert outcome.weighted_total is not None
