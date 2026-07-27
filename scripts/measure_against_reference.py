"""Measure the system against the two-scorer reference. Read-only.

Five runs of the agreement study measured scorer against scorer. This measures
the PRODUCT: parse the 30-case corpus into real intakes, run the shipped
assessment path against a live model, and compare what comes back with the slots
the two scorers agreed on.

Three rules the design turns on, each earned from a mistake this project has
already made:

**A slot enters the reference only where both scorers gave the same score.**
Disagreements are excluded rather than averaged or adjudicated. Averaging would
invent a right answer the study never established; adjudicating now would let the
result choose it. The exclusion count is reported per dimension because it is the
honest cost of never having reconciled — and because 22 of the 25 excluded slots
sit in the three dimensions the model does the most work on, so the model is
graded most thinly exactly where it matters (ADR-031).

**Derived and model-scored dimensions are reported separately.** Mixing them
would let four lookups flatter three judgements. That is the masking error of
ADR-024 and ADR-029, made twice already in this project, and it is not made here.

**The verdict result is a confusion matrix, never a scalar.** A single number lets
one severe error trade against two mild ones and read as progress (ADR-024). The
cost ordering is stated on the output:
``false go > false not_ai > false no_go > spurious incomplete``.

Timeouts are an infrastructure outcome with their own class. A request that never
came back is not a wrong verdict, and counting it as one would make a slow model
look like an inaccurate one.

Usage::

    python scripts/measure_against_reference.py [--out results.json] [--limit N]

Requires a reachable provider. Nothing here writes to a production file.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml  # noqa: E402

from assess import assess_request  # noqa: E402
from config import PATTERNS, RUBRIC  # noqa: E402
from provider import get_provider  # noqa: E402
from schemas import (  # noqa: E402
    Assessment,
    Confidence,
    DataSensitivity,
    DeterministicArtefact,
    DimensionAssessment,
    Period,
    RequestIntake,
)
from scoring import derive_fallback_scores, derive_scores  # noqa: E402
from scoring import score as score_assessment  # noqa: E402

CORPUS = PROJECT_ROOT / "evals" / "CASOS_CIEGOS_v2.md"
SCORES_B = PROJECT_ROOT / "evals" / "scores_B_run5.yaml"
SCORES_A = Path("/mnt/c/Claude/Projects/Gatekeeper/evaluacion/scores_A_run5.yaml")

DIMENSIONS = [d.id for d in RUBRIC.dimensions]

#: Cost ordering for verdict errors, worst first (ADR-024). Reported with the
#: matrix so a reader cannot collapse it to a scalar without noticing.
COST_ORDER = [
    ("false go", "approves what should have been stopped"),
    ("false not_ai", "rejects with the stronger claim"),
    ("false no_go", "rejects, and there is no next turn"),
    ("spurious incomplete", "sends back, recoverable"),
]

#: How the corpus writes a period, and the (times, Period) it means. "trimestral"
#: has no Period member, so it is expressed as 4 a year — the same annualization
#: the rubric's band table would do, made explicit here rather than hidden.
PERIOD_WORDS = {
    "semanal": (1, Period.WEEK),
    "mensual": (1, Period.MONTH),
    "trimestral": (4, Period.YEAR),
    "anual": (1, Period.YEAR),
}
PERIOD_SUFFIX = {
    "al mes": Period.MONTH,
    "al año": Period.YEAR,
    "a la semana": Period.WEEK,
    "al día": Period.DAY,
}
SENSITIVITY_WORDS = {
    "público": DataSensitivity.PUBLIC,
    "publico": DataSensitivity.PUBLIC,
    "interno": DataSensitivity.INTERNAL,
    "confidencial": DataSensitivity.CONFIDENTIAL,
    "regulado": DataSensitivity.REGULATED,
}
#: The corpus writes an unanswered field as an em dash.
BLANK = {"—", "-", "", "(no indicado)", "nada"}


class CorpusError(RuntimeError):
    """A case did not parse. Raised rather than defaulted, on purpose.

    A silently defaulted field would change which dimensions the model is asked
    to score — a blank volume field puts `process_frequency` back in the prompt —
    so a parse failure that defaults is a measurement that quietly tests
    something else.
    """


@dataclass
class Case:
    """One parsed corpus case."""

    case_id: str
    title: str
    intake: RequestIntake


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _parse_frequency(raw: str) -> tuple[int | None, Period | None]:
    """Turn the corpus's frequency wording into ``(times_per_period, period)``."""
    value = _clean(raw).lower()
    if value in BLANK:
        return None, None
    if value in PERIOD_WORDS:
        return PERIOD_WORDS[value]
    for suffix, period in PERIOD_SUFFIX.items():
        if value.endswith(suffix):
            head = value[: -len(suffix)].strip()
            # "250 altas al mes", "3,000 órdenes al mes" — a noun may sit between
            # the number and the period, and it is not part of the count.
            digits = re.match(r"^([\d,\.]+)", head)
            if not digits:
                raise CorpusError(f"frequency {raw!r}: no leading count")
            return int(digits.group(1).replace(",", "").replace(".", "")), period
    raise CorpusError(f"frequency {raw!r}: unrecognised period")


def _parse_people(raw: str) -> int | None:
    value = _clean(raw)
    if value in BLANK:
        return None
    digits = re.match(r"^([\d,\.]+)", value)
    if not digits:
        raise CorpusError(f"people {raw!r}: not a count")
    return int(digits.group(1).replace(",", "").replace(".", ""))


def _parse_sensitivity(raw: str) -> DataSensitivity:
    value = _clean(raw).lower()
    if value in BLANK:
        return DataSensitivity.UNKNOWN
    if value not in SENSITIVITY_WORDS:
        raise CorpusError(f"classification {raw!r}: unrecognised")
    return SENSITIVITY_WORDS[value]


def _parse_artefacts(block: str) -> list[DeterministicArtefact]:
    """Parse the stated artefact section.

    ``nada`` is an EMPTY LIST, not an absent one — the requester was asked and
    answered. That distinction drives the whole dimension: empty derives level 1,
    absent refuses and returns `incomplete` (ADR-030). Returning the wrong one
    would silently change the measurement.
    """
    header = re.search(
        r"\*\*Lo determinista que ya existe hoy para este trabajo:\*\*(.*?)(?=\n---|\Z)",
        block,
        re.S,
    )
    if header is None:
        raise CorpusError("no artefact section")
    body = header.group(1)
    if _clean(body).lower().rstrip(".") in BLANK:
        return []

    artefacts: list[DeterministicArtefact] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        entry = line.lstrip("- ").strip()
        match = re.match(r"^\*(?P<name>[^*]+)\*\s*—\s*(?P<rest>.+)$", entry)
        if match is None:
            raise CorpusError(f"artefact line does not parse: {entry!r}")
        rest = match.group("rest")
        done = "el trabajo queda hecho" in rest
        undecided = "todavía tiene que decidir algo" in rest
        if done == undecided:
            raise CorpusError(
                f"artefact {match.group('name')!r}: completion flag is "
                "missing or says both things"
            )
        artefacts.append(
            DeterministicArtefact(
                name=_clean(match.group("name")),
                what_it_does=_clean(rest),
                completes_without_judgement=done,
            )
        )
    if not artefacts:
        raise CorpusError("artefact section is neither 'nada' nor a list")
    return artefacts


def parse_corpus(path: Path = CORPUS) -> list[Case]:
    """Parse every case, or raise. No field is ever defaulted on failure."""
    text = path.read_text()
    blocks = re.split(r"\n## ", text)[1:]
    if not blocks:
        raise CorpusError(f"{path} contains no cases")

    cases: list[Case] = []
    for block in blocks:
        heading = block.splitlines()[0]
        head = re.match(r"^(?P<id>[AB]-\d\d)\s*·\s*(?P<title>.+)$", heading.strip())
        if head is None:
            raise CorpusError(f"unparseable heading: {heading!r}")
        case_id = head.group("id")

        def need(pattern: str, what: str, flags: int = 0) -> str:
            found = re.search(pattern, block, flags)
            if found is None:
                raise CorpusError(f"{case_id}: missing {what}")
            return found.group(1)

        area = need(r"\*\*Área:\*\*\s*(.+?)\s*·", "área")
        owner = _clean(need(r"\*\*Solicitante:\*\*\s*(.+?)\s*$", "solicitante", re.M))
        request_lines = [
            line.lstrip("> ").strip()
            for line in block.splitlines()
            if line.startswith(">")
        ]
        if not any(request_lines):
            raise CorpusError(f"{case_id}: empty request text")
        process = need(r"\*\*Cómo se hace hoy:\*\*\s*(.+?)\s*$", "cómo se hace hoy", re.M)
        benefit = need(
            r"\*\*Beneficio afirmado:\*\*\s*(.+?)\s*$", "beneficio afirmado", re.M
        )
        meta = need(
            r"^Personas:\s*(.+?)\s*·\s*Frecuencia:\s*(.+?)\s*·\s*Datos:\s*(.+?)"
            r"\s*·\s*Clasificación:\s*(.+?)\s*$",
            "metadata line",
            re.M,
        )
        meta_match = re.search(
            r"^Personas:\s*(.+?)\s*·\s*Frecuencia:\s*(.+?)\s*·\s*Datos:\s*(.+?)"
            r"\s*·\s*Clasificación:\s*(.+?)\s*$",
            block,
            re.M,
        )
        assert meta_match is not None  # `need` above already proved it
        people_raw, freq_raw, data_raw, sens_raw = meta_match.groups()
        times, period = _parse_frequency(freq_raw)

        cases.append(
            Case(
                case_id=case_id,
                title=_clean(head.group("title")),
                intake=RequestIntake(
                    request_text="\n".join(line for line in request_lines if line),
                    requesting_area=_clean(area),
                    business_owner="" if owner in BLANK else owner,
                    process_description=_clean(process),
                    stated_benefit=_clean(benefit) or None,
                    who_does_this_today="",
                    people_affected=_parse_people(people_raw),
                    times_per_period=times,
                    period=period,
                    where_the_data_lives=None
                    if _clean(data_raw) in BLANK
                    else _clean(data_raw),
                    data_sensitivity=_parse_sensitivity(sens_raw),
                    existing_deterministic_artefacts=_parse_artefacts(block),
                ),
            )
        )
    return cases


# ---------------------------------------------------------------------------
# The reference
# ---------------------------------------------------------------------------


@dataclass
class Reference:
    """Slots the two scorers agreed on, plus what agreeing cost."""

    #: (case_id, dimension) -> agreed score
    slots: dict[tuple[str, str], int] = field(default_factory=dict)
    #: (case_id, dimension) pairs where the scorers disagreed — no right answer
    excluded: list[tuple[str, str]] = field(default_factory=list)
    #: (case_id, dimension) pairs where BOTH refused to score
    both_null: list[tuple[str, str]] = field(default_factory=list)
    #: case_id -> agreed verdict, computed by the production scorer
    verdicts: dict[str, str] = field(default_factory=dict)
    #: case_ids where the two scorers' computed verdicts differ
    verdict_excluded: list[tuple[str, str, str]] = field(default_factory=list)


def _assessment_from_scores(case: dict) -> Assessment:
    """Rebuild a scorer's file entry as an Assessment the production scorer eats."""
    from schemas import AntiPatternMatch

    matches = []
    for entry in case.get("anti_pattern_matches") or []:
        matches.append(
            AntiPatternMatch(
                anti_pattern_id=entry["id"],
                quote=entry["quote"],
                second_quote=entry.get("second_quote"),
                quote_confidence=Confidence.HIGH,
            )
        )
    return Assessment(
        archetype_id=case.get("archetype"),
        anti_pattern_matches=matches,
        dimension_assessments=[
            DimensionAssessment(
                dimension_id=dim,
                score=case["dimensions"][dim]["score"],
                evidence=str(case["dimensions"][dim].get("note") or "from the reference"),
                confidence=Confidence(case["dimensions"][dim].get("confidence") or "low"),
            )
            for dim in DIMENSIONS
        ],
    )


def build_reference(cases: list[Case]) -> Reference:
    """Agreed slots only. Disagreements are excluded, never reconciled."""
    a_file = {c["case_id"]: c for c in yaml.safe_load(SCORES_A.read_text())}
    b_file = {c["case_id"]: c for c in yaml.safe_load(SCORES_B.read_text())}
    if set(a_file) != set(b_file):
        raise CorpusError("the two scorer files cover different cases")

    reference = Reference()
    intakes = {case.case_id: case.intake for case in cases}
    for case_id in sorted(b_file):
        for dim in DIMENSIONS:
            a_score = a_file[case_id]["dimensions"][dim]["score"]
            b_score = b_file[case_id]["dimensions"][dim]["score"]
            if a_score is None or b_score is None:
                if a_score is None and b_score is None:
                    reference.both_null.append((case_id, dim))
                else:
                    reference.excluded.append((case_id, dim))
            elif a_score == b_score:
                reference.slots[(case_id, dim)] = a_score
            else:
                reference.excluded.append((case_id, dim))

        # Verdicts through the production scorer, so gates, completeness and
        # bands are the shipped ones rather than anything reimplemented here.
        intake = intakes[case_id]
        a_verdict = score_assessment(
            _assessment_from_scores(a_file[case_id]), RUBRIC, PATTERNS, intake
        ).verdict.value
        b_verdict = score_assessment(
            _assessment_from_scores(b_file[case_id]), RUBRIC, PATTERNS, intake
        ).verdict.value
        if a_verdict == b_verdict:
            reference.verdicts[case_id] = a_verdict
        else:
            reference.verdict_excluded.append((case_id, a_verdict, b_verdict))
    return reference


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run_system(cases: list[Case], provider) -> list[dict]:
    """Assess every case through the shipped path, recording latency and shape."""
    rows: list[dict] = []
    for index, case in enumerate(cases, 1):
        print(f"  [{index:2}/{len(cases)}] {case.case_id} …", end="", flush=True)
        started = time.monotonic()
        try:
            result = assess_request(case.intake, provider)
            elapsed = time.monotonic() - started
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            elapsed = time.monotonic() - started
            print(f" ERROR after {elapsed:.1f}s: {type(exc).__name__}")
            rows.append(
                {
                    "case_id": case.case_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_s": round(elapsed, 2),
                    "timed_out": False,
                    "verdict": None,
                    "scores": {},
                    "derived": [],
                }
            )
            continue

        if result.timed_out:
            print(f" TIMEOUT at {elapsed:.1f}s")
            rows.append(
                {
                    "case_id": case.case_id,
                    "error": None,
                    "latency_s": round(elapsed, 2),
                    "timed_out": True,
                    "verdict": None,
                    "scores": {},
                    "derived": sorted(result.derived_dimensions),
                }
            )
            continue

        outcome = result.outcome
        # `resolved_scores` carries every dimension's post-derivation value whether
        # or not the case turned out scorable (ADR-032). It exists because this
        # script needed it and reconstructing it by hand was wrong twice:
        # `contributions` is empty on a gated or incomplete case, and the merged
        # assessment lacks the fallback derivations.
        scores = dict(outcome.resolved_scores)
        # A dimension can be absent from the merged assessment, and it is a
        # property of the system rather than of this script: `build_response_schema`
        # pins dimension_assessments to exactly one entry per asked dimension and
        # pins dimension_id to an enum, but nothing enforces DISTINCTNESS. A model
        # can satisfy the schema by emitting one id twice and omitting another;
        # `_index_assessments` then drops the duplicate into `ignored_dimension_ids`
        # and the omitted dimension is simply unknown. Recorded as a null, with the
        # duplication kept visible.
        dropped = sorted(set(DIMENSIONS) - set(scores))
        for dim in dropped:
            scores[dim] = None
        print(f" {outcome.verdict.value:11} {elapsed:5.1f}s")
        rows.append(
            {
                "case_id": case.case_id,
                "error": None,
                "latency_s": round(elapsed, 2),
                "timed_out": False,
                "verdict": outcome.verdict.value,
                "weighted_total": outcome.weighted_total,
                "gates": outcome.triggered_gate_ids,
                "requires_human_confirmation": outcome.requires_human_confirmation,
                "retry_count": result.retry_count,
                "scores": scores,
                "derived": sorted(
                    set(outcome.derived_dimensions)
                    | set(outcome.fallback_derived_dimensions)
                ),
                "model_scored": sorted(result.model_scored_dimensions),
                # Visible rather than swallowed: a duplicated dimension_id means a
                # dimension the model was asked for came back with no score at all.
                "dropped_by_duplication": dropped,
                "ignored_dimension_ids": outcome.ignored_dimension_ids,
                "unsupported_anti_patterns": [
                    u.anti_pattern_id for u in outcome.unsupported_anti_patterns
                ],
            }
        )
    return rows


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def _pct(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:5.0%}" if denominator else "    —"


def report(rows: list[dict], reference: Reference) -> dict:
    """Print the report and return it as a dict for the JSON artefact."""
    by_case = {row["case_id"]: row for row in rows}
    completed = [r for r in rows if r["verdict"] is not None]

    print("\n" + "=" * 78)
    print("PER-DIMENSION, AGAINST AGREED SLOTS ONLY")
    print("=" * 78)
    print("Derived and model-scored are reported apart. Mixing them would let the")
    print("lookups flatter the model — the masking error of ADR-024 and ADR-029.\n")

    # Which dimensions were derived is per case, not global, so classify each slot.
    per_dim: dict[str, dict] = {}
    for dim in DIMENSIONS:
        for kind in ("derived", "model"):
            per_dim[(dim, kind)] = {"n": 0, "exact": 0, "within1": 0}
    for (case_id, dim), expected in reference.slots.items():
        row = by_case.get(case_id)
        if row is None or row["verdict"] is None:
            continue  # timeout or error: not a scoring result
        actual = row["scores"].get(dim)
        kind = "derived" if dim in row["derived"] else "model"
        bucket = per_dim[(dim, kind)]
        bucket["n"] += 1
        if actual is None:
            continue  # the engine refused where the scorers agreed on a value
        if actual == expected:
            bucket["exact"] += 1
        if abs(actual - expected) <= 1:
            bucket["within1"] += 1

    excluded_by_dim = {dim: 0 for dim in DIMENSIONS}
    for _, dim in reference.excluded:
        excluded_by_dim[dim] += 1
    null_by_dim = {dim: 0 for dim in DIMENSIONS}
    for _, dim in reference.both_null:
        null_by_dim[dim] += 1

    table = []
    for kind, label in (("derived", "DERIVED FROM AN INTAKE FIELD"), ("model", "MODEL-SCORED")):
        print(f"{label}")
        print(f"  {'dimension':24} {'n':>3} {'exact':>7} {'±1':>7}   excl  both-null")
        subtotal = {"n": 0, "exact": 0, "within1": 0}
        for dim in DIMENSIONS:
            bucket = per_dim[(dim, kind)]
            if not bucket["n"]:
                continue
            for key in subtotal:
                subtotal[key] += bucket[key]
            print(
                f"  {dim:24} {bucket['n']:3} {_pct(bucket['exact'], bucket['n'])} "
                f"{_pct(bucket['within1'], bucket['n'])}   {excluded_by_dim[dim]:4}"
                f"  {null_by_dim[dim]:9}"
            )
            table.append({"dimension": dim, "kind": kind, **bucket})
        print(
            f"  {'— subtotal':24} {subtotal['n']:3} "
            f"{_pct(subtotal['exact'], subtotal['n'])} "
            f"{_pct(subtotal['within1'], subtotal['n'])}\n"
        )

    print("=" * 78)
    print("VERDICTS — CONFUSION MATRIX (never collapsed to a scalar, ADR-024)")
    print("=" * 78)
    print("Cost ordering, worst first:")
    for name, why in COST_ORDER:
        print(f"  {name:22} {why}")
    print()

    classes = ["go", "no_go", "not_ai", "incomplete"]
    matrix = {ref: {got: 0 for got in classes} for ref in classes}
    off_reference = []
    timeouts = [r["case_id"] for r in rows if r["timed_out"]]
    errors = [r["case_id"] for r in rows if r["error"]]
    for case_id, expected in reference.verdicts.items():
        row = by_case.get(case_id)
        if row is None or row["verdict"] is None:
            continue  # not run, or timeout/error: never counted as a mismatch
        matrix[expected][row["verdict"]] += 1
        if row["verdict"] != expected:
            off_reference.append((case_id, expected, row["verdict"]))

    header = "  reference \\ system   " + "".join(f"{c:>12}" for c in classes)
    print(header)
    for ref in classes:
        line = f"  {ref:20} " + "".join(f"{matrix[ref][got]:12}" for got in classes)
        print(line)
    scored = sum(matrix[r][g] for r in classes for g in classes)
    print(f"\n  cases in the verdict reference: {len(reference.verdicts)}")
    print(f"  of those, assessed without timeout: {scored}")
    print(f"  excluded (the two scorers disagreed): {len(reference.verdict_excluded)}")
    for case_id, a_v, b_v in reference.verdict_excluded:
        print(f"      {case_id}: A={a_v} B={b_v}")
    print(f"  timeouts (own class, not a mismatch): {len(timeouts)} {timeouts}")
    if errors:
        print(f"  errors: {len(errors)} {errors}")

    print("\n  errors by cost class:")
    named = {
        "false go": sum(matrix[r]["go"] for r in classes if r != "go"),
        "false not_ai": sum(matrix[r]["not_ai"] for r in classes if r != "not_ai"),
        "false no_go": sum(matrix[r]["no_go"] for r in classes if r != "no_go"),
        "spurious incomplete": sum(
            matrix[r]["incomplete"] for r in classes if r != "incomplete"
        ),
    }
    for name, _ in COST_ORDER:
        print(f"    {name:22} {named[name]}")
    if off_reference:
        print("\n  every off-reference verdict:")
        for case_id, expected, got in off_reference:
            print(f"    {case_id}: reference {expected} -> system {got}")

    print("\n" + "=" * 78)
    print("LATENCY")
    print("=" * 78)
    latencies = [r["latency_s"] for r in rows if not r["timed_out"] and not r["error"]]
    if latencies:
        print(f"  n={len(latencies)}  min {min(latencies):.1f}s  "
              f"median {statistics.median(latencies):.1f}s  max {max(latencies):.1f}s")
        print(f"  timeouts: {len(timeouts)} of {len(rows)} "
              f"({len(timeouts) / len(rows):.0%}) — counted as their own outcome class")
        retries = sum(r.get("retry_count", 0) for r in rows)
        print(f"  corrective retries across the run: {retries}")
    else:
        print("  no completed requests")

    return {
        "per_dimension": table,
        "excluded_by_dimension": excluded_by_dim,
        "both_null_by_dimension": null_by_dim,
        "confusion_matrix": matrix,
        "errors_by_cost_class": named,
        "off_reference": off_reference,
        "verdict_reference_n": len(reference.verdicts),
        "verdict_excluded": reference.verdict_excluded,
        "timeouts": timeouts,
        "errors": errors,
        "latency": {
            "n": len(latencies),
            "min_s": min(latencies) if latencies else None,
            "median_s": statistics.median(latencies) if latencies else None,
            "max_s": max(latencies) if latencies else None,
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="write the JSON artefact here")
    parser.add_argument("--limit", type=int, default=None, help="first N cases only")
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    print("Parsing the corpus …")
    cases = parse_corpus()
    print(f"  {len(cases)} cases parsed, no field defaulted")

    # The reference is always built from the WHOLE corpus, so that --limit can
    # shorten a smoke run without silently shrinking the reference it is measured
    # against. Only the assessment loop is limited.
    print("Building the reference from the two scorer files …")
    reference = build_reference(cases)
    if args.limit:
        cases = cases[: args.limit]
    print(
        f"  {len(reference.slots)} agreed slots · "
        f"{len(reference.excluded)} excluded · "
        f"{len(reference.both_null)} both refused"
    )

    provider = get_provider(args.provider) if args.provider else get_provider()
    print(f"Provider: {type(provider).__name__} | model: {getattr(provider, 'model', 'n/a')}")
    print("Running the shipped assessment path …")
    rows = run_system(cases, provider)

    payload = report(rows, reference)
    if args.out:
        out = Path(args.out)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
