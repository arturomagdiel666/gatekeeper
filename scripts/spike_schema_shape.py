"""Schema-shape disambiguation matrix for the Phase 1.5 scenario-D RED.

Phase 1.5's scenario D (nested rubric-shaped tool call) scored 0/10, but the
scenario differed from the passing flat scenarios in TWO ways at once: it
introduced a nested object AND a lexical collision between the prompt's prose
("give a one-paragraph summary") and the schema key (``summary``). This spike
runs a 2x2 factorial over {schema shape} x {prompt prose} on native tool
calls, plus two grammar-constrained arms (Ollama ``format=`` JSON schema,
no tools) as a mechanism baseline:

    D1  nested  clean      native tools
    D2  nested  colliding  native tools   <- verbatim Phase 1.5 replication
    D3  flat    colliding  native tools
    D4  flat    clean      native tools
    S1  nested  clean      format= JSON schema (no tools)
    S2  flat    clean      format= JSON schema (no tools)

D2 is the control: if it does not reproduce ~0%, the harness differs from the
committed baseline (scripts/spike_toolcalling.py) and no other number is
interpretable — the report withholds its conclusion in that case.

This spike measures the LOCAL model specifically, so it instantiates
OllamaProvider directly and ignores LLM_PROVIDER. Measurement script, not a
feature: nothing imports it and pytest does not collect it.

Usage:
    python scripts/spike_schema_shape.py --trials 10
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from provider import ChatResponse, OllamaProvider  # noqa: E402

# --------------------------------------------------------------------------
# Tool schemas. NESTED is copied VERBATIM from scripts/spike_toolcalling.py
# (the committed Phase 1.5 baseline) so arm D2 is an exact replication.
# FLAT carries the same four pieces of information and mirrors every
# description string exactly (including "One-paragraph justification.") so
# the only difference between shapes is the shape itself.
# --------------------------------------------------------------------------

TOOL_SCORE_NESTED = {
    "type": "function",
    "function": {
        "name": "score_use_case",
        "description": (
            "Record the triage assessment of a proposed AI use case. "
            "Call this exactly once with the full assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {
                    "type": "string",
                    "description": "One-sentence restatement of the use case.",
                },
                "data_readiness": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "How ready the data is, 1 (none) to 5 (clean and labeled).",
                },
                "verdict": {
                    "type": "string",
                    "enum": ["go", "no_go", "not_ai"],
                    "description": "Triage verdict.",
                },
                "rationale": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "One-paragraph justification.",
                        },
                        "risks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Main risks, as short strings.",
                        },
                    },
                    "required": ["summary", "risks"],
                },
            },
            "required": ["use_case", "data_readiness", "verdict", "rationale"],
        },
    },
}

TOOL_SCORE_FLAT = {
    "type": "function",
    "function": {
        "name": "score_use_case",
        "description": (
            "Record the triage assessment of a proposed AI use case. "
            "Call this exactly once with the full assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {
                    "type": "string",
                    "description": "One-sentence restatement of the use case.",
                },
                "data_readiness": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "How ready the data is, 1 (none) to 5 (clean and labeled).",
                },
                "verdict": {
                    "type": "string",
                    "enum": ["go", "no_go", "not_ai"],
                    "description": "Triage verdict.",
                },
                "rationale_summary": {
                    "type": "string",
                    "description": "One-paragraph justification.",
                },
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main risks, as short strings.",
                },
            },
            "required": [
                "use_case",
                "data_readiness",
                "verdict",
                "rationale_summary",
                "risks",
            ],
        },
    },
}

# --------------------------------------------------------------------------
# Pydantic validators, extra="forbid" as in Phase 1.5
# --------------------------------------------------------------------------


class Rationale(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    risks: list[str]


class NestedScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_case: str
    data_readiness: int = Field(ge=1, le=5)
    verdict: Literal["go", "no_go", "not_ai"]
    rationale: Rationale


class FlatScore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_case: str
    data_readiness: int = Field(ge=1, le=5)
    verdict: Literal["go", "no_go", "not_ai"]
    rationale_summary: str
    risks: list[str]


# --------------------------------------------------------------------------
# Prompts. The preambles and TAIL_COLLIDING reproduce the Phase 1.5
# scenario-D wording verbatim; the clean tails refer to fields only by their
# exact schema names and contain no near-synonym of any key (no "paragraph",
# "overview", "description", "abstract", "explanation" — and no
# "justification"/"assessment", near-synonyms of "rationale").
# --------------------------------------------------------------------------

SYSTEM_PROMPT_TOOLS = (
    "You are a helpful assistant. Use the provided tools when they apply to "
    "the user's request."
)
SYSTEM_PROMPT_JSON = (
    "You are a helpful assistant. Respond only with a single JSON object "
    "that matches the requested schema."
)

USE_CASE_TEXT = (
    "'A regional hospital wants an AI assistant that summarizes patient "
    "discharge notes for the follow-up team. They have five years of clean, "
    "structured electronic health records.'"
)

PREAMBLE_TOOLS = (
    "Triage this AI use case and record your assessment with the "
    f"score_use_case tool: {USE_CASE_TEXT} The data readiness is high — rate "
    "it 4 out of 5. Your verdict is that this is a good AI use case (go). "
)
PREAMBLE_JSON = (
    "Triage this AI use case and respond with your assessment as a single "
    f"JSON object: {USE_CASE_TEXT} The data readiness is high — rate it 4 "
    "out of 5. Your verdict is that this is a good AI use case (go). "
)

TAIL_COLLIDING = (
    "In the rationale, give a one-paragraph summary and list at least two risks."
)
TAIL_CLEAN_NESTED = (
    "In the rationale, provide the summary and the risks, with at least two risks."
)
TAIL_CLEAN_FLAT = (
    "Provide the rationale_summary and the risks, with at least two risks."
)

ARMS: list[dict[str, Any]] = [
    {"key": "D1", "shape": "nested", "prose": "clean", "mechanism": "tools"},
    {"key": "D2", "shape": "nested", "prose": "colliding", "mechanism": "tools"},
    {"key": "D3", "shape": "flat", "prose": "colliding", "mechanism": "tools"},
    {"key": "D4", "shape": "flat", "prose": "clean", "mechanism": "tools"},
    {"key": "S1", "shape": "nested", "prose": "clean", "mechanism": "format"},
    {"key": "S2", "shape": "flat", "prose": "clean", "mechanism": "format"},
]


def build_prompt(arm: dict) -> str:
    """Assemble the user message for one arm."""
    preamble = PREAMBLE_TOOLS if arm["mechanism"] == "tools" else PREAMBLE_JSON
    if arm["prose"] == "colliding":
        tail = TAIL_COLLIDING
    else:
        tail = TAIL_CLEAN_NESTED if arm["shape"] == "nested" else TAIL_CLEAN_FLAT
    return preamble + tail


def arm_model(arm: dict) -> type[BaseModel]:
    return NestedScore if arm["shape"] == "nested" else FlatScore


# --------------------------------------------------------------------------
# Failure classification
# --------------------------------------------------------------------------

RANGE_ERROR_TYPES = {
    "greater_than_equal",
    "less_than_equal",
    "greater_than",
    "less_than",
}


def emitted_key_sets(args: Any) -> dict[str, list[str]]:
    """Record the key set the model emitted at every dict level."""
    if not isinstance(args, dict):
        return {"root": [f"<not an object: {type(args).__name__}>"]}
    sets = {"root": sorted(args.keys())}
    for key, value in args.items():
        if isinstance(value, dict):
            sets[key] = sorted(value.keys())
    return sets


def classify_failure(
    exc: ValidationError, args: dict, shape: str
) -> tuple[str, str]:
    """Map a ValidationError to exactly one pre-registered failure class.

    Returns (failure_class, detail). Precedence: structure_error is checked
    first where the evidence is structural (a nested object where flat was
    expected, or flat keys spilled to the root); then key_renamed (a missing
    key and an extra key under the same parent); then key_missing,
    enum_violation, range_violation, type_error.
    """
    errors = exc.errors()
    missing = [tuple(e["loc"]) for e in errors if e["type"] == "missing"]
    extra = [tuple(e["loc"]) for e in errors if e["type"] == "extra_forbidden"]
    other = [e for e in errors if e["type"] not in ("missing", "extra_forbidden")]

    if shape == "flat" and isinstance(args.get("rationale"), dict):
        return "structure_error", "nested 'rationale' object where flat was expected"

    if shape == "nested":
        rationale_type_errors = [e for e in other if tuple(e["loc"]) == ("rationale",)]
        if rationale_type_errors:
            return (
                "structure_error",
                f"'rationale' is not an object ({type(args.get('rationale')).__name__})",
            )
        if ("rationale",) in missing:
            root_extra = [loc[0] for loc in extra if len(loc) == 1]
            renamed_to = [k for k in root_extra if isinstance(args.get(k), dict)]
            if renamed_to:
                return "key_renamed", f"rationale → {renamed_to[0]}"
            if root_extra:
                return (
                    "structure_error",
                    f"flat keys at root where nested was expected: {root_extra}",
                )
            return "key_missing", "rationale"

    missing_by_parent = defaultdict(list)
    for loc in missing:
        missing_by_parent[loc[:-1]].append(str(loc[-1]))
    extra_by_parent = defaultdict(list)
    for loc in extra:
        extra_by_parent[loc[:-1]].append(str(loc[-1]))
    for parent, missing_keys in missing_by_parent.items():
        if parent in extra_by_parent:
            extra_keys = extra_by_parent[parent]
            pairs = ", ".join(
                f"{m} → {x}" for m, x in zip(sorted(missing_keys), sorted(extra_keys))
            )
            leftovers = sorted(missing_keys)[len(extra_keys):]
            detail = pairs + (f"; also missing: {leftovers}" if leftovers else "")
            return "key_renamed", detail

    if missing:
        return "key_missing", ", ".join(".".join(map(str, loc)) for loc in missing)
    if any(e["type"] == "literal_error" for e in errors):
        locs = [e["loc"] for e in errors if e["type"] == "literal_error"]
        return "enum_violation", ", ".join(".".join(map(str, l)) for l in locs)
    if any(e["type"] in RANGE_ERROR_TYPES for e in errors):
        locs = [e["loc"] for e in errors if e["type"] in RANGE_ERROR_TYPES]
        return "range_violation", ", ".join(".".join(map(str, l)) for l in locs)
    details = ", ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in errors
    )
    return "type_error", details


# --------------------------------------------------------------------------
# Trial execution
# --------------------------------------------------------------------------


def run_trial(provider: OllamaProvider, arm: dict, temperature: float) -> dict:
    """Run one trial of one arm and return its raw record."""
    record: dict[str, Any] = {
        "arm": arm["key"],
        "fully_valid": False,
        "failure_class": None,
        "failure_detail": None,
        "tool_name": None,
        "emitted_key_sets": None,
        "raw_args": None,
        "malformed_flag": None,
        "latency_s": None,
        "error": None,
    }
    system = SYSTEM_PROMPT_TOOLS if arm["mechanism"] == "tools" else SYSTEM_PROMPT_JSON
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": build_prompt(arm)},
    ]
    start = time.perf_counter()
    try:
        if arm["mechanism"] == "tools":
            response: ChatResponse = provider.chat(
                messages,
                tools=[TOOL_SCORE_NESTED if arm["shape"] == "nested" else TOOL_SCORE_FLAT],
                temperature=temperature,
            )
        else:
            response = provider.chat(
                messages,
                tools=None,
                temperature=temperature,
                format=arm_model(arm).model_json_schema(),
            )
    except Exception as exc:  # one bad trial must never abort the run
        record["latency_s"] = round(time.perf_counter() - start, 3)
        record["failure_class"] = "exception"
        record["failure_detail"] = f"{type(exc).__name__}: {exc}"
        record["error"] = record["failure_detail"]
        return record
    record["latency_s"] = round(time.perf_counter() - start, 3)
    record["malformed_flag"] = response.malformed_tool_calls

    if arm["mechanism"] == "tools":
        if not response.tool_calls:
            record["failure_class"] = "no_call"
            record["failure_detail"] = "no tool call emitted"
            return record
        call = response.tool_calls[0]
        record["tool_name"] = call["name"]
        if call["name"] != "score_use_case":
            record["failure_class"] = "no_call"
            record["failure_detail"] = f"called nonexistent tool {call['name']!r}"
            return record
        args = call["arguments"]
    else:
        try:
            args = json.loads(response.text)
        except (json.JSONDecodeError, ValueError) as exc:
            record["failure_class"] = "no_call"
            record["failure_detail"] = f"unparseable JSON: {exc}"
            record["raw_args"] = (response.text or "")[:500]
            return record
        if not isinstance(args, dict):
            record["failure_class"] = "structure_error"
            record["failure_detail"] = f"JSON is not an object ({type(args).__name__})"
            record["raw_args"] = args
            return record

    record["raw_args"] = args
    record["emitted_key_sets"] = emitted_key_sets(args)
    try:
        arm_model(arm).model_validate(args)
        record["fully_valid"] = True
    except ValidationError as exc:
        cls, detail = classify_failure(exc, args, arm["shape"])
        record["failure_class"] = cls
        record["failure_detail"] = detail
    return record


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def summarize(arm: dict, records: list[dict]) -> dict:
    n = len(records)
    latencies = [r["latency_s"] for r in records if r["latency_s"] is not None]
    histogram = Counter(
        r["failure_class"] for r in records if r["failure_class"] is not None
    )
    valid = sum(1 for r in records if r["fully_valid"])
    return {
        **{k: arm[k] for k in ("key", "shape", "prose", "mechanism")},
        "trials": n,
        "fully_valid": valid,
        "fully_valid_rate": valid / n if n else 0.0,
        "failure_histogram": dict(histogram),
        "median_latency_s": round(statistics.median(latencies), 2) if latencies else None,
    }


def _rate(summaries: dict[str, dict], key: str) -> float:
    return summaries[key]["fully_valid_rate"]


def _fmt_effect(label: str, a: str, b: str, s: dict[str, dict]) -> str:
    ra, rb = _rate(s, a), _rate(s, b)
    return (
        f"  {label}: {a} {ra:.0%} vs {b} {rb:.0%} "
        f"(Δ {100 * (ra - rb):+.0f}pp)"
    )


def conclusion(s: dict[str, dict]) -> str:
    """Match the observed pattern against the pre-registered table."""
    d1, d2, d3, d4 = (_rate(s, k) for k in ("D1", "D2", "D3", "D4"))
    s1, s2 = _rate(s, "S1"), _rate(s, "S2")
    if d1 >= 0.90 and d4 >= 0.90 and (d2 < 0.70 or d3 < 0.70):
        return (
            "CAUSE = LEXICAL COLLISION. Nesting is safe. Phase 2 fix: "
            "schema-key naming hygiene + prompts that never near-synonym a key."
        )
    if d3 >= 0.90 and d4 >= 0.90 and d1 < 0.70 and d2 < 0.70:
        return "CAUSE = NESTING. Phase 2 must use a flat scoring schema."
    if d4 >= 0.90 and d1 < 0.90 and d2 < 0.90 and d3 < 0.90:
        return "CAUSE = BOTH, additive. Phase 2: flat schema AND clean prose."
    if all(r < 0.90 for r in (d1, d2, d3, d4)) and (s1 >= 0.90 or s2 >= 0.90):
        return (
            "CAUSE = NATIVE TOOL ARGUMENTS. Move scoring off tool calls onto "
            "constrained JSON generation; keep native tools only for flat "
            "control-flow decisions."
        )
    if all(r < 0.90 for r in (d1, d2, d3, d4, s1, s2)):
        return (
            "qwen2.5:7b cannot carry this payload. Escalate: try a 14B, or "
            "make the hosted provider the scoring path."
        )
    raw = ", ".join(f"{k}={_rate(s, k):.0%}" for k in ("D1", "D2", "D3", "D4", "S1", "S2"))
    return f"PATTERN UNMATCHED — raw rates: {raw}. Read the JSON artifact."


def print_report(meta: dict, summaries: dict[str, dict]) -> dict:
    print()
    print("=" * 78)
    print("SCHEMA-SHAPE DISAMBIGUATION MATRIX")
    print("=" * 78)
    for key, value in meta.items():
        if key == "prompts":
            continue
        print(f"{key:>24}: {value}")
    print("-" * 78)
    print("Prompts under test (user message = preamble + tail):")
    for name, text in meta["prompts"].items():
        print(f"  [{name}]")
        print(f"    {text}")
    print("-" * 78)
    print(f"{'arm':<5}{'shape':<8}{'prose':<11}{'mech':<8}{'fully-valid':<14}{'lat(s)':<8}failures")
    for s in summaries.values():
        hist = (
            ", ".join(f"{k}:{v}" for k, v in sorted(s["failure_histogram"].items()))
            or "—"
        )
        print(
            f"{s['key']:<5}{s['shape']:<8}{s['prose']:<11}{s['mechanism']:<8}"
            f"{s['fully_valid']}/{s['trials']} ({s['fully_valid_rate']:.0%})"
            f"{'':<4}{s['median_latency_s'] if s['median_latency_s'] is not None else '—':<8}{hist}"
        )
    print("-" * 78)

    d2_rate = _rate(summaries, "D2")
    replication_ok = d2_rate <= 0.20
    if replication_ok:
        print(
            f"REPLICATION CHECK: OK — D2 fully-valid {d2_rate:.0%} reproduces the "
            "Phase 1.5 baseline (0%)."
        )
    else:
        print(
            f"REPLICATION CHECK: FAILED — D2 fully-valid {d2_rate:.0%} does NOT "
            "reproduce the Phase 1.5 baseline (~0%). The harness differs from "
            "the committed baseline; no other number below is interpretable."
        )

    print()
    print("Factor effects (fully-valid rates):")
    print(_fmt_effect("Nesting   (clean, tools)   ", "D1", "D4", summaries))
    print(_fmt_effect("Nesting   (clean, format=) ", "S1", "S2", summaries))
    print(_fmt_effect("Collision (nested, tools)  ", "D1", "D2", summaries))
    print(_fmt_effect("Collision (flat, tools)    ", "D4", "D3", summaries))
    print(_fmt_effect("Mechanism (nested, clean)  ", "D1", "S1", summaries))
    print(_fmt_effect("Mechanism (flat, clean)    ", "D4", "S2", summaries))
    print()
    if replication_ok:
        verdict = conclusion(summaries)
        print(f"PRE-REGISTERED CONCLUSION: {verdict}")
    else:
        verdict = (
            "CONCLUSION WITHHELD — replication check failed; harness differs "
            "from the Phase 1.5 baseline."
        )
        print(verdict)
    print("=" * 78)
    return {"replication_ok": replication_ok, "d2_rate": d2_rate, "conclusion": verdict}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=10, help="Trials per arm.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--out", default=None, help="Path for the JSON artifact (default: evals/)."
    )
    args = parser.parse_args()

    load_dotenv()
    # This spike measures the local model specifically: OllamaProvider is
    # instantiated directly and LLM_PROVIDER is deliberately ignored.
    provider = OllamaProvider()
    try:
        from importlib.metadata import version

        ollama_version = version("ollama")
    except Exception:
        ollama_version = "unknown"

    print(
        f"Provider: OllamaProvider (instantiated directly; LLM_PROVIDER ignored) "
        f"| model: {provider.model}"
    )
    print("Preflight: sending a trivial prompt to confirm Ollama is reachable...")
    try:
        provider.chat(
            [{"role": "user", "content": "Reply with the single word: READY."}],
            temperature=args.temperature,
        )
    except Exception as exc:
        print(
            f"FATAL: Ollama is unreachable or failed before any trial ran:\n"
            f"  {type(exc).__name__}: {exc}\n"
            "No results were produced — this is a connection/config failure, "
            "NOT a model failure.",
            file=sys.stderr,
        )
        return 2
    print("Preflight OK.\n")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    all_records: list[dict] = []
    summaries: dict[str, dict] = {}
    for arm in ARMS:
        print(
            f"Arm {arm['key']} ({arm['shape']}/{arm['prose']}/{arm['mechanism']}): ",
            end="",
            flush=True,
        )
        records = []
        for _ in range(args.trials):
            record = run_trial(provider, arm, args.temperature)
            records.append(record)
            print(
                "E" if record["failure_class"] == "exception"
                else ("+" if record["fully_valid"] else "."),
                end="",
                flush=True,
            )
        print()
        all_records.extend(records)
        summaries[arm["key"]] = summarize(arm, records)

    meta = {
        "started_at": started_at,
        "provider": "OllamaProvider (direct; LLM_PROVIDER ignored)",
        "model": provider.model,
        "ollama_client_version": ollama_version,
        "temperature": args.temperature,
        "trials_per_arm": args.trials,
        "baseline": "Phase 1.5 scenario D = arm D2 (commit 2ce12d3)",
        "prompts": {
            "system (tools arms)": SYSTEM_PROMPT_TOOLS,
            "system (format arms)": SYSTEM_PROMPT_JSON,
            "D1 nested+clean": build_prompt(ARMS[0]),
            "D2 nested+colliding (verbatim Phase 1.5)": build_prompt(ARMS[1]),
            "D3 flat+colliding": build_prompt(ARMS[2]),
            "D4 flat+clean": build_prompt(ARMS[3]),
            "S1 nested+clean (format=)": build_prompt(ARMS[4]),
            "S2 flat+clean (format=)": build_prompt(ARMS[5]),
        },
    }
    outcome = print_report(meta, summaries)

    out_path = (
        Path(args.out)
        if args.out
        else REPO_ROOT
        / "evals"
        / f"spike_schema_shape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "meta": meta,
                "outcome": outcome,
                "summaries": summaries,
                "trials": all_records,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nJSON artifact: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
