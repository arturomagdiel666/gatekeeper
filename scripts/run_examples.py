"""Run all six reference examples through the real provider and compare.

Not a test — a demo-day confidence check. The offline test suite already
asserts that the scoring ENGINE produces the expected verdict from each
example's hand-authored assessment. This script asks the different question:
what does the MODEL produce from the raw request text?

A mismatch here is information, not a failure. It tells you which requests the
model reads differently from a human assessor, which is exactly what you want
to know before standing up in front of an audience.

Usage:
    python scripts/run_examples.py
    python scripts/run_examples.py --provider mock --out /tmp/run.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from assess import AssessmentError, assess_request  # noqa: E402
from examples import load_examples  # noqa: E402
from provider import get_provider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", default=None, help="Override LLM_PROVIDER.")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--out", default=None, help="Optional JSON artifact path.")
    args = parser.parse_args()

    load_dotenv()
    provider = get_provider(args.provider)
    model = getattr(provider, "model", "n/a")
    print(f"Provider: {type(provider).__name__} | model: {model}")

    print("Preflight: confirming the provider is reachable...")
    try:
        provider.chat(
            [{"role": "user", "content": "Reply with the single word: READY."}],
            temperature=args.temperature,
        )
    except Exception as exc:
        print(
            f"FATAL: provider unreachable before any example ran:\n"
            f"  {type(exc).__name__}: {exc}\n"
            "This is a connection or configuration failure, NOT a model result.",
            file=sys.stderr,
        )
        return 2
    print("Preflight OK.\n")

    examples = load_examples()
    rows = []
    for example in examples:
        print(f"  running {example.id} ...", end="", flush=True)
        started = time.perf_counter()
        row = {
            "id": example.id,
            "expected_verdict": example.expected_verdict,
            "expected_gate": example.expected_gate,
            "actual_verdict": None,
            "actual_gate": None,
            "weighted_total": None,
            "retry_count": None,
            "unknown_dimensions": [],
            "error": None,
        }
        try:
            result = assess_request(
                example.intake,
                provider,
                approval_date=date(2026, 4, 1),
                temperature=args.temperature,
            )
            outcome = result.outcome
            row.update(
                actual_verdict=outcome.verdict.value,
                actual_gate=(outcome.triggered_gate_ids or [None])[0],
                weighted_total=outcome.weighted_total,
                retry_count=result.retry_count,
                unknown_dimensions=outcome.unknown_dimensions,
                unknown_weight=outcome.unknown_weight,
                derived_dimensions=result.derived_dimensions,
                has_contract=result.contract is not None,
            )
        except AssessmentError as exc:
            row["error"] = str(exc)[:200]
        except Exception as exc:  # one bad example must not abort the run
            row["error"] = f"{type(exc).__name__}: {exc}"[:200]
        row["seconds"] = round(time.perf_counter() - started, 1)
        rows.append(row)
        print(f" {row['actual_verdict'] or 'ERROR'} ({row['seconds']}s)")

    print()
    print("=" * 92)
    print("EXAMPLE COMPARISON — expected is the human, anchor-faithful reading")
    print("=" * 92)
    header = (
        f"{'':<2}{'example':<30}{'expected':<12}{'actual':<12}"
        f"{'score':<7}{'secs':<7}{'gate (actual)':<30}"
    )
    print(header)
    print("-" * 92)
    matches = 0
    for row in rows:
        match = row["actual_verdict"] == row["expected_verdict"]
        matches += int(match)
        total = (
            f"{row['weighted_total']:.2f}" if row["weighted_total"] is not None else "-"
        )
        print(
            f"{'OK' if match else 'XX':<2}{row['id']:<30}"
            f"{row['expected_verdict']:<12}{str(row['actual_verdict'] or 'ERROR'):<12}"
            f"{total:<7}{row['seconds']:<7}{str(row['actual_gate'] or '-'):<30}"
        )
        if row["error"]:
            print(f"    error: {row['error']}")
        elif not match:
            print(f"    expected gate: {row['expected_gate'] or '-'}")
            if row["unknown_dimensions"]:
                print(f"    model left unknown: {', '.join(row['unknown_dimensions'])}")
    print("-" * 92)
    retries = sum(r["retry_count"] or 0 for r in rows)
    latencies = sorted(r["seconds"] for r in rows)
    median = latencies[len(latencies) // 2]
    print(
        f"{matches}/{len(rows)} verdicts match the human reading | "
        f"{retries} schema retry(ies)"
    )
    print(
        f"Latency per request: min {latencies[0]:.1f}s | median {median:.1f}s | "
        f"max {latencies[-1]:.1f}s | total {sum(latencies):.0f}s"
    )
    print(
        "A mismatch is information: it shows where the model reads a request "
        "differently from a human assessor."
    )
    print("=" * 92)

    if args.out:
        artifact = {
            "meta": {
                "provider": type(provider).__name__,
                "model": model,
                "temperature": args.temperature,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
            "rows": rows,
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
        print(f"\nJSON artifact: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
