"""The tools the intake agent may call. Every decision in the system lives here.

The measurement programme that preceded this module concluded, over six runs and
two model sizes: **the model finds and quotes the evidence; the form and the
tables decide.** Rubric slots computed from a stated intake field reach
kw = 0.97 against a two-assessor reference and are identical across a doubling of
model size. Slots scored by the model reach kappa = 0.04 — chance — while
reproducing their own answers at kw = 0.37, which makes the model reproducibly
wrong rather than noisy (`evaluacion/14_kappa.md`, `15_bias_shape.md`).

So this module holds the deciding, and it is all deterministic Python. The agent
in `agent.py` chooses which question to ask and phrases it; it never computes a
score, and `score_and_gate` is the only thing here that produces one. It takes a
`RequestIntake` and never free text, which is the structural reason a
model-produced number cannot reach a score: there is no argument to pass one in.

The one tool that calls a model, `find_anti_patterns`, asks it for **quotes** and
then verifies every quote is a substring of the source before any gate may fire
on it. That asymmetry is deliberate: anti-patterns whose signals describe what
the requester *said* reached full agreement between independent assessors, while
the same model's dimension scores reached none.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import PATTERNS, RUBRIC
from contracts import ContractResult, issue_contract
from provider import LLMProvider, parse_json_content
from schemas import (
    AntiPatternMatch,
    Assessment,
    Confidence,
    DataSensitivity,
    DeterministicArtefact,
    DimensionAssessment,
    Period,
    PriorTool,
    RequestIntake,
)
from scoring import Outcome, Verdict, quote_is_supported
from scoring import score as score_assessment

# ---------------------------------------------------------------------------
# What the interview can ask about
# ---------------------------------------------------------------------------


class Askable(BaseModel):
    """One intake field the agent may ask a question about.

    Attributes:
        name: The `RequestIntake` attribute this fills.
        blocks_gate: The id of the blocking gate this field can decide, or
            ``None``. Gate-blocking fields are asked first because an answer can
            end the conversation with a decided verdict, which is worth more to
            the requester than a marginally better weighted total.
        feeds_dimension: The rubric dimension the field derives or informs.
        prompt_hint: What the question needs to establish, in plain terms. The
            model turns this into a sentence in the requester's language; it is
            not shown to the requester as written.
        parser: Name of the coercion applied to the requester's answer.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    blocks_gate: str | None = None
    feeds_dimension: str | None = None
    prompt_hint: str
    parser: str = "text"


#: The askable intake fields, most decisive first. Order is the tie-break the
#: agent falls back on; `assess_completeness` re-sorts by gate-blocking anyway.
ASKABLE_FIELDS: list[Askable] = [
    Askable(
        name="business_owner",
        blocks_gate="no_named_business_owner",
        prompt_hint=(
            "the name of the specific person who will be accountable for this "
            "agent and for its measurement contract — a named individual, not a "
            "team or a department"
        ),
    ),
    Askable(
        name="existing_deterministic_artefacts",
        blocks_gate="non_ai_alternative_suffices",
        feeds_dimension="non_ai_alternative",
        prompt_hint=(
            "what already exists today that does part of this work without any "
            "AI — reports, spreadsheets, macros, saved queries, routing rules — "
            "what each one produces, and whether the work is finished when it "
            "runs or somebody still has to decide something"
        ),
        parser="artefacts",
    ),
    Askable(
        name="data_sensitivity",
        feeds_dimension="data_governance",
        prompt_hint=(
            "how the data this would process is classified: public, internal, "
            "confidential, or regulated (personal, financial or health data "
            "under a legal regime)"
        ),
        parser="data_sensitivity",
    ),
    Askable(
        name="times_per_period",
        feeds_dimension="process_frequency",
        prompt_hint=(
            "how many times this task is done END TO END in a period — if one "
            "submission contains many items handled separately, count the items, "
            "not the submissions — and say whether that is per day, week, month "
            "or year"
        ),
        parser="volume",
    ),
    Askable(
        name="minutes_per_instance",
        feeds_dimension="business_value",
        prompt_hint=(
            "how many minutes one instance of this task takes a person today"
        ),
        parser="number",
    ),
    Askable(
        name="where_the_data_lives",
        prompt_hint="which systems hold the data this would need",
    ),
    Askable(
        name="prior_tool_for_these_users",
        prompt_hint=(
            "what happened to the last tool built for these same users — was it "
            "adopted, was it abandoned, or was there never one"
        ),
        parser="prior_tool",
    ),
    Askable(
        name="who_does_this_today",
        prompt_hint="who does this work now, and roughly how many people",
    ),
    Askable(
        name="process_description",
        prompt_hint="how the work is done today, step by step",
    ),
    Askable(
        name="requesting_area",
        prompt_hint="which business area or team is making this request",
    ),
]

ASKABLE_BY_NAME = {field.name: field for field in ASKABLE_FIELDS}


def _is_empty(intake: RequestIntake, name: str) -> bool:
    """Whether the field still carries its not-asked value.

    ``existing_deterministic_artefacts`` is the case that makes this a function
    rather than a truth test: ``[]`` means *asked, and nothing exists* — a strong
    derivable signal — while ``None`` means nobody was asked (ADR-030). Treating
    the empty list as falsey would re-ask a question already answered and throw
    away the answer.
    """
    value = getattr(intake, name)
    if name == "existing_deterministic_artefacts":
        return value is None
    if isinstance(value, PriorTool):
        return value is PriorTool.UNKNOWN
    if isinstance(value, DataSensitivity):
        return value is DataSensitivity.UNKNOWN
    return value is None or value == ""


# ---------------------------------------------------------------------------
# Tool 1 — assess_completeness
# ---------------------------------------------------------------------------


class CompletenessReport(BaseModel):
    """What the intake is still missing, most decisive first.

    Attributes:
        missing: Fields with no value, ordered gate-blocking first.
        filled: Fields that already carry a value.
        unknown_dimensions: Rubric dimensions currently unresolved.
        unknown_weight: Their combined rubric weight.
        blocking_gates_reachable: Gate ids a missing field could still decide.
        premature_gates: Gates that fired only because a field the interview has
            not asked about yet is empty. See :func:`assess_completeness`.
        can_reach_verdict: Whether a decided verdict is reachable now.
    """

    model_config = ConfigDict(extra="forbid")

    missing: list[Askable] = Field(default_factory=list)
    filled: list[str] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    unknown_weight: float = 0.0
    blocking_gates_reachable: list[str] = Field(default_factory=list)
    premature_gates: list[str] = Field(default_factory=list)
    can_reach_verdict: bool = False


def assess_completeness(
    intake: RequestIntake, asked: frozenset[str] = frozenset()
) -> CompletenessReport:
    """Which intake fields are still missing, ordered by what they can decide.

    Gate-blocking fields sort first. The reason is not tidiness: a gate-blocking
    answer can end the conversation with a decided verdict, so asking it first
    can save the requester every remaining question. A field that only moves a
    weight cannot do that.

    **Premature gates are the interview's one real departure from the form.**
    `no_named_business_owner` fires on an empty `business_owner`, which is right
    for a submitted form — the requester left it blank and had their chance. In
    an interview an empty field means *not asked yet*, so honouring that gate at
    turn zero would end every conversation with `no_go` before a word was
    exchanged. A gate whose deciding field is still unasked is reported here and
    is not treated as a stopping condition; **once the question has been put and
    the answer is still empty, the gate stands exactly as it does for a form.**
    That second half is the point of ``asked``: a requester who is asked who will
    own this and cannot name anyone has answered, and `no_named_business_owner`
    is then a correct and decided `no_go`. Without tracking what was asked, an
    unanswerable question would be indistinguishable from an unasked one and the
    gate could never fire at all.

    Args:
        intake: The intake as filled so far.
        asked: Field names the interview has already put to the requester,
            whether or not the reply filled them.

    Returns:
        A :class:`CompletenessReport`.
    """
    missing = [f for f in ASKABLE_FIELDS if _is_empty(intake, f.name)]
    missing.sort(key=lambda f: (f.blocks_gate is None, ASKABLE_FIELDS.index(f)))
    filled = [f.name for f in ASKABLE_FIELDS if not _is_empty(intake, f.name)]

    outcome = score_and_gate(intake)
    unasked_gates = {
        f.blocks_gate for f in missing if f.blocks_gate and f.name not in asked
    }
    premature = [g.gate_id for g in outcome.triggered_gates if g.gate_id in unasked_gates]
    return CompletenessReport(
        missing=missing,
        filled=filled,
        unknown_dimensions=list(outcome.unknown_dimensions),
        unknown_weight=outcome.unknown_weight,
        blocking_gates_reachable=sorted(unasked_gates),
        premature_gates=premature,
        can_reach_verdict=outcome.verdict is not Verdict.INCOMPLETE and not premature,
    )


# ---------------------------------------------------------------------------
# Tool 2 — record_field
# ---------------------------------------------------------------------------


class FieldProvenance(BaseModel):
    """Where one filled field came from.

    Attributes:
        field: The intake attribute filled.
        value: The coerced value, rendered for display.
        span: The requester's own words that justified it, copied verbatim.
        turn: The interview turn that produced it.
        question: The question that was asked.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    value: str
    span: str
    turn: int
    question: str


class RecordResult(BaseModel):
    """The outcome of one `record_field` call.

    Attributes:
        accepted: Whether the field was written.
        reason: Why it was rejected, when it was.
        intake: The updated intake; unchanged when rejected.
        provenance: The provenance entry, when accepted.
    """

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reason: str | None = None
    intake: RequestIntake
    provenance: FieldProvenance | None = None


def _coerce(field: Askable, value: str) -> Any:
    """Turn the model's extracted string into the field's declared type.

    Raises:
        ValueError: If the answer does not carry the value the field needs. The
            message is fed back to the model, so it names what was wrong.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("the answer carried no value for this field")

    if field.parser == "number":
        return float(text.replace(",", "."))
    if field.parser == "volume":
        payload = json.loads(text) if text.startswith("{") else None
        if not payload or "times" not in payload or "period" not in payload:
            raise ValueError(
                'expected {"times": <int>, "period": "day|week|month|year"}; '
                "volume and its period are one answer because a number without "
                "its unit cannot be annualised"
            )
        return (int(payload["times"]), Period(str(payload["period"]).lower()))
    if field.parser == "data_sensitivity":
        return DataSensitivity(text.lower())
    if field.parser == "prior_tool":
        return PriorTool(text.lower())
    if field.parser == "artefacts":
        payload = json.loads(text) if text.startswith("[") else None
        if payload is None:
            raise ValueError(
                "expected a JSON list of artefacts, each with name, "
                "what_it_does and completes_without_judgement. An empty list is "
                "a valid and meaningful answer: it means nothing exists"
            )
        return [DeterministicArtefact.model_validate(item) for item in payload]
    return text


def record_field(
    intake: RequestIntake,
    name: str,
    value: str,
    span: str,
    turn: int,
    question: str,
    answer: str,
) -> RecordResult:
    """Write one intake field, with the verbatim span that justified it.

    The span is held to the same standard as an anti-pattern quote and for the
    same reason: a field the requester did not say is a fabrication, and a
    fabricated field can fire a gate. It is checked as a substring of the
    requester's actual answer, normalised for whitespace only.

    Args:
        intake: The intake to update. Never mutated; a copy is returned.
        name: The field to fill.
        value: The extracted value, as a string, coerced by the field's parser.
        span: The requester's own words justifying it, copied verbatim.
        turn: The interview turn.
        question: The question that was asked.
        answer: What the requester actually replied, for span verification.

    Returns:
        A :class:`RecordResult`. Rejections carry the reason and leave the
        intake untouched.
    """
    field = ASKABLE_BY_NAME.get(name)
    if field is None:
        return RecordResult(
            accepted=False,
            reason=f"{name!r} is not a field the interview may fill",
            intake=intake,
        )
    if not quote_is_supported(span, answer):
        return RecordResult(
            accepted=False,
            reason=(
                f"the span {span!r} does not appear in the requester's answer; "
                "copy their words rather than paraphrasing"
            ),
            intake=intake,
        )
    try:
        coerced = _coerce(field, value)
    except (ValueError, ValidationError, KeyError, TypeError) as exc:
        return RecordResult(accepted=False, reason=str(exc), intake=intake)

    data = intake.model_dump()
    if field.parser == "volume":
        data["times_per_period"], data["period"] = coerced
        shown = f"{coerced[0]} per {coerced[1].value}"
    elif field.parser == "artefacts":
        data[name] = [a.model_dump() for a in coerced]
        shown = f"{len(coerced)} artefact(s)"
    else:
        data[name] = coerced
        shown = str(getattr(coerced, "value", coerced))

    try:
        updated = RequestIntake.model_validate(data)
    except ValidationError as exc:
        return RecordResult(accepted=False, reason=str(exc), intake=intake)

    return RecordResult(
        accepted=True,
        intake=updated,
        provenance=FieldProvenance(
            field=name, value=shown, span=span, turn=turn, question=question
        ),
    )


# ---------------------------------------------------------------------------
# Tool 3 — find_anti_patterns
# ---------------------------------------------------------------------------

ANTI_PATTERN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "anti_pattern_id": {
                        "type": "string",
                        "enum": [p.id for p in PATTERNS.anti_patterns],
                    },
                    "quote": {"type": "string"},
                    "second_quote": {"type": "string"},
                    "quote_confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["anti_pattern_id", "quote", "quote_confidence"],
            },
        }
    },
    "required": ["matches"],
}


class AntiPatternResult(BaseModel):
    """Verified matches, and the ones thrown away for lacking evidence.

    Attributes:
        matches: Matches whose quotes were found in the source.
        discarded: ``(id, reason)`` for every match rejected.
    """

    model_config = ConfigDict(extra="forbid")

    matches: list[AntiPatternMatch] = Field(default_factory=list)
    discarded: list[tuple[str, str]] = Field(default_factory=list)


def _anti_pattern_prompt(text: str) -> list[dict]:
    catalogue = "\n\n".join(
        f"{p.id} — {p.label}\n"
        + "\n".join(f"  - {s}" for s in p.signals)
        + (
            "\n  BOTH parts must be quoted; a match with only one is no match."
            if p.two_part_evidence
            else ""
        )
        for p in PATTERNS.anti_patterns
    )
    return [
        {
            "role": "system",
            "content": (
                "You find anti-patterns in a request for an AI agent, and you "
                "quote the words that establish each one. You never judge "
                "whether the request is good. Copy quotes WORD FOR WORD from "
                "the request: a quote that is not in the text is discarded, and "
                "so is the match. If nothing matches, return an empty list — "
                "that is the common and correct answer.\n\n" + catalogue
            ),
        },
        {"role": "user", "content": f"REQUEST:\n{text}"},
    ]


def find_anti_patterns(
    text: str, provider: LLMProvider, temperature: float = 0.0
) -> AntiPatternResult:
    """Search the request for anti-patterns, keeping only verifiable quotes.

    This is the one tool that calls a model, and it asks for quotes rather than
    judgements. Every returned quote is checked as a substring of ``text``; a
    quote that is not there is a fabrication and the whole match is discarded,
    because an anti-pattern can fire a gate and a gate cannot be outvoted.

    Args:
        text: The request text to search.
        provider: The model backend.
        temperature: Sampling temperature; 0.0 by default.

    Returns:
        An :class:`AntiPatternResult`.
    """
    response = provider.chat(
        _anti_pattern_prompt(text),
        temperature=temperature,
        response_schema=ANTI_PATTERN_SCHEMA,
    )
    try:
        payload = parse_json_content(response)
    except ValueError as exc:
        return AntiPatternResult(discarded=[("<unparseable>", str(exc))])

    kept: list[AntiPatternMatch] = []
    discarded: list[tuple[str, str]] = []
    by_id = {p.id: p for p in PATTERNS.anti_patterns}
    for raw in payload.get("matches", []) or []:
        try:
            match = AntiPatternMatch.model_validate(
                {
                    "anti_pattern_id": raw.get("anti_pattern_id", ""),
                    "quote": raw.get("quote", ""),
                    "second_quote": raw.get("second_quote") or None,
                    "quote_confidence": raw.get("quote_confidence", "low"),
                }
            )
        except ValidationError as exc:
            discarded.append((str(raw.get("anti_pattern_id", "?")), str(exc)))
            continue
        pattern = by_id.get(match.anti_pattern_id)
        if pattern is None:
            discarded.append((match.anti_pattern_id, "not in patterns.yaml"))
        elif not quote_is_supported(match.quote, text):
            discarded.append((match.anti_pattern_id, "quote not found in request"))
        elif pattern.two_part_evidence and not (
            match.second_quote and quote_is_supported(match.second_quote, text)
        ):
            discarded.append(
                (match.anti_pattern_id, "two-part evidence: second quote missing")
            )
        else:
            kept.append(match)
    return AntiPatternResult(matches=kept, discarded=discarded)


# ---------------------------------------------------------------------------
# Tool 4 — score_and_gate
# ---------------------------------------------------------------------------


def score_and_gate(
    intake: RequestIntake,
    anti_patterns: list[AntiPatternMatch] | None = None,
) -> Outcome:
    """Score the intake and evaluate the gates. The only source of a score.

    **Its signature is the guarantee.** It takes a `RequestIntake` and a list of
    quote-verified `AntiPatternMatch`, and there is no parameter through which a
    model-produced number could arrive. Every dimension is handed to the scorer
    as unknown; the four that derive from a stated intake field are then filled
    by the rubric's own derivations, in code, and the three that have no
    derivation stay unknown and are reported as such.

    That last part is the honest consequence of the architecture rule, and it is
    not hidden: `adoption_risk`, `data_readiness` and `implementation_effort`
    carry 0.45 of the rubric's weight between them and no intake field supplies
    any of them, so an intake alone cannot clear the 0.25 unknown-weight budget.
    A verdict of `go` is therefore unreachable through this path. What is
    reachable is `no_go` and `not_ai` — both by gate, both decided — and
    `incomplete` naming exactly what is missing. Converting those three
    dimensions to intake fields is what the measurement recommended
    (`13_system_measurement.md` §8.1) and is not this module's business.

    Args:
        intake: The intake to score.
        anti_patterns: Quote-verified matches from `find_anti_patterns`.

    Returns:
        The :class:`Outcome`, with its gate trace and explanation.
    """
    assessment = Assessment(
        archetype_id=None,
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=dimension.id,
                score=None,
                confidence=Confidence.LOW,
                evidence="not asked by the interview",
            )
            for dimension in RUBRIC.dimensions
        ],
        anti_pattern_matches=list(anti_patterns or []),
    )
    return score_assessment(assessment, RUBRIC, PATTERNS, intake)


# ---------------------------------------------------------------------------
# Tool 5 — draft_contract
# ---------------------------------------------------------------------------


def draft_contract(
    intake: RequestIntake, outcome: Outcome, approval_date: date | None = None
) -> ContractResult:
    """Draft the Measurement Contract, for a `go` and nothing else.

    Args:
        intake: The filled intake.
        outcome: The scored outcome.
        approval_date: Injected rather than read from the clock, so the review
            arithmetic stays testable. Defaults to today.

    Returns:
        A :class:`ContractResult`; its ``contract`` is ``None`` unless the
        verdict is ``go``.
    """
    assessment = Assessment(
        archetype_id=None,
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=d.id,
                score=None,
                confidence=Confidence.LOW,
                evidence="not asked by the interview",
            )
            for d in RUBRIC.dimensions
        ],
        anti_pattern_matches=[],
    )
    return issue_contract(
        outcome, assessment, intake, approval_date or date.today()
    )
