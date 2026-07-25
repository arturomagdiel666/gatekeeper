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
    validate_cross_references,
)

EXPECTED_DIMENSIONS = {
    "business_value",
    "adoption_risk",
    "data_readiness",
    "process_frequency",
    "implementation_effort",
    "data_governance",
    "non_ai_alternative",
}


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


def gate_by_id(rubric_data: dict, gate_id: str) -> dict:
    """Find a gate in the raw config dict."""
    return next(g for g in rubric_data["blocking_gates"] if g["id"] == gate_id)


class TestShippedConfigLoads:
    def test_seven_dimensions_with_weights_summing_to_one(self):
        rubric = load_rubric()
        assert set(rubric.dimension_ids) == EXPECTED_DIMENSIONS
        assert sum(d.weight for d in rubric.dimensions) == pytest.approx(1.0)
        assert rubric.version

    def test_every_dimension_declares_a_single_axis(self):
        """Acceptance criterion 4 — the axis line is mandatory, not optional."""
        for dimension in load_rubric().dimensions:
            assert dimension.axis.strip()

    def test_every_dimension_has_an_anchor_for_every_level(self):
        rubric = load_rubric()
        for dimension in rubric.dimensions:
            assert sorted(dimension.anchors) == rubric.scale.levels
            for text in dimension.anchors.values():
                assert text.strip()

    def test_the_two_gated_dimensions_carry_the_lowest_weights(self):
        """The weight rationale, asserted so a retune cannot silently break it.

        data_governance and non_ai_alternative are gated at their extremes, so
        their weight only expresses the non-extreme gradient.
        """
        rubric = load_rubric()
        weights = {d.id: d.weight for d in rubric.dimensions}
        gated = {"data_governance", "non_ai_alternative"}
        ungated_min = min(w for i, w in weights.items() if i not in gated)
        assert all(weights[i] <= ungated_min for i in gated)

    def test_adoption_risk_is_the_second_heaviest_dimension(self):
        weights = sorted(
            ((d.weight, d.id) for d in load_rubric().dimensions), reverse=True
        )
        assert weights[0][1] == "business_value"
        assert weights[1][1] == "adoption_risk"

    def test_bands_only_produce_go_and_no_go(self):
        assert {b.verdict for b in load_rubric().verdict_bands} == {"go", "no_go"}

    def test_the_five_shipped_gates_are_present_in_precedence_order(self):
        rubric = load_rubric()
        assert [(g.id, g.verdict) for g in rubric.gates_by_precedence] == [
            ("existing_capability_covers_it", "not_ai"),
            ("non_ai_alternative_suffices", "not_ai"),
            ("no_named_business_owner", "no_go"),
            ("no_usable_data", "no_go"),
            ("unacceptable_data_governance", "no_go"),
        ]

    def test_patterns_load_with_archetypes_and_anti_patterns(self):
        patterns = load_patterns()
        assert set(patterns.archetype_ids) == {
            "classification",
            "extraction",
            "summarization",
            "forecasting",
            "anomaly_detection",
            "rag_qa",
            "recommendation",
        }
        assert len(patterns.anti_patterns) >= 9

    def test_the_expected_anti_patterns_hard_block(self):
        assert set(load_patterns().hard_block_ids) == {
            "existing_licensed_capability",
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
            "single_user_workaround",
        ):
            assert patterns.anti_pattern_by_id(anti_pattern_id).hard_block is False

    def test_existing_licensed_capability_signals_name_categories_not_products(self):
        """It must not name vendors, which differ by org and date faster than YAML."""
        anti_pattern = load_patterns().anti_pattern_by_id(
            "existing_licensed_capability"
        )
        joined = " ".join(anti_pattern.signals).lower()
        for vendor in ("microsoft", "copilot", "servicenow", "salesforce", "google"):
            assert vendor not in joined


class TestDirectionNormalization:
    def test_higher_is_better_passes_through(self):
        rubric = load_rubric()
        dimension = rubric.dimension_by_id("business_value")
        assert dimension.direction == "higher_is_better"
        assert [rubric.normalize(dimension, raw) for raw in (1, 3, 5)] == [1, 3, 5]

    def test_lower_is_better_is_flipped_about_the_scale(self):
        rubric = load_rubric()
        dimension = rubric.dimension_by_id("adoption_risk")
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

    def test_missing_axis_is_rejected(self, tmp_path, rubric_data):
        del rubric_data["dimensions"][0]["axis"]
        with pytest.raises(ConfigError, match="axis"):
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
        rubric_data["verdict_bands"][0]["upper"] = 3.0
        with pytest.raises(ConfigError, match="gap"):
            write_rubric(tmp_path, rubric_data)

    def test_overlapping_bands_are_rejected(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][0]["upper"] = 4.0
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
        """Acceptance criterion: not_ai is reachable only through a gate."""
        rubric_data["verdict_bands"][0]["verdict"] = "not_ai"
        with pytest.raises(ConfigError, match="not_ai"):
            write_rubric(tmp_path, rubric_data)

    def test_incomplete_cannot_be_a_verdict_band(self, tmp_path, rubric_data):
        rubric_data["verdict_bands"][0]["verdict"] = "incomplete"
        with pytest.raises(ConfigError):
            write_rubric(tmp_path, rubric_data)

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


class TestGateValidationFailures:
    def test_gate_naming_an_unknown_dimension_is_rejected(self, tmp_path, rubric_data):
        gate_by_id(rubric_data, "no_usable_data")["any_of"][0]["dimension"] = "nope"
        with pytest.raises(ConfigError, match="not a declared dimension"):
            write_rubric(tmp_path, rubric_data)

    def test_gate_threshold_off_the_scale_is_rejected(self, tmp_path, rubric_data):
        gate_by_id(rubric_data, "no_usable_data")["any_of"][0]["threshold"] = 9
        with pytest.raises(ConfigError, match="outside the scale"):
            write_rubric(tmp_path, rubric_data)

    def test_gate_on_an_ungateable_intake_field_is_rejected(
        self, tmp_path, rubric_data
    ):
        gate_by_id(rubric_data, "no_named_business_owner")["any_of"][0]["field"] = (
            "favourite_colour"
        )
        with pytest.raises(ConfigError, match="not a gateable"):
            write_rubric(tmp_path, rubric_data)

    def test_duplicate_gate_ids_are_rejected(self, tmp_path, rubric_data):
        rubric_data["blocking_gates"][1]["id"] = rubric_data["blocking_gates"][0]["id"]
        with pytest.raises(ConfigError, match="duplicate blocking gate ids"):
            write_rubric(tmp_path, rubric_data)

    def test_a_gate_cannot_force_a_go(self, tmp_path, rubric_data):
        """Gates exist to stop a request, never to wave one through."""
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

    def test_anti_pattern_condition_needs_exactly_one_form(
        self, tmp_path, rubric_data
    ):
        condition = gate_by_id(rubric_data, "existing_capability_covers_it")["any_of"][0]
        condition["hard_block_any"] = True  # already has anti_pattern_ids
        with pytest.raises(ConfigError, match="exactly one"):
            write_rubric(tmp_path, rubric_data)

    def test_anti_pattern_condition_with_neither_form_is_rejected(
        self, tmp_path, rubric_data
    ):
        condition = gate_by_id(rubric_data, "existing_capability_covers_it")["any_of"][0]
        condition["anti_pattern_ids"] = []
        with pytest.raises(ConfigError, match="must set either"):
            write_rubric(tmp_path, rubric_data)

    def test_removing_every_gate_is_allowed(self, tmp_path, rubric_data):
        """Gates are optional: an empty list leaves pure band behaviour."""
        rubric_data["blocking_gates"] = []
        assert write_rubric(tmp_path, rubric_data).blocking_gates == []


class TestCrossReferenceValidation:
    def test_shipped_config_cross_references_cleanly(self):
        validate_cross_references(load_rubric(), load_patterns())

    def test_gate_referencing_an_unknown_anti_pattern_is_rejected(
        self, tmp_path, rubric_data
    ):
        gate_by_id(rubric_data, "existing_capability_covers_it")["any_of"][0][
            "anti_pattern_ids"
        ] = ["no_such_anti_pattern"]
        rubric = write_rubric(tmp_path, rubric_data)
        with pytest.raises(ConfigError, match="not defined in patterns.yaml"):
            validate_cross_references(rubric, load_patterns())

    def test_gate_excluding_an_unknown_anti_pattern_is_rejected(
        self, tmp_path, rubric_data
    ):
        condition = gate_by_id(rubric_data, "non_ai_alternative_suffices")["any_of"][1]
        condition["exclude_ids"] = ["ghost"]
        rubric = write_rubric(tmp_path, rubric_data)
        with pytest.raises(ConfigError, match="not defined in patterns.yaml"):
            validate_cross_references(rubric, load_patterns())


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
