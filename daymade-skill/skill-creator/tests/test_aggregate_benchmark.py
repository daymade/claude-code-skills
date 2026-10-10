"""Calibrate the actual benchmark writer and its shipped JS reader."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.aggregate_benchmark import generate_benchmark, generate_markdown


ROOT = Path(__file__).resolve().parents[1]


def grade(passes=(True,), seconds=None, chars=12345):
    passed = sum(passes)
    data = {
        "expectations": [
            {"text": f"Outcome {i}", "passed": value, "evidence": f"Artifact {i}"}
            for i, value in enumerate(passes)
        ],
        "summary": {"passed": passed, "failed": len(passes) - passed,
                    "total": len(passes), "pass_rate": passed / len(passes)},
        "execution_metrics": {"output_chars": chars},
    }
    if seconds is not None:
        data["timing"] = {"total_duration_seconds": seconds}
    return data


def write_run(root, config="with_skill", case=1, run=1, grading=None, timing=None):
    target = root / f"eval-{case}" / config / f"run-{run}"
    target.mkdir(parents=True)
    if grading is not None:
        (target / "grading.json").write_text(json.dumps(grading))
    if timing is not None:
        (target / "timing.json").write_text(json.dumps(timing))
    return target


def healthy_pair(root, candidate="with_skill", baseline="old_skill"):
    write_run(root, candidate, grading=grade(),
              timing={"total_tokens": 700, "total_duration_seconds": 9})
    write_run(root, baseline, grading=grade((True, False)),
              timing={"total_tokens": 1000, "total_duration_seconds": 12})


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("candidate,baseline", [
    ("with_skill", "old_skill"), ("with_skill", "without_skill"),
    ("new_skill", "old_skill"),
])
def test_complete_healthy_layouts_keep_numeric_results(tmp_path, legacy, candidate, baseline):
    root = tmp_path / "runs" if legacy else tmp_path
    healthy_pair(root, candidate, baseline)
    data = generate_benchmark(tmp_path)
    assert len(data["runs"]) == 2
    assert data["metadata"]["runs_per_configuration"] == 1
    assert data["metadata"]["attempts_per_configuration"] == {candidate: 1, baseline: 1}
    assert data["comparison"]["status"] == "complete"
    assert data["comparison"]["candidate"] == candidate
    assert data["comparison"]["baseline"] == baseline
    assert data["run_summary"]["delta"] == {
        "pass_rate": "+0.50", "time_seconds": "-3.0", "tokens": "-300",
    }
    assert data["run_summary"][candidate]["pass_rate"]["count"] == 1
    assert "unknown" not in generate_markdown(data)
    assert "1/1 observed" in generate_markdown(data)


def test_missing_and_corrupt_grading_keep_attempts_and_withhold_all_deltas(tmp_path):
    healthy_pair(tmp_path)
    write_run(tmp_path, "with_skill", run=2)
    bad = write_run(tmp_path, "with_skill", run=3)
    (bad / "grading.json").write_text("{")
    write_run(tmp_path, "old_skill", run=2, grading=grade())
    write_run(tmp_path, "old_skill", run=3, grading=grade())
    data = generate_benchmark(tmp_path)
    assert len(data["runs"]) == 6
    candidate = [r for r in data["runs"] if r["configuration"] == "with_skill"]
    assert [r["grading_status"] for r in candidate] == [
        "graded", "missing_grading", "invalid_grading",
    ]
    assert [r["result"]["pass_rate"] for r in candidate] == [1, None, None]
    stat = data["run_summary"]["with_skill"]["pass_rate"]
    assert stat["count"] == 1 and stat["total"] == 3
    assert data["comparison"]["paired_runs"] == 3
    assert all(v is None for v in data["run_summary"]["delta"].values())
    assert "1/3 observed" in generate_markdown(data)


def test_missing_cost_stays_unknown_and_characters_stay_characters(tmp_path):
    write_run(tmp_path, grading=grade())
    data = generate_benchmark(tmp_path)
    run = data["runs"][0]
    assert run["result"]["time_seconds"] is None
    assert run["result"]["tokens"] is None
    assert run["result"]["output_chars"] == 12345
    assert run["metric_sources"] == {"time_seconds": None, "tokens": None}
    assert data["run_summary"]["with_skill"]["tokens"]["mean"] is None
    assert data["run_summary"]["with_skill"]["tokens"]["count"] == 0
    assert data["comparison"]["status"] == "unbound"
    assert "unknown" in generate_markdown(data)


def test_cost_fields_are_independent_and_real_zero_is_observed(tmp_path):
    write_run(tmp_path, grading=grade(seconds=9), timing={"total_tokens": 700})
    write_run(tmp_path, "old_skill", grading=grade(seconds=0), timing={"total_tokens": 0})
    data = generate_benchmark(tmp_path)
    runs = {r["configuration"]: r for r in data["runs"]}
    assert runs["with_skill"]["result"]["tokens"] == 700
    assert runs["with_skill"]["metric_sources"]["tokens"] == "timing.json.total_tokens"
    assert runs["with_skill"]["metric_sources"]["time_seconds"] == "grading.json.timing.total_duration_seconds"
    assert runs["old_skill"]["result"]["time_seconds"] == 0
    assert runs["old_skill"]["result"]["tokens"] == 0
    assert data["run_summary"]["old_skill"]["tokens"]["count"] == 1
    assert data["comparison"]["status"] == "complete"


def test_duration_ms_and_grading_token_copy_are_supported(tmp_path):
    g = grade()
    g["timing"] = {"total_tokens": 700}
    write_run(tmp_path, grading=g, timing={"duration_ms": 23000})
    run = generate_benchmark(tmp_path)["runs"][0]
    assert run["result"]["time_seconds"] == 23
    assert run["result"]["tokens"] == 700
    assert run["metric_sources"]["time_seconds"] == "timing.json.duration_ms/1000"
    assert run["metric_sources"]["tokens"] == "grading.json.timing.total_tokens"


@pytest.mark.parametrize("value", [None, "", "0", -1, True, float("nan"), float("inf")])
def test_missing_or_invalid_measurements_never_become_zero(tmp_path, value):
    write_run(tmp_path, grading=grade(),
              timing={"total_duration_seconds": value, "total_tokens": value})
    run = generate_benchmark(tmp_path)["runs"][0]
    assert run["result"]["time_seconds"] is None
    assert run["result"]["tokens"] is None


@pytest.mark.parametrize("bad_grade", [None, [], {}, "bad"])
def test_invalid_grading_shape_is_retained_without_crashing(tmp_path, bad_grade):
    target = write_run(tmp_path)
    (target / "grading.json").write_text(json.dumps(bad_grade))
    run = generate_benchmark(tmp_path)["runs"][0]
    assert run["grading_status"] == "invalid_grading"
    assert run["result"]["pass_rate"] is None


@pytest.mark.parametrize("mutation", ["counts", "rate", "missing", "null", "empty", "passed_type", "evidence"])
def test_grading_consistency_does_not_self_certify(tmp_path, mutation):
    g = grade((False,))
    if mutation == "counts":
        g["summary"].update(passed=1, failed=0)
    elif mutation == "rate":
        g["summary"]["pass_rate"] = 1
    elif mutation == "missing":
        del g["summary"]["passed"]
    elif mutation == "null":
        g["summary"] = None
    elif mutation == "empty":
        g["expectations"] = []
    elif mutation == "passed_type":
        g["expectations"][0]["passed"] = 1
    else:
        del g["expectations"][0]["evidence"]
    write_run(tmp_path, grading=g)
    run = generate_benchmark(tmp_path)["runs"][0]
    assert run["grading_status"] == "invalid_grading"
    assert run["result"]["pass_rate"] is None
    assert run["issues"]


def test_two_decimal_legacy_summary_is_not_rejected(tmp_path):
    g = grade((True, True, False))
    g["summary"]["pass_rate"] = 0.67
    write_run(tmp_path, grading=g)
    run = generate_benchmark(tmp_path)["runs"][0]
    assert run["grading_status"] == "graded"
    assert run["result"]["pass_rate"] == 0.67


def test_extra_config_cannot_change_comparison_roles(tmp_path):
    healthy_pair(tmp_path, "new_skill", "old_skill")
    write_run(tmp_path, "a_aux", grading=grade((False,)))
    data = generate_benchmark(tmp_path)
    assert list(data["run_summary"])[0] == "a_aux"
    assert data["comparison"]["candidate"] == "new_skill"
    assert data["comparison"]["baseline"] == "old_skill"
    assert data["run_summary"]["delta"]["pass_rate"] == "+0.50"


def test_unmatched_cases_and_runs_withhold_deltas(tmp_path):
    healthy_pair(tmp_path)
    write_run(tmp_path, "old_skill", case=2, grading=grade((False,)))
    data = generate_benchmark(tmp_path)
    assert len(data["runs"]) == 3
    assert data["metadata"]["runs_per_configuration"] is None
    assert data["comparison"]["paired_runs"] == 1
    assert data["comparison"]["unmatched_runs"] == ["eval-2/old_skill/run-1"]
    assert all(v is None for v in data["run_summary"]["delta"].values())


def test_unknown_and_ambiguous_roles_require_explicit_binding(tmp_path):
    healthy_pair(tmp_path, "candidate_v2", "baseline_v1")
    data = generate_benchmark(tmp_path)
    assert data["comparison"]["status"] == "unbound"
    bound = generate_benchmark(tmp_path, candidate="candidate_v2", baseline="baseline_v1")
    assert bound["comparison"]["status"] == "complete"
    with pytest.raises(ValueError, match="both"):
        generate_benchmark(tmp_path, candidate="candidate_v2")
    with pytest.raises(ValueError, match="distinct"):
        generate_benchmark(tmp_path, candidate="candidate_v2", baseline="candidate_v2")
    healthy_pair(tmp_path, "with_skill", "old_skill")
    write_run(tmp_path, "new_skill", grading=grade())
    assert generate_benchmark(tmp_path)["comparison"]["status"] == "unbound"


@pytest.mark.parametrize("problem", ["duplicate", "invalid_run"])
def test_duplicate_eval_ids_and_invalid_run_numbers_do_not_pair(tmp_path, problem):
    healthy_pair(tmp_path)
    if problem == "duplicate":
        for config in ("with_skill", "old_skill"):
            write_run(tmp_path, config, case=2, grading=grade())
        (tmp_path / "eval-2/eval_metadata.json").write_text('{"eval_id": 1}')
    else:
        write_run(tmp_path, "with_skill", run="bad", grading=grade())
    data = generate_benchmark(tmp_path)
    assert len(data["runs"]) == (4 if problem == "duplicate" else 3)
    assert all(v is None for v in data["run_summary"]["delta"].values())
    assert any("duplicate or invalid" in issue for issue in data["comparison"]["issues"])


def test_conflicting_or_mixed_scopes_withhold_cost_deltas(tmp_path):
    g = grade(seconds=9)
    g["timing"]["total_tokens"] = 701
    write_run(tmp_path, grading=g,
              timing={"total_duration_seconds": 10, "total_tokens": 700})
    write_run(tmp_path, "old_skill", grading=grade(),
              timing={"total_duration_seconds": 10, "total_tokens": 700})
    data = generate_benchmark(tmp_path)
    run = next(r for r in data["runs"] if r["configuration"] == "with_skill")
    assert run["result"]["time_seconds"] is None and run["result"]["tokens"] is None
    assert data["run_summary"]["delta"]["pass_rate"] == "+0.00"
    assert data["run_summary"]["delta"]["time_seconds"] is None
    assert data["run_summary"]["delta"]["tokens"] is None


def test_complete_values_with_different_scopes_do_not_imply_speedup(tmp_path):
    write_run(tmp_path, grading=grade(), timing={"total_duration_seconds": 9,
              "total_tokens": 700, "time_scope": "end_to_end"})
    write_run(tmp_path, "old_skill", grading=grade(), timing={"total_duration_seconds": 10,
              "total_tokens": 700, "time_scope": "executor"})
    data = generate_benchmark(tmp_path)
    assert all(r["result"]["time_seconds"] is not None for r in data["runs"])
    assert data["run_summary"]["delta"]["time_seconds"] is None
    assert data["run_summary"]["delta"]["tokens"] == "+0"
    assert any("mixed measurement scopes" in x for x in data["comparison"]["issues"])


def render_benchmark(data, run=None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the shipped JS viewer renderer")
    html = (ROOT / "eval-viewer/viewer.html").read_text()
    renderer = html.split("// ---- Benchmark rendering ----", 1)[1].split("// ---- Start ----", 1)[0]
    renderer += html.split("// ---- Grades ----", 1)[1].split("function toggleGrades()", 1)[0]
    script = """
const nodes = {};
const document = {getElementById: id => nodes[id] ||= {style: {}, innerHTML: '', classList: {remove() {}}}};
const escapeHtml = text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;');
const EMBEDDED_DATA = JSON.parse(require('fs').readFileSync(0, 'utf8'));
""" + renderer + """
if (EMBEDDED_DATA.run) {
  renderGrades(EMBEDDED_DATA.run);
  process.stdout.write(nodes['grades-content'].innerHTML);
} else {
  renderBenchmark();
  process.stdout.write(nodes['benchmark-content'].innerHTML);
}
"""
    return subprocess.run([node, "-e", script], input=json.dumps({"benchmark": data, "run": run}), text=True,
                          capture_output=True, check=True).stdout


def test_real_viewer_renders_unknown_without_zero_or_nan(tmp_path):
    write_run(tmp_path)
    write_run(tmp_path, "old_skill")
    data = generate_benchmark(tmp_path)
    html = render_benchmark(data)
    assert html.count("unknown") >= 8
    assert "0%" not in html and "NaN" not in html
    assert "0.0" not in html
    assert "grading.json is missing" in html


def test_real_viewer_uses_bound_roles_and_keeps_healthy_legacy_stats(tmp_path):
    healthy_pair(tmp_path, "new_skill", "old_skill")
    write_run(tmp_path, "a_aux", grading=grade((False,)))
    data = generate_benchmark(tmp_path)
    html = render_benchmark(data)
    assert "<th>New Skill</th><th>Old Skill</th>" in html
    assert "+0.50" in html and "1/1 observed" in html
    del data["comparison"]
    for group in data["run_summary"].values():
        for stat in group.values():
            if isinstance(stat, dict):
                stat.pop("count", None)
                stat.pop("total", None)
    html = render_benchmark(data)
    assert "100% ± 0%" in html and "50% ± 0%" in html
    assert "legacy; pairing not recorded" in html


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("extra_config", [False, True])
def test_unbound_custom_configs_keep_all_observed_summary_metrics(tmp_path, legacy, extra_config):
    write_run(tmp_path, "candidate_v2", grading=grade(),
              timing={"total_duration_seconds": 9, "total_tokens": 700})
    write_run(tmp_path, "baseline_v1", grading=grade((False,)),
              timing={"total_duration_seconds": 12, "total_tokens": 1000})
    if extra_config:
        write_run(tmp_path, "third_arm", grading=grade((False,)),
                  timing={"total_duration_seconds": 18, "total_tokens": 300})
    data = generate_benchmark(tmp_path)
    if legacy:
        del data["comparison"]
        for name, group in data["run_summary"].items():
            if name != "delta":
                for stat in group.values():
                    stat.pop("count", None)
                    stat.pop("total", None)
    # A saved delta without role binding is not evidence, even when non-null.
    data["run_summary"]["delta"] = {
        "pass_rate": "+9.99", "time_seconds": "+987.6", "tokens": "+999999",
    }
    table = render_benchmark(data).split("</table>", 1)[0]
    assert "<th>Baseline V1</th>" in table and "<th>Candidate V2</th>" in table
    assert "<td>0% ± 0%" in table and "<td>100% ± 0%" in table
    assert "Time (s)" in table and "12.0 ± 0.0" in table and "9.0 ± 0.0" in table
    assert "Tokens" in table and "1000.0 ± 0.0" in table and "700.0 ± 0.0" in table
    assert "+9.99" not in table and "+987.6" not in table and "+999999" not in table
    assert table.count("unknown") == 3
    if extra_config:
        assert "<th>Third Arm</th>" in table
        assert "18.0 ± 0.0" in table and "300.0 ± 0.0" in table


def test_bound_custom_pair_keeps_other_config_stats_and_labels_delta_pair(tmp_path):
    healthy_pair(tmp_path, "candidate_v2", "baseline_v1")
    write_run(tmp_path, "third_arm", grading=grade((False,)),
              timing={"total_duration_seconds": 18, "total_tokens": 300})
    data = generate_benchmark(tmp_path, candidate="candidate_v2", baseline="baseline_v1")
    table = render_benchmark(data).split("</table>", 1)[0]
    assert "<th>Candidate V2</th><th>Baseline V1</th><th>Third Arm</th>" in table
    assert "Candidate V2 − Baseline V1" in table
    assert "+0.50" in table and "-3.0s" in table and "-300" in table
    assert "18.0 ± 0.0" in table and "300.0 ± 0.0" in table


def test_output_grades_honor_unknown_aggregator_verdict(tmp_path):
    g = grade((False,))
    g["summary"]["pass_rate"] = 1
    write_run(tmp_path, grading=g)
    data = generate_benchmark(tmp_path)
    html = render_benchmark(data, run={"id": "eval-1-with_skill-run-1", "grading": g,
                                       "grading_status": "graded", "assertion_binding": "unbound"})
    assert "Grading unknown: invalid_grading" in html
    assert "100%" not in html and "0 passed" not in html


def test_output_grades_keep_healthy_zero_and_missing_counts_distinct(tmp_path):
    g = grade((False,))
    write_run(tmp_path, grading=g)
    data = generate_benchmark(tmp_path)
    html = render_benchmark(data, run={"id": "eval-1-with_skill-run-1", "grading": g,
                                       "grading_status": "graded", "assertion_binding": "unbound"})
    assert "0%" in html and "0 passed, 1 failed of 1" in html
    html = render_benchmark({}, run={"id": "legacy", "grading": {"summary": {}}})
    assert "Grading unknown: unknown" in html and "0 passed" not in html


def test_cli_writes_reopenable_unknown_report_and_validates_role_flags(tmp_path):
    write_run(tmp_path)
    command = [sys.executable, "-m", "scripts.aggregate_benchmark", str(tmp_path)]
    actual = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert actual.returncode == 0
    assert "Comparison:    unbound" in actual.stdout
    data = json.loads((tmp_path / "benchmark.json").read_text())
    assert len(data["runs"]) == 1
    assert data["runs"][0]["result"]["tokens"] is None
    assert "unknown" in (tmp_path / "benchmark.md").read_text()
    bad = subprocess.run([*command, "--candidate", "with_skill"], cwd=ROOT,
                         text=True, capture_output=True)
    assert bad.returncode == 2
    assert "both --candidate and --baseline" in bad.stderr


def test_documented_cli_role_flags_write_complete_custom_comparison(tmp_path):
    healthy_pair(tmp_path, "candidate_v2", "baseline_v1")
    command = [sys.executable, "-m", "scripts.aggregate_benchmark", str(tmp_path),
               "--candidate", "candidate_v2", "--baseline", "baseline_v1"]
    actual = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert actual.returncode == 0
    data = json.loads((tmp_path / "benchmark.json").read_text())
    assert data["comparison"]["candidate"] == "candidate_v2"
    assert data["comparison"]["baseline"] == "baseline_v1"
    assert data["comparison"]["status"] == "complete"
    assert data["run_summary"]["delta"]["tokens"] == "-300"
    assert "Comparison:    complete" in actual.stdout


@pytest.mark.parametrize("target", [None, "assertion", {}, [""], [None]])
def test_malformed_canonical_target_retains_cost_and_attempts(tmp_path, target):
    healthy_pair(tmp_path)
    (tmp_path / "eval-1/eval_metadata.json").write_text(json.dumps({"assertions": target}))
    data = generate_benchmark(tmp_path)
    assert len(data["runs"]) == 2
    assert all(r["assertion_binding"] == "invalid_expected" for r in data["runs"])
    assert all(r["result"]["pass_rate"] is None for r in data["runs"])
    assert all(r["result"]["tokens"] is not None for r in data["runs"])
    assert all(v is None for v in data["run_summary"]["delta"].values())


@pytest.mark.parametrize("target", [[], "absent"])
def test_legacy_target_binding_is_reported_without_losing_numeric_comparison(tmp_path, target):
    healthy_pair(tmp_path)
    metadata = {} if target == "absent" else {"assertions": target}
    (tmp_path / "eval-1/eval_metadata.json").write_text(json.dumps(metadata))
    data = generate_benchmark(tmp_path)
    assert all(r["assertion_binding"] == "unbound" for r in data["runs"])
    assert data["comparison"]["status"] == "complete"
    assert "Unbound assertions" in generate_markdown(data)
    assert "Unbound assertions" in render_benchmark(data)


@pytest.mark.parametrize("variant", ["exact", "reordered", "wrong_case", "subset", "duplicate", "extra"])
def test_canonical_assertion_identity_controls_rate_but_preserves_cost(tmp_path, variant):
    evals = json.loads((ROOT / "evals/evals.json").read_text())["evals"]
    target = evals[1]["expectations"]
    texts = {"exact": target, "reordered": target[::-1],
             "wrong_case": evals[2]["expectations"], "subset": target[:1],
             "duplicate": [target[0]] * len(target), "extra": [*target, "Extra"]}[variant]
    def graded(texts, verdict):
        g = grade([verdict] * len(texts))
        for item, text in zip(g["expectations"], texts):
            item["text"] = text
        return g
    write_run(tmp_path, grading=graded(texts, True),
              timing={"total_tokens": 700, "total_duration_seconds": 9})
    write_run(tmp_path, "old_skill", grading=graded(target, False),
              timing={"total_tokens": 1000, "total_duration_seconds": 12})
    (tmp_path / "eval-1/eval_metadata.json").write_text(json.dumps({"assertions": target}))
    data = generate_benchmark(tmp_path)
    candidate = next(r for r in data["runs"] if r["configuration"] == "with_skill")
    assert len(data["runs"]) == 2 and candidate["result"]["tokens"] == 700
    assert candidate["result"]["time_seconds"] == 9
    if variant in {"exact", "reordered"}:
        assert candidate["assertion_binding"] == "bound"
        assert candidate["result"]["pass_rate"] == 1
        assert data["run_summary"]["delta"]["pass_rate"] == "+1.00"
    else:
        assert candidate["assertion_binding"] == "mismatch"
        assert candidate["grading_status"] == "invalid_grading" and candidate["issues"]
        assert candidate["result"]["pass_rate"] is None
        assert data["comparison"]["status"] == "incomplete"
        assert all(v is None for v in data["run_summary"]["delta"].values())


@pytest.mark.parametrize("valid", [True, False])
def test_absolute_aggregate_cli_and_dynamic_import_are_bundle_bound(tmp_path, valid):
    workspace = tmp_path / "workspace"
    healthy_pair(workspace)
    target = ["Outcome 0"] if valid else ["Different outcome"]
    (workspace / "eval-1/eval_metadata.json").write_text(json.dumps({"assertions": target}))
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    entry = ROOT / "scripts/aggregate_benchmark.py"
    cli = subprocess.run([sys.executable, str(entry), str(workspace)], cwd=cwd,
                         env=env, text=True, capture_output=True)
    assert cli.returncode == 0, cli.stderr
    script = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('external_aggregate', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.generate_benchmark(Path(sys.argv[2]))))
"""
    dynamic = subprocess.run([sys.executable, "-c", script, str(entry), str(workspace)],
                             cwd=cwd, env=env, text=True, capture_output=True)
    assert dynamic.returncode == 0, dynamic.stderr
    for data in [json.loads((workspace / "benchmark.json").read_text()), json.loads(dynamic.stdout)]:
        candidate = next(r for r in data["runs"] if r["configuration"] == "with_skill")
        assert candidate["grading_status"] == ("graded" if valid else "invalid_grading")
        assert candidate["assertion_binding"] == ("bound" if valid else "mismatch")
        assert candidate["result"]["pass_rate"] == (1 if valid else None)
        assert candidate["result"]["tokens"] == 700
