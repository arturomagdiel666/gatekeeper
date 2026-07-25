"""Tests for single-shot assessment. The live test auto-skips."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date

import pytest

from assess import (
    DEFAULT_TIMEOUT_SECONDS,
    AssessmentError,
    assess_timeout_seconds,
    assess_request,
    build_response_schema,
    build_system_prompt,
    build_user_message,
)
from config import PATTERNS, RUBRIC
from examples import load_example, load_examples
from provider import ChatResponse, LLMProvider, MockProvider, OllamaProvider
from schemas import (
    Assessment,
    DataSensitivity,
    Period,
    RequestIntake,
    banned_synonyms,
)
from scoring import Verdict, derive_scores

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


class TestDerivedDimensionsAreNotAsked:
    """Change 2: a dimension settled by the intake is not sent to the model.

    Its anchors are dead weight in the prompt, and on a 7B model that weight
    costs latency and compliance (ADR-022).
    """

    BOTH = {"times_per_period": 3, "period": Period.WEEK,
            "data_sensitivity": DataSensitivity.INTERNAL}

    def intake(self, **fields):
        return load_example("ticket_handover_summaries").intake.model_copy(
            update={
                "times_per_period": None,
                "period": None,
                "data_sensitivity": DataSensitivity.UNKNOWN,
                **fields,
            }
        )

    def test_both_fields_omit_both_dimensions_from_the_prompt(self):
        omit = set(derive_scores(RUBRIC, self.intake(**self.BOTH)))
        assert omit == {"process_frequency", "data_governance"}
        prompt = build_system_prompt(omit_dimensions=omit)
        assert "Fewer than about a dozen instances" not in prompt  # freq anchor
        assert "Public or internal-unclassified data" not in prompt  # gov anchor
        assert "About 200-1,000 person-hours" in prompt  # business_value survives

    def test_both_fields_omit_both_dimensions_from_the_schema(self):
        omit = {"process_frequency", "data_governance"}
        schema = build_response_schema(omit_dimensions=omit)
        enum = schema["$defs"]["DimensionAssessment"]["properties"]["dimension_id"]["enum"]
        assert set(enum) == set(RUBRIC.dimension_ids) - omit
        assert schema["properties"]["dimension_assessments"]["minItems"] == 5
        assert schema["properties"]["dimension_assessments"]["maxItems"] == 5

    def test_no_fields_produce_the_full_prompt_and_schema(self):
        assert derive_scores(RUBRIC, self.intake()) == {}
        prompt = build_system_prompt(omit_dimensions=set())
        for dimension in RUBRIC.dimensions:
            assert dimension.anchors[1] .split(".")[0][:30] in " ".join(prompt.split())
        schema = build_response_schema(omit_dimensions=set())
        assert schema["properties"]["dimension_assessments"]["minItems"] == 7

    def test_one_field_omits_exactly_one_dimension(self):
        omit = set(derive_scores(RUBRIC, self.intake(times_per_period=3, period=Period.WEEK)))
        assert omit == {"process_frequency"}
        assert build_response_schema(omit_dimensions=omit)["properties"][
            "dimension_assessments"
        ]["minItems"] == 6

    def test_the_trimmed_prompt_still_passes_the_banned_synonym_check(self):
        prompt = build_system_prompt(
            omit_dimensions={"process_frequency", "data_governance"}
        ).lower()
        assert [w for w in banned_synonyms() if w in prompt] == []

    def test_the_merged_assessment_is_complete_after_parsing(self):
        """The model returns 5 entries; the result carries all 7."""
        intake = self.intake(**self.BOTH)
        payload = load_example("ticket_handover_summaries").reference_assessment
        trimmed = payload.model_copy(deep=True)
        trimmed.dimension_assessments = [
            e for e in trimmed.dimension_assessments
            if e.dimension_id not in {"process_frequency", "data_governance"}
        ]
        provider = ScriptedProvider([json.dumps(trimmed.model_dump(mode="json"))])
        result = assess_request(intake, provider, approval_date=date(2026, 4, 1))

        assert len(trimmed.dimension_assessments) == 5
        scored = {e.dimension_id for e in result.assessment.dimension_assessments}
        assert scored == set(RUBRIC.dimension_ids)
        assert result.derived_dimensions == ["data_governance", "process_frequency"]
        assert set(result.model_scored_dimensions) == set(RUBRIC.dimension_ids) - {
            "data_governance", "process_frequency"
        }
        assert result.outcome.verdict is not None
        assert result.outcome.unknown_dimensions == []


class SlowProvider(LLMProvider):
    """Blocks for `delay` seconds, then returns a valid assessment."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.calls = 0

    def chat(self, messages, tools=None, temperature=0.2, response_schema=None, **kwargs):
        self.calls += 1
        time.sleep(self.delay)
        return ChatResponse(text=valid_assessment_json(), raw={"slow": True})


class TestTimeout:
    """A slow provider is an infrastructure condition, not a model error."""

    def test_a_slow_provider_returns_timed_out_without_raising(self):
        provider = SlowProvider(delay=5.0)
        result = assess_request(
            load_example("ticket_handover_summaries").intake,
            provider,
            timeout_seconds=0.2,
        )
        assert result.timed_out is True
        assert result.timeout_seconds == 0.2
        assert result.assessment is None
        assert result.outcome is None
        assert result.contract is None

    def test_a_timeout_is_not_retried(self):
        """One slow call is the pathological tail; a second only doubles it."""
        provider = SlowProvider(delay=5.0)
        assess_request(
            load_example("ticket_handover_summaries").intake,
            provider,
            timeout_seconds=0.2,
        )
        assert provider.calls == 1

    def test_the_timeout_returns_promptly_rather_than_waiting_it_out(self):
        provider = SlowProvider(delay=10.0)
        started = time.perf_counter()
        assess_request(
            load_example("ticket_handover_summaries").intake,
            provider,
            timeout_seconds=0.2,
        )
        assert time.perf_counter() - started < 3.0

    def test_a_fast_provider_is_untouched_by_the_budget(self):
        provider = ScriptedProvider([valid_assessment_json()])
        result = assess_request(
            load_example("ticket_handover_summaries").intake,
            provider,
            timeout_seconds=30.0,
        )
        assert result.timed_out is False
        assert result.outcome is not None
        assert result.assessment is not None

    def test_a_provider_error_still_propagates_rather_than_looking_like_a_timeout(self):
        class BrokenProvider(LLMProvider):
            def chat(self, messages, tools=None, temperature=0.2, response_schema=None, **kwargs):
                raise ConnectionError("ollama is not running")

        with pytest.raises(ConnectionError, match="not running"):
            assess_request(
                load_example("ticket_handover_summaries").intake,
                BrokenProvider(),
                timeout_seconds=5.0,
            )

    def test_derived_dimensions_are_still_reported_on_a_timeout(self):
        """The intake-derived half does not depend on the model answering."""
        result = assess_request(
            load_example("ticket_handover_summaries").intake,
            SlowProvider(delay=5.0),
            timeout_seconds=0.2,
        )
        assert result.derived_dimensions == ["data_governance", "process_frequency"]


class TestTimeoutConfiguration:
    def test_the_default_is_thirty_seconds(self, monkeypatch):
        monkeypatch.delenv("ASSESS_TIMEOUT_SECONDS", raising=False)
        assert assess_timeout_seconds() == DEFAULT_TIMEOUT_SECONDS == 30.0

    def test_the_default_sits_between_the_median_and_the_tail(self):
        """Phase 3.2 measured median 5.1s and a 416.6s outlier."""
        assert DEFAULT_TIMEOUT_SECONDS > 5.1 * 5
        assert DEFAULT_TIMEOUT_SECONDS < 416.6 / 5

    def test_the_env_var_overrides_it(self, monkeypatch):
        monkeypatch.setenv("ASSESS_TIMEOUT_SECONDS", "7.5")
        assert assess_timeout_seconds() == 7.5

    @pytest.mark.parametrize("bad", ["nonsense", "-1", "0", ""])
    def test_a_malformed_override_falls_back_rather_than_disabling_the_timeout(
        self, monkeypatch, bad
    ):
        monkeypatch.setenv("ASSESS_TIMEOUT_SECONDS", bad)
        assert assess_timeout_seconds() == DEFAULT_TIMEOUT_SECONDS
