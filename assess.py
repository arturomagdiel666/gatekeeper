"""Single-shot assessment of a request, from intake to verdict to contract.

**One constrained-generation call.** No conversational interview, no agent
loop, no native tool calls. The justification is this project's own
measurement (ADR-015): the constrained path returned valid structured output in
60 of 60 trials, while the native tool-call path lost 10-20% of attempts to
``no_call``. A multi-turn loop multiplies that per-turn failure across every
turn; a single constrained call has one failure point, one retry, and a
deterministic parse.

The flow is deliberately thin:

1. Generate the system prompt **from the config** — ``rubric.yaml`` anchors
   included verbatim, so the model scores against the real descriptors and
   tuning the rubric tunes the prompt. There is no second copy to drift.
2. One :meth:`~provider.LLMProvider.chat` call with ``response_schema``.
3. Parse and validate. On failure, retry **once** with the validation error
   appended as a corrective message, then surface the failure rather than
   looping.
4. Score deterministically, and issue a Measurement Contract if the verdict is
   ``go``.

Everything that decides anything lives in ``scoring.py`` and ``contracts.py``.
This module only assembles the prompt and moves data between them.
"""

from __future__ import annotations

import copy
import logging
import os
import threading
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import PATTERNS, RUBRIC, Patterns, Rubric
from contracts import CONTRACTS, ContractsConfig, issue_contract
from provider import LLMProvider, parse_json_content
from schemas import (
    Assessment,
    Confidence,
    DimensionAssessment,
    MeasurementContract,
    RequestIntake,
)
from scoring import Outcome, derive_scores, score

__all__ = [
    "AssessmentResult",
    "AssessmentError",
    "build_system_prompt",
    "build_response_schema",
    "build_user_message",
    "assess_request",
    "assess_timeout_seconds",
    "MAX_RETRIES",
    "DEFAULT_TIMEOUT_SECONDS",
]

logger = logging.getLogger(__name__)

#: Seconds to wait for the provider before abandoning the call. Phase 3.2
#: measured per-request latency as bimodal: five of six requests completed in
#: about five seconds, one took 416.6s. 30s is roughly six times the median and
#: far below the pathological tail, so it cuts the tail without touching normal
#: operation. Override with ASSESS_TIMEOUT_SECONDS.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: One retry, then surface the failure. Retrying further hides a systematic
#: problem behind latency instead of reporting it.
MAX_RETRIES = 1


class AssessmentError(RuntimeError):
    """Raised when the model could not produce a valid assessment."""


class _ProviderTimeout(RuntimeError):
    """Internal: the provider did not answer within the budget."""


def assess_timeout_seconds() -> float:
    """The provider timeout in seconds, from ``ASSESS_TIMEOUT_SECONDS``.

    A missing, unparseable, or non-positive value falls back to
    :data:`DEFAULT_TIMEOUT_SECONDS` with a logged warning — a malformed
    override must not silently disable the timeout.
    """
    raw = os.environ.get("ASSESS_TIMEOUT_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "ASSESS_TIMEOUT_SECONDS=%r is not a number; using %.0fs",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        logger.warning(
            "ASSESS_TIMEOUT_SECONDS=%r is not positive; using %.0fs",
            raw,
            DEFAULT_TIMEOUT_SECONDS,
        )
        return DEFAULT_TIMEOUT_SECONDS
    return value


def _chat_with_timeout(
    provider: LLMProvider,
    messages: list[dict],
    schema: dict,
    temperature: float,
    timeout: float,
):
    """Call the provider, giving up after ``timeout`` seconds.

    Runs the call on a **daemon** thread and joins with a deadline. Two
    deliberate consequences:

    * The abandoned call cannot be killed — Python offers no way to interrupt a
      blocking socket read in another thread — so it keeps running and keeps
      occupying the model until it finishes on its own. What the timeout buys is
      that the *caller* is freed, not that the work stops.
    * The thread is a daemon precisely so that orphan does not hold the
      interpreter open at exit, which is what would otherwise turn a 416-second
      outlier into a 416-second hang for a script that had already moved on.

    Raises:
        _ProviderTimeout: If the provider did not answer in time.
    """
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["response"] = provider.chat(
                messages, response_schema=schema, temperature=temperature
            )
        except BaseException as exc:  # re-raised on the calling thread
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True, name="gatekeeper-assess")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise _ProviderTimeout(
            f"the provider did not answer within {timeout:g}s"
        )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["response"]


class AssessmentResult(BaseModel):
    """Everything produced by assessing one request."""

    model_config = ConfigDict(extra="forbid")

    intake: RequestIntake
    #: ``None`` only when the call timed out — there is no assessment to carry.
    assessment: Assessment | None = None
    #: ``None`` only when the call timed out; nothing was scored.
    outcome: Outcome | None = None
    contract: MeasurementContract | None = None
    #: True when the provider exceeded the timeout budget. This is an
    #: INFRASTRUCTURE result, not a model result: it says nothing about the
    #: request and must never be counted as a wrong verdict.
    timed_out: bool = False
    #: The budget that was applied, so a timeout can be read in context.
    timeout_seconds: float | None = None
    #: Metric proposals the model made that were not candidates for the
    #: archetype. Recorded rather than honoured, like hallucinated dimension ids.
    ignored_metric_ids: list[str] = Field(default_factory=list)
    #: How many corrective retries were needed. Above zero is worth watching.
    retry_count: int = 0
    #: Dimensions settled from the intake form; never shown to the model.
    derived_dimensions: list[str] = Field(default_factory=list)
    #: Dimensions the model was actually asked to score.
    model_scored_dimensions: list[str] = Field(default_factory=list)


def _render_dimensions(rubric: Rubric, omit: set[str] | None = None) -> str:
    """Render each dimension with its axis and all five anchors.

    Dimensions in ``omit`` are skipped entirely: they are resolved
    deterministically from the intake for this request, so the model is not
    being asked to score them and their anchors are dead weight in the prompt.
    On a 7B model that weight is not free — see ADR-022.
    """
    skip = omit or set()
    blocks: list[str] = []
    for dimension in rubric.dimensions:
        if dimension.id in skip:
            continue
        lines = [
            f"### {dimension.id}  ({dimension.label})",
            f"Measures: {' '.join(dimension.axis.split())}",
        ]
        # A dimension may carry a procedure as well as a construct. It is
        # rendered here rather than folded into `axis` so that the axis line
        # stays a single-construct statement a reader can check the anchors
        # against — see ADR-026.
        if dimension.scoring_rule:
            lines.append(
                f"How to score: {' '.join(dimension.scoring_rule.split())}"
            )
        lines += [
            f"Direction: {dimension.direction} (weight {dimension.weight})",
            "Levels:",
        ]
        for level in rubric.scale.levels:
            anchor = " ".join(dimension.anchors[level].split())
            lines.append(f"  {level} = {anchor}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_archetypes(patterns: Patterns) -> str:
    """Render the archetype ids with a one-line description and their signals."""
    lines: list[str] = []
    for archetype in patterns.archetypes:
        description = " ".join(archetype.description.split())
        lines.append(f"- {archetype.id}: {description}")
        lines.append(f"    Signals: {'; '.join(archetype.signals)}")
    return "\n".join(lines)


def _render_anti_patterns(patterns: Patterns) -> str:
    """Render the anti-pattern ids with their signals and blocking status."""
    lines: list[str] = []
    for anti_pattern in patterns.anti_patterns:
        blocking = "BLOCKING" if anti_pattern.hard_block else "advisory"
        description = " ".join(anti_pattern.description.split())
        lines.append(f"- {anti_pattern.id} [{blocking}]: {description}")
        if anti_pattern.two_part_evidence:
            lines.append(
                "    NEEDS TWO QUOTES: fill in both quote and second_quote. "
                "One part alone is not a match."
            )
        lines.append(f"    Signals: {'; '.join(anti_pattern.signals)}")
    return "\n".join(lines)


def _render_metrics(contracts_config: ContractsConfig) -> str:
    """Render the candidate metrics per archetype."""
    lines: list[str] = []
    for template in contracts_config.archetypes:
        candidates = ", ".join(template.candidate_metric_ids)
        lines.append(f"- {template.id}: {candidates}")
    return "\n".join(lines)


def build_system_prompt(
    rubric: Rubric | None = None,
    patterns: Patterns | None = None,
    contracts_config: ContractsConfig | None = None,
    omit_dimensions: set[str] | None = None,
) -> str:
    """Assemble the assessment system prompt from the configuration.

    The anchors are embedded verbatim so the model scores against the same
    descriptors a human reviewer would read. Tuning ``rubric.yaml`` therefore
    tunes the prompt.

    Every field is referred to by its exact schema name. Near-synonyms are
    forbidden — see :data:`schemas.BANNED_PROMPT_SYNONYMS` and the test that
    enforces it — because prompt prose that names a field differently makes the
    model rename the key (ADR-004).

    Args:
        rubric: Rubric to describe; defaults to the loaded ``rubric.yaml``.
        patterns: Pattern library; defaults to the loaded ``patterns.yaml``.
        contracts_config: Contract templates; defaults to ``contracts.yaml``.

    Returns:
        The system prompt.
    """
    active_rubric = rubric or RUBRIC
    active_patterns = patterns or PATTERNS
    active_contracts = contracts_config or CONTRACTS
    skip = omit_dimensions or set()
    asked = [d for d in active_rubric.dimensions if d.id not in skip]

    return f"""You assess requests submitted to an internal IT AI Agent Hub.

A business area has asked the Hub to build an AI agent. Your task is to read
the request and fill in a structured record of what it establishes. You do NOT
decide anything. You do NOT add up numbers. A separate program applies weights,
gates and thresholds to what you record, and produces the decision.

## What you produce

dimension_assessments must contain EXACTLY these {len(asked)} entries, one per
dimension, in this order:

{chr(10).join(f"  {i}. {d.id}" for i, d in enumerate(asked, 1))}

Those {len(asked)} ids are the ONLY valid values for dimension_id. They are not
the same thing as proposed_metric_id, which comes from a separate list further
down — never put a metric id in dimension_id.

Each entry contains:

- dimension_id: one of the {len(asked)} ids listed immediately above.
- score: an integer from {active_rubric.scale.min} to {active_rubric.scale.max}
  matching the level whose description fits what the request actually says, or
  null if the request does not establish it.
- evidence: what in the request supports that score, quoted or closely
  paraphrased from the request text. Point at something actually present.
- confidence: low, medium, or high.

Plus, at the top level:

- archetype_id: the best-matching archetype id, or null if none fits.
- anti_pattern_matches: every anti-pattern the request matches. Each entry is
  an object with anti_pattern_id, quote, and quote_confidence. Empty list if
  none match — which is the common case. A few anti-patterns are marked below as
  needing two quotes; for those, also fill in second_quote.
- proposed_metric_id: the candidate metric id that best fits this request, from
  the list for the matching archetype, or null to accept the default.
- stated_baseline_value: the current value of that metric as a number, ONLY if
  the request states it. Otherwise null.

## Rules you must follow

1. NEVER invent a score. If the request does not establish a dimension, set
   score to null and say in evidence what was missing. A null is a useful
   answer; a guess is not.
2. Score against the level descriptions below, not against your impression.
   Find the level whose description matches, and record that number.
3. evidence must refer to the request. Do not import assumptions about how such
   things usually work.
4. Use exact ids from the lists below. Do not invent ids.
5. Set confidence to low when you are extrapolating from thin information, even
   if you are confident in the extrapolation.
6. An anti_pattern_matches entry REQUIRES a quote: a span of text copied word
   for word from the request above. Not a paraphrase, not a summary, not
   something you inferred. If you cannot copy out a span that shows the
   pattern, the pattern is not there — leave it out. A quote that does not
   appear in the request is discarded and the match is thrown away, so an
   invented quote gains you nothing.
7. Do not match an anti-pattern because the request RESEMBLES its category.
   Match it only on what the request says. Where an anti-pattern below is
   marked as needing two quotes, both parts must be copied out of the request;
   naming a platform as the place the data lives is not the second part, and
   without the second part there is no match.

## Dimensions

{_render_dimensions(active_rubric, skip)}

## Archetypes

{_render_archetypes(active_patterns)}

## Anti-patterns

Those marked BLOCKING stop the request outright, so they are held to a higher
standard than a dimension score: each needs a quote copied from the request.
Most requests match NONE of these. An empty anti_pattern_matches list is a
normal, common, correct answer.

{_render_anti_patterns(active_patterns)}

## Candidate metrics, by archetype

Pick proposed_metric_id from the list for the archetype you selected.

{_render_metrics(active_contracts)}

Respond with a single JSON object matching the schema. No prose outside it."""


def build_response_schema(
    rubric: Rubric | None = None,
    patterns: Patterns | None = None,
    contracts_config: ContractsConfig | None = None,
    omit_dimensions: set[str] | None = None,
) -> dict:
    """Derive the response schema from :class:`~schemas.Assessment` and the config.

    Every id the model may emit is pinned to an ``enum`` drawn from the loaded
    configuration, and ``dimension_assessments`` is pinned to exactly one entry
    per rubric dimension.

    This is not belt-and-braces on top of the prompt — it is the mechanism that
    works. Told in prose that ``dimension_id`` must come from the rubric's seven
    ids, ``qwen2.5:7b`` emitted metric ids from the adjacent section anyway, in
    every attempt. Under a grammar-constrained enum it cannot: the tokens are
    not reachable. The same reasoning as ADR-005 — constrain the output rather
    than ask for it — applied one level deeper.

    Args:
        rubric: Rubric supplying the dimension ids; defaults to the loaded one.
        patterns: Pattern library supplying archetype and anti-pattern ids.
        contracts_config: Contract templates supplying the metric ids.

    Returns:
        A JSON Schema dict ready to pass as ``response_schema``.
    """
    active_rubric = rubric or RUBRIC
    active_patterns = patterns or PATTERNS
    active_contracts = contracts_config or CONTRACTS

    schema = Assessment.model_json_schema()
    skip = omit_dimensions or set()
    dimension_ids = [i for i in active_rubric.dimension_ids if i not in skip]

    entry = schema["$defs"]["DimensionAssessment"]["properties"]
    entry["dimension_id"] = {"type": "string", "enum": dimension_ids}
    #: One PINNED copy of the entry schema per dimension, in rubric order, so the
    #: grammar itself decides which id sits in which position. See the block
    #: comment on `prefixItems` below.
    pinned_entries = []
    for dimension_id in dimension_ids:
        pinned = copy.deepcopy(schema["$defs"]["DimensionAssessment"])
        pinned["properties"]["dimension_id"] = {"const": dimension_id}
        pinned_entries.append(pinned)

    root = schema["properties"]
    root["archetype_id"] = {
        "anyOf": [{"type": "string", "enum": active_patterns.archetype_ids}, {"type": "null"}]
    }
    schema["$defs"]["AntiPatternMatch"]["properties"]["anti_pattern_id"] = {
        "type": "string",
        "enum": [a.id for a in active_patterns.anti_patterns],
    }
    root["proposed_metric_id"] = {
        "anyOf": [
            {"type": "string", "enum": [m.id for m in active_contracts.metrics]},
            {"type": "null"},
        ]
    }
    # Exactly one entry per dimension: fewer is an incomplete assessment the
    # model chose not to make, more is duplication the scorer would discard.
    slot = root["dimension_assessments"]
    slot["minItems"] = len(dimension_ids)
    slot["maxItems"] = len(dimension_ids)
    # DISTINCTNESS BELONGS IN THE GRAMMAR (ADR-032). Count plus an enum is not
    # enough: `qwen2.5:7b` satisfied both by emitting data_readiness twice and
    # omitting implementation_effort, on 29 of 30 cases across two measurement
    # passes, which made that dimension null everywhere and drove 15 of 22 verdict
    # errors. `uniqueItems` would not have caught it either — two entries with the
    # same id and different evidence are distinct items.
    #
    # `prefixItems` pins position i to `{"const": <dimension i>}`, so the decoder
    # cannot emit any other id there. Measured, not assumed: told to put one id in
    # every slot, the model emitted the pinned sequence instead.
    slot["prefixItems"] = pinned_entries
    # `items` MUST be removed rather than left as a fallback. Measured too: with
    # both present, Ollama's converter honours `items` and ignores `prefixItems`,
    # and the model duplicated freely again. The belt-and-braces version disables
    # the belt. minItems == maxItems == len(prefixItems) already forbids extras.
    slot.pop("items", None)
    return schema


def build_user_message(intake: RequestIntake) -> str:
    """Render the intake as the user turn of the assessment call."""
    stated = intake.stated_benefit or "(not stated)"
    volume = "(not stated)"
    if intake.times_per_period is not None and intake.period is not None:
        volume = (
            f"{intake.times_per_period} per {intake.period.value} "
            f"(about {intake.instances_per_year:,.0f} a year)"
        )
    artefacts = "(not asked)"
    if intake.existing_deterministic_artefacts is not None:
        artefacts = "(none — the requester was asked and listed nothing)"
        if intake.existing_deterministic_artefacts:
            artefacts = "\n" + "\n".join(
                f"    * {a.name}: {a.what_it_does} "
                + (
                    "[after this runs the work is done]"
                    if a.completes_without_judgement
                    else "[after this runs somebody still has to decide something]"
                )
                for a in intake.existing_deterministic_artefacts
            )
    return f"""Assess this request.

Requesting area: {intake.requesting_area or "(not stated)"}
Business owner: {intake.business_owner or "(none named)"}

Request:
{intake.request_text}

How the work is done today:
{intake.process_description or "(not described)"}

Benefit claimed by the requester:
{stated}

Answers the requester gave on the intake form:
- Who does this today: {intake.who_does_this_today or "(not stated)"}
- People affected: {intake.people_affected if intake.people_affected is not None else "(not stated)"}
- Times this task would be done, end to end: {volume}
- Minutes one instance takes today: {intake.minutes_per_instance if intake.minutes_per_instance is not None else "(not stated)"}
- Cost of one instance today: {intake.cost_per_instance if intake.cost_per_instance is not None else "(not stated)"}
- Last tool built for these same users: {intake.prior_tool_for_these_users.value}
- Where the data lives: {intake.where_the_data_lives or "(not stated)"}
- Data classification: {intake.data_sensitivity.value}
- Deterministic things that already exist for this work: {artefacts}

Use these answers. "Last tool built for these same users" is direct evidence
for adoption_risk and appears nowhere else. Where an answer is "(not stated)"
or "unknown", fall back to the request text, and set score to null if neither
establishes the dimension.

The last two answers are NOT yours to multiply together. If the request itself
states no magnitude, business_value is null and the program computes it from
those two numbers — see How to score under that dimension."""


def assess_request(
    intake: RequestIntake,
    provider: LLMProvider,
    rubric: Rubric | None = None,
    patterns: Patterns | None = None,
    contracts_config: ContractsConfig | None = None,
    approval_date: date | None = None,
    temperature: float = 0.2,
    timeout_seconds: float | None = None,
) -> AssessmentResult:
    """Assess a request end to end: model call, scoring, and contract.

    Args:
        intake: The submitted request.
        provider: The LLM backend to use.
        rubric: Rubric override; defaults to the loaded ``rubric.yaml``.
        patterns: Pattern library override.
        contracts_config: Contract template override.
        approval_date: Date recorded on an issued contract. Defaults to today.
            Injected so tests can pin it; the scorer itself never reads a clock.
        temperature: Sampling temperature for the assessment call.
        timeout_seconds: Seconds to wait for the provider; defaults to
            ``ASSESS_TIMEOUT_SECONDS`` or :data:`DEFAULT_TIMEOUT_SECONDS`.

    Returns:
        An :class:`AssessmentResult` with the assessment, the scored outcome,
        and a contract when the verdict is ``go``. On timeout, a result with
        ``timed_out=True`` and no assessment — the call is **not** retried and
        **not** raised, because a slow provider is an infrastructure condition
        and the caller should be free to fall back rather than to fail.

    Raises:
        AssessmentError: If the model answered but could not produce a
            schema-valid assessment within :data:`MAX_RETRIES` retries.
    """
    active_rubric = rubric or RUBRIC
    active_patterns = patterns or PATTERNS
    active_contracts = contracts_config or CONTRACTS

    # Dimensions this intake settles outright are not asked of the model:
    # omitted from the prompt and from the schema, then merged back after
    # parsing so the Assessment is still complete.
    derived = derive_scores(active_rubric, intake)
    omit = set(derived)

    system_prompt = build_system_prompt(
        active_rubric, active_patterns, active_contracts, omit
    )
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_user_message(intake)},
    ]
    schema = build_response_schema(
        active_rubric, active_patterns, active_contracts, omit
    )

    assessment: Assessment | None = None
    retry_count = 0
    last_error = ""
    budget = timeout_seconds if timeout_seconds is not None else assess_timeout_seconds()
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = _chat_with_timeout(
                provider, messages, schema, temperature, budget
            )
        except _ProviderTimeout:
            # Deliberately not retried: a call that ran past the budget once is
            # the pathological tail, and a second attempt only doubles the wait.
            logger.warning(
                "assessment timed out after %gs; returning a timed_out result",
                budget,
            )
            return AssessmentResult(
                intake=intake,
                timed_out=True,
                timeout_seconds=budget,
                derived_dimensions=sorted(derived),
                model_scored_dimensions=[
                    i for i in active_rubric.dimension_ids if i not in omit
                ],
            )
        try:
            assessment = Assessment.model_validate(parse_json_content(response))
            break
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
            if attempt >= MAX_RETRIES:
                break
            retry_count += 1
            messages = [
                *messages,
                {"role": "assistant", "content": response.text or ""},
                {
                    "role": "user",
                    "content": (
                        "That response did not match the schema. Fix exactly "
                        f"these problems and return the whole object again:\n"
                        f"{last_error}"
                    ),
                },
            ]

    if assessment is None:
        raise AssessmentError(
            "The model did not return a schema-valid assessment after "
            f"{retry_count} retry(ies). Last error:\n{last_error}"
        )

    # Merge the derived dimensions back in, so the Assessment carried on the
    # result is complete even though the model never saw them.
    scored_by_model = [e.dimension_id for e in assessment.dimension_assessments]
    for dimension_id, (score_value, why) in derived.items():
        if dimension_id not in scored_by_model:
            assessment.dimension_assessments.append(
                DimensionAssessment(
                    dimension_id=dimension_id,
                    score=score_value,
                    evidence=why,
                    confidence=Confidence.HIGH,
                )
            )

    outcome = score(assessment, active_rubric, active_patterns, intake)
    contract_result = issue_contract(
        outcome,
        assessment,
        intake,
        approval_date or date.today(),
        active_contracts,
    )

    return AssessmentResult(
        intake=intake,
        assessment=assessment,
        outcome=outcome,
        contract=contract_result.contract,
        ignored_metric_ids=contract_result.ignored_metric_ids,
        retry_count=retry_count,
        derived_dimensions=sorted(derived),
        model_scored_dimensions=[
            i for i in active_rubric.dimension_ids if i not in omit
        ],
    )
