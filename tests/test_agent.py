"""The intake agent: its loop, its stopping conditions, and its one hard rule.

The hard rule is that no dimension score anywhere originates from model output.
`test_no_dimension_score_can_originate_from_the_model` is the test that fails if
it ever does, and it is the reason this file exists — the rest verifies that the
loop terminates for the right reason and that every filled field carries the
words that filled it.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

import agent
import agent_tools as tools
from agent import StopReason, run_interview
from provider import MockProvider
from schemas import (
    DataEvidence,
    DataSensitivity,
    EffortEvidence,
    Period,
    PriorTool,
    Procurement,
    RequestIntake,
    SampleCheck,
)
from scoring import Verdict

VAGUE = "We think there is something AI could do with our supplier invoices."


def script(*entries: dict) -> MockProvider:
    """A mock whose first reply is the anti-pattern scan the loop always runs."""
    return MockProvider([{"matches": []}, *entries])


def ask(field: str, question: str = "A question?") -> dict:
    return {"tool": "ask", "target_field": field, "question": question, "why": "test"}


def answered(value: str, span: str) -> dict:
    return {"answered": True, "value": value, "span": span}


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_no_dimension_score_can_originate_from_the_model():
    """The architecture rule, enforced structurally rather than by inspection.

    `score_and_gate` is the only producer of a dimension score in the agent path.
    Its signature accepts a `RequestIntake` and a list of quote-verified
    anti-pattern matches, and nothing else — so there is no parameter through
    which a model-produced number could arrive. If someone adds one, this fails.

    The second half checks the assessment it builds: every dimension is handed to
    the scorer as `score=None`, which means every score in the outcome was put
    there by a rubric derivation reading an intake field.
    """
    signature = inspect.signature(tools.score_and_gate)
    assert list(signature.parameters) == ["intake", "anti_patterns"]

    source = inspect.getsource(tools.score_and_gate)
    assert "score=None" in source, (
        "score_and_gate must hand every dimension to the scorer as unknown; a "
        "literal score here would be a number the rubric did not derive"
    )

    intake = RequestIntake(
        request_text=VAGUE,
        business_owner="Rocio Delgado",
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        existing_deterministic_artefacts=[],
    )
    outcome = tools.score_and_gate(intake)
    scored = {d: s for d, s in outcome.resolved_scores.items() if s is not None}
    assert scored, "the derivations should have produced at least one score"
    assert set(scored) <= set(
        outcome.derived_dimensions + outcome.fallback_derived_dimensions
    ), "a score appeared that no derivation claims responsibility for"


def test_a_model_that_returns_scores_cannot_get_them_into_a_verdict():
    """Even handed a payload full of scores, the tools ignore it.

    A live model asked to interview will sometimes volunteer a score anyway. The
    loop's schemas have no field for one, and this shows the consequence: the
    verdict is identical whether or not the model tried.
    """
    intake = RequestIntake(request_text=VAGUE, business_owner="R. Delgado")
    honest = tools.score_and_gate(intake)

    hostile = script(
        {**ask("data_sensitivity"), "business_value": 5, "adoption_risk": 1},
        {**answered("confidential", "confidential"), "data_readiness": 5},
    )
    result = run_interview(
        VAGUE, lambda q: "It is confidential data.", hostile, max_questions=1
    )
    assert result.outcome.resolved_scores["business_value"] in (None, honest.resolved_scores["business_value"])
    assert result.outcome.resolved_scores["adoption_risk"] is None
    assert result.outcome.resolved_scores["data_readiness"] is None


# ---------------------------------------------------------------------------
# Stopping conditions
# ---------------------------------------------------------------------------


def test_it_stops_early_when_a_gate_fires_and_says_which():
    """Acceptance 2: a requester who cannot name an owner is told in one turn."""
    provider = script(ask("business_owner"), {"answered": False, "value": "", "span": ""})
    result = run_interview(
        VAGUE, lambda q: "Nobody yet, we were going to work that out later.", provider
    )
    assert result.stop_reason is StopReason.GATE_FIRED
    assert result.verdict is Verdict.NO_GO
    assert "no_named_business_owner" in result.stop_detail
    assert len(result.transcript) == 1, "a decided verdict must not cost more questions"


def test_it_returns_incomplete_naming_the_reason_rather_than_burning_the_budget():
    """Acceptance 3: when no remaining question can help, say so and stop.

    The three judged dimensions have no intake field. Once everything askable is
    answered, continuing to ask would be theatre — and the budget is 8, so a loop
    that ran to exhaustion would look identical from outside except for six
    wasted questions.
    """
    provider = script(
        ask("business_owner"),
        answered("Rocio Delgado", "Rocio Delgado"),
        ask("existing_deterministic_artefacts"),
        answered("[]", "nothing exists"),
        ask("data_sensitivity"),
        answered("confidential", "confidential"),
        ask("times_per_period"),
        answered('{"times": 400, "period": "month"}', "400 a month"),
    )
    replies = iter(
        [
            "Rocio Delgado owns it.",
            "nothing exists for this today",
            "it is confidential",
            "about 400 a month",
        ]
    )
    result = run_interview(VAGUE, lambda q: next(replies, "not sure"), provider, max_questions=8)
    assert result.stop_reason is StopReason.NO_NEW_INFORMATION
    assert result.verdict is Verdict.INCOMPLETE
    assert len(result.transcript) < 8, "it should stop before exhausting the budget"
    for dimension in ("adoption_risk", "data_readiness", "implementation_effort"):
        assert dimension in result.stop_detail


def test_two_barren_answers_end_the_interview():
    """The information does not exist, so asking six more times will not find it."""
    provider = script(
        ask("business_owner"),
        {"answered": False, "value": "", "span": ""},
        ask("business_owner"),
        {"answered": False, "value": "", "span": ""},
    )
    result = run_interview(VAGUE, lambda q: "I really don't know.", provider)
    assert result.stop_reason in (StopReason.GATE_FIRED, StopReason.NO_NEW_INFORMATION)


def test_the_budget_is_honoured():
    """A model that keeps asking about a field nobody answers still terminates."""
    provider = MockProvider(
        [{"matches": []}, ask("where_the_data_lives"), answered("SAP", "SAP")]
    )
    result = run_interview(
        "We want an agent.", lambda q: "It is in SAP.", provider, max_questions=2
    )
    assert len(result.transcript) <= 2


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_every_filled_field_carries_its_turn_and_the_words_that_filled_it():
    """Acceptance 5."""
    provider = script(ask("business_owner"), answered("Rocio Delgado", "Rocio Delgado"))
    result = run_interview(
        VAGUE, lambda q: "That would be Rocio Delgado in Finance.", provider, max_questions=1
    )
    assert result.provenance
    for entry in result.provenance:
        assert entry.turn >= 1
        assert entry.span
        assert entry.question
        turn = result.transcript[entry.turn - 1]
        assert entry.span in turn.answer, "the span must be the requester's own words"


def test_a_span_the_requester_did_not_say_is_rejected():
    """A fabricated span is a fabricated field, and a field can fire a gate."""
    result = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "business_owner",
        "Juan Perez",
        "Juan Perez",
        1,
        "Who owns it?",
        "That would be Rocio Delgado.",
    )
    assert not result.accepted
    assert "does not appear" in result.reason


def test_a_field_outside_the_interview_menu_is_refused():
    result = tools.record_field(
        RequestIntake(request_text=VAGUE), "request_text", "x", "x", 1, "?", "x"
    )
    assert not result.accepted
    assert "not a field the interview may fill" in result.reason


# ---------------------------------------------------------------------------
# The interview / form distinction
# ---------------------------------------------------------------------------


def test_a_gate_does_not_fire_on_a_field_that_has_not_been_asked_yet():
    """Otherwise every interview would end at turn zero with `no_go`."""
    report = tools.assess_completeness(RequestIntake(request_text=VAGUE))
    assert "no_named_business_owner" in report.premature_gates
    assert not report.can_reach_verdict


def test_the_same_gate_fires_once_the_question_has_been_put():
    """Asked and unanswerable is not the same as never asked."""
    report = tools.assess_completeness(
        RequestIntake(request_text=VAGUE), asked=frozenset({"business_owner"})
    )
    assert report.premature_gates == []


def test_an_empty_artefact_list_is_an_answer_and_is_not_re_asked():
    """`[]` means asked-and-nothing-exists; `None` means nobody asked (ADR-030)."""
    asked = RequestIntake(request_text=VAGUE, existing_deterministic_artefacts=[])
    never = RequestIntake(request_text=VAGUE)
    assert "existing_deterministic_artefacts" in [
        f.name for f in tools.assess_completeness(never).missing
    ]
    assert "existing_deterministic_artefacts" not in [
        f.name for f in tools.assess_completeness(asked).missing
    ]


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_an_unusable_turn_falls_back_instead_of_crashing():
    """Someone is sitting in front of this. A KeyError is not an option."""
    provider = MockProvider([{"matches": []}, {"nonsense": True}, {"also": "nonsense"}])
    result = run_interview(VAGUE, lambda q: "I don't know.", provider, max_questions=2)
    assert result.verdict in set(Verdict)
    assert result.transcript


def test_anti_pattern_matches_without_a_verifiable_quote_are_discarded():
    """A quote that is not in the request is a fabrication, and it can fire a gate."""
    provider = MockProvider(
        [
            {
                "matches": [
                    {
                        "anti_pattern_id": "deterministic_rule_suffices",
                        "quote": "a sentence nobody wrote",
                        "quote_confidence": "high",
                    }
                ]
            }
        ]
    )
    found = tools.find_anti_patterns("We want an agent for invoices.", provider)
    assert found.matches == []
    assert found.discarded and "quote not found" in found.discarded[0][1]


def test_a_transcript_round_trips(tmp_path):
    provider = script(ask("business_owner"), answered("Rocio Delgado", "Rocio Delgado"))
    result = run_interview(
        VAGUE, lambda q: "Rocio Delgado.", provider, max_questions=1,
        approval_date=date(2026, 7, 27),
    )
    path = agent.save_transcript(result, tmp_path)
    assert path.exists()
    assert "Rocio Delgado" in path.read_text()


@pytest.mark.parametrize(
    "value,expected",
    [("confidential", DataSensitivity.CONFIDENTIAL), ("REGULATED", DataSensitivity.REGULATED)],
)
def test_enum_answers_are_coerced_case_insensitively(value, expected):
    result = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "data_sensitivity",
        value,
        "sensitive",
        1,
        "?",
        "it is sensitive",
    )
    assert result.accepted
    assert result.intake.data_sensitivity is expected


def test_a_volume_answer_without_its_period_is_refused():
    """A number without its unit cannot be annualised, so it is not an answer."""
    result = tools.record_field(
        RequestIntake(request_text=VAGUE), "times_per_period", "400", "400", 1, "?", "400"
    )
    assert not result.accepted
    assert "period" in result.reason


def test_prior_tool_abandoned_is_recorded():
    result = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "prior_tool_for_these_users",
        "abandoned",
        "nobody used it",
        1,
        "?",
        "we built one and nobody used it",
    )
    assert result.accepted
    assert result.intake.prior_tool_for_these_users is PriorTool.ABANDONED


# ---------------------------------------------------------------------------
# Extraction shape
# ---------------------------------------------------------------------------


def test_structured_fields_get_a_structured_extraction_schema():
    """The defect the first live run found, pinned.

    Asking for a JSON list inside a JSON string puts the hard part outside the
    grammar: the constraint applies to the string, not its contents. The 7B
    emitted unquoted keys twice and the interview died with one field filled.
    """
    artefacts = agent.extract_schema_for("existing_deterministic_artefacts")
    assert artefacts["properties"]["value"]["type"] == "array"
    assert (
        artefacts["properties"]["value"]["items"]["properties"][
            "completes_without_judgement"
        ]["type"]
        == "boolean"
    )

    volume = agent.extract_schema_for("times_per_period")
    assert volume["properties"]["value"]["type"] == "object"
    assert volume["properties"]["value"]["properties"]["period"]["enum"] == [
        "day",
        "week",
        "month",
        "year",
    ]

    sensitivity = agent.extract_schema_for("data_sensitivity")
    assert "regulated" in sensitivity["properties"]["value"]["enum"]
    assert "unknown" not in sensitivity["properties"]["value"]["enum"], (
        "unknown is the absence of an answer, not one the requester can give"
    )

    plain = agent.extract_schema_for("business_owner")
    assert plain["properties"]["value"]["type"] == "string"


def test_record_field_accepts_a_native_value_and_a_json_string():
    """Both, so every transcript recorded before the schema change still replays."""
    native = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "existing_deterministic_artefacts",
        [{"name": "Excel", "what_it_does": "lists them", "completes_without_judgement": False}],
        "an Excel report",
        1,
        "?",
        "we have an Excel report",
    )
    as_string = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "existing_deterministic_artefacts",
        '[{"name": "Excel", "what_it_does": "lists them", "completes_without_judgement": false}]',
        "an Excel report",
        1,
        "?",
        "we have an Excel report",
    )
    assert native.accepted and as_string.accepted
    assert (
        native.intake.existing_deterministic_artefacts
        == as_string.intake.existing_deterministic_artefacts
    )


def test_an_empty_artefact_list_is_recorded_rather_than_refused_as_no_value():
    """`[]` is the answer that says nothing exists, and it derives a score."""
    result = tools.record_field(
        RequestIntake(request_text=VAGUE),
        "existing_deterministic_artefacts",
        [],
        "nothing really",
        1,
        "?",
        "nothing really, people just do it by hand",
    )
    assert result.accepted
    assert result.intake.existing_deterministic_artefacts == []
    outcome = tools.score_and_gate(result.intake)
    assert outcome.resolved_scores["non_ai_alternative"] == 1


# ---------------------------------------------------------------------------
# v3.0.0 — the interview reaches approval
# ---------------------------------------------------------------------------


def test_a_decided_verdict_does_not_end_the_interview_while_a_question_could_move_it():
    """The ordering v3.0.0 forced.

    `adoption_risk` weighs 0.17, which fits inside the 0.25 unknown-weight
    budget — so a request could clear completeness with nobody having been asked
    who was consulted, and the loop would stop and approve. An approval issued
    while a question that could still change it went unasked is the one outcome
    this product exists to prevent.
    """
    from agent_tools import assess_completeness, score_and_gate

    intake = RequestIntake(
        request_text=VAGUE,
        business_owner="Ana Ruiz",
        times_per_period=4000,
        period=Period.MONTH,
        data_sensitivity=DataSensitivity.INTERNAL,
        existing_deterministic_artefacts=[],
        data_evidence=DataEvidence(
            systems=["ServiceNow"],
            sample_checked=SampleCheck.LOOKED_USABLE,
            correct_examples=200_000,
            quality_criteria_agreed=True,
        ),
        effort_evidence=EffortEvidence(
            systems_to_integrate=["ServiceNow"],
            procurement=Procurement.EXISTING_LICENCE,
            approving_teams=["Service Desk"],
        ),
    )
    report = assess_completeness(intake, frozenset({"business_owner"}))
    outcome = score_and_gate(intake)
    assert outcome.verdict is not Verdict.INCOMPLETE, "completeness already passes"
    assert "adoption_risk" in outcome.unknown_dimensions
    assert agent._stopping_reason(report, outcome, [], 0, 8) is None, (
        "the interview must keep going while adoption_evidence is still askable"
    )


def test_the_baseline_is_asked_for_only_when_a_contract_will_be_issued():
    """A `contract_field` buys nothing on a verdict that issues no contract."""
    from agent_tools import ASKABLE_BY_NAME, assess_completeness, score_and_gate

    assert ASKABLE_BY_NAME["stated_baseline_value"].contract_field
    intake = RequestIntake(request_text=VAGUE)
    report = assess_completeness(intake)
    outcome = score_and_gate(intake)
    assert outcome.verdict is not Verdict.GO
    offered = {f.name for f in agent.useful_fields(report, outcome)}
    assert "stated_baseline_value" not in offered


def test_the_fallback_prefers_a_field_that_has_not_been_asked_yet():
    """A live run put the identical question twice: the decide call timed out,
    the fallback took the first still-missing field, the extraction failed too,
    so the field stayed missing and the next fallback took it again."""
    from agent_tools import ASKABLE_FIELDS

    askable = ASKABLE_FIELDS[:3]
    first = askable[0].name
    assert agent._resolve_field("not_a_field", askable, set()) == first
    assert agent._resolve_field("not_a_field", askable, {first}) == askable[1].name
    # Every option exhausted: fall back rather than crash on an empty list.
    every = {f.name for f in askable}
    assert agent._resolve_field("not_a_field", askable, every) == first
