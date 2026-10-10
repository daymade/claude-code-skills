"""Execute the standalone builder and shipped JavaScript grade renderer."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_aggregate_benchmark import render_benchmark
from test_grading_validation import OTHER, TARGET, receipt


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "eval-viewer/generate_review.py"
spec = importlib.util.spec_from_file_location("standalone_grade_builder", BUILDER)
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)
ABSENT = object()


def run_fixture(root, grading, assertions=TARGET):
    run_dir = root / "eval-1/with_skill/run-1"
    (run_dir / "outputs").mkdir(parents=True)
    (run_dir / "outputs/result.txt").write_text("Synthetic output")
    metadata = {"prompt": "Canonical task", "eval_id": 1}
    if assertions is not ABSENT:
        metadata["assertions"] = assertions
    (run_dir.parent.parent / "eval_metadata.json").write_text(json.dumps(metadata))
    if grading is not ABSENT:
        (run_dir / "grading.json").write_text(json.dumps(grading))
    return run_dir


@pytest.mark.parametrize("mutation", ["wrong_case", "subset", "duplicate", "extra",
                                     "missing", "empty", "evidence", "text", "json_null"])
def test_standalone_rejected_receipts_never_render_raw_rate(tmp_path, mutation):
    g = receipt()
    if mutation == "wrong_case":
        g = receipt(OTHER)
    elif mutation == "subset":
        g = receipt(TARGET[:1])
    elif mutation == "duplicate":
        g = receipt([TARGET[0]] * len(TARGET))
    elif mutation == "extra":
        g = receipt([*TARGET, "Extra"])
    elif mutation == "missing":
        del g["expectations"]
    elif mutation == "empty":
        g["expectations"] = []
    elif mutation == "evidence":
        del g["expectations"][0]["evidence"]
    elif mutation == "text":
        g["expectations"][0]["text"] = " "
    else:
        g = None
    run = viewer.build_run(tmp_path, run_fixture(tmp_path, g))
    assert run["grading_status"] == "invalid_grading" and run["grading"] is None
    html = render_benchmark({}, run=run)
    assert "Grading unknown: invalid_grading" in html
    assert "100%" not in html and "grade-pass" not in html


@pytest.mark.parametrize("assertions", [None, "", {}, [""], [None]])
def test_standalone_malformed_canonical_target_is_invalid(tmp_path, assertions):
    run = viewer.build_run(tmp_path, run_fixture(tmp_path, receipt(), assertions))
    assert run["assertion_binding"] == "invalid_expected" and run["grading"] is None
    assert "Grading unknown" in render_benchmark({}, run=run)


@pytest.mark.parametrize("assertions", [ABSENT, []])
def test_standalone_legacy_numbers_are_visibly_unbound(tmp_path, assertions):
    run = viewer.build_run(tmp_path, run_fixture(tmp_path, receipt(), assertions))
    html = render_benchmark({}, run=run)
    assert run["assertion_binding"] == "unbound"
    assert "100%" in html and "Unbound assertions" in html


def test_reordered_zero_and_rounded_rates_render_as_real_observations(tmp_path):
    cases = [(TARGET[::-1], [True] * len(TARGET), 1, "100%"),
             (TARGET, [False] * len(TARGET), 0, "0%"),
             (TARGET[:3], [True, True, False], 0.67, "67%")]
    for i, (texts, passes, rate, label) in enumerate(cases):
        root = tmp_path / str(i)
        g = receipt(texts, passes)
        g["summary"]["pass_rate"] = rate
        run = viewer.build_run(root, run_fixture(root, g, texts))
        html = render_benchmark({}, run=run)
        assert run["assertion_binding"] == "bound" and label in html
        if rate == 0:
            assert "0 passed, 4 failed of 4" in html


def test_run_prompt_fallback_cannot_shadow_canonical_target(tmp_path):
    target = run_fixture(tmp_path, receipt(OTHER))
    (target / "eval_metadata.json").write_text('{"prompt":"Display prompt","assertions":[]}')
    run = viewer.build_run(tmp_path, target)
    assert run["prompt"] == "Display prompt"
    assert run["assertion_binding"] == "mismatch" and run["grading"] is None


def test_stale_graded_benchmark_cannot_override_invalid_current_run(tmp_path):
    run = viewer.build_run(tmp_path, run_fixture(tmp_path, receipt(OTHER)))
    stale = {"runs": [{"run_id": "eval-1/with_skill/run-1", "grading_status": "graded"}]}
    assert "Grading unknown: invalid_grading" in render_benchmark(stale, run=run)
    target = tmp_path / "healthy"
    run = viewer.build_run(target, run_fixture(target, receipt()))
    stale["runs"][0]["grading_status"] = "invalid_grading"
    assert "Grading unknown: invalid_grading" in render_benchmark(stale, run=run)


@pytest.mark.parametrize("malformed", ["{", "[]"])
def test_malformed_present_grade_cannot_fall_back_to_parent(tmp_path, malformed):
    target = run_fixture(tmp_path, receipt())
    (target / "grading.json").write_text(malformed)
    (target.parent / "grading.json").write_text(json.dumps(receipt()))
    run = viewer.build_run(tmp_path, target)
    assert run["grading_status"] == "invalid_grading" and run["grading"] is None


def test_missing_grading_is_visible_unknown_without_a_benchmark(tmp_path):
    run = viewer.build_run(tmp_path, run_fixture(tmp_path, ABSENT))
    assert run["grading_status"] == "missing_grading"
    assert "Grading unknown: missing_grading" in render_benchmark({}, run=run)


@pytest.mark.parametrize("texts,status,binding", [(TARGET, "graded", "bound"),
                                                (OTHER, "invalid_grading", "mismatch")])
def test_absolute_cli_and_dynamic_import_work_without_caller_pythonpath(tmp_path, texts, status, binding):
    workspace = tmp_path / "workspace"
    target = run_fixture(workspace, receipt(texts))
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    output = tmp_path / "review.html"
    cli = subprocess.run([sys.executable, str(BUILDER), str(workspace), "--static", str(output)],
                         cwd=unrelated, env=env, text=True, capture_output=True)
    assert cli.returncode == 0, cli.stderr
    assert json.dumps("grading_status") + ": " + json.dumps(status) in output.read_text()
    script = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('external_builder', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.build_run(Path(sys.argv[2]), Path(sys.argv[3]))))
"""
    dynamic = subprocess.run([sys.executable, "-c", script, str(BUILDER), str(workspace), str(target)],
                             cwd=unrelated, env=env, text=True, capture_output=True)
    assert dynamic.returncode == 0, dynamic.stderr
    run = json.loads(dynamic.stdout)
    assert run["grading_status"] == status and run["assertion_binding"] == binding


@pytest.mark.parametrize("malformed", ["{", "[]", "null"])
def test_canonical_metadata_file_errors_cannot_become_unbound(tmp_path, malformed):
    target = run_fixture(tmp_path, receipt())
    (target.parent.parent / "eval_metadata.json").write_text(malformed)
    run = viewer.build_run(tmp_path, target)
    assert run["grading_status"] == "invalid_grading"
    assert run["assertion_binding"] == "invalid_expected" and run["issues"]


def test_legacy_parent_grade_is_still_accepted_when_run_grade_is_absent(tmp_path):
    target = run_fixture(tmp_path, ABSENT)
    (target.parent / "grading.json").write_text(json.dumps(receipt()))
    run = viewer.build_run(tmp_path, target)
    assert run["grading_status"] == "graded" and run["assertion_binding"] == "bound"
