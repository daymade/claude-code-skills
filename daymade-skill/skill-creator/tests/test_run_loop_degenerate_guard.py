"""Regression suite for run_loop.py's degenerate-harness / infra-error guard.

Everything here mocks run_eval/improve_description — no real `claude -p` subprocess calls,
so this suite is fast, deterministic, and free to run on every change to run_loop.py or
generate_report.py. That matters here specifically: the guard exists to stop a loop that
burns real API calls against a broken measurement, so its own test suite burning real API
calls would be the same mistake one layer up.

NOTE: this directory is not currently wired into scripts/ci/test-suites.txt (see that
file's admission criteria) — run locally with:
    uv run --with pytest --with PyYAML python -m pytest tests/test_run_loop_degenerate_guard.py -q
"""

from pathlib import Path
from unittest.mock import patch

from scripts import run_loop as rl
from scripts.generate_report import generate_html

EVAL_SET = [
    {"query": "should trigger #1", "should_trigger": True},
    {"query": "should trigger #2", "should_trigger": True},
    {"query": "should trigger #3", "should_trigger": True},
    {"query": "should not trigger #1", "should_trigger": False},
    {"query": "should not trigger #2", "should_trigger": False},
]


def _fake_run_eval(pos_triggers=0, neg_triggers=0, pos_errors=0, neg_errors=0):
    """Builds a fake run_eval() that reports a fixed trigger/error count per query,
    uniformly across all should_trigger=True queries and all should_trigger=False queries."""

    def _fake(eval_set, skill_name, description, num_workers, timeout,
              project_root, runs_per_query=1, trigger_threshold=0.5, model=None):
        results = []
        for item in eval_set:
            if item["should_trigger"]:
                triggers, errors = pos_triggers, pos_errors
            else:
                triggers, errors = neg_triggers, neg_errors
            did_pass = (
                (triggers / runs_per_query) >= trigger_threshold
                if item["should_trigger"]
                else (triggers / runs_per_query) < trigger_threshold
            )
            results.append({
                "query": item["query"], "should_trigger": item["should_trigger"],
                "trigger_rate": triggers / runs_per_query, "triggers": triggers,
                "runs": runs_per_query, "errors": errors, "pass": did_pass,
            })
        return {
            "skill_name": skill_name, "description": description, "results": results,
            "error_count": sum(r["errors"] for r in results),
            "summary": {"total": len(results), "passed": sum(1 for r in results if r["pass"])},
        }

    return _fake


def _run(fake_eval, *, max_iterations=3, holdout=0.4, expect_improve_calls=None):
    """Runs run_loop() with run_eval/improve_description mocked. If expect_improve_calls is
    given, asserts improve_description was called exactly that many times; if it's 0,
    improve_description raises on any call instead of silently returning a fake description,
    so an unexpected call fails loudly rather than producing a misleading iteration count."""
    call_count = {"n": 0}

    def _improve(**kwargs):
        call_count["n"] += 1
        if expect_improve_calls == 0:
            raise AssertionError("improve_description was called but the guard should have aborted first")
        return f"improved description v{call_count['n']}"

    with patch.object(rl, "run_eval", fake_eval), \
         patch.object(rl, "improve_description", _improve), \
         patch.object(rl, "find_project_root", lambda: Path(".")), \
         patch.object(rl, "parse_skill_md", lambda p: ("fake-skill", "original description", "content")):
        output = rl.run_loop(
            eval_set=EVAL_SET, skill_path=Path("."), description_override=None,
            num_workers=1, timeout=5, max_iterations=max_iterations, runs_per_query=3,
            trigger_threshold=0.5, holdout=holdout, model="sonnet", verbose=False,
        )
    if expect_improve_calls is not None and expect_improve_calls != 0:
        assert call_count["n"] == expect_improve_calls
    return output, call_count["n"]


def test_guard_aborts_on_total_silence_at_iteration_1():
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=0), expect_improve_calls=0)
    assert output["iterations_run"] == 1
    assert output["exit_reason"].startswith("degenerate_harness")
    assert calls == 0


def test_guard_does_not_fire_on_weak_nonzero_signal():
    output, calls = _run(_fake_run_eval(pos_triggers=1, neg_triggers=0), max_iterations=2, expect_improve_calls=1)
    assert not output["exit_reason"].startswith(("degenerate_harness", "infra_error"))
    assert output["iterations_run"] == 2


def test_guard_does_not_misfire_when_only_negatives_trigger():
    """Regression for round-1 review finding #1: a description that is merely
    polarity-inverted (misses every positive, matches several negatives) proves the probe
    works and improve_description has real gradient — must not be aborted as degenerate."""
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=3), max_iterations=2, expect_improve_calls=1)
    assert not output["exit_reason"].startswith("degenerate_harness")
    assert output["iterations_run"] == 2


def test_infra_error_when_positive_side_raises_exceptions():
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=0, pos_errors=3), expect_improve_calls=0)
    assert output["exit_reason"].startswith("infra_error")
    assert "9/15" in output["exit_reason"]  # 3 positive queries x 3 errors each = 9, out of 15 total runs


def test_infra_error_when_only_negative_side_raises_exceptions():
    """Regression for round-2 review finding #1: if positives are cleanly silent but
    negatives are silent only because they errored (never actually ran), the negative side
    can't be used as evidence the probe is genuinely dead — must route to infra_error, not
    degenerate_harness."""
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=0, neg_errors=3), expect_improve_calls=0)
    assert output["exit_reason"].startswith("infra_error")


def test_single_flake_still_routes_to_infra_error_with_accurate_ratio():
    """Documents intended behavior for round-2 review finding #2: even a small error
    fraction alongside total trigger silence takes the infra_error branch (a crash, however
    rare, is a more specific and actionable lead than bare silence) — but the message must
    carry the true ratio so a reader can judge whether it's a small flake or the whole
    picture."""
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=0, pos_errors=1), expect_improve_calls=0)
    assert output["exit_reason"].startswith("infra_error")
    assert "3/15" in output["exit_reason"]  # 3 positive queries x 1 error each = 3, out of 15 total runs


def test_guard_scoped_to_iteration_1_only():
    """Iteration 2+ going silent must not retroactively abort — only iteration 1 is checked."""
    fake = _fake_run_eval(pos_triggers=1, neg_triggers=0)  # weak but real signal, every iteration
    output, calls = _run(fake, max_iterations=3, expect_improve_calls=2)
    assert not output["exit_reason"].startswith(("degenerate_harness", "infra_error"))
    assert output["iterations_run"] == 3


def test_guard_skipped_when_eval_set_has_no_positive_queries():
    """No should_trigger=True query at all means the guard has nothing to judge the probe
    against and must not fire — falls through to normal iteration/exit logic instead."""
    all_negative = [
        {"query": "negative #1", "should_trigger": False},
        {"query": "negative #2", "should_trigger": False},
    ]
    with patch.object(rl, "run_eval", _fake_run_eval(pos_triggers=0, neg_triggers=0)), \
         patch.object(rl, "improve_description", lambda **kw: (_ for _ in ()).throw(
             AssertionError("should not reach improve_description with all_passed on iteration 1"))), \
         patch.object(rl, "find_project_root", lambda: Path(".")), \
         patch.object(rl, "parse_skill_md", lambda p: ("fake-skill", "original description", "content")):
        output = rl.run_loop(
            eval_set=all_negative, skill_path=Path("."), description_override=None,
            num_workers=1, timeout=5, max_iterations=3, runs_per_query=3,
            trigger_threshold=0.5, holdout=0.4, model="sonnet", verbose=False,
        )
    assert not output["exit_reason"].startswith(("degenerate_harness", "infra_error"))


def test_report_banner_renders_for_degenerate_and_infra_exit_reasons_but_not_all_passed():
    def _history_row():
        result = {"query": "q", "should_trigger": True, "triggers": 0, "runs": 3, "pass": False}
        return {
            "iteration": 1, "description": "d",
            "train_passed": 0, "train_failed": 1, "train_total": 1, "train_results": [result],
            "test_passed": 0, "test_failed": 1, "test_total": 1, "test_results": [dict(result, query="q2")],
            "passed": 0, "failed": 1, "total": 1, "results": [result],
        }

    for exit_reason, banner_expected in [
        ("degenerate_harness: 0/9 triggers...", True),
        ("infra_error: 3/9 raised...", True),
        ("all_passed (iteration 2)", False),
        ("max_iterations (5)", False),
    ]:
        html = generate_html(
            {
                "exit_reason": exit_reason, "iterations_run": 1, "history": [_history_row()],
                "original_description": "o", "best_description": "o",
                "best_score": "0/1", "best_test_score": "0/1", "best_train_score": "0/1",
            },
            skill_name="x",
        )
        # Assert on the banner's own text, not the CSS class name — the class is defined
        # unconditionally in <style>, so checking for it there is a false positive
        # regardless of whether the banner div actually rendered.
        assert ("Loop aborted early" in html) == banner_expected, exit_reason


def test_report_does_not_crash_when_holdout_zero_disables_test_split():
    """Regression for a pre-existing bug this guard's testing surfaced (not introduced by
    the guard itself, confirmed via `git show HEAD` to predate it): run_loop stores an
    explicit None for test_results when holdout=0, and `.get("test_results", [])` doesn't
    fall back to the default for a present-but-None key, so aggregate_runs(None) used to
    raise TypeError."""
    output, calls = _run(_fake_run_eval(pos_triggers=0, neg_triggers=0), holdout=0, expect_improve_calls=0)
    assert output["exit_reason"].startswith("degenerate_harness")
    html = generate_html(output, skill_name="fake-skill")  # must not raise
    assert "Loop aborted early" in html
