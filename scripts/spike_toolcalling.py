"""Tool-calling reliability spike for the Gatekeeper provider layer.

Measures whether the configured model (default: local qwen2.5:7b via Ollama)
can actually produce native tool calls, and how often. This is a measurement
script, not a feature: nothing imports it, pytest does not collect it, and it
does not alter provider behaviour.

Four scenarios, each run --trials times with an identical prompt (the
variation measured is the model's own nondeterminism):

    A  obvious single tool, all arguments stated plainly
    B  tool selection between two plausible tools
    C  no tool applicable (measures the false-positive rate)
    D  rubric-shaped call: nested object + enum + bounded int
       (the shape Phase 2 actually needs — this one decides the verdict)

Prints a per-scenario report and a GREEN/YELLOW/RED verdict judged on
scenario D's fully-valid rate, with scenario C's false-positive rate as a
secondary gate. Also writes a JSON artifact with every raw trial record so
results are comparable across models later.

Usage:
    python scripts/spike_toolcalling.py --trials 10
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from provider import ChatResponse, get_provider  # noqa: E402

# --------------------------------------------------------------------------
# Tool schemas (OpenAI-style function schemas, as Ollama also accepts them)
# --------------------------------------------------------------------------

TOOL_GET_WEATHER = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name."},
                "unit": {
                    "type": "string",
                    "enum": ["c", "f"],
                    "description": "Temperature unit: 'c' for Celsius, 'f' for Fahrenheit.",
                },
            },
            "required": ["city", "unit"],
        },
    },
}

TOOL_CONVERT_CURRENCY = {
    "type": "function",
    "function": {
        "name": "convert_currency",
        "description": "Convert an amount of money from one currency to another.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount to convert."},
                "from_code": {
                    "type": "string",
                    "description": "ISO 4217 code of the source currency, e.g. 'USD'.",
                },
                "to_code": {
                    "type": "string",
                    "description": "ISO 4217 code of the target currency, e.g. 'MXN'.",
                },
            },
            "required": ["amount", "from_code", "to_code"],
        },
    },
}

TOOL_SCORE_USE_CASE = {
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

# --------------------------------------------------------------------------
# Pydantic validators for each scenario's expected arguments
# --------------------------------------------------------------------------


class WeatherArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str
    unit: Literal["c", "f"]


class CurrencyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: float
    from_code: str
    to_code: str


class Rationale(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    risks: list[str]


class ScoreArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    use_case: str
    data_readiness: int = Field(ge=1, le=5)
    verdict: Literal["go", "no_go", "not_ai"]
    rationale: Rationale


SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the provided tools when they apply to "
    "the user's request."
)

SCENARIOS: list[dict[str, Any]] = [
    {
        "key": "A",
        "title": "Obvious single tool",
        "tools": [TOOL_GET_WEATHER],
        "prompt": (
            "What is the current weather in Xalapa? "
            "I want the temperature in Celsius."
        ),
        "expect_tool": "get_weather",
        "args_model": WeatherArgs,
        "expected_values": {"city": "xalapa", "unit": "c"},
    },
    {
        "key": "B",
        "title": "Tool selection (two offered)",
        "tools": [TOOL_GET_WEATHER, TOOL_CONVERT_CURRENCY],
        "prompt": (
            "How much is 150 US dollars in Mexican pesos? "
            "Use USD as the source currency and MXN as the target."
        ),
        "expect_tool": "convert_currency",
        "args_model": CurrencyArgs,
        "expected_values": {"amount": 150.0, "from_code": "usd", "to_code": "mxn"},
    },
    {
        "key": "C",
        "title": "No tool applicable (false-positive gate)",
        "tools": [TOOL_GET_WEATHER, TOOL_CONVERT_CURRENCY],
        "prompt": (
            "What's a good name for a golden retriever puppy? "
            "Just give me one suggestion."
        ),
        "expect_tool": None,
        "args_model": None,
        "expected_values": None,
    },
    {
        "key": "D",
        "title": "Rubric-shaped call (decides the verdict)",
        "tools": [TOOL_SCORE_USE_CASE],
        "prompt": (
            "Triage this AI use case and record your assessment with the "
            "score_use_case tool: 'A regional hospital wants an AI assistant "
            "that summarizes patient discharge notes for the follow-up team. "
            "They have five years of clean, structured electronic health "
            "records.' The data readiness is high — rate it 4 out of 5. Your "
            "verdict is that this is a good AI use case (go). In the "
            "rationale, give a one-paragraph summary and list at least two "
            "risks."
        ),
        "expect_tool": "score_use_case",
        "args_model": ScoreArgs,
        "expected_values": None,
    },
]

# --------------------------------------------------------------------------
# Trial execution
# --------------------------------------------------------------------------


def run_trial(provider: Any, scenario: dict, temperature: float) -> dict:
    """Run one trial of one scenario and return its raw record."""
    record: dict[str, Any] = {
        "scenario": scenario["key"],
        "emitted": False,
        "tool_name": None,
        "name_correct": None,
        "args_is_dict": None,
        "required_keys_present": None,
        "types_valid": None,
        "values_expected": None,
        "fully_valid": False,
        "malformed_flag": None,
        "latency_s": None,
        "num_tool_calls": 0,
        "text": None,
        "error": None,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": scenario["prompt"]},
    ]
    start = time.perf_counter()
    try:
        response: ChatResponse = provider.chat(
            messages, tools=scenario["tools"], temperature=temperature
        )
    except Exception as exc:  # one bad trial must never abort the run
        record["latency_s"] = round(time.perf_counter() - start, 3)
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record
    record["latency_s"] = round(time.perf_counter() - start, 3)
    record["malformed_flag"] = response.malformed_tool_calls
    record["num_tool_calls"] = len(response.tool_calls)
    record["text"] = (response.text or "")[:300]
    record["emitted"] = bool(response.tool_calls)

    if scenario["expect_tool"] is None:
        # Scenario C: correct behaviour is NO tool call plus a text answer.
        record["fully_valid"] = not response.tool_calls and bool(
            (response.text or "").strip()
        )
        if response.tool_calls:
            record["tool_name"] = response.tool_calls[0]["name"]
        return record

    if not response.tool_calls:
        return record

    call = response.tool_calls[0]
    record["tool_name"] = call["name"]
    record["name_correct"] = call["name"] == scenario["expect_tool"]
    record["args_is_dict"] = isinstance(call["arguments"], dict)

    try:
        validated = scenario["args_model"].model_validate(call["arguments"])
        record["required_keys_present"] = True
        record["types_valid"] = True
    except ValidationError as exc:
        record["required_keys_present"] = not any(
            e["type"] == "missing" for e in exc.errors()
        )
        record["types_valid"] = False
        record["validation_errors"] = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['type']}" for e in exc.errors()
        ]
        return record

    if scenario["expected_values"]:
        actual = validated.model_dump()
        record["values_expected"] = all(
            (
                str(actual.get(k, "")).strip().lower() == str(v)
                if isinstance(v, str)
                else actual.get(k) == v
            )
            for k, v in scenario["expected_values"].items()
        )
    record["fully_valid"] = bool(
        record["name_correct"]
        and record["types_valid"]
        and record["values_expected"] is not False
    )
    return record


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({100.0 * numerator / denominator:.0f}%)"


def summarize(scenario: dict, records: list[dict]) -> dict:
    """Aggregate one scenario's trial records into summary counts."""
    n = len(records)
    latencies = [r["latency_s"] for r in records if r["latency_s"] is not None]
    summary = {
        "scenario": scenario["key"],
        "title": scenario["title"],
        "trials": n,
        "errors": sum(1 for r in records if r["error"]),
        "emitted": sum(1 for r in records if r["emitted"]),
        "correct_name": sum(1 for r in records if r["name_correct"]),
        "valid_args": sum(1 for r in records if r["types_valid"]),
        "fully_valid": sum(1 for r in records if r["fully_valid"]),
        "malformed": sum(1 for r in records if r["malformed_flag"]),
        "median_latency_s": round(statistics.median(latencies), 2) if latencies else None,
    }
    summary["fully_valid_rate"] = summary["fully_valid"] / n if n else 0.0
    if scenario["expect_tool"] is None:
        summary["false_positive_rate"] = summary["emitted"] / n if n else 0.0
    return summary


def print_report(meta: dict, summaries: list[dict]) -> list[str]:
    """Print the human report; return the verdict lines for the artifact."""
    print()
    print("=" * 76)
    print("TOOL-CALLING SPIKE REPORT")
    print("=" * 76)
    for key in ("provider", "model", "ollama_client_version", "temperature", "trials_per_scenario"):
        print(f"{key:>24}: {meta[key]}")
    print("-" * 76)
    header = (
        f"{'sc':<3}{'scenario':<38}{'emitted':>9}{'name':>7}"
        f"{'args':>7}{'valid':>7}{'lat(s)':>7}"
    )
    print(header)
    for s in summaries:
        n = s["trials"]
        is_c = "false_positive_rate" in s
        print(
            f"{s['scenario']:<3}{s['title']:<38}"
            f"{s['emitted']:>4}/{n:<4}"
            f"{('—' if is_c else str(s['correct_name'])):>4}"
            + (f"{'—':>7}" if is_c else f"{s['valid_args']:>7}")
            + f"{s['fully_valid']:>7}"
            + f"{s['median_latency_s'] if s['median_latency_s'] is not None else '—':>7}"
        )
        detail = (
            f"    emitted {pct(s['emitted'], n)} | fully-valid {pct(s['fully_valid'], n)}"
        )
        if is_c:
            detail += f" | false-positive rate {pct(s['emitted'], n)}"
        if s["errors"]:
            detail += f" | errors {s['errors']}"
        if s["malformed"]:
            detail += f" | malformed_tool_calls {s['malformed']}"
        print(detail)
    print("-" * 76)

    d = next(s for s in summaries if s["scenario"] == "D")
    c = next(s for s in summaries if s["scenario"] == "C")
    d_rate = d["fully_valid_rate"]
    verdict_lines = []
    if d_rate >= 0.90:
        verdict_lines.append(
            "GREEN — native tool-calling is viable; proceed to Phase 2 as designed."
        )
    elif d_rate >= 0.70:
        verdict_lines.append(
            "YELLOW — viable but Phase 4 needs a retry-with-reprompt loop and "
            "strict validation before scoring."
        )
    else:
        verdict_lines.append(
            "RED — do not build Phase 4 on native tool calls. Evaluate Ollama "
            "JSON/structured-output mode, or make the hosted provider the demo "
            "default."
        )
    verdict_lines[0] = (
        f"VERDICT (scenario D fully-valid {d['fully_valid']}/{d['trials']} = "
        f"{d_rate:.0%}): {verdict_lines[0]}"
    )
    if c.get("false_positive_rate", 0.0) > 0.20:
        verdict_lines.append(
            f"WARNING: scenario C false-positive rate is "
            f"{c['false_positive_rate']:.0%} (> 20%) — the Phase 2 system "
            "prompt needs an explicit \"call no tool\" instruction regardless "
            "of the D verdict."
        )
    for line in verdict_lines:
        print(line)
    print("=" * 76)
    return verdict_lines


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=10, help="Trials per scenario.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--provider", default=None, help="Override LLM_PROVIDER (ollama|openai|mock)."
    )
    parser.add_argument(
        "--out", default=None, help="Path for the JSON artifact (default: evals/)."
    )
    args = parser.parse_args()

    load_dotenv()
    provider = get_provider(args.provider)
    model = getattr(provider, "model", "n/a (mock)")
    try:
        from importlib.metadata import version

        ollama_version = version("ollama")
    except Exception:
        ollama_version = "unknown"

    print(f"Provider: {type(provider).__name__} | model: {model}")
    print("Preflight: sending a trivial prompt to confirm the provider is reachable...")
    try:
        provider.chat(
            [{"role": "user", "content": "Reply with the single word: READY."}],
            temperature=args.temperature,
        )
    except Exception as exc:
        print(
            f"FATAL: provider is unreachable or failed before any trial ran:\n"
            f"  {type(exc).__name__}: {exc}\n"
            "No results were produced — this is a connection/config failure, "
            "NOT a model tool-calling failure.",
            file=sys.stderr,
        )
        return 2
    print("Preflight OK.\n")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    all_records: list[dict] = []
    summaries: list[dict] = []
    for scenario in SCENARIOS:
        print(f"Scenario {scenario['key']} — {scenario['title']}: ", end="", flush=True)
        records = []
        for _ in range(args.trials):
            record = run_trial(provider, scenario, args.temperature)
            records.append(record)
            print("E" if record["error"] else ("+" if record["fully_valid"] else "."), end="", flush=True)
        print()
        all_records.extend(records)
        summaries.append(summarize(scenario, records))

    meta = {
        "started_at": started_at,
        "provider": type(provider).__name__,
        "model": model,
        "ollama_client_version": ollama_version,
        "temperature": args.temperature,
        "trials_per_scenario": args.trials,
    }
    verdict_lines = print_report(meta, summaries)

    out_path = (
        Path(args.out)
        if args.out
        else REPO_ROOT
        / "evals"
        / f"spike_toolcalling_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "meta": meta,
                "verdict": verdict_lines,
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
