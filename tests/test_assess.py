"""Tests for single-shot assessment. The live test auto-skips."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date

import pytest

from assess import (
    AssessmentError,
    assess_request,
    build_system_prompt,
    build_user_message,
)
from config import PATTERNS, RUBRIC
from examples import load_example, load_examples
from provider import ChatResponse, LLMProvider, MockProvider, OllamaProvider
from schemas import Assessment, RequestIntake, banned_synonyms
from scoring import Verdict

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _ollama_reachable() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_HOST, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


class ScriptedProvider(LLMProvider):
    """Returns canned texts in order, recording what it was asked."""

    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.2, response_schema=None, **kwargs):
        self.calls.append(messages)
        text = self.texts.pop(0) if self.texts else "{}"
        return ChatResponse(text=text, raw={"scripted": True})


def valid_assessment_json(**overrides) -> str:
    """A schema-valid assessment for the go example, as JSON text."""
    assessment = load_example("ticket_handover_summaries").reference_assessment
    payload = assessment.model_dump(mode="json")
    payload.update(overrides)
    return json.dumps(payload)


class TestPromptGeneration:
    def test_prompt_is_generated_from_the_config(self):
        """Tuning the rubric must tune the prompt — no second copy of anchors."""
        prompt = build_system_prompt()
        for dimension in RUBRIC.dimensions:
            assert dimension.id in prompt
            for level in RUBRIC.scale.levels:
                anchor = " ".join(dimension.anchors[level].split())
                assert anchor in prompt, (dimension.id, level)

    def test_prompt_lists_every_archetype_and_anti_pattern(self):
        prompt = build_system_prompt()
        for archetype in PATTERNS.archetypes:
            assert archetype.id in prompt
        for anti_pattern in PATTERNS.anti_patterns:
            assert anti_pattern.id in prompt

    def test_prompt_marks_hard_blocking_anti_patterns(self):
        prompt = build_system_prompt()
        assert "BLOCKING" in prompt

    def test_prompt_contains_no_banned_near_synonym(self):
        """Acceptance criterion 9.

        Prompt prose that names a field differently makes the model rename the
        key — the Phase 1.6 finding (ADR-004). The banned list lives in
        schemas.py so this check and the rule cannot drift apart.
        """
        prompt = build_system_prompt().lower()
        offenders = [word for word in banned_synonyms() if word in prompt]
        assert offenders == []

    def test_prompt_refers_to_fields_by_their_exact_names(self):
        prompt = build_system_prompt()
        for field in Assessment.model_fields:
            assert field in prompt

    def test_prompt_tells_the_model_it_does_not_decide(self):
        # Whitespace-normalized: line wrapping in the prompt source must not
        # break a semantic assertion about what the prompt says.
        prompt = " ".join(build_system_prompt().lower().split())
        assert "do not decide anything" in prompt
        assert "do not add up numbers" in prompt

    def test_user_message_carries_every_intake_field(self):
        intake = RequestIntake(
            request_text="Body of the request.",
            requesting_area="Finance",
            business_owner="Ana Ruiz",
            process_description="Done by hand.",
            stated_benefit="Saves time.",
        )
        message = build_user_message(intake)
        for value in (
            "Body of the request.",
            "Finance",
            "Ana Ruiz",
            "Done by hand.",
            "Saves time.",
        ):
            assert value in message

    def test_user_message_marks_a_missing_owner_rather_than_hiding_it(self):
        message = build_user_message(RequestIntake(request_text="x"))
        assert "(none named)" in message


class TestAssessRequestFlow:
    def test_happy_path_scores_and_issues_a_contract(self):
        example = load_example("ticket_handover_summaries")
        provider = ScriptedProvider([valid_assessment_json()])
        result = assess_request(
            example.intake, provider, approval_date=date(2026, 4, 1)
        )
        assert result.outcome.verdict is Verdict.GO
        assert result.contract is not None
        assert result.retry_count == 0

    def test_only_one_call_is_made_on_success(self):
        """Single-shot: no interview, no loop."""
        provider = ScriptedProvider([valid_assessment_json()])
        assess_request(
            load_example("ticket_handover_summaries").intake, provider
        )
        assert len(provider.calls) == 1

    def test_no_tools_are_ever_offered(self):
        """The payload goes through constrained JSON, never tool arguments."""

        class ToolWatchingProvider(ScriptedProvider):
            def chat(self, messages, tools=None, temperature=0.2, response_schema=None, **kwargs):
                assert tools is None
                assert response_schema is not None
                return super().chat(messages, tools, temperature, response_schema, **kwargs)

        provider = ToolWatchingProvider([valid_assessment_json()])
        assess_request(load_example("ticket_handover_summaries").intake, provider)

    def test_malformed_response_retries_once_with_the_error(self):
        provider = ScriptedProvider(["not json at all", valid_assessment_json()])
        result = assess_request(
            load_example("ticket_handover_summaries").intake, provider
        )
        assert result.retry_count == 1
        assert len(provider.calls) == 2
        corrective = provider.calls[1][-1]["content"]
        assert "did not match the schema" in corrective

    def test_it_does_not_retry_more_than_once(self):
        provider = ScriptedProvider(["nope", "still nope", valid_assessment_json()])
        with pytest.raises(AssessmentError, match="schema-valid"):
            assess_request(
                load_example("ticket_handover_summaries").intake, provider
            )
        assert len(provider.calls) == 2

    def test_a_gated_request_produces_no_contract(self):
        example = load_example("hr_policy_questions")
        payload = json.dumps(example.reference_assessment.model_dump(mode="json"))
        result = assess_request(example.intake, ScriptedProvider([payload]))
        assert result.outcome.verdict is Verdict.NOT_AI
        assert result.contract is None

    def test_a_hallucinated_metric_is_recorded_not_honoured(self):
        provider = ScriptedProvider(
            [valid_assessment_json(proposed_metric_id="metric_i_invented")]
        )
        result = assess_request(
            load_example("ticket_handover_summaries").intake, provider
        )
        assert result.ignored_metric_ids == ["metric_i_invented"]
        assert result.contract is not None

    def test_the_mock_provider_path_fails_loudly_rather_than_silently(self):
        """MockProvider returns {"mock": true}, which is not an Assessment."""
        with pytest.raises(AssessmentError):
            assess_request(
                load_example("ticket_handover_summaries").intake, MockProvider()
            )


@pytest.mark.skipif(
    not _ollama_reachable(), reason=f"Ollama not reachable at {OLLAMA_HOST}"
)
class TestLiveAssessment:
    """Runs only when a live Ollama server is available."""

    def test_a_real_request_produces_a_schema_valid_assessment(self):
        example = load_examples()[0]
        result = assess_request(
            example.intake, OllamaProvider(), approval_date=date(2026, 4, 1)
        )
        assert isinstance(result.assessment, Assessment)
        assert result.outcome.verdict in set(Verdict)
        # The engine must produce a coherent outcome whatever the model said.
        assert result.outcome.explanation.strip()
