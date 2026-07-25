"""Reference exemplars: realistic internal IT requests, scored against the anchors.

These are the worked cases for the project. Each file carries the intake as a
requester would actually write it, the verdict it should produce, the gate that
should fire (if any), and a hand-authored ``reference_assessment`` whose scores
each quote the anchor level they satisfy.

They serve three purposes: they are the offline test of the scoring engine
(``tests/test_examples.py``), the demo script (``scripts/run_examples.py`` and
the Streamlit app), and the reference exemplars that the synthetic arithmetic
fixture in ``tests/test_scoring.py`` must never be mistaken for.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from schemas import Assessment, DataSensitivity, Period, PriorTool, RequestIntake

__all__ = ["Example", "EXAMPLES_DIR", "load_examples", "load_example"]

EXAMPLES_DIR = Path(__file__).resolve().parent


class Example(BaseModel):
    """One reference exemplar."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    expected_verdict: str
    expected_gate: str | None = None
    requesting_area: str
    business_owner: str
    request_text: str
    process_description: str
    stated_benefit: str | None = None
    who_does_this_today: str = ""
    people_affected: int | None = None
    times_per_period: int | None = None
    period: Period | None = None
    prior_tool_for_these_users: PriorTool = PriorTool.UNKNOWN
    where_the_data_lives: str | None = None
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    reference_assessment: Assessment

    @property
    def intake(self) -> RequestIntake:
        """The example rendered as a request intake."""
        return RequestIntake(
            request_text=self.request_text.strip(),
            requesting_area=self.requesting_area,
            business_owner=self.business_owner,
            process_description=self.process_description.strip(),
            stated_benefit=(self.stated_benefit or "").strip() or None,
            who_does_this_today=self.who_does_this_today,
            people_affected=self.people_affected,
            times_per_period=self.times_per_period,
            period=self.period,
            prior_tool_for_these_users=self.prior_tool_for_these_users,
            where_the_data_lives=self.where_the_data_lives,
            data_sensitivity=self.data_sensitivity,
        )


def load_examples() -> list[Example]:
    """Load every example, ordered by filename."""
    return [
        Example.model_validate(yaml.safe_load(path.read_text()))
        for path in sorted(EXAMPLES_DIR.glob("*.yaml"))
    ]


def load_example(example_id: str) -> Example:
    """Load one example by its id.

    Raises:
        KeyError: If no example has that id.
    """
    for example in load_examples():
        if example.id == example_id:
            return example
    raise KeyError(f"no example with id {example_id!r}")
