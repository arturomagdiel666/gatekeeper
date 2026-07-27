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


def triage_button(app):
    """The Assess submit button."""
    return next(b for b in app.button if b.label == "Assess")


def review_button(app):
    """The Run review submit button."""
    return next(b for b in app.button if b.label == "Run review")


def offline_checkbox(app):
    """The checkbox that scores an exemplar without calling the model."""
    return next(c for c in app.checkbox if "hand-authored" in c.label)


def select_by_label(app, label: str):
    """Find a selectbox by its label rather than its index.

    Positional lookup broke the moment Tab 1 gained the structured intake
    fields; a label is stable against layout changes.
    """
    for box in app.selectbox:
        if box.label == label:
            return box
    raise AssertionError(f"no selectbox labelled {label!r}")


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

    def test_the_three_tabs_exist(self):
        """Named rather than counted, so a fourth tab does not fail this test.

        The product's claim spans all three: the gate, the interview that fills
        it, and the review that retires what it approved.
        """
        app = fresh_app()
        labels = {str(tab.label) for tab in app.tabs}
        assert {"Triage", "Intake agent", "Review simulator"} <= labels

    def test_the_title_and_sidebar_render(self):
        app = fresh_app()
        assert any("Gatekeeper" in str(item.value) for item in app.title)
        sidebar_text = " ".join(str(item.value) for item in app.sidebar.markdown)
        assert "dimensions" in sidebar_text
        assert "Review policy" in sidebar_text

    def test_every_example_is_offered_in_the_triage_dropdown(self):
        from examples import load_examples

        app = fresh_app()
        options = select_by_label(app, "Load a reference example").options
        assert len(options) == len(load_examples()) + 1  # + the blank form

    def test_both_scenarios_are_offered_in_the_review_simulator(self):
        app = fresh_app()
        assert set(select_by_label(app, "Pre-loaded scenario").options) == {
            "Healthy agent",
            "Failing agent",
        }


class TestTriageEndToEnd:
    """Acceptance criterion 10, triage half — driven through the offline path."""

    def test_loading_an_example_and_scoring_it_produces_a_verdict(self):
        app = fresh_app()
        select_by_label(app, "Load a reference example").select("Shift handover summaries for the service desk").run()
        assert not app.exception

        # Tick the offline checkbox so no provider is needed, then submit.
        offline_checkbox(app).check().run()
        triage_button(app).click().run()
        assert not app.exception

        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "GO" in rendered
        assert "Measurement Contract" in " ".join(
            str(item.value) for item in app.subheader
        )

    def test_a_gated_example_shows_its_gate_and_no_contract(self):
        app = fresh_app()
        select_by_label(app, "Load a reference example").select(
            "An assistant that answers HR policy questions in the chat client"
        ).run()
        offline_checkbox(app).check().run()
        triage_button(app).click().run()
        assert not app.exception

        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "existing_capability_covers_it" in rendered
        subheaders = " ".join(str(item.value) for item in app.subheader)
        assert "Blocking gates" in subheaders
        assert "Measurement Contract" not in subheaders

    def test_submitting_an_empty_request_reports_an_error_not_a_crash(self):
        app = fresh_app()
        triage_button(app).click().run()
        assert not app.exception
        assert any("empty" in str(item.value).lower() for item in app.error)


class TestReviewEndToEnd:
    """Acceptance criterion 10, review half — no model is involved at all."""

    def test_the_healthy_scenario_recommends_continue(self):
        app = fresh_app()
        review_button(app).click().run()
        assert not app.exception
        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "CONTINUE" in rendered

    def test_the_failing_scenario_recommends_retiring(self):
        app = fresh_app()
        select_by_label(app, "Pre-loaded scenario").select("Failing agent").run()
        review_button(app).click().run()
        assert not app.exception
        rendered = " ".join(str(item.value) for item in app.markdown)
        assert "RETIRE" in rendered
        # The failing scenario is the one that looks adopted but is not working,
        # so the quality-side conditions must be visible.
        assert "cost_exceeds_value" in rendered or "quality_below_threshold" in rendered

    def test_the_review_reports_its_computed_indicators(self):
        app = fresh_app()
        review_button(app).click().run()
        assert not app.exception
        labels = {item.label for item in app.metric}
        assert {"Adoption rate", "Cost / successful task", "Value / task"} <= labels


class TestTimeoutFallback:
    """A timeout must degrade to the offline path, not to a stack trace."""

    def _timed_out(self, monkeypatch):
        """Make assess_request always report a timeout.

        Patching the module attribute works because app.py resolves
        `from assess import assess_request` when AppTest executes the script,
        which happens after this patch is applied.
        """
        import assess

        def fake(intake, provider, **kwargs):
            return assess.AssessmentResult(
                intake=intake, timed_out=True, timeout_seconds=30.0
            )

        monkeypatch.setattr(assess, "assess_request", fake)

    def test_a_timeout_with_an_exemplar_loaded_falls_back_and_says_so(
        self, monkeypatch
    ):
        self._timed_out(monkeypatch)
        app = fresh_app()
        select_by_label(app, "Load a reference example").select(
            "Shift handover summaries for the service desk"
        ).run()
        triage_button(app).click().run()
        assert not app.exception

        info = " ".join(str(i.value) for i in app.info)
        assert "did not answer within 30 seconds" in info
        assert "not a verdict" in info

        warning = " ".join(str(i.value) for i in app.warning)
        assert "stored offline assessment" in warning
        assert "written by hand" in warning

        # The engine really ran: the verdict and the contract are rendered.
        rendered = " ".join(str(i.value) for i in app.markdown)
        assert "GO" in rendered
        assert "Measurement Contract" in " ".join(
            str(i.value) for i in app.subheader
        )

    def test_a_timeout_with_no_exemplar_shows_the_message_only(self, monkeypatch):
        self._timed_out(monkeypatch)
        app = fresh_app()
        # Blank form: type a request without loading an example.
        app.text_area[0].set_value("We would like an agent for something.").run()
        triage_button(app).click().run()
        assert not app.exception

        assert "did not answer within" in " ".join(str(i.value) for i in app.info)
        captions = " ".join(str(i.value) for i in app.caption)
        assert "no stored assessment to fall back to" in captions
        assert "Measurement Contract" not in " ".join(
            str(i.value) for i in app.subheader
        )


class TestAgentTab:
    """The intake agent tab. Rendering only — the loop is tested in test_agent."""

    def test_the_agent_tab_states_the_architecture_rule(self):
        """A visitor must not think the model is scoring anything."""
        app = fresh_app()
        text = " ".join(str(item.value) for item in app.markdown)
        assert "The model asks. The tables decide." in text
        assert "never assigns a score" in text

    def test_it_offers_the_canonical_vague_request(self):
        """06_something_with_the_invoices: the case a form cannot finish."""
        app = fresh_app()
        assert any(
            "supplier invoices" in str(area.value) for area in app.text_area
        )
