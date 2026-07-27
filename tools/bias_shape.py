"""The shape of the judged-slot error. Analysis only.

Phase 7 measured that on judged slots the system reproduces its own answers about
four times better than it matches the reference — κw ≈ 0.37 against κ ≈ 0.04.
That makes the dominant error a bias rather than noise: a stable position that is
not the rubric's.

κ cannot say more than that. A model that scores every case one level too high
and a model that scores at random can produce the same κ, because κ measures how
much agreement exceeds chance and not *which way* the disagreement points. This
file measures direction and shape:

* **A** — marginal distributions and Shannon entropy, which is where a judge that
  has collapsed onto one or two levels becomes visible and nowhere else.
* **B** — signed error ``system − reference``, which separates a directional
  offset from symmetric noise.
* **C** — the 5×5 confusion matrix per dimension, printed and never summarised.
* **D** — whether misses cluster in a minority of cases (some requests are hard)
  or spread evenly (the criterion is), against the exact Poisson-binomial
  expectation for independent misses at the observed base rate.
* **E** — the system against each assessor separately, on every slot that
  assessor scored rather than only the agreed ones. The reference is the subset
  where two assessors agreed, so it is both the easier slots and a construct
  built from the same two people; this checks how much work it is doing.

It runs no model, changes no config and reads no summary table. The reference is
rebuilt from the two scorer files, which is deterministic.

Mechanism is read per slot from each run row's ``derived`` list, never inferred
from the dimension name — ``business_value`` falls back to the model when the
intake magnitude is unknown, so a nominally-derived dimension is judged on some
cases. See ``tools/kappa_system.py`` for why that distinction changes the
numbers.

Usage::

    python tools/bias_shape.py \\
        --seven evals/measure_ref_v2_pass{1,2,3}.json \\
        --fourteen evals/measure_ref_14b_pass{1,2,3}.json \\
        --scores-a evaluacion/scores_A_run5.yaml \\
        --scores-b evals/scores_B_run5.yaml \\
        --out evals/bias_shape_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from kappa_system import UNDEFINED, cohen_kappa, weighted_kappa  # noqa: E402

DERIVABLE = ["process_frequency", "data_governance", "non_ai_alternative", "business_value"]
JUDGED_ONLY = ["implementation_effort", "data_readiness", "adoption_risk"]
DIMENSIONS = DERIVABLE + JUDGED_ONLY
LEVELS = [1, 2, 3, 4, 5]

#: The three dimensions that derive unconditionally. `business_value` is absent
#: on purpose: it derives only when the intake magnitude is known, so it is the
#: one derivable dimension whose error is not structurally zero. The P4 control
#: is these three.
UNCONDITIONAL = ["process_frequency", "data_governance", "non_ai_alternative"]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def load_passes(paths: list[Path]) -> list[dict[str, dict]]:
    out = []
    for path in paths:
        payload = json.loads(Path(path).read_text())
        out.append({row["case_id"]: row for row in payload["rows"]})
    return out


def load_assessor(path: Path) -> dict[tuple[str, str], int | None]:
    """Every slot the assessor recorded, including the ones they left null."""
    cases = yaml.safe_load(Path(path).read_text())
    return {
        (case["case_id"], dim): case["dimensions"][dim]["score"]
        for case in cases
        for dim in DIMENSIONS
    }


def build_agreed_reference(a: dict, b: dict) -> dict[tuple[str, str], int]:
    """Slots where both assessors scored and scored the same. Nothing reconciled.

    Reimplemented here rather than imported so the tool runs from a clean
    checkout with the scorer files given as arguments; the rule is four lines and
    identical to `build_reference()`'s slot half. Verdicts are not needed by any
    analysis in this file, so the production scorer is not invoked.
    """
    if set(a) != set(b):
        raise SystemExit("the two scorer files cover different slots")
    return {
        key: a[key]
        for key in a
        if a[key] is not None and b[key] is not None and a[key] == b[key]
    }


def slots(reference: dict, passes: list[dict]):
    """(case_id, dimension, expected, actual, mechanism) over live rows."""
    for (case_id, dim), expected in reference.items():
        for rows in passes:
            row = rows.get(case_id)
            if row is None or row["verdict"] is None:
                continue  # timeout or error: not a scoring result
            mechanism = "derived" if dim in row["derived"] else "judged"
            yield case_id, dim, expected, row["scores"].get(dim), mechanism


# ---------------------------------------------------------------------------
# A · marginals and entropy
# ---------------------------------------------------------------------------


def entropy_bits(counts: dict[int, int]) -> float | str:
    """Shannon entropy in bits. Maximum is log2(5) = 2.322 over five levels."""
    total = sum(counts.values())
    if total == 0:
        return UNDEFINED
    return -sum(
        (n / total) * math.log2(n / total) for n in counts.values() if n > 0
    )


def marginals(pairs: list[tuple[int, int]]) -> dict:
    ref = Counter(a for a, _ in pairs)
    sys_ = Counter(b for _, b in pairs)
    return {
        "n": len(pairs),
        "reference_counts": {lv: ref.get(lv, 0) for lv in LEVELS},
        "system_counts": {lv: sys_.get(lv, 0) for lv in LEVELS},
        "reference_entropy": entropy_bits(ref),
        "system_entropy": entropy_bits(sys_),
        "reference_levels_used": sum(1 for lv in LEVELS if ref.get(lv, 0)),
        "system_levels_used": sum(1 for lv in LEVELS if sys_.get(lv, 0)),
    }


# ---------------------------------------------------------------------------
# B · signed error
# ---------------------------------------------------------------------------


def _quantile(sorted_values: list[int], q: float) -> float:
    """Linear-interpolated quantile. Explicit because the medians here decide P2."""
    if not sorted_values:
        return float("nan")
    position = q * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(sorted_values[low])
    return sorted_values[low] + (position - low) * (sorted_values[high] - sorted_values[low])


def signed_error(pairs: list[tuple[int, int]], offered: int) -> dict:
    errors = sorted(b - a for a, b in pairs)
    n = len(errors)
    if n == 0:
        return {
            "n": 0,
            "offered": offered,
            "dropped": offered,
            "median": UNDEFINED,
            "iqr": UNDEFINED,
            "distribution": {},
        }
    counts = Counter(errors)
    q1, q3 = _quantile(errors, 0.25), _quantile(errors, 0.75)
    return {
        "n": n,
        "offered": offered,
        "dropped": offered - n,
        "median": _quantile(errors, 0.50),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "mean": sum(errors) / n,
        "distribution": {d: counts.get(d, 0) for d in range(-4, 5)},
        "proportions": {d: counts.get(d, 0) / n for d in range(-4, 5)},
        "share_too_high": sum(v for k, v in counts.items() if k > 0) / n,
        "share_too_low": sum(v for k, v in counts.items() if k < 0) / n,
        "percentiles": {
            str(p): _quantile(errors, p / 100) for p in (0, 5, 25, 50, 75, 95, 100)
        },
    }


# ---------------------------------------------------------------------------
# C · confusion
# ---------------------------------------------------------------------------


def confusion(pairs: list[tuple[int, int]]) -> dict:
    table = {a: {b: 0 for b in LEVELS} for a in LEVELS}
    for a, b in pairs:
        table[a][b] += 1
    return table


# ---------------------------------------------------------------------------
# D · case-borne or slot-borne
# ---------------------------------------------------------------------------


def _binomial_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * (p**k) * ((1 - p) ** (n - k))


def miss_clustering(per_case: dict[str, tuple[int, int]]) -> dict:
    """Observed per-case miss counts against the exact Poisson-binomial expectation.

    Each case contributes a different number of scored judged slots, because the
    system refused a different number on each. So the null is not one binomial
    but a sum of per-case binomials, each with that case's own n — computed
    exactly by summing PMFs rather than simulated.

    The variance ratio is the summary: under independent misses it is 1. Above 1
    means misses concentrate in fewer cases than chance allows, which is what
    "some requests are hard" looks like. Near 1 means the misses are spread as
    evenly as independence predicts, which points at the criterion rather than
    the cases.
    """
    cases = {c: v for c, v in per_case.items() if v[1] > 0}
    if not cases:
        return {"cases": 0}
    total_misses = sum(m for m, _ in cases.values())
    total_slots = sum(n for _, n in cases.values())
    p = total_misses / total_slots

    observed = Counter(m for m, _ in cases.values())
    largest = max(n for _, n in cases.values())
    # Already a count of cases, not a probability: each case contributes its own
    # binomial PMF and the sum over cases is the expected number of cases with
    # exactly k misses. Multiplying by the case count again would inflate it.
    expected = {
        k: sum(_binomial_pmf(k, n, p) for _, n in cases.values() if k <= n)
        for k in range(largest + 1)
    }
    assert abs(sum(expected.values()) - len(cases)) < 1e-6, "expected counts must sum to the cases"

    counts = [m for m, _ in cases.values()]
    mean = sum(counts) / len(counts)
    observed_var = sum((c - mean) ** 2 for c in counts) / (len(counts) - 1)
    # Var of the ensemble under independence: within-case binomial variance plus
    # the spread the differing slot counts induce on their own.
    within = sum(n * p * (1 - p) for _, n in cases.values()) / len(cases)
    expected_means = [n * p for _, n in cases.values()]
    grand = sum(expected_means) / len(expected_means)
    between = sum((m - grand) ** 2 for m in expected_means) / len(expected_means)
    expected_var = within + between

    return {
        "cases": len(cases),
        "total_slots": total_slots,
        "total_misses": total_misses,
        "base_rate": p,
        "observed_distribution": {k: observed.get(k, 0) for k in range(largest + 1)},
        "expected_distribution": {k: expected[k] for k in range(largest + 1)},
        "cases_with_zero_misses": observed.get(0, 0),
        "expected_zero_misses": expected[0],
        "observed_variance": observed_var,
        "expected_variance": expected_var,
        "variance_ratio": observed_var / expected_var if expected_var else UNDEFINED,
    }


# ---------------------------------------------------------------------------
# E · against each assessor separately
# ---------------------------------------------------------------------------


def against_assessor(
    assessor: dict[tuple[str, str], int | None],
    passes: list[dict],
    want_dims: list[str] | None = None,
    want_mechanism: str | None = None,
) -> dict:
    """Every slot this assessor scored, not only the ones the other agreed with."""
    pairs: list[tuple[int, int]] = []
    offered = 0
    for (case_id, dim), expected in assessor.items():
        if expected is None:
            continue  # the assessor abstained: no target to score against
        if want_dims is not None and dim not in want_dims:
            continue
        for rows in passes:
            row = rows.get(case_id)
            if row is None or row["verdict"] is None:
                continue
            mechanism = "derived" if dim in row["derived"] else "judged"
            if want_mechanism is not None and mechanism != want_mechanism:
                continue
            offered += 1
            actual = row["scores"].get(dim)
            if actual is not None:
                pairs.append((expected, actual))
    ref_counts = Counter(a for a, _ in pairs)
    sys_counts = Counter(b for _, b in pairs)
    return {
        "offered": offered,
        "n": len(pairs),
        "dropped": offered - len(pairs),
        "exact": sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else None,
        "kappa": cohen_kappa(pairs, LEVELS) if pairs else UNDEFINED,
        "kappa_w": weighted_kappa(pairs, LEVELS) if pairs else UNDEFINED,
        "median_signed_error": _quantile(sorted(b - a for a, b in pairs), 0.5)
        if pairs
        else UNDEFINED,
        "reference_marginals": {lv: ref_counts.get(lv, 0) for lv in LEVELS},
        "system_marginals": {lv: sys_counts.get(lv, 0) for lv in LEVELS},
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def analyse(reference: dict, passes: list[dict], a: dict, b: dict) -> dict:
    collected: dict[str, list[tuple[int, int]]] = {}
    offered: Counter = Counter()
    by_mechanism: dict[str, list[tuple[int, int]]] = {"derived": [], "judged": []}
    mech_offered: Counter = Counter()
    per_case: dict[str, list[int]] = {}

    for case_id, dim, expected, actual, mechanism in slots(reference, passes):
        key = f"{dim} · {mechanism}"
        offered[key] += 1
        mech_offered[mechanism] += 1
        if actual is None:
            continue
        collected.setdefault(key, []).append((expected, actual))
        by_mechanism[mechanism].append((expected, actual))
        if mechanism == "judged":
            per_case.setdefault(case_id, []).append(1 if actual != expected else 0)

    per_dimension = {}
    for key in sorted(offered):
        pairs = collected.get(key, [])
        per_dimension[key] = {
            "marginals": marginals(pairs),
            "signed_error": signed_error(pairs, offered[key]),
            "confusion": confusion(pairs),
        }

    blocks = {
        mech: {
            "marginals": marginals(pairs),
            "signed_error": signed_error(pairs, mech_offered[mech]),
            "confusion": confusion(pairs),
        }
        for mech, pairs in by_mechanism.items()
    }

    control = [
        (dim, collected.get(f"{dim} · derived", []))
        for dim in UNCONDITIONAL
    ]
    control_failures = [
        {"dimension": dim, "reference": a_, "system": b_}
        for dim, pairs in control
        for a_, b_ in pairs
        if a_ != b_
    ]

    clustering = miss_clustering(
        {c: (sum(v), len(v)) for c, v in per_case.items()}
    )

    assessors = {}
    for name, table in (("A", a), ("B", b)):
        assessors[name] = {
            "judged_block": against_assessor(table, passes, want_mechanism="judged"),
            "derived_block": against_assessor(table, passes, want_mechanism="derived"),
            "per_dimension": {
                dim: against_assessor(table, passes, want_dims=[dim], want_mechanism="judged")
                for dim in JUDGED_ONLY
            },
        }
    assessors["reference"] = {
        "judged_block": {
            "offered": mech_offered["judged"],
            "n": len(by_mechanism["judged"]),
            "dropped": mech_offered["judged"] - len(by_mechanism["judged"]),
            "exact": sum(1 for x, y in by_mechanism["judged"] if x == y)
            / len(by_mechanism["judged"])
            if by_mechanism["judged"]
            else None,
            "kappa": cohen_kappa(by_mechanism["judged"], LEVELS),
            "kappa_w": weighted_kappa(by_mechanism["judged"], LEVELS),
        }
    }

    return {
        "per_dimension": per_dimension,
        "blocks": blocks,
        "control_failures": control_failures,
        "clustering": clustering,
        "assessors": assessors,
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------


def _f(value, spec: str = "+.3f") -> str:
    if value == UNDEFINED or value is None:
        return UNDEFINED if value == UNDEFINED else "—"
    if isinstance(value, float) and math.isnan(value):
        return "—"
    return format(value, spec)


def print_model(name: str, result: dict) -> None:
    print("=" * 104)
    print(f"MODEL: {name}")
    print("=" * 104)

    print("\n  P4 CONTROL — signed error on the three unconditionally derived dimensions")
    failures = result["control_failures"]
    if failures:
        print(f"  *** {len(failures)} non-zero errors. The control failed; everything below is suspect.")
        for f in failures[:20]:
            print(f"      {f}")
    else:
        print("  0 non-zero errors at every percentile. Control holds.")

    print("\n  A · MARGINALS AND ENTROPY (bits; max over five levels = 2.322)")
    print(f"  {'block / dimension':34} {'n':>4} {'reference 1..5':>22} {'H':>6}   "
          f"{'system 1..5':>22} {'H':>6}")
    rows = [("BLOCK derived", result["blocks"]["derived"]),
            ("BLOCK judged", result["blocks"]["judged"])]
    rows += [(k, v) for k, v in result["per_dimension"].items()]
    for label, entry in rows:
        m = entry["marginals"]
        ref = " ".join(f"{m['reference_counts'][lv]:4}" for lv in LEVELS)
        sysc = " ".join(f"{m['system_counts'][lv]:4}" for lv in LEVELS)
        print(f"  {label:34} {m['n']:4} {ref:>22} {_f(m['reference_entropy'], '.3f'):>6}   "
              f"{sysc:>22} {_f(m['system_entropy'], '.3f'):>6}")

    print("\n  B · SIGNED ERROR (system − reference)")
    print(f"  {'block / dimension':34} {'off':>4} {'n':>4} {'drop':>4} "
          f"{'median':>7} {'IQR':>6} {'mean':>7} {'too high':>9} {'too low':>8}")
    for label, entry in rows:
        s = entry["signed_error"]
        if not s["n"]:
            print(f"  {label:34} {s['offered']:4} {s['n']:4} {s['dropped']:4}  {UNDEFINED}")
            continue
        print(f"  {label:34} {s['offered']:4} {s['n']:4} {s['dropped']:4} "
              f"{_f(s['median'], '+.2f'):>7} {_f(s['iqr'], '.2f'):>6} {_f(s['mean'], '+.3f'):>7} "
              f"{s['share_too_high']:8.0%} {s['share_too_low']:7.0%}")

    print(f"\n  {'block / dimension':34} " + "".join(f"{d:>6}" for d in range(-4, 5)))
    for label, entry in rows:
        s = entry["signed_error"]
        if not s["n"]:
            continue
        print(f"  {label:34} " + "".join(f"{s['distribution'][d]:6}" for d in range(-4, 5)))

    print("\n  C · CONFUSION, 5x5, REFERENCE (rows) AGAINST SYSTEM (columns)")
    for dim in JUDGED_ONLY:
        key = f"{dim} · judged"
        if key not in result["per_dimension"]:
            continue
        entry = result["per_dimension"][key]
        print(f"\n  {key}   n={entry['marginals']['n']} "
              f"dropped={entry['signed_error']['dropped']} of {entry['signed_error']['offered']}")
        print("        sys→ " + "".join(f"{lv:6}" for lv in LEVELS))
        for lv in LEVELS:
            row = entry["confusion"][lv]
            marker = " " if sum(row.values()) else "·"
            print(f"    ref {lv}{marker}   " + "".join(f"{row[c]:6}" for c in LEVELS))

    print("\n  D · CASE-BORNE OR SLOT-BORNE? judged misses per case, pooled over passes")
    c = result["clustering"]
    print(f"  {c['cases']} cases with at least one scored judged slot · "
          f"{c['total_misses']} misses of {c['total_slots']} slots · "
          f"base rate {c['base_rate']:.0%}")
    print(f"  {'misses in a case':22}" + "".join(f"{k:7}" for k in c["observed_distribution"]))
    print(f"  {'observed cases':22}" + "".join(f"{v:7}" for v in c["observed_distribution"].values()))
    print(f"  {'expected if independent':22}"
          + "".join(f"{v:7.1f}" for v in c["expected_distribution"].values()))
    print(f"  observed variance {c['observed_variance']:.3f} · "
          f"expected {c['expected_variance']:.3f} · "
          f"ratio {_f(c['variance_ratio'], '.3f')}   (1.0 = independent)")

    print("\n  E · AGAINST EACH ASSESSOR SEPARATELY — every slot that assessor scored")
    print(f"  {'comparison':30} {'off':>4} {'n':>4} {'drop':>4} {'exact':>6} "
          f"{'kappa':>8} {'kappa_w':>8} {'median err':>10}")
    ref_row = result["assessors"]["reference"]["judged_block"]
    print(f"  {'judged vs REFERENCE (agreed)':30} {ref_row['offered']:4} {ref_row['n']:4} "
          f"{ref_row['dropped']:4} {(ref_row['exact'] or 0):5.0%} "
          f"{_f(ref_row['kappa']):>8} {_f(ref_row['kappa_w']):>8}")
    for who in ("A", "B"):
        for block in ("judged_block", "derived_block"):
            r = result["assessors"][who][block]
            label = f"{block.split('_')[0]} vs assessor {who}"
            print(f"  {label:30} {r['offered']:4} {r['n']:4} {r['dropped']:4} "
                  f"{(r['exact'] or 0):5.0%} {_f(r['kappa']):>8} {_f(r['kappa_w']):>8} "
                  f"{_f(r['median_signed_error'], '+.2f'):>10}")
    print()
    for dim in JUDGED_ONLY:
        for who in ("A", "B"):
            r = result["assessors"][who]["per_dimension"][dim]
            print(f"  {dim + ' vs ' + who:30} {r['offered']:4} {r['n']:4} {r['dropped']:4} "
                  f"{(r['exact'] or 0):5.0%} {_f(r['kappa']):>8} {_f(r['kappa_w']):>8} "
                  f"{_f(r['median_signed_error'], '+.2f'):>10}")
            if r["kappa"] == UNDEFINED or r["kappa_w"] == UNDEFINED:
                print(f"      marginals — assessor {r['reference_marginals']} "
                      f"system {r['system_marginals']}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seven", nargs=3, required=True, type=Path)
    parser.add_argument("--fourteen", nargs=3, required=True, type=Path)
    parser.add_argument("--scores-a", required=True, type=Path)
    parser.add_argument("--scores-b", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    a = load_assessor(args.scores_a)
    b = load_assessor(args.scores_b)
    reference = build_agreed_reference(a, b)
    print(f"reference: {len(reference)} agreed slots of {len(a)} offered "
          f"({len(a) - len(reference)} excluded or unscored by one side)\n")

    payload = {"reference_slots": len(reference), "models": {}}
    for name, paths in (("qwen2.5:7b", args.seven), ("qwen2.5:14b", args.fourteen)):
        result = analyse(reference, load_passes(paths), a, b)
        print_model(name, result)
        payload["models"][name] = result

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2, default=str))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
