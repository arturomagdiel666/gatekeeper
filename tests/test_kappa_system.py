"""The agreement statistics, checked against published values.

Two of this project's measurements were wrong before they were right, and both
wrong versions produced plausible numbers. A statistic that has never been run
against an answer someone else computed is in exactly that position. So each
function here is pinned to an external value rather than to its own output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from kappa_system import (  # noqa: E402
    UNDEFINED,
    cohen_kappa,
    krippendorff_alpha_ordinal,
    weighted_kappa,
)

SCALE = [1, 2, 3, 4, 5]


def test_cohen_kappa_matches_the_textbook_two_by_two():
    """po = .70, pe = .50, so κ = .40 — the standard worked example."""
    pairs = (
        [("y", "y")] * 20 + [("y", "n")] * 5 + [("n", "y")] * 10 + [("n", "n")] * 15
    )
    assert cohen_kappa(pairs, ["y", "n"]) == pytest.approx(0.40)


def test_ordinal_alpha_matches_krippendorffs_published_example():
    """Krippendorff (2011), the four-observer twelve-unit example.

    Published values for that matrix are nominal .743, **ordinal .815**,
    interval .849. Reproducing .815 validates the ordinal difference function,
    the missing-value handling and the expected-disagreement term together —
    the three places an α implementation usually goes wrong.
    """
    n = None
    observers = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, n, n, n],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, n, n],
        [n, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, n],
        [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, n],
    ]
    units = [list(u) for u in zip(*observers)]
    assert krippendorff_alpha_ordinal(units) == pytest.approx(0.815, abs=0.001)


def test_perfect_agreement_is_one_under_every_statistic():
    pairs = [(v, v) for v in SCALE * 4]
    assert weighted_kappa(pairs, SCALE) == pytest.approx(1.0)
    assert krippendorff_alpha_ordinal([[v, v] for v in SCALE * 4]) == pytest.approx(1.0)


def test_weighted_kappa_credits_near_misses_that_unweighted_does_not():
    """Half these pairs are off by one level; κw must exceed κ, not equal it."""
    pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 4), (1, 1), (2, 2), (3, 3)]
    assert weighted_kappa(pairs, SCALE) > cohen_kappa(pairs, SCALE)


def test_a_single_used_category_is_undefined_not_zero_and_not_one():
    """Both raters agreeing perfectly on one level is 0/0, not κ = 1.

    Substituting 1 would report a degenerate dimension as flawless; substituting
    0 would report it as worthless. Neither is what the data says.
    """
    assert cohen_kappa([(3, 3)] * 10, SCALE) == UNDEFINED
    assert weighted_kappa([(3, 3)] * 10, SCALE) == UNDEFINED


def test_empty_input_is_undefined():
    assert cohen_kappa([], SCALE) == UNDEFINED
    assert weighted_kappa([], SCALE) == UNDEFINED
    assert krippendorff_alpha_ordinal([]) == UNDEFINED


def test_alpha_ignores_units_rated_by_fewer_than_two_coders():
    """With two coders this is exactly pairwise deletion — α buys nothing here.

    That equivalence is the reason the judged block is reported both ways: α's
    advantage over dropping only appears from three coders upward.
    """
    with_missing = [[1, 1], [2, 2], [3, None], [None, None], [4, 4]]
    without = [[1, 1], [2, 2], [4, 4]]
    assert krippendorff_alpha_ordinal(with_missing) == krippendorff_alpha_ordinal(without)
