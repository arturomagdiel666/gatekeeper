"""Gatekeeper demo UI — triage on one tab, review simulation on the other.

Run with:  streamlit run app.py

Two tabs, because the product's claim spans both. Tab 1 shows the intake gate:
a request in, a verdict out, with the arithmetic and the evidence visible. Tab 2
is the differentiating half — an approved agent, its Measurement Contract, and a
deterministic recommendation about whether to keep it running.

Design constraints, deliberate:

* no network calls except to the configured provider;
* readable when projected — large type, nothing dense except the one dimension
  table that has to be dense;
* if the provider is unreachable, say so plainly instead of showing a stack
  trace. Everything except the assessment call works with no model at all.
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from dotenv import load_dotenv

from assess import AssessmentError, assess_request
from config import PATTERNS, RUBRIC
from contracts import CONTRACTS, issue_contract
from examples import load_examples
from provider import get_provider
from review import POLICY, ObservedMetrics, Recommendation, review
from schemas import MeasurementContract, RequestIntake
from scoring import Verdict, score

load_dotenv()

st.set_page_config(page_title="Gatekeeper", page_icon="🚪", layout="wide")

VERDICT_STYLE: dict[str, tuple[str, str]] = {
    "go": ("#1a7f37", "GO"),
    "no_go": ("#b42318", "NO-GO"),
    "not_ai": ("#8250df", "NOT AI"),
    "incomplete": ("#9a6700", "INCOMPLETE"),
}

RECOMMENDATION_STYLE: dict[str, tuple[str, str]] = {
    "continue": ("#1a7f37", "CONTINUE"),
    "adjust": ("#9a6700", "ADJUST"),
    "retire": ("#b42318", "RETIRE"),
    "insufficient_telemetry": ("#57606a", "INSUFFICIENT TELEMETRY"),
}


def banner(colour: str, label: str, subtitle: str) -> None:
    """Render the headline verdict, large and unmissable."""
    st.markdown(
        f"""
        <div style="background:{colour};color:#fff;padding:1.6rem 2rem;
                    border-radius:12px;margin:0.5rem 0 1.2rem 0;">
          <div style="font-size:3.2rem;font-weight:800;line-height:1;">{label}</div>
          <div style="font-size:1.15rem;opacity:0.94;margin-top:0.6rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab 1 — Triage
# ---------------------------------------------------------------------------


def render_dimension_table(outcome) -> None:
    """The per-dimension breakdown: how the number was actually built."""
    if not outcome.contributions:
        st.info(
            "No weighted total was computed, so there is no breakdown to show. "
            "See the missing dimensions above."
        )
        return
    rows = []
    for item in outcome.contributions:
        dimension = RUBRIC.dimension_by_id(item.dimension_id)
        rows.append(
            {
                "Dimension": item.label,
                "Raw": item.raw_score,
                "Direction": "higher=better"
                if dimension and dimension.direction == "higher_is_better"
                else "lower=better",
                "Normalized": item.normalized_score,
                "Weight": f"{item.effective_weight:.3f}",
                "Contribution": f"{item.contribution:.3f}",
                "Confidence": item.confidence,
                "Evidence": item.evidence,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_outcome(outcome, contract: MeasurementContract | None) -> None:
    """Render a scored outcome: verdict, gates, arithmetic, contract."""
    colour, label = VERDICT_STYLE[outcome.verdict.value]
    if outcome.weighted_total is not None:
        subtitle = (
            f"Weighted total {outcome.weighted_total:.2f} of 5.00 · "
            f"approval threshold 3.50"
        )
    else:
        subtitle = "No weighted total — see below"
    banner(colour, label, subtitle)

    if outcome.triggered_gates:
        st.subheader("Blocking gates")
        st.caption(
            "Gates are evaluated before the bands and override them. The first "
            "one listed decided the verdict."
        )
        for gate in outcome.triggered_gates:
            with st.container(border=True):
                st.markdown(
                    f"**{gate.gate_id}** → `{gate.verdict.value}` "
                    f"(precedence {gate.precedence})"
                )
                st.markdown(f"*What fired it:* {gate.detail}")
                st.markdown(gate.reason)
                for anti_pattern_id in gate.matched_anti_pattern_ids:
                    anti_pattern = PATTERNS.anti_pattern_by_id(anti_pattern_id)
                    if anti_pattern:
                        st.markdown(f"**Instead:** {anti_pattern.better_alternative}")

    if outcome.unknown_dimensions:
        st.warning(
            "The request did not establish: "
            + ", ".join(f"`{d}`" for d in outcome.unknown_dimensions)
            + f". The limit is {RUBRIC.completeness.max_unknown_dimensions}. "
            "These are recorded as unknown rather than guessed — answer them "
            "and resubmit."
        )

    if outcome.weighted_total is not None:
        st.progress(
            min(1.0, max(0.0, (outcome.weighted_total - 1.0) / 4.0)),
            text=(
                f"{outcome.weighted_total:.2f} / 5.00 — "
                + ("at or above" if outcome.weighted_total >= 3.5 else "below")
                + " the 3.50 approval threshold"
            ),
        )

    st.subheader("How the score was built")
    render_dimension_table(outcome)

    if outcome.ignored_dimension_ids or outcome.ignored_anti_pattern_ids:
        st.caption(
            "Ignored ids the model produced that are not in the config: "
            f"{outcome.ignored_dimension_ids + outcome.ignored_anti_pattern_ids}"
        )

    if contract is not None:
        st.subheader("Measurement Contract")
        st.caption(
            "An agent may only be approved together with the definition of its "
            "own failure. This is what the review on the date below is against."
        )
        with st.container(border=True):
            left, right = st.columns(2)
            with left:
                st.metric("Primary metric", contract.primary_metric_label)
                st.markdown(f"**Unit:** `{contract.primary_metric_unit}`")
                st.markdown(f"**Success threshold:** {contract.success_threshold:g}")
                st.markdown(
                    "**Baseline:** "
                    + (
                        f"{contract.baseline_value:g} (measured)"
                        if contract.baseline_is_measured
                        else "not measured — this is a finding, not a formality"
                    )
                )
            with right:
                st.metric("Review date", str(contract.review_date))
                st.markdown(f"**Business owner:** {contract.business_owner}")
                st.markdown(f"**Approved:** {contract.approval_date}")
                st.markdown(f"**Archetype:** `{contract.archetype_id}`")
            st.markdown(f"**How it is measured:** {contract.measurement_method}")
            with st.expander("Instrumentation plan — all four layers"):
                plan = contract.instrumentation_plan
                for layer, items in (
                    ("Usage", plan.usage),
                    ("Quality", plan.quality),
                    ("Business", plan.business),
                    ("Cost", plan.cost),
                ):
                    st.markdown(f"**{layer}**")
                    for item in items:
                        st.markdown(f"- {item}")
            with st.expander("Decommission triggers this agent is subject to"):
                for trigger_id in contract.decommission_trigger_ids:
                    trigger = next(
                        (t for t in CONTRACTS.decommission_triggers if t.id == trigger_id),
                        None,
                    )
                    if trigger:
                        manual = " *(reviewer must assert)*" if trigger.manual_assertion else ""
                        st.markdown(f"- **{trigger.label}**{manual} — {trigger.description}")

    with st.expander("Full explanation (plain text)"):
        st.code(outcome.explanation, language=None)


def triage_tab() -> None:
    st.header("Triage a request")
    st.caption(
        "One constrained-generation call scores the request against the rubric. "
        "The model never decides and never adds up — Python applies the weights, "
        "the gates and the bands."
    )

    examples = load_examples()
    labels = ["(blank form)"] + [f"{e.title}" for e in examples]
    chosen = st.selectbox("Load a reference example", labels)
    preset = examples[labels.index(chosen) - 1] if chosen != labels[0] else None

    with st.form("intake"):
        col_a, col_b = st.columns(2)
        with col_a:
            requesting_area = st.text_input(
                "Requesting area", value=preset.requesting_area if preset else ""
            )
        with col_b:
            business_owner = st.text_input(
                "Business owner",
                value=preset.business_owner if preset else "",
                help="Leave empty to see the no_named_business_owner gate fire.",
            )
        request_text = st.text_area(
            "The request, in the requester's words",
            value=preset.request_text.strip() if preset else "",
            height=200,
        )
        process_description = st.text_area(
            "How the work is done today",
            value=preset.process_description.strip() if preset else "",
            height=120,
        )
        stated_benefit = st.text_area(
            "Benefit claimed by the requester",
            value=(preset.stated_benefit or "").strip() if preset else "",
            height=70,
        )
        use_reference = st.checkbox(
            "Score the example's hand-authored assessment instead of calling the model",
            value=False,
            help=(
                "Offline path: exercises the scoring engine with no provider. "
                "Only available when an example is loaded."
            ),
            disabled=preset is None,
        )
        submitted = st.form_submit_button("Assess", type="primary")

    if not submitted:
        return
    if not request_text.strip():
        st.error("The request text is empty — there is nothing to assess.")
        return

    intake = RequestIntake(
        request_text=request_text.strip(),
        requesting_area=requesting_area.strip(),
        business_owner=business_owner.strip(),
        process_description=process_description.strip(),
        stated_benefit=stated_benefit.strip() or None,
    )

    if use_reference and preset is not None:
        assessment = preset.reference_assessment
        outcome = score(assessment, RUBRIC, PATTERNS, intake)
        result_contract = issue_contract(
            outcome, assessment, intake, date.today()
        ).contract
        st.info(
            "Scored from the example's hand-authored assessment. No model was "
            "called — this is the offline engine path."
        )
        render_outcome(outcome, result_contract)
        return

    try:
        provider = get_provider()
    except Exception as exc:
        st.error(
            f"Could not create the provider: {exc}\n\n"
            "Check LLM_PROVIDER in your .env, or tick the offline checkbox above."
        )
        return

    with st.spinner(f"Assessing with {type(provider).__name__}…"):
        try:
            result = assess_request(intake, provider, approval_date=date.today())
        except AssessmentError as exc:
            st.error(
                "The model did not return a valid assessment, even after a "
                f"corrective retry.\n\n{exc}"
            )
            return
        except Exception as exc:
            st.error(
                f"The provider is unreachable or failed: {type(exc).__name__}: {exc}\n\n"
                "This is a connection or configuration problem, not a verdict. "
                "Start Ollama, or tick the offline checkbox above to exercise "
                "the scoring engine without a model."
            )
            return

    if result.retry_count:
        st.caption(f"Needed {result.retry_count} corrective retry to match the schema.")
    if result.ignored_metric_ids:
        st.caption(
            "The model proposed a metric that is not a candidate for this "
            f"archetype: {result.ignored_metric_ids}. The archetype default was used."
        )
    render_outcome(result.outcome, result.contract)


# ---------------------------------------------------------------------------
# Tab 2 — Review simulator
# ---------------------------------------------------------------------------

HEALTHY_AGENT = {
    "label": "Healthy agent — adopted, working, cheap",
    "contract": MeasurementContract(
        primary_metric_id="hours_reclaimed_per_month",
        primary_metric_label="Hours reclaimed per month",
        primary_metric_unit="hours_per_month",
        primary_metric_direction="higher_is_better",
        measurement_method="Sampled time study against platform usage volume.",
        baseline_value=None,
        baseline_is_measured=False,
        success_threshold=40.0,
        review_date=date(2026, 6, 30),
        business_owner="Ana Ruiz",
        decommission_trigger_ids=CONTRACTS.trigger_ids,
        archetype_id="summarization",
        approval_date=date(2026, 3, 31),
    ),
    "observed": ObservedMetrics(
        months_since_launch=6,
        window_months=1.0,
        active_users=60,
        addressable_population=100,
        sessions=800,
        task_starts=500,
        repeat_users=45,
        time_to_first_value_days=1.0,
        task_completion_rate=0.90,
        override_rate=0.10,
        escalation_rate=0.05,
        mid_task_abandonment_rate=0.05,
        primary_metric_value=60.0,
        inference_cost=200.0,
        licence_cost=300.0,
        maintenance_hours=5.0,
        maintenance_hourly_rate=100.0,
        owner_absent=False,
        superseded_by_platform=False,
    ),
}

FAILING_AGENT = {
    "label": "Failing agent — looks adopted, is not working",
    "contract": HEALTHY_AGENT["contract"].model_copy(
        update={"business_owner": "Marcos Pena"}
    ),
    "observed": HEALTHY_AGENT["observed"].model_copy(
        update={
            "active_users": 55,
            "repeat_users": 8,
            "task_completion_rate": 0.55,
            "override_rate": 0.48,
            "primary_metric_value": 12.0,
            "inference_cost": 1800.0,
        }
    ),
}

SCENARIOS = {"Healthy agent": HEALTHY_AGENT, "Failing agent": FAILING_AGENT}


def review_tab() -> None:
    st.header("Review an approved agent")
    st.caption(
        "The other half of the claim: an approved agent is reviewed against the "
        "contract it was approved under. No model is involved anywhere in this "
        "tab — the retirement recommendation must be reproducible by anyone who "
        "disagrees with it."
    )

    scenario_name = st.selectbox("Pre-loaded scenario", list(SCENARIOS))
    scenario = SCENARIOS[scenario_name]
    contract: MeasurementContract = scenario["contract"]
    preset: ObservedMetrics = scenario["observed"]

    with st.container(border=True):
        st.markdown("**Contract under review**")
        cols = st.columns(4)
        cols[0].metric("Primary metric", contract.primary_metric_label)
        cols[1].metric("Threshold", f"{contract.success_threshold:g}")
        cols[2].metric("Review date", str(contract.review_date))
        cols[3].metric("Owner", contract.business_owner)

    with st.form("observed"):
        st.markdown("### Observed metrics — all four instrumentation layers")
        st.caption(
            "Leave a field at its 'not reported' value to see how missing "
            "telemetry is handled. It is never read as success."
        )
        usage, quality = st.columns(2)
        with usage:
            st.markdown("**Usage**")
            months_since_launch = st.number_input(
                "Months since launch", 0, 60, preset.months_since_launch or 0
            )
            active_users = st.number_input("Active users", 0, 100000, preset.active_users or 0)
            addressable_population = st.number_input(
                "Addressable population", 1, 100000, preset.addressable_population or 1
            )
            task_starts = st.number_input("Task starts", 0, 1000000, preset.task_starts or 0)
            repeat_users = st.number_input("Repeat users", 0, 100000, preset.repeat_users or 0)
        with quality:
            st.markdown("**Quality**")
            task_completion_rate = st.slider(
                "Task completion rate", 0.0, 1.0, preset.task_completion_rate or 0.0, 0.01
            )
            override_rate = st.slider(
                "Human override / correction rate", 0.0, 1.0, preset.override_rate or 0.0, 0.01
            )
            escalation_rate = st.slider(
                "Escalation rate", 0.0, 1.0, preset.escalation_rate or 0.0, 0.01
            )
            remediation_in_flight = st.checkbox("A quality fix is already in flight", False)

        business, cost = st.columns(2)
        with business:
            st.markdown("**Business**")
            primary_metric_value = st.number_input(
                f"{contract.primary_metric_label} (current)",
                0.0,
                1e6,
                float(preset.primary_metric_value or 0.0),
            )
            window_months = st.number_input("Measurement window (months)", 1.0, 24.0, 1.0)
        with cost:
            st.markdown("**Cost** (over the window)")
            inference_cost = st.number_input(
                "Inference spend", 0.0, 1e6, float(preset.inference_cost or 0.0)
            )
            licence_cost = st.number_input(
                "Licence / platform cost", 0.0, 1e6, float(preset.licence_cost or 0.0)
            )
            maintenance_hours = st.number_input(
                "Maintenance hours", 0.0, 1000.0, float(preset.maintenance_hours or 0.0)
            )
            maintenance_hourly_rate = st.number_input(
                "Hourly rate", 0.0, 1000.0, float(preset.maintenance_hourly_rate or 0.0)
            )

        st.markdown("**Reviewer assertions** — these cannot be computed, so they must be answered")
        assertions = st.columns(2)
        owner_answer = assertions[0].radio(
            "Is the named business owner still in place and sponsoring it?",
            ["Yes", "No", "Not answered"],
            index=0 if not preset.owner_absent else 1,
        )
        platform_answer = assertions[1].radio(
            "Does a licensed platform capability now cover this natively?",
            ["No", "Yes", "Not answered"],
            index=0,
        )
        run = st.form_submit_button("Run review", type="primary")

    if not run:
        return

    observed = ObservedMetrics(
        months_since_launch=months_since_launch,
        window_months=window_months,
        active_users=active_users,
        addressable_population=addressable_population,
        task_starts=task_starts,
        repeat_users=repeat_users,
        task_completion_rate=task_completion_rate,
        override_rate=override_rate,
        escalation_rate=escalation_rate,
        primary_metric_value=primary_metric_value,
        inference_cost=inference_cost,
        licence_cost=licence_cost,
        maintenance_hours=maintenance_hours,
        maintenance_hourly_rate=maintenance_hourly_rate,
        remediation_in_flight=remediation_in_flight,
        owner_absent={"Yes": False, "No": True, "Not answered": None}[owner_answer],
        superseded_by_platform={"No": False, "Yes": True, "Not answered": None}[
            platform_answer
        ],
    )

    outcome = review(contract, observed, POLICY)
    colour, label = RECOMMENDATION_STYLE[outcome.recommendation.value]
    subtitle = (
        f"Next review {outcome.next_review_date}"
        if outcome.next_review_date
        else "No next review — decommission recommended"
    )
    banner(colour, label, subtitle)

    st.subheader("Computed indicators")
    indicators = outcome.indicators
    cols = st.columns(4)
    cols[0].metric(
        "Adoption rate",
        f"{indicators.adoption_rate:.0%}" if indicators.adoption_rate is not None else "—",
    )
    cols[1].metric(
        "Repeat-usage ratio",
        f"{indicators.repeat_usage_ratio:.0%}"
        if indicators.repeat_usage_ratio is not None
        else "—",
    )
    cols[2].metric(
        "Cost / successful task",
        f"{indicators.cost_per_successful_task:.2f}"
        if indicators.cost_per_successful_task is not None
        else "—",
    )
    cols[3].metric(
        "Value / task",
        f"{indicators.value_per_task:.2f}" if indicators.value_per_task is not None else "—",
    )

    if outcome.triggered_conditions:
        st.subheader("Conditions that fired")
        for condition in outcome.triggered_conditions:
            with st.container(border=True):
                st.markdown(
                    f"**{condition.trigger_id}** → `{condition.recommendation}`"
                )
                st.markdown(f"*Observed:* {condition.observed}")
                st.markdown(condition.detail)
    else:
        st.success("No decommission condition fired.")

    if outcome.unevaluated_conditions:
        st.subheader("Could not be evaluated")
        st.caption(
            "Missing telemetry is a finding in itself. It never reads as success, "
            "and it outranks an 'adjust' recommendation."
        )
        for condition in outcome.unevaluated_conditions:
            st.markdown(f"- **{condition.trigger_id}** — needs `{condition.missing}`")

    with st.expander("Full rationale (plain text)"):
        st.code(outcome.rationale, language=None)


# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🚪 Gatekeeper")
    st.markdown(
        "**The intake gate of a lifecycle governance model for an internal IT "
        "AI Agent Hub.** Requests are triaged against a rubric; approvals issue "
        "a Measurement Contract; agents are reviewed against that contract and "
        "retired when it is not met."
    )
    with st.sidebar:
        st.header("Configuration")
        st.markdown(f"Rubric `v{RUBRIC.version}` — {len(RUBRIC.dimensions)} dimensions")
        st.markdown(f"Gates: {len(RUBRIC.blocking_gates)}")
        st.markdown(f"Patterns `v{PATTERNS.version}` — {len(PATTERNS.archetypes)} archetypes")
        st.markdown(f"Review policy `v{POLICY.version}`")
        st.divider()
        st.caption(
            "Everything that decides anything lives in the YAML files. The model "
            "scores dimensions and cites evidence; it never computes a total and "
            "never picks a verdict."
        )

    triage, review_sim = st.tabs(["Triage", "Review simulator"])
    with triage:
        triage_tab()
    with review_sim:
        review_tab()


main()
