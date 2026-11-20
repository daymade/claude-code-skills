#!/usr/bin/env python3
"""Run a unittest suite directory across parallel worker processes using stdlib only.

Preserves exact unittest discovery semantics:
- Small suites (< 8 tests or --jobs 1) execute in-process with zero spawn overhead.
- Classes with custom setUpClass/tearDownClass stay grouped in one work unit.
- Large stateless classes (>= 4 tests) split per test method so slow subprocess
  tests fan out cleanly across all available CI vCPUs.
- Any discovery/load error, test failure, or missing execution exits nonzero.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import io
import os
from pathlib import Path
import sys
import time
import unittest


def _iter_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
        else:
            yield item


def _has_class_fixture(cls: type[unittest.TestCase]) -> bool:
    return (
        cls.setUpClass.__func__ is not unittest.TestCase.setUpClass.__func__
        or cls.tearDownClass.__func__ is not unittest.TestCase.tearDownClass.__func__
    )


def _plan_units(target: str) -> tuple[list[list[str]], list[str], int]:
    """Return (work_units, load_errors, total_tests) for discovered tests."""
    abs_target = str(Path(target).resolve())
    if abs_target not in sys.path:
        sys.path.insert(0, abs_target)
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=abs_target)
    load_errors: list[str] = []
    by_class: dict[tuple[str, str], list[tuple[type[unittest.TestCase], str]]] = defaultdict(list)

    for case in _iter_cases(suite):
        cls = type(case)
        if cls.__module__ == "unittest.loader":
            buf = io.StringIO()
            unittest.TextTestRunner(stream=buf, verbosity=2).run(case)
            load_errors.append(buf.getvalue().strip() or f"Failed to load {case.id()}")
            continue
        by_class[(cls.__module__, cls.__qualname__)].append((cls, case.id()))

    units: list[list[str]] = []
    total = 0
    for (_mod, _qual), entries in sorted(by_class.items()):
        cls = entries[0][0]
        ids = [tid for _, tid in entries]
        total += len(ids)
        if len(ids) >= 4 and not _has_class_fixture(cls):
            for tid in ids:
                units.append([tid])
        else:
            units.append(ids)
    return units, load_errors, total


def _run_unit(abs_target: str, test_ids: list[str]) -> dict:
    if abs_target not in sys.path:
        sys.path.insert(0, abs_target)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tid in test_ids:
        suite.addTests(loader.loadTestsFromName(tid))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    return {
        "ids": test_ids,
        "ran": result.testsRun,
        "ok": result.wasSuccessful(),
        "skipped": len(result.skipped),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "output": stream.getvalue(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Directory passed to unittest discover -s")
    parser.add_argument(
        "--jobs",
        type=int,
        default=min(os.cpu_count() or 1, 4),
        help="Maximum parallel worker processes (default: min(nproc, 4))",
    )
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be >= 1")

    abs_target = str(Path(args.target).resolve())
    start = time.monotonic()
    units, load_errors, total = _plan_units(abs_target)
    if load_errors:
        for err in load_errors:
            print(err, file=sys.stderr)
        return 1

    if total < 8 or args.jobs == 1 or len(units) <= 1:
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=abs_target)
        res = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if res.wasSuccessful() else 1

    workers = min(args.jobs, len(units))
    ran = 0
    skipped = 0
    failed_outputs: list[str] = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_unit, abs_target, unit) for unit in units]
        for fut in as_completed(futures):
            rec = fut.result()
            ran += rec["ran"]
            skipped += rec["skipped"]
            if not rec["ok"]:
                failed_outputs.append(rec["output"])

    elapsed = time.monotonic() - start
    for out in failed_outputs:
        sys.stderr.write(out)
        if not out.endswith("\n"):
            sys.stderr.write("\n")

    if ran != total:
        print(
            f"FAIL: executed {ran} of {total} discovered tests in {args.target}",
            file=sys.stderr,
        )
        return 1

    status = "FAILED" if failed_outputs else "OK"
    extra = f" (skipped={skipped})" if skipped else ""
    print(f"Ran {ran} tests in {elapsed:.3f}s ({workers} workers) - {status}{extra}")
    return 1 if failed_outputs else 0


if __name__ == "__main__":
    raise SystemExit(main())
