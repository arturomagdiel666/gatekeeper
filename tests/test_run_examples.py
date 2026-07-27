"""Tests for the demo-day comparison script's outcome accounting.

The one behaviour worth locking down here: a TIMEOUT is its own outcome class.
Counting it as a wrong verdict would aggregate two things that are not
interchangeable — an infrastructure result and a model result — which is the
wrong-unit error recorded in ADR-004 and ADR-022.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from examples import load_examples

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_examples.py"


@pytest.fixture
def run_script(monkeypatch, capsys):
    """Run the script with a patched assess_request and return its output."""

    def _run(fake_assess):
        import assess

        monkeypatch.setattr(assess, "assess_request", fake_assess)
        monkeypatch.setattr(sys, "argv", ["run_examples.py", "--provider", "mock"])
        try:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        except SystemExit:
            pass
        return capsys.readouterr().out

    return _run


def test_timeouts_are_counted_separately_and_never_as_mismatches(run_script):
    import assess

    def always_times_out(intake, provider, **kwargs):
        return assess.AssessmentResult(
            intake=intake, timed_out=True, timeout_seconds=30.0
        )

    output = run_script(always_times_out)

    assert output.count("TIMEOUT") >= len(load_examples())
    assert f"{len(load_examples())} timed out (not counted as mismatches)" in output
    # Nothing completed, so nothing can have matched or mismatched.
    assert "0/0 completed verdicts match" in output
    assert "no answer within 30s" in output


def test_a_timeout_row_is_marked_distinctly_from_a_mismatch(run_script):
    import assess
    from examples import load_examples

    ids = [e.id for e in load_examples()]

    def one_times_out(intake, provider, **kwargs):
        # Time out on the first example only; the rest score normally offline.
        example = next(
            e for e in load_examples() if e.request_text.strip() == intake.request_text
        )
        if example.id == ids[0]:
            return assess.AssessmentResult(
                intake=intake, timed_out=True, timeout_seconds=30.0
            )
        from config import PATTERNS, RUBRIC
        from scoring import score

        return assess.AssessmentResult(
            intake=intake,
            assessment=example.reference_assessment,
            outcome=score(example.reference_assessment, RUBRIC, PATTERNS, intake),
        )

    output = run_script(one_times_out)

    assert "1 timed out (not counted as mismatches)" in output
    # The five that completed are all anchor-faithful, so all five match.
    assert f"{len(load_examples()) - 1}/{len(load_examples()) - 1} completed verdicts match" in output
    # The timed-out TABLE row (the last such line; the first is progress
    # output) uses its own marker, not the mismatch marker.
    timeout_rows = [l for l in output.splitlines() if "TIMEOUT" in l and ids[0] in l]
    table_row = timeout_rows[-1]
    assert table_row.startswith("--")
    assert not table_row.startswith("XX")
