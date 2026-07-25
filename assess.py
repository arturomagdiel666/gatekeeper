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
    "MAX_RETRIES",
]

#: One retry, then surface the failure. Retrying further hides a systematic
#: problem behind latency instead of reporting it.
MAX_RETRIES = 1


class AssessmentError(RuntimeError):
    """Raised when the model could not produce a valid assessment."""


class AssessmentResult(BaseModel):
    """Everything produced by assessing one request."""

    model_config = ConfigDict(extra="forbid")

    intake: RequestIntake
    assessment: Assessment
    outcome: Outcome
    contract: MeasurementContract | None = None
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
  none match — which is the common case.
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
   Match it only on what the request says. In particular, do not match
   existing_licensed_capability unless the request itself mentions a product,
   a licence, or a tool the company already has.

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
    root["dimension_assessments"]["minItems"] = len(dimension_ids)
    root["dimension_assessments"]["maxItems"] = len(dimension_ids)
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
- How often it runs: {volume}
- Last tool built for these same users: {intake.prior_tool_for_these_users.value}
- Where the data lives: {intake.where_the_data_lives or "(not stated)"}
- Data classification: {intake.data_sensitivity.value}

Use these answers. "Last tool built for these same users" is direct evidence
for adoption_risk and appears nowhere else. Where an answer is "(not stated)"
or "unknown", fall back to the request text, and set score to null if neither
establishes the dimension."""


def assess_request(
    intake: RequestIntake,
    provider: LLMProvider,
    rubric: Rubric | None = None,
    patterns: Patterns | None = None,
    contracts_config: ContractsConfig | None = None,
    approval_date: date | None = None,
    temperature: float = 0.2,
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

    Returns:
        An :class:`AssessmentResult` with the assessment, the scored outcome,
        and a contract when the verdict is ``go``.

    Raises:
        AssessmentError: If the model could not produce a schema-valid
            assessment within :data:`MAX_RETRIES` retries.
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
    for attempt in range(MAX_RETRIES + 1):
        response = provider.chat(
            messages, response_schema=schema, temperature=temperature
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
