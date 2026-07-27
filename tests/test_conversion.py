"""The three dimensions converted in v3.0.0, one test per resolution rule.

Every field here had to pass one question before it was written into the schema:
**could two requesters looking at the same real situation give different answers?**
Where the answer was yes, a numbered rule in `rubric.yaml` forces it. These tests
pin the rules, because a rule that is only prose is a rule that drifts.

The last class is the one that matters most for the paper: the corpus in `evals/`
was scored under rubric v2.0.0, and none of its intakes carry the new evidence
fields. Every derivation here must return `None` for those, leaving the dimension
to the model exactly as before — otherwise this phase silently rewrites published
figures, which §4 of the brief calls a defect rather than an improvement.
"""

from __future__ import annotations

import pytest

from agent_tools import score_and_gate
from config import RUBRIC
from schemas import (
    AdoptionEvidence,
    DataEvidence,
    DataSensitivity,
    DeterministicArtefact,
    EffortEvidence,
    Period,
    Procurement,
    PriorTool,
    RequestIntake,
    SampleCheck,
    UserConsultation,
    WorkflowFit,
)
from scoring import Verdict, derive_scores

REQUEST = "Route incoming service desk tickets to the right team."


def readiness(**kwargs) -> int | None:
    defaults = dict(
        systems=["ServiceNow"],
        sample_checked=SampleCheck.LOOKED_USABLE,
        correct_examples=200_000,
        quality_criteria_agreed=True,
    )
    intake = RequestIntake(
        request_text=REQUEST, data_evidence=DataEvidence(**{**defaults, **kwargs})
    )
    return derive_scores(RUBRIC, intake).get("data_readiness", (None,))[0]


def effort(**kwargs) -> int | None:
    defaults = dict(
        systems_to_integrate=["ServiceNow"],
        procurement=Procurement.EXISTING_LICENCE,
        approving_teams=["Service Desk"],
    )
    intake = RequestIntake(
        request_text=REQUEST, effort_evidence=EffortEvidence(**{**defaults, **kwargs})
    )
    return derive_scores(RUBRIC, intake).get("implementation_effort", (None,))[0]


def adoption(prior=PriorTool.ADOPTED, **kwargs) -> int | None:
    defaults = dict(
        users_consulted=UserConsultation.REQUESTED_IT,
        user_quote="the ticket sits in the wrong queue until someone notices",
        workflow_fit=WorkflowFit.EXISTING_STEP,
        people_who_must_change=4,
    )
    intake = RequestIntake(
        request_text=REQUEST,
        prior_tool_for_these_users=prior,
        adoption_evidence=AdoptionEvidence(**{**defaults, **kwargs}),
    )
    return derive_scores(RUBRIC, intake).get("adoption_risk", (None,))[0]


# ---------------------------------------------------------------------------
# data_readiness
# ---------------------------------------------------------------------------


class TestDataReadinessRules:
    def test_r2_an_empty_system_list_is_an_answer_meaning_nowhere_retrievable(self):
        """R2. Not a blank. Data in heads or on paper is anchor 1, and level 1
        fires the no_usable_data gate — which is the right answer, not a bug."""
        assert readiness(systems=[]) == 1

    def test_r2_the_count_of_systems_sets_availability(self):
        """One system is centralized; three is 'nobody has joined them'."""
        assert readiness(systems=["ServiceNow"]) == 5
        assert readiness(systems=["ServiceNow", "Jira"]) == 4
        assert readiness(systems=["ServiceNow", "Jira", "email"]) == 2

    def test_r3_nobody_having_looked_caps_availability_at_three(self):
        """R3. Anchor 3 is explicit: quality not checked on real records."""
        assert readiness(sample_checked=SampleCheck.NOT_LOOKED) == 3

    def test_r3_looking_and_finding_problems_is_not_better_than_not_looking(self):
        """R3. Both are 'quality unestablished'; one of them knows it."""
        assert readiness(sample_checked=SampleCheck.LOOKED_PROBLEMS) == readiness(
            sample_checked=SampleCheck.NOT_LOOKED
        )

    def test_r4b_no_examples_of_a_correct_output_is_evaluability_one(self):
        """R4b. No outcome variable and no reference set — and `min` carries it
        through to the score however clean the storage is."""
        assert readiness(correct_examples=0, quality_criteria_agreed=False) == 1

    def test_r4_agreed_written_criteria_raise_evaluability_by_one(self):
        """R4. Criteria are what turn examples into a settled way to judge."""
        assert readiness(correct_examples=5, quality_criteria_agreed=False) == 3
        assert readiness(correct_examples=5, quality_criteria_agreed=True) == 4

    def test_the_score_is_the_lower_of_the_two_halves(self):
        """The repair ADR-027 made, preserved: perfect data with no way to judge
        an output is not a 4."""
        assert readiness(systems=["ServiceNow"], correct_examples=0,
                         quality_criteria_agreed=False) == 1

    def test_the_evidence_string_names_both_halves(self):
        """So a reader can see which half set the level."""
        intake = RequestIntake(
            request_text=REQUEST,
            data_evidence=DataEvidence(
                systems=["ServiceNow"],
                sample_checked=SampleCheck.NOT_LOOKED,
                correct_examples=0,
                quality_criteria_agreed=False,
            ),
        )
        why = derive_scores(RUBRIC, intake)["data_readiness"][1]
        assert "AVAILABILITY" in why and "EVALUABILITY" in why


# ---------------------------------------------------------------------------
# implementation_effort
# ---------------------------------------------------------------------------


class TestImplementationEffortRules:
    def test_r5_the_count_of_integrations_sets_a_level(self):
        assert effort(systems_to_integrate=["ServiceNow"]) == 1
        assert effort(systems_to_integrate=["a", "b", "c"]) == 3
        assert effort(systems_to_integrate=["a", "b", "c", "d", "e", "f"]) == 5

    def test_r6_the_count_of_teams_that_can_block_sets_a_level(self):
        assert effort(approving_teams=["Service Desk"]) == 1
        assert effort(approving_teams=["a", "b", "c"]) == 3
        assert effort(approving_teams=["a", "b", "c", "d", "e", "f"]) == 5

    def test_r7_procurement_is_ordered_by_distance_from_the_team(self):
        """A licence on an existing contract is a form; a new vendor is a
        negotiation, which anchor 5 calls blocked outside the team's control."""
        assert effort(procurement=Procurement.NONE) == 1
        assert effort(procurement=Procurement.EXISTING_LICENCE) == 1
        assert effort(procurement=Procurement.NEW_LICENCE_EXISTING_VENDOR) == 3
        assert effort(procurement=Procurement.NEW_VENDOR) == 5

    def test_the_worst_signal_governs_rather_than_the_average(self):
        """The anchors are disjunctive, so a maximum agrees with them. One
        integration and one team do not make a vendor negotiation cheap."""
        assert effort(
            systems_to_integrate=["ServiceNow"],
            approving_teams=["Service Desk"],
            procurement=Procurement.NEW_VENDOR,
        ) == 5


# ---------------------------------------------------------------------------
# adoption_risk — the one most likely to smuggle a judgement through
# ---------------------------------------------------------------------------


class TestAdoptionRiskRules:
    def test_r1_a_consultation_claim_without_a_quote_is_demoted(self):
        """R1, and the load-bearing rule of the whole phase.

        Without this, `users_consulted` is a question about how collaborative
        the requester feels they were, which is exactly the judgement the
        conversion is supposed to remove. The quote makes it checkable.
        """
        assert adoption(users_consulted=UserConsultation.CONSULTED,
                        user_quote="it sits in the wrong queue") == 2
        assert adoption(users_consulted=UserConsultation.CONSULTED,
                        user_quote=None) == 4
        assert adoption(users_consulted=UserConsultation.REQUESTED_IT,
                        user_quote="   ") == 4

    def test_r1_the_demotion_is_named_in_the_evidence(self):
        """A silent demotion would be worse than no demotion."""
        intake = RequestIntake(
            request_text=REQUEST,
            prior_tool_for_these_users=PriorTool.ADOPTED,
            adoption_evidence=AdoptionEvidence(
                users_consulted=UserConsultation.CONSULTED,
                user_quote=None,
                workflow_fit=WorkflowFit.EXISTING_STEP,
                people_who_must_change=4,
            ),
        )
        why = derive_scores(RUBRIC, intake)["adoption_risk"][1]
        assert "demoted" in why and "no quote" in why

    def test_r8_workflow_fit_grades_where_the_output_lands(self):
        assert adoption(workflow_fit=WorkflowFit.EXISTING_STEP) == 1
        assert adoption(workflow_fit=WorkflowFit.EXISTING_STEP_MODIFIED) == 2
        assert adoption(workflow_fit=WorkflowFit.NEW_STEP) == 3
        assert adoption(workflow_fit=WorkflowFit.REPLACES_CHOSEN_WAY) == 5

    def test_r9_a_change_reaching_hundreds_cannot_score_better_than_three(self):
        """R9, and the one band not taken from the anchors' own wording.

        It does not invent a scale: it refuses to let a very large change score
        better than anchor 3, which already says adoption then 'depends on a
        manager asking people to use it'.
        """
        assert adoption(people_who_must_change=4) == 1
        assert adoption(people_who_must_change=60) == 2
        assert adoption(people_who_must_change=900) == 3

    def test_an_abandoned_previous_tool_is_anchor_four_on_its_own(self):
        """However well the rest of it reads. This is the fact the schema has
        always called the single most informative one about adoption."""
        assert adoption(prior=PriorTool.ABANDONED) == 4

    def test_an_unknown_previous_tool_contributes_nothing(self):
        """The absence of a fact is not evidence that adoption will go badly."""
        assert adoption(prior=PriorTool.UNKNOWN) == adoption(prior=PriorTool.ADOPTED)

    def test_no_previous_tool_is_neither_reassurance_nor_alarm(self):
        assert adoption(prior=PriorTool.NONE) == 2


# ---------------------------------------------------------------------------
# What the conversion must not break
# ---------------------------------------------------------------------------


class TestTheMeasuredCorpusIsUntouched:
    """§4: a change that alters a published number is a defect in this phase."""

    @pytest.mark.parametrize(
        "dimension", ["data_readiness", "implementation_effort", "adoption_risk"]
    )
    def test_an_intake_without_the_new_evidence_derives_nothing(self, dimension):
        """Every corpus intake is one of these. The dimension returns to model
        scoring exactly as it did under v2.0.0."""
        intake = RequestIntake(request_text=REQUEST)
        assert dimension not in derive_scores(RUBRIC, intake)

    def test_the_reference_still_has_the_published_shape(self):
        """174 agreed slots, 25 excluded, 11 both-null, 28 verdicts — the numbers
        every figure in evaluacion/ is computed from."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from measure_against_reference import build_reference, parse_corpus

        reference = build_reference(parse_corpus())
        assert len(reference.slots) == 174
        assert len(reference.excluded) == 25
        assert len(reference.both_null) == 11
        assert len(reference.verdicts) == 28

    def test_the_rubric_records_the_version_this_shipped_under(self):
        assert RUBRIC.version == "3.1.0"


class TestGoIsNowReachable:
    """The point of the phase: an interview can end in an approval."""

    def full_intake(self, **overrides) -> RequestIntake:
        base = dict(
            request_text=REQUEST,
            business_owner="Ana Ruiz",
            times_per_period=4000,
            period=Period.MONTH,
            minutes_per_instance=4.0,
            data_sensitivity=DataSensitivity.INTERNAL,
            prior_tool_for_these_users=PriorTool.ADOPTED,
            existing_deterministic_artefacts=[
                DeterministicArtefact(
                    name="Keyword routing rules",
                    what_it_does="route about half the tickets; an analyst picks the rest",
                    completes_without_judgement=False,
                )
            ],
            data_evidence=DataEvidence(
                systems=["ServiceNow"],
                sample_checked=SampleCheck.LOOKED_USABLE,
                correct_examples=200_000,
                quality_criteria_agreed=True,
            ),
            effort_evidence=EffortEvidence(
                systems_to_integrate=["ServiceNow"],
                procurement=Procurement.EXISTING_LICENCE,
                approving_teams=["IT Service Desk"],
            ),
            adoption_evidence=AdoptionEvidence(
                users_consulted=UserConsultation.REQUESTED_IT,
                user_quote="it sits in the wrong queue until someone notices",
                workflow_fit=WorkflowFit.EXISTING_STEP,
                people_who_must_change=4,
            ),
        )
        return RequestIntake(**{**base, **overrides})

    def test_a_fully_answered_intake_reaches_go_with_no_dimension_unknown(self):
        outcome = score_and_gate(self.full_intake())
        assert outcome.verdict is Verdict.GO
        assert outcome.unknown_dimensions == []
        assert outcome.unknown_weight == 0.0

    def test_every_score_in_that_go_came_from_a_derivation(self):
        """Acceptance 2, restated at the level that matters: the approval itself
        contains no model-produced number."""
        outcome = score_and_gate(self.full_intake())
        scored = {d for d, s in outcome.resolved_scores.items() if s is not None}
        assert scored == set(
            outcome.derived_dimensions + outcome.fallback_derived_dimensions
        )
        assert len(scored) == 7

    def test_the_conversion_can_say_no_where_a_gate_exists(self):
        """It must be able to refuse, or it is decoration. Effort at 5 costs
        enough weight to drop the total below the 3.50 approval band."""
        intake = self.full_intake(
            effort_evidence=EffortEvidence(
                systems_to_integrate=["a", "b", "c", "d", "e", "f"],
                procurement=Procurement.NEW_VENDOR,
                approving_teams=["a", "b", "c", "d", "e", "f"],
            ),
            data_evidence=DataEvidence(
                systems=["a", "b", "c"],
                sample_checked=SampleCheck.NOT_LOOKED,
                correct_examples=0,
                quality_criteria_agreed=False,
            ),
        )
        assert score_and_gate(intake).verdict is not Verdict.GO

    def test_the_worst_possible_adoption_profile_is_gated(self):
        """Flipped in v3.1.0. It used to assert the opposite, and said so.

        Nobody consulted, replacing a way of working the users chose themselves,
        900 people to change. `adoption_risk` derives to its maximum of 5 and
        used to be **approved at 3.68**, because at weight 0.17 the other six
        dimensions outvoted it and the dimension had no gate. Phase 11 pinned
        that as a finding and left the decision to the owner; Phase 12 took it.

        Nothing about the arithmetic changed — the weighted total is still 3.68
        and would still band as `go`. The gate overrides it, which is the whole
        argument for gates: a weight small enough to be fair to an ordinary
        request is too small to stop an extreme one.
        """
        intake = self.full_intake(
            adoption_evidence=AdoptionEvidence(
                users_consulted=UserConsultation.NOBODY,
                user_quote=None,
                workflow_fit=WorkflowFit.REPLACES_CHOSEN_WAY,
                people_who_must_change=900,
            )
        )
        outcome = score_and_gate(intake)
        assert outcome.resolved_scores["adoption_risk"] == 5
        assert outcome.verdict is Verdict.NO_GO
        gate = next(
            g for g in outcome.triggered_gates
            if g.gate_id == "unacceptable_adoption_risk"
        )
        assert gate.verdict is Verdict.NO_GO
        # The band would still have said `go`. The gate is what overrides it.
        assert outcome.weighted_total == 3.68
        # A refusal resting on the requester's own reading of workflow_fit is a
        # recommendation for a human to confirm, not a decision (ADR-020, -028).
        assert outcome.requires_human_confirmation


    def test_data_in_nobodys_system_fires_the_no_usable_data_gate(self):
        """Availability 1 propagates through `min` and the gate does fire —
        ADR-027 predicted this would happen more often, and called it the repair
        working rather than a regression."""
        intake = self.full_intake(
            data_evidence=DataEvidence(
                systems=[],
                sample_checked=SampleCheck.NOT_LOOKED,
                correct_examples=0,
                quality_criteria_agreed=False,
            )
        )
        outcome = score_and_gate(intake)
        assert "no_usable_data" in [g.gate_id for g in outcome.triggered_gates]


class TestTheAdoptionGateFiresOnlyOnTheConjunction:
    """It must not fire on the weak signal alone.

    `users_consulted: nobody` derives `adoption_risk = 5` by itself, so a
    `dimension_threshold` gate at 5 would refuse every requester who declined to
    name someone they had spoken to — true of most requests at the start of an
    interview. Gating on that would end conversations at turn one, which is the
    premature-gate mistake Phase 10 found and fixed.
    """

    def intake(self, consulted, fit, people) -> RequestIntake:
        return RequestIntake(
            request_text=REQUEST,
            business_owner="Ana Ruiz",
            times_per_period=4000,
            period=Period.MONTH,
            data_sensitivity=DataSensitivity.INTERNAL,
            existing_deterministic_artefacts=[],
            adoption_evidence=AdoptionEvidence(
                users_consulted=consulted,
                user_quote=None,
                workflow_fit=fit,
                people_who_must_change=people,
            ),
        )

    def fired(self, consulted, fit, people) -> bool:
        outcome = score_and_gate(self.intake(consulted, fit, people))
        return any(
            g.gate_id == "unacceptable_adoption_risk" for g in outcome.triggered_gates
        )

    def test_all_three_facts_together_fire_it(self):
        assert self.fired(
            UserConsultation.NOBODY, WorkflowFit.REPLACES_CHOSEN_WAY, 900
        )

    def test_nobody_consulted_alone_does_not(self):
        """The signal that would have ended every interview at turn one."""
        assert not self.fired(UserConsultation.NOBODY, WorkflowFit.EXISTING_STEP, 4)

    def test_no_scale_does_not(self):
        assert not self.fired(
            UserConsultation.NOBODY, WorkflowFit.REPLACES_CHOSEN_WAY, 4
        )

    def test_not_displacing_a_chosen_practice_does_not(self):
        """A new step is anchor 3's territory, not a prohibition."""
        assert not self.fired(UserConsultation.NOBODY, WorkflowFit.NEW_STEP, 900)

    def test_having_actually_asked_the_users_does_not(self):
        assert not self.fired(
            UserConsultation.CONSULTED, WorkflowFit.REPLACES_CHOSEN_WAY, 900
        )

    def test_the_headcount_boundary_is_the_one_the_rubric_already_declares(self):
        """`adoption_risk`'s own band reads `<=20 -> 1`: below 21 the rubric
        treats the number as immaterial. The gate reuses that rather than
        inventing a second threshold for the same quantity."""
        assert not self.fired(
            UserConsultation.TOLD_NOT_ASKED, WorkflowFit.REPLACES_CHOSEN_WAY, 20
        )
        assert self.fired(
            UserConsultation.TOLD_NOT_ASKED, WorkflowFit.REPLACES_CHOSEN_WAY, 21
        )

    def test_it_cannot_fire_when_nobody_was_asked_about_adoption_at_all(self):
        """A gate never fires on silence — the rule every other gate follows.

        This is also why no exemplar's verdict changed: they predate the field.
        """
        bare = RequestIntake(request_text=REQUEST, business_owner="Ana Ruiz")
        assert not any(
            g.gate_id == "unacceptable_adoption_risk"
            for g in score_and_gate(bare).triggered_gates
        )

class TestTheQuoteIsVerified:
    """R1 has to bite here or it does not bite at all."""

    def test_a_user_quote_the_requester_did_not_say_is_dropped(self):
        """Held to the same standard as a fabricated anti-pattern quote. The
        consequence is a demotion, not a rejection: the claim survives at the
        level that means 'these people have been told'."""
        from agent_tools import record_field

        answer = "I asked Marta and she said it sits in the wrong queue."
        payload = {
            "users_consulted": "consulted",
            "user_quote": "the analysts are thrilled about this",
            "workflow_fit": "existing_step",
            "people_who_must_change": 4,
        }
        result = record_field(
            RequestIntake(request_text=REQUEST),
            "adoption_evidence",
            payload,
            "I asked Marta",
            1,
            "Who did you ask?",
            answer,
        )
        assert result.accepted
        assert result.intake.adoption_evidence.user_quote is None
        assert derive_scores(RUBRIC, result.intake)["adoption_risk"][0] == 4

    def test_a_quote_the_requester_did_say_is_kept(self):
        from agent_tools import record_field

        answer = "I asked Marta and she said it sits in the wrong queue."
        payload = {
            "users_consulted": "consulted",
            "user_quote": "it sits in the wrong queue",
            "workflow_fit": "existing_step",
            "people_who_must_change": 4,
        }
        result = record_field(
            RequestIntake(request_text=REQUEST),
            "adoption_evidence",
            payload,
            "I asked Marta",
            1,
            "Who did you ask?",
            answer,
        )
        assert result.intake.adoption_evidence.user_quote == "it sits in the wrong queue"
        assert derive_scores(RUBRIC, result.intake)["adoption_risk"][0] == 2
