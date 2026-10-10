"""Exercise real trigger pipe consumption with a synthetic CLI, never a model."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts import improve_description as improve
from scripts import run_eval as evaluate


@pytest.fixture
def probe(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "record.json"
    executable = bin_dir / "claude"
    executable.write_text(f"#!{sys.executable}\n" + r'''
import json, os, sys, time
from pathlib import Path
case = sys.argv[2]
path = next((Path.cwd()/'.claude'/'commands').glob('*.md'))
target = path.stem
Path(os.environ['PROBE_RECORD']).write_text(json.dumps({'cwd':str(Path.cwd())}))
def se(kind, **rest): return {'type':'stream_event', 'event':{'type':kind, **rest}}
def start(name='Skill', index=0, initial=None):
    return se('content_block_start',index=index,content_block={'type':'tool_use','name':name,'input':initial or {}})
def delta(text,index=0): return se('content_block_delta',index=index,delta={'type':'input_json_delta','partial_json':text})
def stop(index=0): return se('content_block_stop',index=index)
def tool(name, value, index=0):
    key = 'skill' if name=='Skill' else ('file_path' if name=='Read' else 'command')
    return [start(name,index),delta(json.dumps({key:value}),index),stop(index)]
success = {'type':'result','subtype':'success','is_error':False}
error = {'type':'result','subtype':'error_during_execution','is_error':True,'errors':['synthetic execution failed']}
streams = {
 'skill':tool('Skill',target),
 'read':tool('Read',str(path)),
 'read_relative':tool('Read',str(path.relative_to(Path.cwd()))),
 'other_then_skill':tool('Bash','printf noop')+tool('Skill','unrelated')+tool('Read','/unrelated.md')+[se('message_stop')]+tool('Skill',target),
 'assistant': [{'type':'assistant','message':{'content':[{'type':'tool_use','name':'Skill','input':{'skill':'other'}},{'type':'tool_use','name':'Read','input':{'file_path':str(path)}}]}}],
 'escaped':[start(),delta(json.dumps({'skill':target}).replace('synthetic',r'\u0073ynthetic')),stop()],
 'initial':[start(initial={'skill':target}),stop()],
 'interleaved':[start(),delta('{"skill":"'+target[:5]),start('Read',1),delta('{"file_path":"/other.md"}',1),stop(1),delta(target[5:]+'"}'),stop()],
 'note':tool('Skill','unrelated')[:-2]+[delta(json.dumps({'skill':'unrelated','note':target})),stop()],
 'substring':tool('Skill',target+'-other'),
 'namespace':tool('Skill','other:'+target),
 'foreign_read':tool('Read','/foreign/'+path.name),
 'other_field': [start('Read'),delta(json.dumps({'file_path':'/other.md','note':str(path)})),stop()],
 'half_json':[start(),delta('{"skill":"'+target),delta('-other"}'),stop()],
 'unfinished':[start(),delta(json.dumps({'skill':target}))],
 'malformed_tool':[start(),delta('{"skill":'),stop()],
 'missing_index':[{'type':'stream_event','event':{'type':'content_block_start','content_block':{'type':'tool_use','name':'Skill','input':{'skill':target}}}}],
 'error':[error],
 'missing_result':[],
 'malformed':['{invalid'],
 'malformed_event':[{},success],
 'malformed_identity':[start(initial={'skill':None}),stop(),success],
 'malformed_tail':[success,'{invalid'],
 'success_exit7':[success],
 'success_hangs':[success],
 'success_stdout_closed':[success],
 'large_stderr':[success],
 'stderr_error':[error],
 'target_error':tool('Skill',target)+[error],
 'target_exit7':tool('Skill',target),
 'target_hangs':tool('Skill',target),
 'eof_tail':tool('Skill',target),
 'negative_tail':[success],
 'negative':[],
}
events = streams[case]
if case in ('large_stderr','stderr_error'):
    sys.stderr.write('diagnostic-padding '*20000+'\nsynthetic stderr tail\n');sys.stderr.flush()
if case not in ('error','stderr_error','missing_result','malformed','malformed_tool','unfinished','malformed_tail','target_error','eof_tail','missing_index'):
    events += [success]
data='\n'.join(e if isinstance(e,str) else json.dumps(e) for e in events)
if case not in ('eof_tail','negative_tail'): data+='\n'
sys.stdout.write(data);sys.stdout.flush()
if case=='success_stdout_closed': os.close(1)
if case in ('success_hangs','target_hangs','success_stdout_closed'): time.sleep(5)
if case.endswith('exit7'): sys.exit(7)
''')
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PROBE_RECORD", str(record))

    def run(case, timeout=1):
        try:
            return evaluate.run_single_query(case, "synthetic-demo", "description", timeout, str(tmp_path))
        finally:
            if record.exists():
                assert not Path(json.loads(record.read_text())["cwd"]).exists()
    return run


@pytest.mark.parametrize("case", ["skill", "read", "read_relative", "other_then_skill", "assistant", "escaped", "initial", "interleaved", "target_error", "target_exit7", "target_hangs", "eof_tail"])
def test_complete_exact_target_proves_invocation_early(probe, case):
    assert probe(case, timeout=.8) is True


@pytest.mark.parametrize("case", ["note", "substring", "namespace", "foreign_read", "other_field", "half_json", "negative", "negative_tail", "large_stderr"])
def test_complete_negative_requires_real_candidate_identity(probe, case):
    assert probe(case) is False


@pytest.mark.parametrize("case, diagnostic", [
    ("missing_index", "no integer index"), ("unfinished", "unfinished tool input"), ("malformed_tool", "malformed stream"),
    ("error", "synthetic execution failed"), ("missing_result", "missing successful result"),
    ("malformed", "malformed stream"), ("malformed_event", "stream record has no type"),
    ("malformed_identity", "Skill input has no string skill identity"), ("malformed_tail", "malformed stream"),
    ("success_exit7", "exited 7"), ("success_hangs", "timed out"),
    ("success_stdout_closed", "timed out"), ("stderr_error", "synthetic stderr tail"),
])
def test_invalid_measurement_is_error_not_false(probe, case, diagnostic):
    with pytest.raises(RuntimeError, match=diagnostic) as error:
        probe(case, timeout=.3)
    assert error.value.__cause__ is not None


def test_missing_cli_retains_original_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="FileNotFoundError") as error:
        evaluate.run_single_query("q", "synthetic", "desc", 1, str(tmp_path))
    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_aggregate_retains_valid_observations_and_errors(monkeypatch, tmp_path):
    calls = {}
    def observed(query, *args):
        calls[query] = calls.get(query, 0) + 1
        if query == "mixed" and calls[query] == 1:
            return True
        if query == "negative":
            return False
        raise RuntimeError("synthetic measurement unavailable")
    monkeypatch.setattr(evaluate, "ProcessPoolExecutor", ThreadPoolExecutor)
    monkeypatch.setattr(evaluate, "run_single_query", observed)
    result = evaluate.run_eval([
        {"query":"mixed","should_trigger":True},
        {"query":"missing","should_trigger":False},
        {"query":"negative","should_trigger":False},
    ], "synthetic", "description", 1, 1, tmp_path, runs_per_query=2)
    rows = {row["query"]:row for row in result["results"]}
    assert rows["mixed"]["trigger_rate"] == 1
    assert rows["mixed"]["runs"] == 1
    assert rows["mixed"]["attempted_runs"] == 2
    assert rows["mixed"]["errors"] == 1
    assert rows["mixed"]["pass"] is None
    assert rows["missing"]["trigger_rate"] is None
    assert rows["missing"]["runs"] == 0
    assert rows["missing"]["pass"] is None
    assert rows["missing"]["attempts"][0]["error"] == "synthetic measurement unavailable"
    assert rows["negative"]["pass"] is True
    assert result["summary"] == {"total":3,"passed":1,"failed":0,"incomplete":2}
    assert result["error_count"] == 3


def test_improver_rejects_unknown_measurements_without_model_call(monkeypatch):
    monkeypatch.setattr(improve, "_call_claude", lambda *a: pytest.fail("must not call model"))
    with pytest.raises(ValueError, match="Incomplete trigger measurements"):
        improve.improve_description("synthetic", "body", "desc", {
            "results":[{"query":"unknown negative","should_trigger":False,"pass":None,"runs":0,"triggers":0,"errors":1}],
            "summary":{"passed":0,"total":1},
        }, [], "synthetic-model")


def test_zero_attempts_remain_unknown_not_zero_trigger_rate(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluate, "ProcessPoolExecutor", ThreadPoolExecutor)
    result = evaluate.run_eval([{"query":"unmeasured","should_trigger":False}],
                               "synthetic", "desc", 1, 1, tmp_path, runs_per_query=0)
    row = result["results"][0]
    assert row["attempted_runs"] == row["runs"] == row["errors"] == 0
    assert row["trigger_rate"] is None
    assert row["pass"] is None
    assert result["summary"]["incomplete"] == 1


def test_improver_skips_unknown_history_and_preserves_real_mismatches(monkeypatch):
    prompts = []
    monkeypatch.setattr(improve, "_call_claude", lambda prompt, model: prompts.append(prompt) or "<new_description>new</new_description>")
    valid = {"query":"valid mismatch","should_trigger":True,"pass":False,"runs":1,"triggers":0}
    result = improve.improve_description("synthetic", "body", "desc", {
        "results":[valid],"summary":{"passed":0,"total":1},
    }, [{"description":"missing data","train_results":[{"query":"unknown","pass":None}]}], "synthetic-model")
    assert result == "new"
    assert "FAILED TO TRIGGER" in prompts[0]
    assert "valid mismatch" in prompts[0]
    assert "missing data" not in prompts[0]
    assert '"unknown"' not in prompts[0]
