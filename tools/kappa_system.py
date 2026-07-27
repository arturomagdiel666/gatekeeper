"""Chance-corrected agreement for the system measurement. Analysis only.

Every agreement figure this project has published is raw percent agreement. That
is not a reliability statistic when categories are used unevenly: two raters who
both put nearly everything in one level agree 90% of the time and share no
information. This recomputes the measurements already on disk as Cohen's κ,
linear-weighted κw and Krippendorff's α.

It runs no model, changes no config, and reads no summary table. Its inputs are
the per-slot JSON files written by ``scripts/measure_against_reference.py`` and
the two scorer YAML files the reference is built from.

**Missingness is the load-bearing part.** The 7B left ``adoption_risk`` unscored
on 19-24 of 30 cases. κ has no defined behaviour for a missing rating, and
dropping the slot is precisely the move that flatters a model for refusing —
the cases it refused are not a random sample. So every table carries ``n`` and
``dropped`` on the same row as the statistic, the refusal rate is a column rather
than a footnote, and the judged block is computed both by dropping and by α,
which admits missing values by design.

Three conventions worth stating because they change the numbers:

* **Cases, not slots, are the bootstrap unit.** Seven slots from one case are not
  independent; resampling slots would produce an interval that is too narrow.
* **κ is never averaged across dimensions.** Pooled figures are computed once
  over the pooled slots.
* **Undefined stays undefined.** Where one rater used a single category, κ has no
  value; it is reported as ``undefined`` with the marginals that caused it, never
  substituted with 0 or 1.

Usage::

    python tools/kappa_system.py \\
        --seven evals/measure_ref_v2_pass1.json evals/measure_ref_v2_pass2.json \\
                evals/measure_ref_v2_pass3.json \\
        --fourteen evals/measure_ref_14b_pass1.json ... \\
        --out evals/kappa_system_results.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from measure_against_reference import build_reference, parse_corpus  # noqa: E402

#: Dimensions that *can* be resolved from an intake field. Membership here is not
#: the same as being derived on a given case: `business_value` falls back to the
#: model when the field is unknown, and `data_governance` / `non_ai_alternative`
#: derive only when their fields parse. Mechanism is therefore read per slot from
#: the row's `derived` list, never assumed from the name — grouping by name mixes
#: the two mechanisms inside one figure, which is the thing this file exists to
#: separate.
DERIVABLE = ["process_frequency", "data_governance", "non_ai_alternative", "business_value"]
JUDGED_ONLY = ["implementation_effort", "data_readiness", "adoption_risk"]
DIMENSIONS = DERIVABLE + JUDGED_ONLY
VERDICTS = ["go", "no_go", "not_ai", "incomplete"]

SEED = 20260727
RESAMPLES = 2000

#: Printed wherever a statistic has no defined value, in place of a number.
UNDEFINED = "undefined"


# ---------------------------------------------------------------------------
# The statistics
# ---------------------------------------------------------------------------


def _confusion(pairs: list[tuple], categories: list) -> dict:
    table = {a: {b: 0 for b in categories} for a in categories}
    for left, right in pairs:
        table[left][right] += 1
    return table


def _marginals(pairs: list[tuple], categories: list) -> tuple[dict, dict]:
    left = {c: 0 for c in categories}
    right = {c: 0 for c in categories}
    for a, b in pairs:
        left[a] += 1
        right[b] += 1
    return left, right


def cohen_kappa(pairs: list[tuple], categories: list) -> float | str:
    """Unweighted Cohen's κ, or ``undefined`` when expected agreement is 1.

    pe reaches 1 exactly when both raters used a single identical category, at
    which point the statistic is 0/0 — no information about agreement beyond
    chance exists, because there is no chance structure to correct for.
    """
    n = len(pairs)
    if n == 0:
        return UNDEFINED
    observed = sum(1 for a, b in pairs if a == b) / n
    left, right = _marginals(pairs, categories)
    expected = sum((left[c] / n) * (right[c] / n) for c in categories)
    if abs(1.0 - expected) < 1e-12:
        return UNDEFINED
    return (observed - expected) / (1.0 - expected)


def weighted_kappa(pairs: list[tuple[int, int]], categories: list[int]) -> float | str:
    """Linear-weighted κw: weight ``1 - |i-j| / (k-1)``.

    Linear rather than quadratic on purpose. Quadratic weights make a two-level
    error four times a one-level error, which on a 1-5 rubric scale asserts an
    interval property the anchors do not have.
    """
    n = len(pairs)
    if n == 0:
        return UNDEFINED
    span = max(categories) - min(categories)
    if span == 0:
        return UNDEFINED

    def weight(a: int, b: int) -> float:
        return 1.0 - abs(a - b) / span

    observed = sum(weight(a, b) for a, b in pairs) / n
    left, right = _marginals(pairs, categories)
    expected = sum(
        weight(a, b) * (left[a] / n) * (right[b] / n)
        for a in categories
        for b in categories
    )
    if abs(1.0 - expected) < 1e-12:
        return UNDEFINED
    return (observed - expected) / (1.0 - expected)


def bootstrap_kappa_w(
    by_case: dict[str, list[tuple[int, int]]],
    categories: list[int],
    resamples: int = RESAMPLES,
    seed: int = SEED,
) -> tuple[float, float] | str:
    """Percentile 95% interval on κw, resampling CASES with replacement.

    The unit matters: seven slots from one case share a request, a requester and
    an intake form, so they are not independent draws. Resampling slots would
    treat them as though they were and report an interval narrower than the data
    supports.
    """
    cases = sorted(by_case)
    if len(cases) < 2:
        return UNDEFINED
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        drawn = [rng.choice(cases) for _ in cases]
        pairs = [pair for case in drawn for pair in by_case[case]]
        value = weighted_kappa(pairs, categories)
        if value != UNDEFINED:
            estimates.append(value)
    if len(estimates) < resamples * 0.5:
        return UNDEFINED
    estimates.sort()
    lower = estimates[int(0.025 * len(estimates))]
    upper = estimates[min(int(0.975 * len(estimates)), len(estimates) - 1)]
    return (lower, upper)


def krippendorff_alpha_ordinal(units: list[list[int | None]]) -> float | str:
    """Krippendorff's α on the ordinal metric, admitting missing values.

    ``units`` is one list per unit, one slot per coder, ``None`` where that coder
    did not rate it. Units with fewer than two ratings contribute nothing — which
    is the honest limit of what α buys: with only two coders it discards exactly
    the same units pairwise deletion does, and its advantage over dropping
    appears only from three coders upward.

    The ordinal difference function uses the marginal frequencies of the values,
    so a one-level disagreement between two crowded levels counts for less than a
    one-level disagreement between two rare ones.
    """
    pairable = [[v for v in unit if v is not None] for unit in units]
    pairable = [unit for unit in pairable if len(unit) >= 2]
    if not pairable:
        return UNDEFINED

    values = sorted({v for unit in pairable for v in unit})
    if len(values) < 2:
        return UNDEFINED
    counts = {v: 0 for v in values}
    for unit in pairable:
        for v in unit:
            counts[v] += 1
    total = sum(counts.values())

    def delta_squared(a: int, b: int) -> float:
        if a == b:
            return 0.0
        low, high = (a, b) if a < b else (b, a)
        between = sum(counts[v] for v in values if low <= v <= high)
        return (between - (counts[low] + counts[high]) / 2.0) ** 2

    observed = 0.0
    for unit in pairable:
        m = len(unit)
        for i in range(m):
            for j in range(m):
                if i != j:
                    observed += delta_squared(unit[i], unit[j]) / (m - 1)
    observed /= total

    expected = 0.0
    for a in values:
        for b in values:
            if a != b:
                expected += counts[a] * counts[b] * delta_squared(a, b)
    expected /= total * (total - 1)

    if abs(expected) < 1e-12:
        return UNDEFINED
    return 1.0 - observed / expected


# ---------------------------------------------------------------------------
# Assembling the slot pairs
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """One row of a table: the pairs, and everything that conditions them."""

    label: str
    pairs: list[tuple[int, int]] = field(default_factory=list)
    by_case: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    #: Reference slots where the system produced no score at all.
    dropped: int = 0
    #: Slots offered by the reference before any dropping.
    offered: int = 0

    def add(self, case_id: str, reference: int, system: int | None) -> None:
        self.offered += 1
        if system is None:
            self.dropped += 1
            return
        self.pairs.append((reference, system))
        self.by_case.setdefault(case_id, []).append((reference, system))

    def report(self, categories: list[int]) -> dict:
        n = len(self.pairs)
        exact = sum(1 for a, b in self.pairs if a == b) / n if n else None
        within1 = sum(1 for a, b in self.pairs if abs(a - b) <= 1) / n if n else None
        kappa = cohen_kappa(self.pairs, categories) if n else UNDEFINED
        kappa_w = weighted_kappa(self.pairs, categories) if n else UNDEFINED
        interval = bootstrap_kappa_w(self.by_case, categories) if n else UNDEFINED
        left, right = _marginals(self.pairs, categories) if n else ({}, {})
        return {
            "label": self.label,
            "offered": self.offered,
            "n": n,
            "dropped": self.dropped,
            "refusal_rate": self.dropped / self.offered if self.offered else None,
            "exact": exact,
            "within1": within1,
            "kappa": kappa,
            "kappa_w": kappa_w,
            "kappa_w_ci": interval,
            "reference_marginals": {k: v for k, v in left.items() if v},
            "system_marginals": {k: v for k, v in right.items() if v},
        }


def load_passes(paths: list[Path]) -> list[dict[str, dict]]:
    out = []
    for path in paths:
        payload = json.loads(Path(path).read_text())
        out.append({row["case_id"]: row for row in payload["rows"]})
    return out


def _slots(reference, passes: list[dict], want=None):
    """Yield (case_id, dimension, expected, actual, mechanism) over live rows.

    ``mechanism`` is read from the row, so a nominally-derivable dimension that
    fell back to the model on this case is reported as ``judged`` — which is what
    it was.
    """
    for (case_id, dim), expected in reference.slots.items():
        for index, rows in enumerate(passes, 1):
            row = rows.get(case_id)
            if row is None or row["verdict"] is None:
                continue  # timeout or error: not a scoring result
            mechanism = "derived" if dim in row["derived"] else "judged"
            if want is not None and index != want:
                continue
            yield case_id, dim, expected, row["scores"].get(dim), mechanism


def accuracy_tables(reference, passes: list[dict], categories: list[int]) -> dict:
    """Per dimension, per dimension×mechanism, and pooled by mechanism."""
    result = {"per_dimension": [], "per_dimension_mechanism": [], "pooled": [], "per_pass": []}

    for dim in DIMENSIONS:
        block = Block(dim)
        for case_id, slot_dim, expected, actual, _ in _slots(reference, passes):
            if slot_dim == dim:
                block.add(case_id, expected, actual)
        result["per_dimension"].append(block.report(categories))

    for dim in DIMENSIONS:
        for mech in ("derived", "judged"):
            block = Block(f"{dim} · {mech}")
            for case_id, slot_dim, expected, actual, m in _slots(reference, passes):
                if slot_dim == dim and m == mech:
                    block.add(case_id, expected, actual)
            if block.offered:
                result["per_dimension_mechanism"].append(block.report(categories))

    for mech in ("derived", "judged"):
        block = Block(mech)
        for case_id, _, expected, actual, m in _slots(reference, passes):
            if m == mech:
                block.add(case_id, expected, actual)
        result["pooled"].append(block.report(categories))

    for index in range(1, len(passes) + 1):
        for mech in ("derived", "judged"):
            block = Block(f"pass {index} · {mech}")
            for case_id, _, expected, actual, m in _slots(reference, passes, want=index):
                if m == mech:
                    block.add(case_id, expected, actual)
            result["per_pass"].append(block.report(categories))
    return result


def alpha_tables(reference, passes: list[dict]) -> dict:
    """The judged block computed the second way: α, which admits missing values.

    Two forms, because they answer different questions and only the second uses
    α's missing-value handling for anything:

    * **two coders** — reference against one pass. With two coders α discards the
      same units pairwise deletion does, so its ``n`` matches the dropping table
      exactly and only the statistic differs.
    * **four coders** — reference plus all three passes. Here a slot the system
      refused in one pass still contributes through the other two. This is NOT an
      accuracy figure: it mixes agreement-with-reference and
      agreement-with-itself in one number, and is reported to show what admitting
      missingness actually changes.
    """
    out = {}
    for name in ("derived", "judged"):
        two_coder = []
        for index in range(1, len(passes) + 1):
            units = [
                [expected, actual]
                for _, _, expected, actual, m in _slots(reference, passes, want=index)
                if m == name
            ]
            rated = sum(1 for u in units if len([v for v in u if v is not None]) >= 2)
            two_coder.append(
                {
                    "pass": index,
                    "units_offered": len(units),
                    "units_used": rated,
                    "alpha_ordinal": krippendorff_alpha_ordinal(units),
                }
            )
        units4 = []
        for (case_id, slot_dim), expected in reference.slots.items():
            first = passes[0].get(case_id)
            if first is None or first["verdict"] is None:
                continue
            mechanism = "derived" if slot_dim in first["derived"] else "judged"
            if mechanism != name:
                continue  # mechanism taken from pass 1; see mechanism_drift
            row_values = [
                (rows[case_id]["scores"].get(slot_dim) if case_id in rows else None)
                for rows in passes
            ]
            units4.append([expected, *row_values])
        used4 = sum(1 for u in units4 if len([v for v in u if v is not None]) >= 2)
        out[name] = {
            "two_coder": two_coder,
            "four_coder": {
                "units_offered": len(units4),
                "units_used": used4,
                "alpha_ordinal": krippendorff_alpha_ordinal(units4),
            },
        }
    return out


def mechanism_drift(passes: list[dict]) -> dict:
    """Slots whose resolution mechanism was not the same in all three passes.

    `business_value` derives only when the intake magnitude is known and falls
    back to the model otherwise, so the mechanism is itself a model-dependent
    outcome on some cases. Any slot that drifted cannot be cleanly assigned to
    either block, and is counted here rather than silently filed under one.
    """
    drifted = []
    for case_id in sorted(passes[0]):
        for dim in DIMENSIONS:
            kinds = {
                ("derived" if dim in p[case_id]["derived"] else "judged")
                for p in passes
                if case_id in p
            }
            if len(kinds) > 1:
                drifted.append({"case_id": case_id, "dimension": dim})
    return {"count": len(drifted), "slots": drifted}


def self_consistency(passes: list[dict], categories: list[int]) -> dict:
    """Three passes of one scorer are not three raters, so report both forms.

    A slot counts toward a block only if every pass resolved it by that block's
    mechanism; drifting slots are reported separately by `mechanism_drift`.
    """

    def block_of(case_id: str, dim: str) -> str | None:
        kinds = {
            ("derived" if dim in p[case_id]["derived"] else "judged")
            for p in passes
            if case_id in p
        }
        return kinds.pop() if len(kinds) == 1 else None

    out = {}
    for name in ("derived", "judged", "all"):
        pairwise = []
        for i, j in ((0, 1), (0, 2), (1, 2)):
            block = Block(f"pass {i + 1}-{j + 1}")
            for case_id in sorted(passes[i]):
                for dim in DIMENSIONS:
                    if name != "all" and block_of(case_id, dim) != name:
                        continue
                    left = passes[i][case_id]["scores"].get(dim)
                    right = passes[j][case_id]["scores"].get(dim)
                    block.offered += 1
                    if left is None or right is None:
                        block.dropped += 1
                        continue
                    block.pairs.append((left, right))
                    block.by_case.setdefault(case_id, []).append((left, right))
            pairwise.append(block.report(categories))
        values = [b["kappa_w"] for b in pairwise if b["kappa_w"] != UNDEFINED]
        units = []
        for case_id in sorted(passes[0]):
            for dim in DIMENSIONS:
                if name != "all" and block_of(case_id, dim) != name:
                    continue
                units.append([p[case_id]["scores"].get(dim) for p in passes])
        used = sum(1 for u in units if len([v for v in u if v is not None]) >= 2)
        out[name] = {
            "pairwise": pairwise,
            "mean_kappa_w": sum(values) / len(values) if values else UNDEFINED,
            "range_kappa_w": [min(values), max(values)] if values else UNDEFINED,
            "alpha_ordinal": krippendorff_alpha_ordinal(units),
            "alpha_units_offered": len(units),
            "alpha_units_used": used,
        }
    return out


def verdict_table(reference, passes: list[dict]) -> dict:
    """Verdicts are nominal: unweighted κ only, plus the full 4x4."""
    pairs: list[tuple[str, str]] = []
    by_case: dict[str, list] = {}
    dropped = 0
    for case_id, expected in reference.verdicts.items():
        for rows in passes:
            row = rows.get(case_id)
            if row is None or row["verdict"] is None:
                dropped += 1
                continue
            pairs.append((expected, row["verdict"]))
            by_case.setdefault(case_id, []).append((expected, row["verdict"]))
    left, right = _marginals(pairs, VERDICTS)
    return {
        "n": len(pairs),
        "dropped": dropped,
        "exact": sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else None,
        "kappa": cohen_kappa(pairs, VERDICTS),
        "confusion": _confusion(pairs, VERDICTS),
        "reference_marginals": left,
        "system_marginals": right,
        "self_consistency_kappa": _verdict_self_consistency(passes),
    }


def _verdict_self_consistency(passes: list[dict]) -> dict:
    out = []
    for i, j in ((0, 1), (0, 2), (1, 2)):
        pairs = [
            (passes[i][c]["verdict"], passes[j][c]["verdict"])
            for c in sorted(passes[i])
            if passes[i][c]["verdict"] and passes[j][c]["verdict"]
        ]
        out.append(
            {
                "pair": f"{i + 1}-{j + 1}",
                "n": len(pairs),
                "exact": sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else None,
                "kappa": cohen_kappa(pairs, VERDICTS),
            }
        )
    return out


def _fmt(value) -> str:
    if value == UNDEFINED or value is None:
        return UNDEFINED if value == UNDEFINED else "—"
    if isinstance(value, tuple):
        return f"[{value[0]:+.2f}, {value[1]:+.2f}]"
    if isinstance(value, float):
        return f"{value:+.3f}" if abs(value) < 10 else f"{value:.1f}"
    return str(value)


def print_model(name: str, tables: dict) -> None:
    print("=" * 100)
    print(f"MODEL: {name}")
    print("=" * 100)
    print(f"\n  A · ACCURACY AGAINST THE REFERENCE — pooled over three passes")
    print(f"  {'dimension':24} {'offered':>7} {'n':>5} {'drop':>5} {'refuse':>7} "
          f"{'exact':>7} {'kappa':>8} {'kappa_w':>8}  95% CI on kappa_w")
    for row in tables["accuracy"]["per_dimension"] + tables["accuracy"]["pooled"]:
        print(f"  {row['label']:24} {row['offered']:7} {row['n']:5} {row['dropped']:5} "
              f"{(row['refusal_rate'] or 0):6.0%} "
              f"{(row['exact'] if row['exact'] is not None else 0):6.0%} "
              f"{_fmt(row['kappa']):>8} {_fmt(row['kappa_w']):>8}  {_fmt(row['kappa_w_ci'])}")
        if row["kappa"] == UNDEFINED or row["kappa_w"] == UNDEFINED:
            print(f"      marginals — reference {row['reference_marginals']} "
                  f"system {row['system_marginals']}")
    print(f"\n  the same dimensions split by the mechanism that actually resolved each slot")
    print(f"  {'dimension · mechanism':34} {'offered':>7} {'n':>5} {'drop':>5} {'refuse':>7} "
          f"{'exact':>7} {'kappa':>8} {'kappa_w':>8}")
    for row in tables["accuracy"]["per_dimension_mechanism"]:
        print(f"  {row['label']:34} {row['offered']:7} {row['n']:5} {row['dropped']:5} "
              f"{(row['refusal_rate'] or 0):6.0%} "
              f"{(row['exact'] if row['exact'] is not None else 0):6.0%} "
              f"{_fmt(row['kappa']):>8} {_fmt(row['kappa_w']):>8}")
        if row["kappa"] == UNDEFINED or row["kappa_w"] == UNDEFINED:
            print(f"      marginals — reference {row['reference_marginals']} "
                  f"system {row['system_marginals']}")
    drift = tables["drift"]
    print(f"\n  slots whose mechanism drifted across passes: {drift['count']}"
          + (f" — {drift['slots']}" if drift["count"] else ""))

    print(f"\n  per pass")
    for row in tables["accuracy"]["per_pass"]:
        print(f"  {row['label']:24} {row['offered']:7} {row['n']:5} {row['dropped']:5} "
              f"{(row['refusal_rate'] or 0):6.0%} "
              f"{(row['exact'] if row['exact'] is not None else 0):6.0%} "
              f"{_fmt(row['kappa']):>8} {_fmt(row['kappa_w']):>8}")

    print(f"\n  A2 · THE SAME BLOCKS BY KRIPPENDORFF'S ALPHA (admits missing values)")
    for name_block, entry in tables["alpha"].items():
        for row in entry["two_coder"]:
            print(f"  {name_block:10} two coders, pass {row['pass']}: "
                  f"units offered {row['units_offered']:3}, used {row['units_used']:3}, "
                  f"alpha {_fmt(row['alpha_ordinal'])}")
        four = entry["four_coder"]
        print(f"  {name_block:10} four coders (ref + 3 passes): units offered "
              f"{four['units_offered']:3}, used {four['units_used']:3}, "
              f"alpha {_fmt(four['alpha_ordinal'])}   [not an accuracy figure]")

    print(f"\n  B · SELF-CONSISTENCY ACROSS THE THREE PASSES")
    for block, entry in tables["self"].items():
        print(f"  {block:8} mean pairwise kappa_w {_fmt(entry['mean_kappa_w'])}  "
              f"range {_fmt(entry['range_kappa_w'][0]) if entry['range_kappa_w'] != UNDEFINED else UNDEFINED}"
              f"..{_fmt(entry['range_kappa_w'][1]) if entry['range_kappa_w'] != UNDEFINED else ''}  "
              f"alpha(3 coders) {_fmt(entry['alpha_ordinal'])} "
              f"on {entry['alpha_units_used']}/{entry['alpha_units_offered']} units")
        for row in entry["pairwise"]:
            print(f"      {row['label']:12} n {row['n']:4} dropped {row['dropped']:4} "
                  f"exact {(row['exact'] or 0):5.0%}  kappa_w {_fmt(row['kappa_w'])}")

    print(f"\n  C · VERDICTS — nominal, unweighted kappa only")
    v = tables["verdict"]
    print(f"  n {v['n']}  dropped {v['dropped']}  exact {(v['exact'] or 0):.0%}  "
          f"kappa {_fmt(v['kappa'])}")
    print(f"  reference marginals {v['reference_marginals']}")
    print(f"  system    marginals {v['system_marginals']}")
    print(f"  {'reference \\ system':22}" + "".join(f"{c:>12}" for c in VERDICTS))
    for ref in VERDICTS:
        print(f"  {ref:22}" + "".join(f"{v['confusion'][ref][got]:12}" for got in VERDICTS))
    print("  verdict self-consistency:")
    for row in v["self_consistency_kappa"]:
        print(f"      passes {row['pair']}  n {row['n']}  exact {(row['exact'] or 0):.0%}  "
              f"kappa {_fmt(row['kappa'])}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seven", nargs=3, required=True, type=Path)
    parser.add_argument("--fourteen", nargs=3, required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    print(f"seed {SEED} · {RESAMPLES} resamples · resampling unit: CASES\n")
    reference = build_reference(parse_corpus())
    print(f"reference: {len(reference.slots)} agreed slots, "
          f"{len(reference.excluded)} excluded, {len(reference.both_null)} both refused, "
          f"{len(reference.verdicts)} verdicts\n")

    categories = [1, 2, 3, 4, 5]
    payload = {
        "seed": SEED,
        "resamples": RESAMPLES,
        "resampling_unit": "cases",
        "reference": {
            "slots": len(reference.slots),
            "excluded": len(reference.excluded),
            "both_null": len(reference.both_null),
            "verdicts": len(reference.verdicts),
        },
        "models": {},
    }
    for name, paths in (("qwen2.5:7b", args.seven), ("qwen2.5:14b", args.fourteen)):
        passes = load_passes(paths)
        tables = {
            "accuracy": accuracy_tables(reference, passes, categories),
            "alpha": alpha_tables(reference, passes),
            "self": self_consistency(passes, categories),
            "verdict": verdict_table(reference, passes),
            "drift": mechanism_drift(passes),
        }
        print_model(name, tables)
        payload["models"][name] = tables

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2, default=str))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
