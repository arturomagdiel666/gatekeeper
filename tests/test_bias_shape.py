"""The bias-shape statistics, checked against values computed independently.

Section D's expectation was wrong on first run — it multiplied an already-summed
Poisson-binomial PMF by the case count, so "expected cases" exceeded the number
of cases by a factor of 26. It produced a plausible-looking table. That is the
third measurement in this project to do so, hence these.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from bias_shape import (  # noqa: E402
    _quantile,
    build_agreed_reference,
    entropy_bits,
    miss_clustering,
    signed_error,
)


def test_entropy_of_a_uniform_five_level_distribution_is_log2_five():
    assert entropy_bits({1: 4, 2: 4, 3: 4, 4: 4, 5: 4}) == pytest.approx(math.log2(5))


def test_entropy_of_a_single_used_level_is_zero():
    assert entropy_bits({3: 20}) == pytest.approx(0.0)


def test_entropy_of_two_equally_used_levels_is_one_bit():
    assert entropy_bits({2: 10, 4: 10}) == pytest.approx(1.0)


def test_entropy_ignores_the_levels_nobody_used():
    """A level with zero count contributes 0·log0 = 0, not a NaN."""
    assert entropy_bits({1: 0, 2: 10, 3: 0, 4: 10, 5: 0}) == pytest.approx(1.0)


def test_median_of_an_even_length_sample_interpolates():
    assert _quantile([1, 2, 3, 4], 0.5) == pytest.approx(2.5)


def test_signed_error_separates_a_uniform_offset_from_symmetric_noise():
    """Both have the same number of misses; only the median tells them apart.

    This is the distinction κ cannot make and the reason section B exists.
    """
    offset = signed_error([(2, 3), (3, 4), (4, 5), (1, 2)], offered=4)
    noise = signed_error([(2, 3), (3, 2), (4, 5), (2, 1)], offered=4)
    assert offset["median"] == pytest.approx(1.0)
    assert offset["share_too_high"] == 1.0
    assert noise["median"] == pytest.approx(0.0)
    assert noise["share_too_high"] == pytest.approx(0.5)


def test_signed_error_reports_dropped_slots_beside_n():
    result = signed_error([(2, 3), (3, 4)], offered=10)
    assert (result["n"], result["dropped"], result["offered"]) == (2, 8, 10)


def test_expected_miss_counts_sum_to_the_number_of_cases():
    """The bug that shipped first: expected exceeded the cases it described."""
    per_case = {f"c{i}": (i % 4, 5) for i in range(20)}
    result = miss_clustering(per_case)
    assert sum(result["expected_distribution"].values()) == pytest.approx(result["cases"])


def test_independent_misses_give_a_variance_ratio_near_one():
    """Every case at the same rate with the same slot count: ratio ≈ 1."""
    # 12 cases, 4 slots each, misses spread as a binomial(4, .5) would spread them
    counts = [0, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3, 4]
    per_case = {f"c{i}": (m, 4) for i, m in enumerate(counts)}
    assert miss_clustering(per_case)["variance_ratio"] == pytest.approx(1.0, abs=0.25)


def test_clustered_misses_give_a_variance_ratio_above_one():
    """Half the cases miss everything, half miss nothing — maximal clustering."""
    per_case = {f"c{i}": (4 if i % 2 else 0, 4) for i in range(12)}
    assert miss_clustering(per_case)["variance_ratio"] > 3.0


def test_the_reference_keeps_only_slots_both_assessors_scored_and_agreed_on():
    a = {("x", "d"): 3, ("y", "d"): 4, ("z", "d"): None, ("w", "d"): 2}
    b = {("x", "d"): 3, ("y", "d"): 5, ("z", "d"): 3, ("w", "d"): None}
    assert build_agreed_reference(a, b) == {("x", "d"): 3}
