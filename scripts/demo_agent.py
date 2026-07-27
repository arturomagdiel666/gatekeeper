"""Run the intake agent end to end, offline or live.

Offline it uses `MockProvider` with a scripted transcript, so the demo survives a
dead Ollama and a CI box with no model at all. Live it uses whatever
`LLM_PROVIDER` selects.

The canonical case is `06_something_with_the_invoices` — the deliberately vague
one, and the case where an interview visibly does work a form cannot: submitted
as written it returns `incomplete` and stops.

Usage::

    python scripts/demo_agent.py                 # offline, scripted
    python scripts/demo_agent.py --live          # live model, scripted answers
    python scripts/demo_agent.py --live --human  # live model, you answer
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent import Interview, save_transcript  # noqa: E402
from provider import MockProvider, get_provider  # noqa: E402

REQUEST = (
    "We think there is something AI could do with our supplier invoices. The "
    "team spends a lot of time on them and it feels like the kind of thing that "
    "should be automated by now. Other companies are doing this.\n\n"
    "Can you have a look and tell us what is possible?"
)

#: What the requester says, keyed by the field the question was aimed at. Real
#: sentences with filler, because the extractor's job is to find the span inside
#: a human answer rather than to read a form.
SCRIPTED_ANSWERS: dict[str, str] = {
    "business_owner": (
        "That would be Rocio Delgado, she supervises Accounts Payable and she "
        "would own it."
    ),
    "existing_deterministic_artefacts": (
        "We have a monthly Excel report that pulls all invoices over 5000 euros "
        "for review, and a mailbox rule that files them by supplier. The Excel "
        "one gives us the list but somebody still has to check each line."
    ),
    "data_sensitivity": (
        "It is supplier invoices, so commercial terms and bank details. I would "
        "call that confidential, it is not regulated personal data."
    ),
    "times_per_period": (
        "Roughly 400 invoices a month come through, and each one is handled "
        "separately by somebody."
    ),
    "minutes_per_instance": "About 6 minutes each, more if there is a discrepancy.",
    "where_the_data_lives": "They arrive by email and end up in SAP.",
    "prior_tool_for_these_users": (
        "We rolled out a scanning tool two years ago and honestly nobody used "
        "it, it was abandoned within a few months."
    ),
    "who_does_this_today": "Four people in the AP team.",
    "process_description": "Invoices arrive by email and get processed by the AP team.",
    "requesting_area": "Finance.",
}

#: The model's side, scripted for the offline run. Order matters: one
#: `find_anti_patterns` result first, then decide/extract alternating.
OFFLINE_SCRIPT: list[dict] = [
    {"matches": []},
    {
        "tool": "ask",
        "target_field": "business_owner",
        "question": "Who would be accountable for this on your side?",
        "why": "decides a gate",
    },
    {"answered": True, "value": "Rocio Delgado", "span": "Rocio Delgado"},
    {
        "tool": "ask",
        "target_field": "existing_deterministic_artefacts",
        "question": "What do you already use today to handle these invoices, without any AI?",
        "why": "decides a gate",
    },
    {
        "answered": True,
        "value": (
            '[{"name": "Monthly Excel report", "what_it_does": "pulls all invoices '
            'over 5000 euros for review", "completes_without_judgement": false}, '
            '{"name": "Mailbox rule", "what_it_does": "files invoices by supplier", '
            '"completes_without_judgement": false}]'
        ),
        "span": "a monthly Excel report that pulls all invoices over 5000 euros",
    },
    {
        "tool": "ask",
        "target_field": "data_sensitivity",
        "question": "How would you classify the data on these invoices?",
        "why": "derives data_governance",
    },
    {"answered": True, "value": "confidential", "span": "I would call that confidential"},
    {
        "tool": "ask",
        "target_field": "times_per_period",
        "question": "How many invoices are handled one by one, and over what period?",
        "why": "derives process_frequency",
    },
    {
        "answered": True,
        "value": '{"times": 400, "period": "month"}',
        "span": "Roughly 400 invoices a month",
    },
    {
        "tool": "ask",
        "target_field": "minutes_per_instance",
        "question": "How long does one invoice take somebody today?",
        "why": "derives business_value",
    },
    {"answered": True, "value": "6", "span": "About 6 minutes each"},
    {
        "tool": "ask",
        "target_field": "where_the_data_lives",
        "question": "Which systems hold this data?",
        "why": "informs data_readiness",
    },
    {"answered": True, "value": "email and SAP", "span": "They arrive by email and end up in SAP"},
    {
        "tool": "ask",
        "target_field": "prior_tool_for_these_users",
        "question": "What happened to the last tool built for this team?",
        "why": "informs adoption_risk",
    },
    {"answered": True, "value": "abandoned", "span": "it was abandoned within a few months"},
    {
        "tool": "ask",
        "target_field": "who_does_this_today",
        "question": "Who does this work now?",
        "why": "context",
    },
    {"answered": True, "value": "Four people in the AP team", "span": "Four people in the AP team"},
]


#: A second requester, whose FIRST answer ends the conversation. Nobody is
#: accountable, `no_named_business_owner` fires, and the honest thing to do is
#: stop rather than spend seven more of their questions on a decided `no_go`.
#: This is the case a form handles worst: a blank box looks like an oversight,
#: while "we were going to work that out later" is an answer, and a decisive one.
GATE_REQUEST = (
    "We would like an AI agent that reads the medical certificates employees "
    "send to HR and pulls out the diagnosis and the dates, so we stop typing "
    "them in by hand."
)

GATE_ANSWERS: dict[str, str] = {
    "business_owner": (
        "Honestly nobody yet — we were going to work that out later, once we "
        "see whether it is feasible."
    ),
}

GATE_SCRIPT: list[dict] = [
    {"matches": []},
    {
        "tool": "ask",
        "target_field": "business_owner",
        "question": "Who in HR would be accountable for this agent once it runs?",
        "why": "decides a gate",
    },
    {"answered": False, "value": "", "span": ""},
]

#: The approval path, added in v3.0.0. `07_ticket_routing_classifier` — the
#: exemplar the rubric scores as a strong `go`. Before the conversion this could
#: not be reached at all: three dimensions had no intake field, carried 0.45 of
#: the weight between them, and left every interview `incomplete`.
GO_REQUEST = (
    "Every ticket that comes into the service desk gets assigned to one of "
    "fourteen resolver groups. Right now a first-line analyst reads each one and "
    "picks the group. When they pick wrong the ticket bounces - it sits in the "
    "wrong queue until someone notices, gets sent back, and starts again. About "
    "one in five tickets bounces at least once, and a bounced ticket takes "
    "roughly a day and a half longer to close than one that lands correctly the "
    "first time.\n\n"
    "We would like the description to be read automatically and the resolver "
    "group suggested, with the analyst able to override it. The keyword rules we "
    "set up years ago now cover maybe half of the tickets and they get worse "
    "every time a team is renamed or a new service is added."
)

GO_ANSWERS: dict[str, str] = {
    "business_owner": "Ana Ruiz, the Service Desk Manager, would own it.",
    "existing_deterministic_artefacts": (
        "We have the keyword routing rules. They route about half the tickets on "
        "their own, but an analyst still reads and picks the group for the rest, "
        "and they get worse every time a team is renamed."
    ),
    "data_sensitivity": (
        "Ticket descriptions, so internal. Nothing personal or regulated in them."
    ),
    "times_per_period": (
        "About 4,000 tickets a month, and each one is assigned separately."
    ),
    "minutes_per_instance": "Reading and assigning one takes about four minutes.",
    "stated_baseline_value": (
        "Today about 800 tickets a month bounce at least once, so that is the "
        "number we would want to bring down."
    ),
    "data_evidence": (
        "It is all in ServiceNow. We pulled a real sample last month and it was "
        "clean. Every assignment and reassignment since 2021 is in the ticket "
        "history, so for about two hundred thousand tickets we know which group "
        "actually closed it — that is the right answer. And we have written down "
        "and agreed what counts as a correct group."
    ),
    "effort_evidence": (
        "Only ServiceNow, we would read from it and write the suggestion back. "
        "Nothing to buy, the platform licence covers it. It is our own team's "
        "call, nobody else has to approve it."
    ),
    "adoption_evidence": (
        "The analysts asked for this themselves. Marta said it sits in the wrong "
        "queue until someone notices, which is the whole problem. The suggestion "
        "would appear on the same assignment screen they already use for every "
        "ticket. There are four analysts on the triage rota."
    ),
    "prior_tool_for_these_users": (
        "The last thing we built for this team was the keyword rules and they "
        "still use them every day, so that was adopted."
    ),
}

GO_SCRIPT: list[dict] = [
    {"matches": []},
    {"tool": "ask", "target_field": "business_owner",
     "question": "Who would be accountable for this?", "why": "decides a gate"},
    {"answered": True, "value": "Ana Ruiz", "span": "Ana Ruiz, the Service Desk Manager"},
    {"tool": "ask", "target_field": "existing_deterministic_artefacts",
     "question": "What already routes these tickets today, without AI?",
     "why": "decides a gate"},
    {"answered": True, "span": "an analyst still reads and picks the group for the rest",
     "value": [{"name": "Keyword routing rules",
                "what_it_does": "route about half the tickets; an analyst picks the group for the rest",
                "completes_without_judgement": False}]},
    {"tool": "ask", "target_field": "data_sensitivity",
     "question": "How is the ticket data classified?", "why": "derives data_governance"},
    {"answered": True, "value": "internal", "span": "Ticket descriptions, so internal"},
    {"tool": "ask", "target_field": "times_per_period",
     "question": "How many tickets get assigned, and over what period?",
     "why": "derives process_frequency"},
    {"answered": True, "value": {"times": 4000, "period": "month"},
     "span": "About 4,000 tickets a month"},

    {"tool": "ask", "target_field": "data_evidence",
     "question": "Where does this data live, has anyone checked it, and do you have examples of a correct answer?",
     "why": "derives data_readiness"},
    {"answered": True, "span": "It is all in ServiceNow",
     "value": {"systems": ["ServiceNow"], "sample_checked": "looked_usable",
               "correct_examples": 200000, "quality_criteria_agreed": True}},
    {"tool": "ask", "target_field": "effort_evidence",
     "question": "What would have to be connected, bought, or approved?",
     "why": "derives implementation_effort"},
    {"answered": True, "span": "Only ServiceNow",
     "value": {"systems_to_integrate": ["ServiceNow"], "procurement": "existing_licence",
               "approving_teams": ["IT Service Desk"]}},
    {"tool": "ask", "target_field": "adoption_evidence",
     "question": "Who did you ask about this, and what did they say?",
     "why": "derives adoption_risk"},
    {"answered": True, "span": "The analysts asked for this themselves",
     "value": {"users_consulted": "requested_it",
               "user_quote": "it sits in the wrong queue until someone notices",
               "workflow_fit": "existing_step", "people_who_must_change": 4}},
    {"tool": "ask", "target_field": "stated_baseline_value",
     "question": "What is that number today, before anything is built?",
     "why": "the contract needs a baseline"},
    {"answered": True, "value": 800, "span": "about 800 tickets a month bounce at least once"},
]

SCENARIOS = {
    "invoices": (REQUEST, SCRIPTED_ANSWERS, OFFLINE_SCRIPT),
    "gate": (GATE_REQUEST, GATE_ANSWERS, GATE_SCRIPT),
    "go": (GO_REQUEST, GO_ANSWERS, GO_SCRIPT),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use the real provider")
    parser.add_argument("--human", action="store_true", help="answer the questions yourself")
    parser.add_argument("--max-questions", type=int, default=9)
    parser.add_argument(
        "--scenario", choices=sorted(SCENARIOS), default="invoices",
        help="invoices: the vague canonical case. gate: a request a gate ends early.",
    )
    args = parser.parse_args()

    request, answers, script = SCENARIOS[args.scenario]
    provider = get_provider() if args.live else MockProvider(script)
    mode = "LIVE" if args.live else "OFFLINE (scripted mock)"
    print(f"=== Gatekeeper intake agent · {mode} ===\n")
    print(f"REQUEST:\n{request}\n")

    # Driven a turn at a time through `Interview` rather than through
    # `run_interview`, so the scripted requester can answer the question that
    # was actually aimed at them. The loop names the field before it asks, and
    # reading that is what a UI does too.
    interview = Interview(
        request, provider, max_questions=args.max_questions,
        approval_date=date(2026, 7, 27),
    )
    while (question := interview.next_question()) is not None:
        field = interview.pending_field or ""
        print(f"  Q{len(interview.transcript) + 1}: {question}")
        if args.human:
            reply = input("  A : ")
        else:
            reply = answers.get(field, "I am not sure about that one, sorry.")
            print(f"  A : {reply}")
        interview.submit(reply)
    result = interview.result()

    print(f"\n--- STOPPED: {result.stop_reason.value} ---")
    print(f"  {result.stop_detail}\n")
    print(f"VERDICT: {result.verdict.value.upper()}")
    if result.outcome.weighted_total is not None:
        print(f"  weighted total {result.outcome.weighted_total:.2f}")
    for gate in result.outcome.triggered_gates:
        print(f"  GATE {gate.gate_id} (precedence {gate.precedence}) → {gate.verdict.value}")
        print(f"       {gate.detail}")
    if result.outcome.completeness_violation and not result.outcome.triggered_gates:
        print(f"  incomplete because: {result.outcome.completeness_violation}")

    print("\nFIELDS FILLED, each with the words that filled it:")
    for p in result.provenance:
        print(f"  turn {p.turn}  {p.field} = {p.value}")
        print(f"           “{p.span}”")

    print("\nDIMENSIONS (none of these came from the model):")
    for dim, score in sorted(result.outcome.resolved_scores.items()):
        mark = "derived" if dim in result.outcome.derived_dimensions else ""
        mark = mark or ("fallback" if dim in result.outcome.fallback_derived_dimensions else "")
        print(f"  {dim:24} {str(score):>4}  {mark}")

    if result.contract:
        print("\nMEASUREMENT CONTRACT (draft)")
        for key in (
            "primary_metric_label", "measurement_method", "baseline_value",
            "success_threshold", "review_date", "business_owner",
            "decommission_trigger_ids", "instrumentation_plan",
        ):
            value = result.contract.get(key)
            shown = str(value)
            print(f"  {key:26} {shown[:78]}")
    path = save_transcript(result)
    print(f"\ntranscript → {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
