"""Tests for the LLM-facing structured-output models.

The important assertions here are negative: what must NOT be in the schema.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from config import load_rubric
from schemas import SCORE_MAX, SCORE_MIN, Assessment, Confidence, DimensionAssessment


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
    def test_minimal_assessment_is_valid(self):
        assessment = Assessment()
        assert assessment.archetype_id is None
        assert assessment.anti_pattern_ids == []
        assert assessment.dimension_assessments == []

    def test_extra_fields_are_forbidden(self):
        """A hallucinated verdict field must fail loudly, not be ignored."""
        with pytest.raises(ValidationError):
            Assessment.model_validate({"verdict": "go"})

    def test_extra_fields_are_forbidden_on_a_dimension(self):
        with pytest.raises(ValidationError):
            DimensionAssessment.model_validate(
                {
                    "dimension_id": "economic_impact",
                    "score": 4,
                    "evidence": "e",
                    "confidence": "high",
                    "weighted_total": 4.1,
                }
            )

    def test_score_may_be_unknown(self):
        entry = DimensionAssessment(
            dimension_id="data_maturity",
            score=None,
            evidence="The interviewee did not know.",
            confidence=Confidence.LOW,
        )
        assert entry.score is None

    @pytest.mark.parametrize("bad_score", [0, 6, -1, 99])
    def test_scores_outside_the_scale_are_rejected(self, bad_score):
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension_id="data_maturity",
                score=bad_score,
                evidence="e",
                confidence=Confidence.HIGH,
            )

    def test_confidence_is_restricted_to_the_enum(self):
        with pytest.raises(ValidationError):
            DimensionAssessment(
                dimension_id="data_maturity",
                score=3,
                evidence="e",
                confidence="pretty sure",
            )


def test_score_bounds_match_the_rubric_scale():
    """Catch drift between the static schema bounds and the tunable rubric."""
    scale = load_rubric().scale
    assert (SCORE_MIN, SCORE_MAX) == (scale.min, scale.max)
