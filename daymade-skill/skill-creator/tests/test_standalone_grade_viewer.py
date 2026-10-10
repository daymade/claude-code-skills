"""Execute the standalone builder and shipped JavaScript grade renderer."""

import ast
from contextlib import contextmanager
import importlib.util
import json
import os
import re
import signal
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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


@contextmanager
def _own_http_process(command, log_path, handoff=None):
    """Retain exact own-child handles; never discover or terminate listeners."""
    with log_path.open("w+") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                output = log_path.read_text()
                match = re.search(r"URL:\s+(http://localhost:\d+)", output)
                if match and (handoff is None or handoff.exists()):
                    yield process, match.group(1)
                    return
                assert process.poll() is None, output
                time.sleep(.01)
            pytest.fail(f"Own viewer startup timed out: {log_path.read_text()}")
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            assert process.poll() is not None


def _viewer_command(workspace, port, handoff):
    # Replace only browser handoff; actual main, binding, HTTP and writes run.
    wrapper = """
import importlib.util, sys
from pathlib import Path
builder, handoff, *args = sys.argv[1:]
spec = importlib.util.spec_from_file_location('own_viewer', builder)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.webbrowser.open = lambda url: Path(handoff).write_text(url)
sys.argv = [builder, *args]
module.main()
"""
    return [sys.executable, "-u", "-c", wrapper, str(BUILDER), str(handoff),
            str(workspace), "--port", str(port)]


def _http_get(url):
    with urlopen(url, timeout=2) as response:
        assert response.status == 200
        return response.read()


def _check_own_viewer(url, handoff, workspace, output_path, marker):
    assert url == handoff.read_text()
    assert urlparse(url).port > 0
    assert marker.encode() in _http_get(url)
    payload = {"reviews": [{"run_id":"own-run", "feedback":"own feedback marker"}]}
    request = Request(url + "/api/feedback", data=json.dumps(payload).encode(),
                      headers={"Content-Type":"application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        assert response.status == 200
        assert json.loads(response.read()) == {"ok":True}
    assert json.loads((workspace / "feedback.json").read_text()) == payload
    assert json.loads(_http_get(url + "/api/feedback")) == payload
    output_path.write_text(marker + " refreshed")
    assert (marker + " refreshed").encode() in _http_get(url)


def test_busy_port_preserves_incumbent_and_routes_own_feedback_and_refresh(tmp_path):
    incumbent = tmp_path / "incumbent"
    incumbent.mkdir()
    marker = incumbent / "marker.txt"
    marker.write_text("unique incumbent listener marker")
    old_feedback = incumbent / "feedback.json"
    old_feedback.write_text('{"reviews":[{"feedback":"incumbent untouched"}]}')
    original = {p.name:p.read_bytes() for p in incumbent.iterdir()}
    server = """
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import sys
marker = Path(sys.argv[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = marker.read_bytes()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass
server = HTTPServer(('127.0.0.1', 0), Handler)
print(f'URL: http://localhost:{server.server_address[1]}', flush=True)
try: server.serve_forever()
except KeyboardInterrupt: pass
finally: server.server_close()
"""
    with _own_http_process([sys.executable,"-u","-c",server,str(marker)],
                           tmp_path / "incumbent.log") as (old_process, old_url):
        assert _http_get(old_url) == marker.read_bytes()
        workspace = tmp_path / "reviewer"
        target = run_fixture(workspace, receipt())
        output = target / "outputs/result.txt"
        output.write_text("unique new reviewer marker")
        handoff = tmp_path / "viewer-handoff.txt"
        with _own_http_process(_viewer_command(workspace, urlparse(old_url).port, handoff),
                               tmp_path / "viewer.log", handoff) as (process, url):
            assert urlparse(url).port != urlparse(old_url).port
            assert old_process.poll() is None
            assert _http_get(old_url) == original["marker.txt"]
            _check_own_viewer(url, handoff, workspace, output, "unique new reviewer marker")
            assert process.poll() is None and old_process.poll() is None
            assert _http_get(old_url) == original["marker.txt"]
            assert {p.name:p.read_bytes() for p in incumbent.iterdir()} == original


def test_port_zero_advertises_and_hands_off_actual_usable_endpoint(tmp_path):
    workspace = tmp_path / "reviewer"
    target = run_fixture(workspace, receipt())
    output = target / "outputs/result.txt"
    output.write_text("unique zero-port reviewer marker")
    handoff = tmp_path / "handoff.txt"
    with _own_http_process(_viewer_command(workspace, 0, handoff),
                           tmp_path / "viewer.log", handoff) as (process, url):
        _check_own_viewer(url, handoff, workspace, output, "unique zero-port reviewer marker")
        assert process.poll() is None


def test_static_viewer_does_not_bind_or_open_browser_and_default_stays_3117(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    target = run_fixture(workspace, receipt())
    (target / "outputs/result.txt").write_text("unique static marker")
    output = tmp_path / "static.html"
    def forbidden(*args, **kwargs):
        pytest.fail("static generation must not bind or open a browser")
    monkeypatch.setattr(viewer, "HTTPServer", forbidden)
    monkeypatch.setattr(viewer.webbrowser, "open", forbidden)
    monkeypatch.setattr(sys, "argv", [str(BUILDER), str(workspace), "--static", str(output)])
    with pytest.raises(SystemExit) as exit_info:
        viewer.main()
    assert exit_info.value.code == 0
    assert "unique static marker" in output.read_text()
    # Read the declaration without occupying the user's shared default port.
    port_call = next(node for node in ast.walk(ast.parse(BUILDER.read_text()))
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                     and node.func.attr == "add_argument"
                     and any(isinstance(arg, ast.Constant) and arg.value == "--port" for arg in node.args))
    assert next(keyword.value.value for keyword in port_call.keywords if keyword.arg == "default") == 3117
