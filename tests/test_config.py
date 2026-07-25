"""Tests for loading and validating rubric.yaml and patterns.yaml.

Every test runs offline. The validation tests work by loading the real config,
corrupting one thing, writing it to a temp file, and asserting the loader
refuses it — so they stay honest if the shipped config changes shape.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from config import (
    PATTERNS_PATH,
    RUBRIC_PATH,
    ConfigError,
    load_patterns,
    load_rubric,
)


@pytest.fixture
def rubric_data() -> dict:
    """The real rubric.yaml as a plain dict, ready to be corrupted."""
    return yaml.safe_load(RUBRIC_PATH.read_text())


@pytest.fixture
def patterns_data() -> dict:
    """The real patterns.yaml as a plain dict, ready to be corrupted."""
    return yaml.safe_load(PATTERNS_PATH.read_text())


def write_rubric(tmp_path, data: dict):
    """Write a rubric dict to a temp file and load it."""
    path = tmp_path / "rubric.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_rubric(path)


def write_patterns(tmp_path, data: dict):
    """Write a patterns dict to a temp file and load it."""
    path = tmp_path / "patterns.yaml"
    path.write_text(yaml.safe_dump(data))
    return load_patterns(path)


class TestShippedConfigLoads:
    def test_rubric_has_six_dimensions_with_weights_summing_to_one(self):
        rubric = load_rubric()
        assert len(rubric.dimensions) == 6
        assert sum(d.weight for d in rubric.dimensions) == pytest.approx(1.0)
        assert rubric.version

    def test_rubric_dimension_ids_are_the_documented_set(self):
        assert set(load_rubric().dimension_ids) == {
            "economic_impact",
            "process_frequency",
            "data_maturity",
            "implementation_effort",
            "regulatory_risk",
            "non_ai_alternative",
        }

    def test_every_dimension_has_an_anchor_for_every_level(self):
        rubric = load_rubric()
        for dimension in rubric.dimensions:
            assert sorted(dimension.anchors) == rubric.scale.levels
            for text in dimension.anchors.values():
                assert text.strip()

    def test_bands_only_produce_go_and_no_go(self):
        assert {b.verdict for b in load_rubric().verdict_bands} == {"go", "no_go"}

    def test_the_three_shipped_gates_are_present_in_precedence_order(self):
        rubric = load_rubric()
        assert [(g.id, g.verdict) for g in rubric.gates_by_precedence] == [
            ("not_ai_alternative_suffices", "not_ai"),
            ("no_usable_data", "no_go"),
            ("unacceptable_regulatory_exposure", "no_go"),
        ]

    def test_not_ai_outranks_no_go(self):
        by_id = {g.id: g for g in load_rubric().blocking_gates}
        assert (
            by_id["not_ai_alternative_suffices"].precedence
            < by_id["no_usable_data"].precedence
        )

    def test_patterns_load_with_archetypes_and_anti_patterns(self):
        patterns = load_patterns()
        assert {a.id for a in patterns.archetypes} == {
            "classification",
            "extraction",
            "summarization",
            "forecasting",
            "anomaly_detection",
            "rag_qa",
            "recommendation",
        }
        assert len(patterns.anti_patterns) >= 7

    def test_the_expected_anti_patterns_hard_block(self):
        assert set(load_patterns().hard_block_ids) == {
            "deterministic_rule_suffices",
            "reporting_in_disguise",
            "rpa_relabeled",
            "zero_error_tolerance_no_human",
        }

    def test_advisory_anti_patterns_do_not_hard_block(self):
        patterns = load_patterns()
        for anti_pattern_id in (
            "chatbot_without_job_to_be_done",
            "data_does_not_exist_yet",
            "solution_first_no_measurable_problem",
        ):
            assert patterns.anti_pattern_by_id(anti_pattern_id).hard_block is False


class TestDirectionNormalization:
    """The single most likely bug in the phase, isolated from the scorer."""

    def test_higher_is_better_passes_through(self):
        rubric = load_rubric()
        dimension = rubric.dimension_by_id("economic_impact")
        assert dimension.direction == "higher_is_better"
        assert [rubric.normalize(dimension, raw) for raw in (1, 3, 5)] == [1, 3, 5]

    def test_lower_is_better_is_flipped_about_the_scale(self):
        rubric = load_rubric()
        dimension = rubric.dimension_by_id("implementation_effort")
        assert dimension.direction == "lower_is_better"
        assert [rubric.normalize(dimension, raw) for raw in (1, 3, 5)] == [5, 3, 1]


class TestRubricValidationFailures:
    def test_weights_not_summing_to_one_is_rejected(self, tmp_path, rubric_data):
        rubric_data["dimensions"][0]["weight"] = 0.9
        with pytest.raises(ConfigError, match="sum to 1.0"):
            write_rubric(tmp_path, rubric_data)

    def test_missing_anchor_level_is_rejected(self, tmp_path, rubric_data):
        del rubric_data["dimensions"][0]["anchors"][3]
        with pytest.raises(ConfigError, match="anchor"):
            write_rubric(tmp_path, rubric_data)

    def test_unknown_direction_is_rejected(self, tmp_path, rubric_data):
        rubric_data["dimensions"][0]["direction"] = "sideways"
        with pytest.raises(ConfigError, match="direction"):
            write_rubric(tmp_path, rubric_data)

    def test_duplicate_dimension_ids_are_rejected(self, tmp_path, rubric_data):
        rubric_data["dimensions"][1]["id"] = rubric_data["dimensions"][0]["id"]
        with pytest.raises(ConfigError, match="duplicate dimension ids"):
            write_rubric(tmp_path, rubric_data)

    def test_gapped_bands_are_rejected(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][0]["upper"] = 3.0  # go still starts at 3.5
        with pytest.raises(ConfigError, match="gap"):
            write_rubric(tmp_path, rubric_data)

    def test_overlapping_bands_are_rejected(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][0]["upper"] = 4.0  # go also starts at 3.5
        with pytest.raises(ConfigError, match="overlap"):
            write_rubric(tmp_path, rubric_data)

    def test_bands_not_covering_the_top_of_the_scale_are_rejected(
        self, tmp_path, rubric_data
    ):
        rubric_data["verdict_bands"][-1]["upper"] = 4.5
        with pytest.raises(ConfigError, match="scale ends at"):
            write_rubric(tmp_path, rubric_data)

    def test_highest_band_must_include_its_upper_bound(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][-1]["upper_inclusive"] = False
        with pytest.raises(ConfigError, match="upper_inclusive"):
            write_rubric(tmp_path, rubric_data)

    def test_not_ai_cannot_be_a_verdict_band(self, tmp_path, rubric_data):
        """Acceptance criterion 4, enforced at config-load time."""
        rubric_data["verdict_bands"][0]["verdict"] = "not_ai"
        with pytest.raises(ConfigError, match="not_ai"):
            write_rubric(tmp_path, rubric_data)

    def test_incomplete_cannot_be_a_verdict_band(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][0]["verdict"] = "incomplete"
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

    def test_gate_naming_an_unknown_dimension_is_rejected(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][0]["any_of"][0]["dimension"] = "no_such_dimension"
        with pytest.raises(ConfigError, match="not a declared dimension"):
            write_rubric(tmp_path, rubric_data)

    def test_gate_threshold_off_the_scale_is_rejected(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][0]["any_of"][0]["threshold"] = 9
        with pytest.raises(ConfigError, match="outside the scale"):
            write_rubric(tmp_path, rubric_data)

    def test_duplicate_gate_ids_are_rejected(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][1]["id"] = rubric_data["blocking_gates"][0]["id"]
        with pytest.raises(ConfigError, match="duplicate blocking gate ids"):
            write_rubric(tmp_path, rubric_data)

    def test_a_gate_cannot_force_a_go(self, tmp_path, rubric_data):
        """Gates exist to stop a case, never to wave one through."""
        rubric_data["blocking_gates"][0]["verdict"] = "go"
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

    def test_a_gate_needs_at_least_one_condition(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][0]["any_of"] = []
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

    def test_unknown_condition_type_is_rejected(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][0]["any_of"][0]["type"] = "vibes"
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

    def test_removing_every_gate_is_allowed(self, tmp_path, rubric_data):
        """Gates are optional: an empty list leaves pure band behaviour."""
        rubric_data["blocking_gates"] = []
        assert write_rubric(tmp_path, rubric_data).blocking_gates == []

    def test_unknown_limit_above_dimension_count_is_rejected(
        self, tmp_path, rubric_data
    ):
        rubric_data["completeness"]["max_unknown_dimensions"] = 99
        with pytest.raises(ConfigError, match="exceeds the number of dimensions"):
            write_rubric(tmp_path, rubric_data)

    def test_unknown_top_level_key_is_rejected(self, tmp_path, rubric_data):
        rubric_data["surprise"] = True
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

    def test_missing_file_is_reported_clearly(self, tmp_path):
        with pytest.raises(ConfigError, match="Could not read config file"):
            load_rubric(tmp_path / "nope.yaml")

    def test_malformed_yaml_is_reported_clearly(self, tmp_path):
        path = tmp_path / "rubric.yaml"
        path.write_text("dimensions: [unclosed\n")
        with pytest.raises(ConfigError, match="not valid YAML"):
            load_rubric(path)


class TestPatternsValidationFailures:
    def test_duplicate_anti_pattern_ids_are_rejected(self, tmp_path, patterns_data):
        duplicate = copy.deepcopy(patterns_data["anti_patterns"][0])
        patterns_data["anti_patterns"].append(duplicate)
        with pytest.raises(ConfigError, match="duplicate anti-pattern ids"):
            write_patterns(tmp_path, patterns_data)

    def test_duplicate_archetype_ids_are_rejected(self, tmp_path, patterns_data):
        duplicate = copy.deepcopy(patterns_data["archetypes"][0])
        patterns_data["archetypes"].append(duplicate)
        with pytest.raises(ConfigError, match="duplicate archetype ids"):
            write_patterns(tmp_path, patterns_data)

    def test_missing_required_field_is_rejected(self, tmp_path, patterns_data):
        del patterns_data["anti_patterns"][0]["hard_block"]
        with pytest.raises(ConfigError, match="hard_block"):
            write_patterns(tmp_path, patterns_data)
