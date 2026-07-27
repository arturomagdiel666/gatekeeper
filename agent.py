"""The intake agent: it asks, the tools decide.

A request that arrives incomplete — which is most of them — used to return
`incomplete` and stop. That is a correct verdict and a useless product. This
closes the gap by asking.

The division of labour is the one the measurement programme arrived at over six
runs and two model sizes: **the model finds and quotes the evidence; the form
and the tables decide.** Here the model chooses which single question to ask
next and phrases it in the requester's language, and extracts a value and a
verbatim span from the reply. Every score, every gate and every verdict comes
from `agent_tools`, in deterministic Python. The model cannot write a dimension
score because `score_and_gate` takes a `RequestIntake` and there is no parameter
through which a number could arrive.

**Why constrained generation rather than native tool calling.** This project
measured both: a JSON response schema returned a usable object 60 times out of
60, while native tool calling lost 10–20% of turns to the model simply not
emitting a call (`scripts/spike_toolcalling.py`). Native tool calling is the
idiomatic choice and the idiomatic choice lost, so the model emits a structured
object naming the tool and its arguments and this loop dispatches it.

The loop terminates on four conditions and always reports which one it was. The
fourth exists because a model that has run out of useful questions will happily
keep asking useless ones: if two consecutive answers add no field, the
information does not exist, and `incomplete` naming the reason is the honest
outcome rather than the result of exhausting a budget.
"""

from __future__ import annotations

import json
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

import agent_tools as tools
from agent_tools import ASKABLE_BY_NAME, CompletenessReport, FieldProvenance
from assess import ProviderTimeout, assess_timeout_seconds, chat_with_timeout
from provider import LLMProvider, parse_json_content
from schemas import AntiPatternMatch, RequestIntake
from scoring import Outcome, Verdict

RUNS_DIR = Path(__file__).resolve().parent / "runs"

#: How many questions the requester will answer before the agent gives up. Eight
#: is the default because the intake has ten askable fields and an interview that
#: asks for all of them is a form with extra steps.
DEFAULT_MAX_QUESTIONS = 8

#: Consecutive answers that may add nothing before the agent concludes the
#: information does not exist. Two, not one: the first may be a misunderstanding
#: the next question clears up, and a second in a row is a pattern.
BARREN_ANSWER_LIMIT = 2


class StopReason(str, Enum):
    """Why the interview ended. Always reported."""

    VERDICT_REACHED = "verdict_reached"
    GATE_FIRED = "gate_fired"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_NEW_INFORMATION = "no_new_information"


class Turn(BaseModel):
    """One exchange, and what it produced.

    Attributes:
        n: Turn number, from 1.
        tool: The tool the model named.
        target_field: The intake field the question was aimed at.
        question: What was put to the requester.
        answer: What they replied.
        recorded: The provenance entry, when the answer filled a field.
        rejected: Why the extraction was refused, when it was.
    """

    model_config = ConfigDict(extra="forbid")

    n: int
    tool: str
    target_field: str | None = None
    question: str | None = None
    answer: str | None = None
    recorded: FieldProvenance | None = None
    rejected: str | None = None


class InterviewResult(BaseModel):
    """Everything the interview produced, and how it got there.

    Attributes:
        intake: The filled intake.
        verdict: The verdict from `score_and_gate`, never from the model.
        outcome: The full scored outcome with its gate trace.
        stop_reason: Which stopping condition ended the interview.
        stop_detail: The gate id, the missing dimensions, or the budget.
        transcript: Every turn, in order.
        provenance: Every filled field with its turn and verbatim span.
        anti_patterns: Quote-verified matches found in the request.
        discarded_anti_patterns: Matches thrown away, with the reason.
        contract: The Measurement Contract draft, for a `go`.
    """

    model_config = ConfigDict(extra="forbid")

    intake: RequestIntake
    verdict: Verdict
    outcome: Outcome
    stop_reason: StopReason
    stop_detail: str
    transcript: list[Turn] = Field(default_factory=list)
    provenance: list[FieldProvenance] = Field(default_factory=list)
    anti_patterns: list[AntiPatternMatch] = Field(default_factory=list)
    discarded_anti_patterns: list[tuple[str, str]] = Field(default_factory=list)
    contract: dict | None = None


# ---------------------------------------------------------------------------
# The two constrained calls
# ---------------------------------------------------------------------------

DECIDE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": ["ask", "find_anti_patterns", "finish"]},
        "target_field": {"type": "string"},
        "question": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["tool", "target_field", "question", "why"],
}

#: The shape of `value`, per field parser. A field whose value is structured
#: gets a structured schema rather than a string holding JSON.
#:
#: The first live run failed here. `existing_deterministic_artefacts` asked the
#: model to write a JSON list *inside a JSON string*, and grammar-constrained
#: decoding cannot help with that — the grammar constrains the outer string and
#: has nothing to say about its contents. The 7B emitted unquoted keys twice,
#: both were rejected, and two barren answers ended the interview with one field
#: filled. Same lesson as ADR-032 one level down: **a constraint that can be
#: moved into the grammar is not enforced by leaving it implicit.**
VALUE_SCHEMAS: dict[str, dict] = {
    "text": {"type": "string"},
    "number": {"type": "number"},
    "data_sensitivity": {
        "type": "string",
        "enum": ["public", "internal", "confidential", "regulated"],
    },
    "prior_tool": {"type": "string", "enum": ["none", "adopted", "abandoned"]},
    "volume": {
        "type": "object",
        "properties": {
            "times": {"type": "integer"},
            "period": {"type": "string", "enum": ["day", "week", "month", "year"]},
        },
        "required": ["times", "period"],
    },
    "artefacts": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "what_it_does": {"type": "string"},
                "completes_without_judgement": {"type": "boolean"},
            },
            "required": ["name", "what_it_does", "completes_without_judgement"],
        },
    },
    # The three converted in v3.0.0. Every one of them is structured, so every
    # one of them is in the grammar — the lesson ADR-034 paid for.
    "data_evidence": {
        "type": "object",
        "properties": {
            "systems": {"type": "array", "items": {"type": "string"}},
            "sample_checked": {
                "type": "string",
                "enum": ["not_looked", "looked_usable", "looked_problems"],
            },
            "correct_examples": {"type": "integer", "minimum": 0},
            "quality_criteria_agreed": {"type": "boolean"},
        },
        "required": [
            "systems",
            "sample_checked",
            "correct_examples",
            "quality_criteria_agreed",
        ],
    },
    "effort_evidence": {
        "type": "object",
        "properties": {
            "systems_to_integrate": {"type": "array", "items": {"type": "string"}},
            "procurement": {
                "type": "string",
                "enum": [
                    "none",
                    "existing_licence",
                    "new_licence_existing_vendor",
                    "new_vendor",
                ],
            },
            "approving_teams": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["systems_to_integrate", "procurement", "approving_teams"],
    },
    "adoption_evidence": {
        "type": "object",
        "properties": {
            "users_consulted": {
                "type": "string",
                "enum": ["nobody", "told_not_asked", "consulted", "requested_it"],
            },
            # Deliberately NOT nullable in the grammar: the model is told to
            # leave it empty when there is no quote, and `record_field` demotes
            # the consultation level when it is. A schema that let the field
            # vanish would make "no quote" and "forgot the key" the same event.
            "user_quote": {"type": "string"},
            "workflow_fit": {
                "type": "string",
                "enum": [
                    "existing_step",
                    "existing_step_modified",
                    "new_step",
                    "replaces_chosen_way",
                ],
            },
            "people_who_must_change": {"type": "integer", "minimum": 0},
        },
        "required": [
            "users_consulted",
            "user_quote",
            "workflow_fit",
            "people_who_must_change",
        ],
    },
}


def extract_schema_for(field_name: str) -> dict:
    """The extraction schema for one field, with `value` shaped for its parser."""
    parser = ASKABLE_BY_NAME[field_name].parser
    return {
        "type": "object",
        "properties": {
            "value": VALUE_SCHEMAS.get(parser, VALUE_SCHEMAS["text"]),
            "span": {"type": "string"},
            "answered": {"type": "boolean"},
        },
        "required": ["value", "span", "answered"],
    }


def _decide_messages(
    intake: RequestIntake,
    report: CompletenessReport,
    transcript: list[Turn],
    askable: list,
) -> list[dict]:
    asked = "\n".join(f"  - {t.question} → {t.answer}" for t in transcript) or "  (none yet)"
    options = "\n".join(
        f"  - {f.name}"
        + (f"  [decides the gate {f.blocks_gate}]" if f.blocks_gate else "")
        + f"\n      needs: {f.prompt_hint}"
        for f in askable
    )
    return [
        {
            "role": "system",
            "content": (
                "You are interviewing someone who has asked for an AI agent to "
                "be built. Your job is to ask ONE short question that fills ONE "
                "missing field.\n\n"
                "Rules:\n"
                "- Write the question in the same language the requester used.\n"
                "- Use their vocabulary. Never use the words rubric, dimension, "
                "score, gate, anti-pattern, or the field's internal name.\n"
                "- Prefer a field marked as deciding a gate: one answer can end "
                "the conversation and save them every other question.\n"
                "- Never ask something already answered above.\n"
                "- One question. Not two joined by 'and'.\n"
                "- You never assign a score or a verdict. You only ask.\n\n"
                "Set tool to 'ask' with the field you chose. Use "
                "'find_anti_patterns' only to re-scan after the requester has "
                "described something substantial that was not in the original "
                "request. Use 'finish' if no remaining field is worth their time."
            ),
        },
        {
            "role": "user",
            "content": (
                f"ORIGINAL REQUEST:\n{intake.request_text}\n\n"
                f"ALREADY ASKED:\n{asked}\n\n"
                f"STILL MISSING (most decisive first):\n{options}\n\n"
                f"Unresolved rubric weight: {report.unknown_weight:.2f}"
            ),
        },
    ]


def _extract_messages(field_name: str, question: str, answer: str) -> list[dict]:
    field = ASKABLE_BY_NAME[field_name]
    # The schema already constrains the SHAPE of `value` — these say what to put
    # in it, not how to punctuate it.
    shape = {
        "volume": (
            "how many, and the period they are counted in. Count the items "
            "handled separately, not the batches they arrive in"
        ),
        "artefacts": (
            "one entry per thing that already exists. completes_without_judgement "
            "is true only if the work is FINISHED when that thing runs. An empty "
            "list is the correct answer when they said nothing exists"
        ),
        "data_sensitivity": "the classification they described",
        "prior_tool": "what became of the last tool for these users",
        "number": "the number of minutes",
        "data_evidence": (
            "systems: the systems the data is in TODAY — an empty list if it is "
            "only in people's heads or on paper. sample_checked: looked_usable "
            "only if somebody opened real records and reported no problems; "
            "not_looked if the opinion was formed without opening the data. "
            "correct_examples: examples that EXIST NOW, not records that could "
            "be labelled one day. quality_criteria_agreed: true only if a "
            "WRITTEN statement of what makes an output correct has been agreed"
        ),
        "effort_evidence": (
            "systems_to_integrate: only systems CODE must read from or write to "
            "— a file a person exports by hand is not one. approving_teams: only "
            "teams that could STOP this by withholding approval, not teams that "
            "are merely informed. procurement: what must be bought first"
        ),
        "adoption_evidence": (
            "users_consulted: how far the people whose OWN WORK would change "
            "were involved. user_quote: something one of THEM said about this "
            "work, word for word — leave it empty if you have none, and never "
            "invent one; without it the consultation level is demoted. "
            "workflow_fit: existing_step only if the output arrives somewhere "
            "they already open, at the cadence they already open it. "
            "people_who_must_change: people whose own actions change, not people "
            "who receive a different-looking report"
        ),
    }.get(field.parser, "the value in their own words, trimmed")
    return [
        {
            "role": "system",
            "content": (
                "Extract one field from a reply. You are not judging the reply "
                "and you are not scoring anything.\n\n"
                f"value: {shape}\n"
                "span: the requester's words that justify it, copied WORD FOR "
                "WORD from their reply. A span not present in the reply is "
                "rejected, and so is the field.\n"
                "answered: false if the reply does not contain this information "
                "at all — say so rather than inventing a value. 'I don't know' "
                "is an answer that did not answer."
            ),
        },
        {
            "role": "user",
            "content": (
                f"FIELD: {field.name}\nWHAT IT NEEDS: {field.prompt_hint}\n\n"
                f"QUESTION ASKED: {question}\nTHEIR REPLY: {answer}"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class Interview:
    """One interview, resumable a turn at a time.

    The loop is split into `next_question` and `submit` so a UI can drive it —
    Streamlit reruns its script on every interaction and cannot block inside a
    while loop. `run_interview` below is the same loop for callers that can
    block, and is four lines because all of the work is here.

    Attributes:
        intake: The intake as filled so far.
        transcript: Every turn taken.
        provenance: Every filled field with its span.
        stop: The stopping condition once the interview has ended.
    """

    def __init__(
        self,
        request_text: str,
        provider: LLMProvider,
        max_questions: int = DEFAULT_MAX_QUESTIONS,
        approval_date: date | None = None,
    ) -> None:
        """Start an interview and run the opening anti-pattern scan.

        Args:
            request_text: The raw request, as the requester wrote it.
            provider: The model backend, used only to choose and phrase
                questions and to extract values and spans.
            max_questions: Turn budget.
            approval_date: Passed to the contract draft rather than read from
                the clock, so review dates stay testable.
        """
        self.provider = provider
        self.max_questions = max_questions
        self.approval_date = approval_date
        self.intake = RequestIntake(request_text=request_text)
        self.found = tools.find_anti_patterns(request_text, provider)
        self.transcript: list[Turn] = []
        self.provenance: list[FieldProvenance] = []
        # Fields already put to the requester, whether or not the reply filled
        # them. A question asked and not answered is not the same as one never
        # asked, and only the second should hold a gate back.
        self._asked: set[str] = set()
        self._barren = 0
        self._pending: Turn | None = None
        self.stop: tuple[StopReason, str] | None = None
        self.outcome: Outcome = tools.score_and_gate(self.intake, self.found.matches)

    def next_question(self) -> str | None:
        """The next question to put to the requester, or ``None`` if finished."""
        if self.stop is not None:
            return None
        report = tools.assess_completeness(self.intake, frozenset(self._asked))
        self.outcome = tools.score_and_gate(self.intake, self.found.matches)

        self.stop = _stopping_reason(
            report, self.outcome, self.transcript, self._barren, self.max_questions
        )
        if self.stop is not None:
            return None

        askable = useful_fields(report, self.outcome)
        action = _decide(self.provider, self.intake, report, self.transcript, askable)
        turn = Turn(n=len(self.transcript) + 1, tool=action["tool"])

        if action["tool"] != "ask":
            turn.rejected = f"model chose {action['tool']}; ending the interview"
            self.transcript.append(turn)
            self.stop = (StopReason.NO_NEW_INFORMATION, f"agent chose {action['tool']}")
            return None

        field_name = _resolve_field(action.get("target_field", ""), askable)
        self._asked.add(field_name)
        turn.target_field = field_name
        turn.question = action["question"].strip()
        self._pending = turn
        return turn.question

    def submit(self, reply: str) -> Turn:
        """Record the requester's reply to the pending question.

        Args:
            reply: What they said, verbatim.

        Returns:
            The completed :class:`Turn`.

        Raises:
            RuntimeError: If there is no question outstanding.
        """
        if self._pending is None:
            raise RuntimeError("no question is outstanding")
        turn, self._pending = self._pending, None
        turn.answer = reply

        extracted = _extract(self.provider, turn.target_field, turn.question, reply)
        if not extracted.get("answered", False):
            turn.rejected = "the reply did not contain this information"
            self._barren += 1
        else:
            result = tools.record_field(
                self.intake,
                turn.target_field,
                extracted.get("value", ""),
                str(extracted.get("span", "")),
                turn.n,
                turn.question,
                reply,
            )
            if result.accepted:
                self.intake, self._barren = result.intake, 0
                turn.recorded = result.provenance
                self.provenance.append(result.provenance)
            else:
                turn.rejected = result.reason
                self._barren += 1
        self.transcript.append(turn)
        return turn

    def result(self) -> InterviewResult:
        """Everything the interview produced. Callable once it has stopped."""
        reason, detail = self.stop or (
            StopReason.NO_NEW_INFORMATION,
            "interview not finished",
        )
        contract = tools.draft_contract(self.intake, self.outcome, self.approval_date)
        return InterviewResult(
            intake=self.intake,
            verdict=self.outcome.verdict,
            outcome=self.outcome,
            stop_reason=reason,
            stop_detail=detail,
            transcript=self.transcript,
            provenance=self.provenance,
            anti_patterns=self.found.matches,
            discarded_anti_patterns=self.found.discarded,
            contract=(
                contract.contract.model_dump(mode="json") if contract.contract else None
            ),
        )


def run_interview(
    request_text: str,
    answer_fn: Callable[[str], str],
    provider: LLMProvider,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    approval_date: date | None = None,
) -> InterviewResult:
    """Interview the requester until a verdict is reachable, then decide.

    Args:
        request_text: The raw request, as the requester wrote it.
        answer_fn: Called with each question, returns the requester's reply.
        provider: The model backend.
        max_questions: Turn budget.
        approval_date: Injected rather than read from the clock.

    Returns:
        An :class:`InterviewResult`.
    """
    interview = Interview(request_text, provider, max_questions, approval_date)
    while (question := interview.next_question()) is not None:
        interview.submit(answer_fn(question))
    return interview.result()


def _stopping_reason(
    report: CompletenessReport,
    outcome: Outcome,
    transcript: list[Turn],
    barren: int,
    max_questions: int,
) -> tuple[StopReason, str] | None:
    """The four conditions, checked in the order that serves the requester.

    A fired gate comes first because further questions would cost them time for
    an answer already decided. Running out of budget comes last because it is
    the least informative thing that can happen.
    """
    firing = [g for g in outcome.triggered_gates if g.gate_id not in report.premature_gates]
    if firing:
        gate = firing[0]
        return StopReason.GATE_FIRED, f"{gate.gate_id} → {gate.verdict.value}: {gate.detail}"
    if report.can_reach_verdict:
        return StopReason.VERDICT_REACHED, f"{outcome.verdict.value} on the filled intake"
    if barren >= BARREN_ANSWER_LIMIT:
        return StopReason.NO_NEW_INFORMATION, (
            f"{barren} consecutive answers added nothing; unresolved: "
            f"{', '.join(sorted(outcome.unknown_dimensions))}"
        )
    if len(transcript) >= max_questions:
        return StopReason.BUDGET_EXHAUSTED, (
            f"{max_questions} questions asked; unresolved: "
            f"{', '.join(sorted(outcome.unknown_dimensions))}"
        )
    if not report.missing:
        return StopReason.NO_NEW_INFORMATION, "no askable field remains"

    # Nothing left worth asking. A remaining field earns its question only if it
    # can decide a gate or resolve a dimension that is still unknown; asking for
    # anything else spends the requester's time on a verdict that will not move.
    # This is what keeps a request that genuinely cannot be completed from
    # collecting eight questions before admitting it.
    if not useful_fields(report, outcome):
        return StopReason.NO_NEW_INFORMATION, (
            "no remaining question can change the verdict; unresolved: "
            f"{', '.join(sorted(outcome.unknown_dimensions))} — no intake field "
            "supplies any of these"
        )
    return None


def useful_fields(report: CompletenessReport, outcome: Outcome) -> list:
    """The missing fields still worth a question.

    A field earns a question if it can decide a gate or resolve a dimension that
    is currently unknown. Everything else is a form field, and the interview is
    not a form: `who_does_this_today` is useful context on a submission and a
    wasted turn in a conversation, because no verdict moves when it is answered.
    """
    return [
        f
        for f in report.missing
        if (f.blocks_gate and f.blocks_gate in report.blocking_gates_reachable)
        or (f.feeds_dimension in outcome.unknown_dimensions)
    ]


def _call(provider: LLMProvider, messages: list[dict], schema: dict, temperature: float):
    """One bounded model call, or ``None`` if the provider did not answer.

    A demo somebody is sitting in front of must not hang on a slow turn. The
    budget and the daemon-thread mechanism are `assess.py`'s, reused rather than
    reimplemented — including its honest caveat: the abandoned call keeps running
    and keeps occupying the model, so what the timeout buys is that the caller is
    freed, not that the work stops.
    """
    try:
        return chat_with_timeout(
            provider, messages, schema, temperature, assess_timeout_seconds()
        )
    except ProviderTimeout:
        return None


def _decide(
    provider: LLMProvider,
    intake: RequestIntake,
    report: CompletenessReport,
    transcript: list[Turn],
    askable: list,
) -> dict:
    response = _call(
        provider,
        _decide_messages(intake, report, transcript, askable),
        DECIDE_SCHEMA,
        0.2,
    )
    fallback = {
        "tool": "ask",
        "target_field": askable[0].name,
        "question": askable[0].prompt_hint,
        "why": "fallback: the model's turn was unusable",
    }
    if response is None:
        return fallback
    try:
        action = parse_json_content(response)
    except ValueError:
        return fallback
    # Parsing is not the same as conforming. A constrained model still returns
    # the wrong shape occasionally, and a KeyError here would crash a
    # conversation someone is sitting in front of — so an action missing its
    # tool, or naming one that does not exist, falls back to the most decisive
    # remaining field rather than to a traceback.
    if not isinstance(action, dict) or action.get("tool") not in {
        "ask",
        "find_anti_patterns",
        "finish",
    }:
        return fallback
    if action["tool"] == "ask" and not str(action.get("question", "")).strip():
        return fallback
    return action


def _extract(provider: LLMProvider, field_name: str, question: str, answer: str) -> dict:
    response = _call(
        provider,
        _extract_messages(field_name, question, answer),
        extract_schema_for(field_name),
        0.0,
    )
    if response is None:
        return {"answered": False, "value": "", "span": ""}
    try:
        return parse_json_content(response)
    except ValueError:
        return {"answered": False, "value": "", "span": ""}


def _resolve_field(name: str, askable: list) -> str:
    """Hold the model to the menu. A field it invented is replaced, not honoured."""
    return name if name in {f.name for f in askable} else askable[0].name


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


def save_transcript(result: InterviewResult, directory: Path | None = None) -> Path:
    """Persist a run so it can be replayed and shown.

    The filename is derived from the request rather than the clock, so re-running
    the same demo overwrites its own transcript instead of littering.

    Args:
        result: The finished interview.
        directory: Where to write; defaults to ``runs/``.

    Returns:
        The path written.
    """
    target = directory or RUNS_DIR
    target.mkdir(parents=True, exist_ok=True)
    slug = "".join(
        c if c.isalnum() else "_" for c in result.intake.request_text[:40].lower()
    ).strip("_")
    path = target / f"{slug or 'interview'}.json"
    path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)
    )
    return path
