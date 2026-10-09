#!/usr/bin/env python3
"""
Aggregate individual run results into benchmark summary statistics.

Reads grading.json files from run directories and produces:
- run_summary with mean, stddev, min, max for each metric
- coverage and paired candidate-minus-baseline deltas; missing data stays unknown

Usage:
    uv run --frozen python -m scripts.aggregate_benchmark <benchmark_dir>

Example:
    uv run --frozen python -m scripts.aggregate_benchmark benchmarks/2026-01-15T10-30-00/

The script supports two directory layouts:

    Workspace layout (from skill-creator iterations):
    <benchmark_dir>/
    └── eval-N/
        ├── with_skill/
        │   ├── run-1/grading.json
        │   └── run-2/grading.json
        └── without_skill/
            ├── run-1/grading.json
            └── run-2/grading.json

    Legacy layout (with runs/ subdirectory):
    <benchmark_dir>/
    └── runs/
        └── eval-N/
            ├── with_skill/
            │   └── run-1/grading.json
            └── without_skill/
                └── run-1/grading.json
"""

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


METRICS = ("pass_rate", "time_seconds", "tokens")


def calculate_stats(values: list[float], total: int | None = None) -> dict:
    """Summarize observed values; retain missing coverage instead of imputing zero."""
    n = len(values)
    stats = {"mean": None, "stddev": None, "min": None, "max": None,
             "count": n, "total": n if total is None else total}
    if n:
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 0
        stats.update(mean=round(mean, 4), stddev=round(math.sqrt(variance), 4),
                     min=round(min(values), 4), max=round(max(values), 4))
    return stats


def _number(value, integer: bool = False) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0
            and (not integer or isinstance(value, int)))


def _read_object(path: Path, issues: list[str]) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object")
        return data
    except (OSError, ValueError) as exc:
        issues.append(f"{path.name}: {exc}")
        return None


def _summary(grading: dict, issues: list[str]) -> dict | None:
    summary = grading.get("summary")
    expectations = grading.get("expectations")
    if not isinstance(summary, dict) or not isinstance(expectations, list) or not expectations:
        issues.append("grading requires a summary and non-empty expectations")
        return None
    if any(not isinstance(exp, dict) or not isinstance(exp.get("passed"), bool)
           or not isinstance(exp.get("text"), str) or not exp["text"].strip()
           or not isinstance(exp.get("evidence"), str) or not exp["evidence"].strip()
           for exp in expectations):
        issues.append("expectations require text, boolean passed and evidence")
        return None
    passed = sum(exp["passed"] for exp in expectations)
    total = len(expectations)
    counts = {"passed": passed, "failed": total - passed, "total": total}
    if any(not _number(summary.get(k), integer=True) or summary[k] != v
           for k, v in counts.items()):
        issues.append("summary counts disagree with expectations")
        return None
    rate = summary.get("pass_rate")
    # Preserve healthy historical summaries rounded to two decimal places.
    if not _number(rate) or rate > 1 or abs(rate - passed / total) > 0.005001:
        issues.append("summary pass_rate disagrees with expectations")
        return None
    return {**counts, "pass_rate": rate}


def _measurement(sources: list[tuple[str, dict]], field: str,
                 issues: list[str], integer: bool = False) -> tuple:
    observations = []
    for label, data in sources:
        value = data.get(field)
        if value is None and field == "total_duration_seconds":
            millis = data.get("duration_ms")
            if millis is not None:
                if _number(millis):
                    value = millis / 1000
                    label += ".duration_ms/1000"
                else:
                    issues.append(f"{label}.duration_ms is invalid")
        else:
            label += "." + field
        if value is None:
            continue
        if not _number(value, integer):
            issues.append(f"{label} is invalid")
            continue
        scope_field = "time_scope" if field == "total_duration_seconds" else "token_scope"
        scope = data.get(scope_field, "unspecified")
        if not isinstance(scope, str) or not scope.strip():
            issues.append(f"{label}: invalid {scope_field}")
            continue
        observations.append((value, label, scope))
    if not observations:
        return None, None, None
    first = observations[0]
    if any(value != first[0] or scope != first[2] for value, _, scope in observations[1:]):
        issues.append(f"conflicting {field} observations or scopes")
        return None, None, None
    return first


def load_run_results(benchmark_dir: Path) -> dict:
    """Load every observed run directory, including missing or invalid grades."""
    runs_dir = benchmark_dir / "runs"
    search_dir = runs_dir if runs_dir.is_dir() else benchmark_dir
    results: dict[str, list] = {}
    for eval_idx, eval_dir in enumerate(sorted(search_dir.glob("eval-*"))):
        if not eval_dir.is_dir():
            continue
        eval_issues: list[str] = []
        metadata = _read_object(eval_dir / "eval_metadata.json", eval_issues) or {}
        match = re.fullmatch(r"eval-(\d+)", eval_dir.name)
        fallback_id = int(match[1]) if match else eval_idx
        eval_id = metadata.get("eval_id", fallback_id)
        if not isinstance(eval_id, int) or isinstance(eval_id, bool):
            eval_issues.append("eval_metadata.json: invalid eval_id")
            eval_id = fallback_id
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            for run_dir in sorted(config_dir.glob("run-*")):
                if not run_dir.is_dir():
                    continue
                issues = list(eval_issues)
                run_match = re.fullmatch(r"run-(\d+)", run_dir.name)
                run_number = int(run_match[1]) if run_match else None
                if run_number is None:
                    issues.append("invalid run directory number")
                grading_file = run_dir / "grading.json"
                grading = _read_object(grading_file, issues)
                summary = _summary(grading, issues) if grading is not None else None
                status = ("graded" if summary is not None else
                          "invalid_grading" if grading_file.exists() else "missing_grading")
                if status == "missing_grading":
                    issues.append("grading.json is missing; outcome is unknown")
                sources = []
                timing = _read_object(run_dir / "timing.json", issues)
                if timing is not None:
                    sources.append(("timing.json", timing))
                grading = grading or {}
                if isinstance(grading.get("timing"), dict):
                    sources.append(("grading.json.timing", grading["timing"]))
                seconds, time_source, time_scope = _measurement(
                    sources, "total_duration_seconds", issues)
                tokens, token_source, token_scope = _measurement(
                    sources, "total_tokens", issues, integer=True)
                metrics = grading.get("execution_metrics")
                metrics = metrics if isinstance(metrics, dict) else {}
                result = {
                    "eval_id": eval_id,
                    "eval_name": metadata.get("eval_name", eval_dir.name),
                    "run_number": run_number,
                    "run_id": run_dir.relative_to(benchmark_dir).as_posix(),
                    "grading_status": status,
                    "identity_valid": not eval_issues and run_number is not None,
                    **{key: summary[key] if summary else None
                       for key in ("pass_rate", "passed", "failed", "total")},
                    "time_seconds": seconds, "tokens": tokens,
                    "metric_sources": {"time_seconds": time_source, "tokens": token_source},
                    "metric_scopes": {"time_seconds": time_scope, "tokens": token_scope},
                    "expectations": [{key: exp[key] for key in ("text", "passed", "evidence")}
                                     for exp in grading["expectations"]] if summary else [],
                    "issues": issues,
                    "notes": [],
                }
                if not isinstance(result["expectations"], list):
                    result["expectations"] = []
                for target, source in (("tool_calls", "total_tool_calls"),
                                       ("errors", "errors_encountered"),
                                       ("output_chars", "output_chars")):
                    value = metrics.get(source)
                    result[target] = value if _number(value, integer=True) else None
                notes = grading.get("user_notes_summary")
                if isinstance(notes, dict):
                    for key in ("uncertainties", "needs_review", "workarounds"):
                        if isinstance(notes.get(key), list):
                            result["notes"].extend(n for n in notes[key] if isinstance(n, str))
                results.setdefault(config_dir.name, []).append(result)
    return results


def _bind_configs(results: dict, candidate: str | None, baseline: str | None) -> tuple:
    if (candidate is None) != (baseline is None):
        raise ValueError("supply both --candidate and --baseline")
    if candidate is not None:
        if candidate == baseline or candidate not in results or baseline not in results:
            raise ValueError("candidate and baseline must name distinct observed configurations")
        return candidate, baseline
    candidates = [c for c in ("with_skill", "new_skill") if c in results]
    baselines = [c for c in ("old_skill", "without_skill") if c in results]
    if len(candidates) == len(baselines) == 1:
        return candidates[0], baselines[0]
    return None, None


def compare_results(results: dict, candidate: str | None = None,
                    baseline: str | None = None) -> tuple[dict, dict]:
    """Calculate deltas only for explicitly bound, complete, graded run pairs."""
    candidate, baseline = _bind_configs(results, candidate, baseline)
    delta = {metric: None for metric in METRICS}
    comparison = {"candidate": candidate, "baseline": baseline,
                  "status": "unbound", "paired_runs": 0, "unmatched_runs": [],
                  "issues": [], "metrics": {}}
    if candidate is None:
        comparison["issues"].append("comparison roles are missing or ambiguous; supply both role flags")
        return delta, comparison
    indexes = []
    identity_ok = True
    for config in (candidate, baseline):
        index = {}
        for run in results[config]:
            key = (run["eval_id"], run["run_number"])
            if key in index or not run.get("identity_valid", True):
                identity_ok = False
                comparison["issues"].append(f"{config}: duplicate or invalid run identity {key}")
            index[key] = run
        indexes.append(index)
    left, right = indexes
    common = left.keys() & right.keys()
    comparison["paired_runs"] = len(common)
    comparison["unmatched_runs"] = [
        run["run_id"] for index, other in ((left, right), (right, left))
        for key, run in index.items() if key not in other]
    pair_gate = (identity_ok and bool(common) and left.keys() == right.keys()
                 and all(left[k]["pass_rate"] is not None
                         and right[k]["pass_rate"] is not None for k in common))
    if not pair_gate:
        comparison["issues"].append("incomplete identities, pairing or grading; deltas withheld")
    for metric in METRICS:
        pairs = [(left[k], right[k]) for k in common]
        known = [(a, b) for a, b in pairs
                 if a.get(metric) is not None and b.get(metric) is not None]
        scopes = {r.get("metric_scopes", {}).get(metric, "unspecified")
                  for pair in known for r in pair} if metric != "pass_rate" else set()
        complete = pair_gate and len(known) == len(pairs) and len(scopes) <= 1
        comparison["metrics"][metric] = {
            "status": "complete" if complete else "unknown",
            "paired_count": len(known), "total_pairs": len(pairs),
            "scope": next(iter(scopes)) if len(scopes) == 1 else None,
        }
        if complete:
            value = sum(a[metric] - b[metric] for a, b in known) / len(known)
            precision = {"pass_rate": 2, "time_seconds": 1, "tokens": 0}[metric]
            delta[metric] = f"{value:+.{precision}f}"
        elif len(scopes) > 1:
            comparison["issues"].append(f"{metric}: mixed measurement scopes; delta withheld")
    comparison["status"] = ("complete" if all(v["status"] == "complete"
                                             for v in comparison["metrics"].values())
                            else "incomplete")
    return delta, comparison


def aggregate_results(results: dict, candidate: str | None = None,
                      baseline: str | None = None) -> dict:
    """Summarize observed values with coverage and a bound paired delta."""
    summary = {
        config: {metric: calculate_stats([r[metric] for r in runs if r.get(metric) is not None],
                                        len(runs)) for metric in METRICS}
        for config, runs in results.items()
    }
    summary["delta"] = compare_results(results, candidate, baseline)[0]
    return summary


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "",
                       candidate: str | None = None, baseline: str | None = None) -> dict:
    results = load_run_results(benchmark_dir)
    summary = aggregate_results(results, candidate, baseline)
    _, comparison = compare_results(results, candidate, baseline)
    runs = []
    counts: dict[int, dict] = {}
    for config, config_runs in results.items():
        for run in config_runs:
            counts.setdefault(run["eval_id"], {}).setdefault(config, 0)
            counts[run["eval_id"]][config] += 1
            runs.append({
                **{key: run[key] for key in ("eval_id", "eval_name", "run_number", "run_id",
                                            "grading_status", "metric_sources", "metric_scopes",
                                            "issues", "expectations", "notes")},
                "configuration": config,
                "result": {key: run[key] for key in (*METRICS, "passed", "failed", "total",
                                                     "tool_calls", "errors", "output_chars")},
            })
    observed_counts = {n for groups in counts.values() for n in groups.values()}
    uniform = (len(observed_counts) == 1
               and all(set(groups) == set(results) for groups in counts.values()))
    return {
        "metadata": {
            "skill_name": skill_name or "<skill-name>",
            "skill_path": skill_path or "<path/to/skill>",
            "executor_model": "<model-name>", "analyzer_model": "<model-name>",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evals_run": sorted(counts),
            "runs_per_configuration": next(iter(observed_counts)) if uniform else None,
            "attempts_per_configuration": {c: len(rs) for c, rs in results.items()},
            "runs_per_eval": counts,
        },
        "runs": runs, "run_summary": summary, "comparison": comparison,
        "notes": [],
    }


def _format_stat(stat: dict | None, metric: str) -> str:
    if not stat or stat.get("mean") is None:
        return "unknown"
    mean, stddev = stat["mean"], stat["stddev"]
    if metric == "pass_rate":
        value = f"{mean * 100:.0f}% ± {stddev * 100:.0f}%"
    elif metric == "time_seconds":
        value = f"{mean:.1f}s ± {stddev:.1f}s"
    else:
        value = f"{mean:.0f} ± {stddev:.0f}"
    if "count" in stat:
        value += f" ({stat['count']}/{stat['total']} observed)"
    return value


def generate_markdown(benchmark: dict) -> str:
    """Render unknown values and coverage without presenting missing data as gains."""
    metadata, summary = benchmark["metadata"], benchmark["run_summary"]
    comparison = benchmark.get("comparison", {})
    candidate, baseline = comparison.get("candidate"), comparison.get("baseline")
    if not comparison:
        candidate, baseline = _bind_configs(summary, None, None)
    configs = [c for c in summary if c != "delta"]
    # Show all groups when roles cannot be bound; withhold the unlabeled delta.
    displayed = [candidate, baseline] if candidate and baseline else configs
    lines = [f"# Skill Benchmark: {metadata['skill_name']}", "",
             f"**Model**: {metadata['executor_model']}",
             f"**Date**: {metadata['timestamp']}",
             f"**Evals**: {', '.join(map(str, metadata['evals_run']))}",
             f"**Observed attempts**: {metadata.get('attempts_per_configuration', 'unknown')}",
             f"**Comparison**: {comparison.get('status', 'legacy; coverage not recorded')}", "",
             "## Summary", "",
             "| Metric | " + " | ".join(c.replace("_", " ").title() for c in displayed)
             + " | Candidate − baseline |",
             "|---|" + "---|" * (len(displayed) + 1)]
    for metric, label in (("pass_rate", "Pass Rate"), ("time_seconds", "Time"), ("tokens", "Tokens")):
        stats = [_format_stat(summary[c].get(metric), metric) for c in displayed]
        delta = summary.get("delta", {}).get(metric) if comparison else None
        lines.append("| " + label + " | " + " | ".join(stats) + " | "
                     + (delta if delta is not None else "unknown") + " |")
    issues = comparison.get("issues", [])
    if issues or benchmark.get("notes"):
        lines.extend(["", "## Notes", ""])
        lines.extend("- " + note for note in [*issues, *benchmark.get("notes", [])])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark run results into summary statistics"
    )
    parser.add_argument(
        "benchmark_dir",
        type=Path,
        help="Path to the benchmark directory"
    )
    parser.add_argument(
        "--skill-name",
        default="",
        help="Name of the skill being benchmarked"
    )
    parser.add_argument(
        "--skill-path",
        default="",
        help="Path to the skill being benchmarked"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for benchmark.json (default: <benchmark_dir>/benchmark.json)"
    )
    parser.add_argument("--candidate", help="Candidate configuration (requires --baseline)")
    parser.add_argument("--baseline", help="Baseline configuration (requires --candidate)")

    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"Directory not found: {args.benchmark_dir}")
        sys.exit(1)

    # Generate benchmark
    try:
        benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path,
                                       args.candidate, args.baseline)
    except ValueError as exc:
        parser.error(str(exc))

    # Determine output paths
    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    output_md = output_json.with_suffix(".md")

    # Write benchmark.json
    with open(output_json, "w") as f:
        json.dump(benchmark, f, indent=2, allow_nan=False)
    print(f"Generated: {output_json}")

    # Write benchmark.md
    markdown = generate_markdown(benchmark)
    with open(output_md, "w") as f:
        f.write(markdown)
    print(f"Generated: {output_md}")

    # Print summary
    run_summary = benchmark["run_summary"]
    configs = [k for k in run_summary if k != "delta"]
    delta = run_summary.get("delta", {})

    print(f"\nSummary:")
    for config in configs:
        label = config.replace("_", " ").title()
        print(f"  {label}: {_format_stat(run_summary[config]['pass_rate'], 'pass_rate')}")
    print(f"  Comparison:    {benchmark['comparison']['status']}")
    print(f"  Delta:         {delta.get('pass_rate') or 'unknown'}")


if __name__ == "__main__":
    main()
