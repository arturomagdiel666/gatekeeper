"""Tests for the LLM-facing structured-output models.

The important assertions here are negative: what must NOT be in the schema.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from config import load_rubric
from schemas import (
    DeterministicArtefact,
    SCORE_MAX,
    SCORE_MIN,
    Assessment,
    Confidence,
    DimensionAssessment,
    RequestIntake,
    banned_synonyms,
)


_ENTRY = DimensionAssessment(
    dimension_id="business_value", score=3, evidence="e", confidence=Confidence.LOW
)


def property_names(schema: dict) -> set[str]:
    """Every property name anywhere in a JSON Schema, including nested defs."""
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                found.update(properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return found


class TestNoVerdictOrTotalAnywhere:
    """Acceptance criterion 6.

    The model scores dimensions and cites evidence; Python decides. A verdict
    field would invite it to pick the conclusion first and reason backwards.
    """

    def test_no_field_mentions_a_verdict_or_a_total(self):
        names = property_names(Assessment.model_json_schema())
        assert names, "schema produced no properties — the walk is broken"
        offenders = [
            name
            for name in names
            if any(
                banned in name.lower()
                for banned in ("verdict", "total", "score_sum", "decision")
            )
        ]
        assert offenders == []

    def test_the_walk_would_actually_catch_a_nested_offender(self):
        """Guard against the previous test passing because the walk is inert."""
        assert "evidence" in property_names(Assessment.model_json_schema())


class TestAssessmentValidation:
    def test_the_load_bearing_fields_are_required(self):
        """A schema that does not demand the work does not get the work.

        Pydantic omits any field with a default from the JSON Schema's
        `required` list, and grammar-constrained decoding will then satisfy the
        schema with `{}`. The first live run returned exactly that. These three
        fields therefore carry no default.
        """
        assert set(Assessment.model_json_schema()["required"]) == {
            "archetype_id",
            "anti_pattern_matches",
            "dimension_assessments",
        }
        with pytest.raises(ValidationError):
            Assessment()

    def test_an_assessment_with_the_required_fields_is_valid(self):
        assessment = Assessment(
            archetype_id=None,
            anti_pattern_matches=[],
            dimension_assessments=[
                DimensionAssessment(
                    dimension_id="business_value",
                    score=3,
                    evidence="e",
                    confidence=Confidence.LOW,
                )
            ],
        )
        assert assessment.proposed_metric_id is None

    def test_extra_fields_are_forbidden(self):
        """A hallucinated verdict field must fail loudly, not be ignored."""
        with pytest.raises(ValidationError):
            Assessment.model_validate({"verdict": "go"})

    def test_extra_fields_are_forbidden_on_a_dimension(self):
        with pytest.raises(ValidationError):
            DimensionAssessment.model_validate(
                {
                    "dimension_id": "business_value",
                    "score": 4,
                    "evidence": "e",
                    "confidence": "high",
                    "weighted_total": 4.1,
                }
            )

    def test_score_may_be_unknown(self):
        entry = DimensionAssessment(
            dimension_id="data_readiness",
            score=None,
            evidence="The interviewee did not know.",
            confidence=Confidence.LOW,
        )
        assert entry.score is None

    @pytest.mark.parametrize("bad_score", [0, 6, -1, 99])
    def test_scores_outside_the_scale_are_rejected(self, bad_score):
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension_id="data_readiness",
                score=bad_score,
                evidence="e",
                confidence=Confidence.HIGH,
            )

    def test_confidence_is_restricted_to_the_enum(self):
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension_id="data_readiness",
                score=3,
                evidence="e",
                confidence="pretty sure",
            )


def test_score_bounds_match_the_rubric_scale():
    """Catch drift between the static schema bounds and the tunable rubric."""
    scale = load_rubric().scale
    assert (SCORE_MIN, SCORE_MAX) == (scale.min, scale.max)


class TestRequestIntake:
    def test_minimal_intake_needs_only_request_text(self):
        intake = RequestIntake(request_text="We want an agent.")
        assert intake.business_owner == ""
        assert intake.stated_benefit is None

    def test_extra_fields_are_forbidden(self):
        with pytest.raises(ValidationError):
            RequestIntake(request_text="x", budget="lots")


class TestMetricProposalFields:
    """The model's only role in the Measurement Contract."""

    def test_metric_proposal_is_optional(self):
        """Omitting these accepts the archetype default and an unmeasured
        baseline, both of which are valid outcomes — unlike omitting a score."""
        assessment = Assessment(
            archetype_id=None, anti_pattern_matches=[],
            dimension_assessments=[_ENTRY],
        )
        assert assessment.proposed_metric_id is None
        assert assessment.stated_baseline_value is None

    def test_metric_proposal_round_trips(self):
        assessment = Assessment(
            archetype_id=None, anti_pattern_matches=[],
            dimension_assessments=[_ENTRY],
            proposed_metric_id="hours_reclaimed_per_month",
            stated_baseline_value=120.0,
        )
        assert assessment.proposed_metric_id == "hours_reclaimed_per_month"
        assert assessment.stated_baseline_value == 120.0


class TestBannedSynonymList:
    def test_every_banned_word_is_lower_case_and_non_empty(self):
        assert banned_synonyms()
        for word in banned_synonyms():
            assert word == word.lower()
            assert word.strip()

    def test_no_banned_word_is_itself_a_field_name(self):
        """A field name must never appear on its own banned list."""
        names = property_names(Assessment.model_json_schema())
        assert names.isdisjoint(set(banned_synonyms()))


class TestDeterministicArtefacts:
    """ADR-030: non_ai_alternative's input. Three states, all distinct."""

    def test_absent_and_empty_are_different_answers(self):
        """The distinction the derivation turns on, so it must survive the model."""
        assert RequestIntake(request_text="x").existing_deterministic_artefacts is None
        asked = RequestIntake(request_text="x", existing_deterministic_artefacts=[])
        assert asked.existing_deterministic_artefacts == []

    def test_an_entry_carries_a_name_a_description_and_a_completion_flag(self):
        artefact = DeterministicArtefact(
            name="Keyword routing rules",
            what_it_does="route about half of the tickets on their own",
            completes_without_judgement=True,
        )
        intake = RequestIntake(
            request_text="x", existing_deterministic_artefacts=[artefact]
        )
        assert intake.existing_deterministic_artefacts[0].completes_without_judgement

    def test_the_completion_flag_is_required(self):
        """It is the only field that asks for an assessment; a default would let
        the form skip the one question the level turns on."""
        with pytest.raises(ValidationError):
            DeterministicArtefact(name="A report", what_it_does="counts tickets")

    def test_the_user_message_renders_all_three_states_distinguishably(self):
        from assess import build_user_message

        absent = build_user_message(RequestIntake(request_text="x"))
        assert "(not asked)" in absent
        empty = build_user_message(
            RequestIntake(request_text="x", existing_deterministic_artefacts=[])
        )
        assert "listed nothing" in empty
        filled = build_user_message(
            RequestIntake(
                request_text="x",
                existing_deterministic_artefacts=[
                    DeterministicArtefact(
                        name="Monthly pivot",
                        what_it_does="produces the counts",
                        completes_without_judgement=True,
                    ),
                    DeterministicArtefact(
                        name="Summary template",
                        what_it_does="lays out the headings",
                        completes_without_judgement=False,
                    ),
                ],
            )
        )
        assert "Monthly pivot: produces the counts [after this runs the work is done]" in filled
        assert "somebody still has to decide something" in filled
