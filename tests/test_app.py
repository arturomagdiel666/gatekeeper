"""Headless end-to-end tests of the Streamlit UI.

Uses Streamlit's own AppTest harness, so these exercise the real script rather
than a stand-in: the app is imported, both tabs render, and both forms are
submitted. No model is called — the triage path is driven through the offline
checkbox, which scores an example's hand-authored assessment.
"""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")

from pathlib import Path  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def fresh_app() -> AppTest:
    """Run app.py headlessly and assert it did not blow up."""
    app = AppTest.from_file(str(APP_PATH), default_timeout=120)
    app.run()
    assert not app.exception, app.exception
    return app


class TestAppRenders:
    def test_the_script_runs_without_error(self):
        app = fresh_app()
        assert not app.exception

    def test_both_tabs_exist(self):
        app = fresh_app()
        assert len(app.tabs) == 2

    def test_the_title_and_sidebar_render(self):
        app = fresh_app()
        assert any("Gatekeeper" in str(item.value) for item in app.title)
        sidebar_text = " ".join(str(item.value) for item in app.sidebar.markdown)
        assert "dimensions" in sidebar_text
        assert "Review policy" in sidebar_text

    def test_every_example_is_offered_in_the_triage_dropdown(self):
        from examples import load_examples

        app = fresh_app()
        options = app.selectbox[0].options
        assert len(options) == len(load_examples()) + 1  # + the blank form

    def test_both_scenarios_are_offered_in_the_review_simulator(self):
        app = fresh_app()
        assert set(app.selectbox[1].options) == {"Healthy agent", "Failing agent"}


class TestTriageEndToEnd:
    """Acceptance criterion 10, triage half — driven through the offline path."""

    def test_loading_an_example_and_scoring_it_produces_a_verdict(self):
        app = fresh_app()
        app.selectbox[0].select("Shift handover summaries for the service desk").run()
        assert not app.exception

        # Tick the offline checkbox so no provider is needed, then submit.
        app.checkbox[0].check().run()
        app.button[0].click().run()
        assert not app.exception

        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "GO" in rendered
        assert "Measurement Contract" in " ".join(
            str(item.value) for item in app.subheader
        )

    def test_a_gated_example_shows_its_gate_and_no_contract(self):
        app = fresh_app()
        app.selectbox[0].select(
            "An assistant that answers HR policy questions in the chat client"
        ).run()
        app.checkbox[0].check().run()
        app.button[0].click().run()
        assert not app.exception

        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "existing_capability_covers_it" in rendered
        subheaders = " ".join(str(item.value) for item in app.subheader)
        assert "Blocking gates" in subheaders
        assert "Measurement Contract" not in subheaders

    def test_submitting_an_empty_request_reports_an_error_not_a_crash(self):
        app = fresh_app()
        app.button[0].click().run()
        assert not app.exception
        assert any("empty" in str(item.value).lower() for item in app.error)


class TestReviewEndToEnd:
    """Acceptance criterion 10, review half — no model is involved at all."""

    def test_the_healthy_scenario_recommends_continue(self):
        app = fresh_app()
        app.button[1].click().run()
        assert not app.exception
        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "CONTINUE" in rendered

    def test_the_failing_scenario_recommends_retiring(self):
        app = fresh_app()
        app.selectbox[1].select("Failing agent").run()
        app.button[1].click().run()
        assert not app.exception
        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "RETIRE" in rendered
        # The failing scenario is the one that looks adopted but is not working,
        # so the quality-side conditions must be visible.
        assert "cost_exceeds_value" in rendered or "quality_below_threshold" in rendered

    def test_the_review_reports_its_computed_indicators(self):
        app = fresh_app()
        app.button[1].click().run()
        assert not app.exception
        labels = {item.label for item in app.metric}
        assert {"Adoption rate", "Cost / successful task", "Value / task"} <= labels
