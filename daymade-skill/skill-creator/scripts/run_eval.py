#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger (read the skill)
for a set of queries. Outputs results as JSON.
"""

import argparse
import codecs
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts.utils import parse_skill_md


def find_project_root() -> Path:
    """Find the project root by walking up from cwd looking for .claude/.

    Mimics how Claude Code discovers its project root, so the command file
    we create ends up where claude -p will look for it.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    project_root: str,
    model: str | None = None,
) -> bool:
    """Run a single query and return whether the skill was triggered.

    Creates a command file in an isolated temporary directory's .claude/commands/
    so it appears in Claude's available_skills list, then runs `claude -p` with
    the raw query. Each call gets its own throwaway directory rather than writing
    into the shared project directory: run_eval() fans this out across up to
    num_workers concurrent calls (default 10), and if they all wrote into the same
    .claude/commands/, every claude -p subprocess would see every other in-flight
    worker's synthetic candidate as a competing "available_skill" too, diluting
    triggering and producing a systematically depressed, noisy trigger rate that
    has nothing to do with the description under test. Isolating each probe also
    means a run never leaves stray files in the real project being evaluated.
    `project_root` is accepted for backward compatibility with existing callers
    and tests but is intentionally unused here now that probes are self-contained.
    Uses --include-partial-messages to detect triggering early from
    complete tool-input blocks rather than waiting for the full assistant
    message, which only arrives after tool execution. True proves invocation
    only; False requires a successful result, complete EOF and exit code zero.
    Raise on incomplete or failed measurements with a bounded stderr diagnostic.
    """
    unique_id = uuid.uuid4().hex[:8]
    clean_name = f"{skill_name}-skill-{unique_id}"
    probe_dir = Path(tempfile.mkdtemp(prefix="skill-eval-probe-"))
    project_commands_dir = probe_dir / ".claude" / "commands"
    command_file = project_commands_dir / f"{clean_name}.md"

    try:
        project_commands_dir.mkdir(parents=True, exist_ok=True)
        # Use YAML block scalar to avoid breaking on quotes in description
        indented_desc = "\n  ".join(skill_description.split("\n"))
        command_content = (
            f"---\n"
            f"description: |\n"
            f"  {indented_desc}\n"
            f"---\n\n"
            f"# {skill_name}\n\n"
            f"This skill handles: {skill_description}\n"
        )
        command_file.write_text(command_content)

        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session. The guard is for interactive terminal conflicts;
        # programmatic subprocess usage is safe.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        # A file cannot fill a stderr pipe and deadlock the child. Read its
        # bounded tail on failure, after cleaning up only this probe's child.
        with tempfile.TemporaryFile() as stderr_file:
            process = None
            try:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=stderr_file,
                    cwd=probe_dir, env=env,
                )
                deadline = time.monotonic() + timeout
                decoder = codecs.getincrementaldecoder("utf-8")()
                buffer = ""
                pending = {}
                protocol_errors = []
                success_result = False
                eof = False

                def matches(tool_name, tool_input):
                    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
                        raise ValueError("tool name/input has invalid type")
                    if tool_name == "Skill":
                        if not isinstance(tool_input.get("skill"), str):
                            raise ValueError("Skill input has no string skill identity")
                        return tool_input["skill"] == clean_name
                    if tool_name == "Read":
                        path = tool_input.get("file_path")
                        if not isinstance(path, str) or not path:
                            raise ValueError("Read input has no string file_path identity")
                        if path:
                            candidate = Path(path)
                            if not candidate.is_absolute():
                                candidate = probe_dir / candidate
                            return candidate.resolve() == command_file.resolve()
                    return False

                def consume(line):
                    nonlocal success_result
                    if not line.strip():
                        return False
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError("stream record is not an object")
                        kind = event.get("type")
                        if not isinstance(kind, str) or not kind:
                            raise ValueError("stream record has no type")
                        if kind == "stream_event":
                            se = event["event"]
                            event_type = se.get("type")
                            index = se.get("index")
                            if event_type in ("content_block_start", "content_block_delta", "content_block_stop") and type(index) is not int:
                                raise ValueError("content block has no integer index")
                            if event_type == "content_block_start":
                                cb = se["content_block"]
                                if cb.get("type") == "tool_use":
                                    if index in pending:
                                        raise ValueError("tool index restarted before block stop")
                                    pending[index] = {"name": cb.get("name"),
                                                      "input": cb.get("input", {}), "json": ""}
                            elif event_type == "content_block_delta":
                                delta = se["delta"]
                                if delta.get("type") == "input_json_delta":
                                    if index not in pending:
                                        raise ValueError("tool input delta has no block start")
                                    pending[index]["json"] += delta["partial_json"]
                            elif event_type == "content_block_stop" and index in pending:
                                block = pending.pop(index)
                                tool_input = (json.loads(block["json"]) if block["json"]
                                              else block["input"])
                                if not isinstance(tool_input, dict):
                                    raise ValueError("tool input is not an object")
                                return matches(block["name"], tool_input)
                        elif kind == "assistant":
                            for item in event["message"]["content"]:
                                if item.get("type") == "tool_use" and matches(
                                    item.get("name"), item.get("input")
                                ):
                                    return True
                        elif kind == "result":
                            if (event.get("subtype") == "success" and event.get("is_error", False) is False
                                    and not event.get("errors")):
                                success_result = True
                            else:
                                protocol_errors.append("unsuccessful result: " + json.dumps(event))
                    except (ValueError, KeyError, TypeError, AttributeError) as exc:
                        protocol_errors.append(f"malformed stream record: {exc}")
                    return False

                while True:
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if consume(line):
                            # Invocation is now proven. Do not pay for the tool
                            # or task to finish; cleanup termination is expected.
                            return True
                    if eof:
                        if buffer:
                            if consume(buffer):
                                return True
                            buffer = ""
                        returncode = process.poll()
                        if returncode is not None:
                            if pending:
                                protocol_errors.append("unfinished tool input at EOF")
                            if returncode != 0:
                                protocol_errors.append(f"claude exited {returncode}")
                            if not success_result:
                                protocol_errors.append("missing successful result")
                            if protocol_errors:
                                raise RuntimeError("; ".join(protocol_errors))
                            return False
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"claude trigger probe timed out after {timeout}s")
                    if eof:
                        # stdout may close before process exit. Keep the same
                        # deadline rather than accepting result or resetting it.
                        try:
                            process.wait(timeout=remaining)
                        except subprocess.TimeoutExpired as exc:
                            raise TimeoutError(f"claude trigger probe timed out after {timeout}s") from exc
                        continue
                    ready, _, _ = select.select([process.stdout], [], [], min(remaining, 0.1))
                    if ready:
                        chunk = os.read(process.stdout.fileno(), 8192)
                        if chunk:
                            buffer += decoder.decode(chunk)
                        else:
                            buffer += decoder.decode(b"", final=True)
                            eof = True
            except Exception as exc:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                stderr_file.seek(0, os.SEEK_END)
                stderr_file.seek(max(0, stderr_file.tell() - 8192))
                diagnostic = stderr_file.read().decode("utf-8", errors="replace").strip()
                detail = f"{type(exc).__name__}: {exc}"
                if diagnostic:
                    detail += f"\nstderr (tail): {diagnostic}"
                raise RuntimeError(detail) from exc
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    process.stdout.close()

    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict:
    """Run the full eval set and return results."""
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    str(project_root),
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {item["query"]: [] for item in eval_set}
        query_errors: dict[str, int] = {item["query"]: 0 for item in eval_set}
        query_attempts: dict[str, list[dict]] = {item["query"]: [] for item in eval_set}
        query_items: dict[str, dict] = {item["query"]: item for item in eval_set}
        error_count = 0
        for future in as_completed(future_to_info):
            item, run_idx = future_to_info[future]
            query = item["query"]
            try:
                observed = future.result()
                if type(observed) is not bool:
                    raise ValueError("trigger probe returned no boolean observation")
                query_triggers[query].append(observed)
                query_attempts[query].append({"run_index": run_idx, "triggered": observed, "error": None})
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_attempts[query].append({"run_index": run_idx, "triggered": None, "error": str(e)})
                query_errors[query] += 1
                error_count += 1

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers) if triggers else None
        should_trigger = item["should_trigger"]
        if query_errors[query] or trigger_rate is None:
            did_pass = None
        elif should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
            "errors": query_errors[query],
            "attempted_runs": len(query_attempts[query]),
            "attempts": sorted(query_attempts[query], key=lambda a: a["run_index"]),
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"] is True)
    failed = sum(1 for r in results if r["pass"] is False)
    incomplete = sum(1 for r in results if r["pass"] is None)
    total = len(results)

    return {
        "skill_name": skill_name,
        "description": description,
        "results": results,
        "error_count": error_count,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "incomplete": incomplete,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description
    project_root = find_project_root()

    if args.verbose:
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=project_root,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "INCOMPLETE" if r["pass"] is None else ("PASS" if r["pass"] else "FAIL")
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
