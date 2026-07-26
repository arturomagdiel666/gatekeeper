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

#: The shipped rubric, loaded once. The validation tests below deliberately
#: corrupt copies of it; the anchor-wording tests added in Phase 4 read it as
#: shipped, because the wording IS the thing under test.
RUBRIC = load_rubric()

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

    def test_the_matching_signals_name_no_vendor(self):
        """A signal that DEFINES a match must not name a product.

        The reason is unchanged: products differ by organisation and date faster
        than this file, and a vendor list as a match criterion is what fired on
        three of six examples where no licence was mentioned.

        Narrowed in Phase 5 to the signals that define a match. The two-part test
        also carries an illustration of what does NOT count — "Salesforce as a
        data source is not Salesforce as a capability" — and a named product
        there cannot produce a false positive, which is the failure this rule
        exists to prevent. It can only withhold a match, and Part B is what
        restores one: if the request says the platform already does the job, that
        is quotable and it matches. See ADR-029.
        """
        anti_pattern = load_patterns().anti_pattern_by_id(
            "existing_licensed_capability"
        )
        matching = [s for s in anti_pattern.signals if not s.startswith("NOT PART B")]
        assert len(matching) == 2, "Part A and Part B, and nothing else, define a match"
        joined = " ".join(matching).lower()
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

    def test_never_unknown_naming_a_missing_dimension_is_rejected(
        self, tmp_path, rubric_data
    ):
        rubric_data["completeness"]["never_unknown"].append("no_such_dimension")
        with pytest.raises(ConfigError, match="do not exist"):
            write_rubric(tmp_path, rubric_data)

    def test_a_gate_dimension_outside_never_unknown_is_rejected(
        self, tmp_path, rubric_data
    ):
        """The fail-open guard: a gate whose dimension may be unknown cannot fire."""
        rubric_data["completeness"]["never_unknown"] = ["business_value"]
        with pytest.raises(ConfigError, match="fails open"):
            write_rubric(tmp_path, rubric_data)

    def test_every_gate_dimension_is_guarded_in_the_shipped_config(self):
        rubric = load_rubric()
        gated = {
            c.dimension
            for g in rubric.blocking_gates
            for c in g.any_of
            if hasattr(c, "dimension")
        }
        assert gated <= set(rubric.completeness.never_unknown)

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


class TestNonAiAlternativeHasAnOperationalBoundary:
    """ADR-027 / 2A: the repair with the most verdict leverage in the rubric.

    All six verdict disagreements in the agreement study trace to this
    dimension: four as gate flips across the 3/4 line, two as band flips on
    totals it weights. The old boundary was "roughly half the cases" against
    "most of it", which supplied no test at all.
    """

    DIMENSION = RUBRIC.dimension_by_id("non_ai_alternative")

    #: The bands as the anchors now state them, lower bound inclusive. Written
    #: out here so that rewording an anchor without rewording this table fails.
    BANDS = ((1, 0), (2, 0), (3, 25), (4, 75), (5, 99))

    def level_for(self, percentage: float) -> int:
        """The level whose band contains a share of instances finished."""
        return max(level for level, lower in self.BANDS if percentage >= lower)

    def test_the_anchors_state_their_numeric_bounds(self):
        anchors = self.DIMENSION.anchors
        assert "25%" in anchors[2]
        assert "25-75%" in anchors[3]
        assert "75-99%" in anchors[4]
        assert "99-100%" in anchors[5]

    def test_a_stated_sixty_percent_lands_in_level_three(self):
        """B-09 states exactly 60% and used to sit in the gap between two words."""
        assert self.level_for(60) == 3

    def test_the_gated_boundary_is_seventy_five_percent(self):
        """The gate fires at raw >= 4, so this number decides not_ai verdicts."""
        gate = next(
            g for g in RUBRIC.blocking_gates if g.id == "non_ai_alternative_suffices"
        )
        threshold = next(
            c.threshold
            for c in gate.any_of
            if getattr(c, "dimension", None) == "non_ai_alternative"
        )
        assert threshold == 4
        assert self.level_for(74) == 3, "just under the line does not gate"
        assert self.level_for(75) == threshold, "the line itself gates"

    def test_the_bands_tile_zero_to_one_hundred_without_a_gap(self):
        for percentage in range(0, 101):
            assert 1 <= self.level_for(percentage) <= 5

    def test_level_one_no_longer_demands_a_failed_attempt_as_proof(self):
        """A rule-immune request — translation — can never satisfy that test.

        Nobody attempts rules for machine translation, so requiring evidence of
        a failed attempt made the most rule-immune requests in the corpus
        unable to reach the level that describes them.
        """
        level_one = " ".join(self.DIMENSION.anchors[1].split())
        assert "supporting evidence here, not a requirement" in level_one
        assert "attempts have been tried and are known to fail" not in level_one

    def test_the_axis_counts_instances_finished_rather_than_help_given(self):
        axis = " ".join(self.DIMENSION.axis.split())
        assert "SHARE OF INSTANCES" in axis
        assert "END TO END" in axis

    def test_the_relocation_rule_is_gone_from_all_three_places(self):
        """ADR-029, acceptance criterion 2.

        Phase 4 added numeric bands and left the "moves a judgement upstream"
        rule beside them. Two rules, no precedence, 70% -> 61%. These are the
        assertions that used to require the deleted rule to be present, inverted.
        """
        surfaces = {
            "axis": self.DIMENSION.axis,
            "scoring_rule": self.DIMENSION.scoring_rule,
            "description": self.DIMENSION.description,
            **{f"anchor {k}": v for k, v in self.DIMENSION.anchors.items()},
        }
        for where, text in surfaces.items():
            normalized = " ".join((text or "").split()).lower()
            for deleted in (
                "improves every instance but finishes none",
                "helps with every instance while finishing none",
                "partial help on every instance is not coverage",
                "moves a judgement rather than removing it",
            ):
                # The description may NAME the deleted rule while recording that
                # it was deleted; it may not state it as a rule to apply.
                if where == "description" and "deleted" in normalized:
                    continue
                assert deleted not in normalized, (where, deleted)

    def test_a_coarse_deterministic_output_resolves_in_the_axis(self):
        """The case Scorer A could not settle, now settled in one sentence."""
        axis = " ".join(self.DIMENSION.axis.split())
        assert "has not finished the instance" in axis
        for example in ("scorecard", "risk questionnaire", "redline"):
            assert example in axis, example


class TestDataReadinessCombinesTwoSubAssessments:
    """2B: one dimension answering two questions, now combined by `min`.

    NOT tested here: that the engine computes the minimum. It cannot — a
    DimensionAssessment carries one score per dimension, so the two halves are
    combined by whoever scores, and code never sees them separately. Making the
    min mechanical would mean adding two sub-scores to the model's schema, which
    is a change to the frozen live path and belongs to its own phase. See
    ADR-027 for the cost of that option and why it was not taken now.
    """

    DIMENSION = RUBRIC.dimension_by_id("data_readiness")

    def test_the_axis_declares_both_halves_and_the_combining_rule(self):
        axis = " ".join(self.DIMENSION.axis.split())
        assert "LOWER of the two" in axis
        assert "AVAILABILITY:" in axis
        assert "EVALUABILITY:" in axis

    def test_the_scoring_rule_requires_the_evidence_to_name_both_halves(self):
        rule = " ".join(self.DIMENSION.scoring_rule.split())
        assert "record the LOWER of the two" in rule
        assert "must say something about both halves" in rule

    def test_every_anchor_describes_both_halves(self):
        for level, text in self.DIMENSION.anchors.items():
            normalized = " ".join(text.split())
            assert "AVAILABILITY —" in normalized, level
            assert "EVALUABILITY —" in normalized, level

    def test_the_two_halves_can_differ_by_two_levels_in_the_same_case(self):
        """The NDA case: retrievable documents, an outcome nobody recorded.

        Availability matches the level 3 descriptor, evaluability matches the
        level 1 one — and level 1 is the value that fires the no_usable_data
        gate, which is why the ambiguity was verdict-changing rather than
        merely untidy.
        """
        availability_three = " ".join(self.DIMENSION.anchors[3].split())
        evaluability_one = " ".join(self.DIMENSION.anchors[1].split())
        assert "exists in one or two systems" in availability_three
        assert "collecting what nobody recorded" in evaluability_one
        gate = next(g for g in RUBRIC.blocking_gates if g.id == "no_usable_data")
        condition = next(
            c for c in gate.any_of if getattr(c, "dimension", None) == "data_readiness"
        )
        assert (condition.comparison, condition.threshold) == ("at_most", 1)

    def test_access_paperwork_is_no_longer_a_readiness_level(self):
        """It capped perfect-label cases at 4, and blocked 4 as often as 5."""
        for level in (4, 5):
            text = " ".join(self.DIMENSION.anchors[level].split()).lower()
            assert "grant access" not in text, level
            assert "without an exception" not in text, level
            assert "owner" not in text, level

    def test_level_four_accepts_a_plausible_path_to_checking_quality(self):
        """"Checked on a real sample" is almost never stated in a request."""
        assert "plausible path to being checked" in " ".join(
            self.DIMENSION.anchors[4].split()
        )


class TestProcessFrequencyDefinesTheInstance:
    """2C: a latent defect — 100% agreement, but only because of the derivation."""

    DIMENSION = RUBRIC.dimension_by_id("process_frequency")

    def test_the_axis_defines_what_an_instance_is(self):
        axis = " ".join(self.DIMENSION.axis.split())
        assert "one unit of work the agent would handle end to end, once" in axis
        assert axis.strip() != ""

    # The two tests that stood here asserted the recount instruction was present
    # in the axis — the worked examples, and "fill the intake volume field in
    # that same unit". Phase 5 deletes that instruction rather than arbitrating
    # between it and the derivation, so the tests go with it. What replaced them
    # is TestProcessFrequencyAsksOneQuestion below, which asserts the axis
    # defines the unit and does NOT tell a scorer to recount (ADR-029).


class TestTheRewrittenRulesReachTheModel:
    """An anchor nobody sends is a note to self. Only `axis`, `scoring_rule` and
    the anchors are rendered — `description` is documentation."""

    def test_the_prompt_carries_all_three_repairs(self):
        from assess import build_system_prompt

        prompt = " ".join(build_system_prompt().split())
        assert "SHARE OF INSTANCES" in prompt
        assert "LOWER of the two" in prompt
        assert "one unit of work the agent would handle end to end, once" in prompt
        assert "Never estimate a magnitude the request does not state" in prompt


class TestProcessFrequencyAsksOneQuestion:
    """ADR-029: the axis defines the unit, the form asks for it, nothing recounts.

    Phase 4 added a recount instruction to the axis beside a derivation that
    reads the intake field literally. The two disagreed by up to two bands and
    agreement fell from 100% to 88%. The instruction is gone; the definition
    moved into the question the form asks.
    """

    DIMENSION = RUBRIC.dimension_by_id("process_frequency")

    def test_the_axis_still_defines_the_instance(self):
        axis = " ".join(self.DIMENSION.axis.split())
        assert "one unit of work the agent would handle end to end, once" in axis

    def test_the_axis_no_longer_tells_the_scorer_to_recount(self):
        axis = " ".join(self.DIMENSION.axis.split())
        for instruction in (
            "and not one",
            "and not 12",
            "Count what the agent does",
            "fill the intake volume field",
        ):
            assert instruction not in axis, instruction

    def test_the_description_carries_no_recount_rule_either(self):
        """Criterion 2: a deleted rule is deleted from all three places."""
        description = " ".join(self.DIMENSION.description.split())
        assert "4,500 requirement responses" not in description
        assert "recount" in description, "the deletion is recorded, not silent"

    def test_the_derivation_still_reads_the_field_literally(self):
        derivation = self.DIMENSION.derivation
        assert derivation.source == "intake_volume"
        assert [b.below_per_year for b in derivation.bands] == [12, 100, 1000, 10000]
        assert derivation.otherwise == 5
        assert derivation.is_fallback is False, "authoritative, as before"


class TestExemplarVolumesAnswerTheNewQuestion:
    """Criterion: each exemplar's volume field is the agent's unit of work.

    The relabel is only worth anything if the values on the form mean what the
    new question asks. This is the check that would have caught the one that
    did not — exemplar 04, where the form counted laptop FAILURES while the
    reference assessment reasoned about the 4,000-machine fleet, and the
    derivation quietly scored the failures.
    """

    def test_the_laptop_fleet_is_counted_rather_than_its_failures(self):
        from examples import load_example

        example = load_example("predict_laptop_failures")
        assert example.intake.instances_per_year == 4000
        entry = next(
            e
            for e in example.reference_assessment.dimension_assessments
            if e.dimension_id == "process_frequency"
        )
        assert entry.score == 4
        assert "one prediction for one machine" in " ".join(entry.evidence.split())

    def test_every_exemplar_volume_lands_on_the_band_its_evidence_claims(self):
        """The derivation overrides the model, so a mismatch is invisible at runtime."""
        from examples import load_examples
        from scoring import derive_scores

        for example in load_examples():
            derived = derive_scores(RUBRIC, example.intake)
            if "process_frequency" not in derived:
                continue  # blank field: the model scores it, nothing to check
            derived_score, _ = derived["process_frequency"]
            entry = next(
                e
                for e in example.reference_assessment.dimension_assessments
                if e.dimension_id == "process_frequency"
            )
            assert entry.score == derived_score, (
                example.id,
                f"reference says {entry.score}, the form derives {derived_score}",
            )
