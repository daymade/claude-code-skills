#!/usr/bin/env python3
"""Exercise the shipped scout and Workflow body without starting model agents."""

import importlib.util
import json
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scout_repository", SKILL / "scripts/scout_repository.py")
SCOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOUT)


def node(number, kind="issues"):
    value = {"__typename": "Issue" if kind == "issues" else "PullRequest",
             "id": f"node-{number}", "number": number, "title": f"Synthetic item {number}",
             "author": {"login": "sample-contributor"}, "createdAt": "2026-01-01T00:00:00Z"}
    if kind == "issues":
        value["labels"] = {"totalCount": 0, "pageInfo": {"hasNextPage": False}, "nodes": []}
    else:
        value.update({"headRefName": "sample-topic", "additions": 1, "deletions": 0,
                      "changedFiles": 1, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"})
    return value


def page(nodes, total, more=False, cursor=None):
    return {"nodes": nodes, "totalCount": total,
            "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


class InventoryTests(unittest.TestCase):
    def run_pages(self, pages, kind="issues"):
        calls = []
        def api(owner, name, query, cursor=None):
            calls.append((owner, name, query, cursor))
            value = pages[len(calls) - 1]
            if isinstance(value, Exception):
                raise value
            return {kind: value}
        with patch.object(SCOUT, "graphql", side_effect=api):
            result = SCOUT.inventory("sample-owner", "sample-repo", kind)
        return result, calls

    def test_full_inventory_boundary_sizes(self):
        for kind in ("issues", "pullRequests"):
            for size in (0, 31, 100, 101):
                with self.subTest(kind=kind, size=size):
                    items = [node(i, kind) for i in range(1, size + 1)]
                    pages = [page(items[:100], size, size > 100, "cursor-100" if size > 100 else None)]
                    if size > 100:
                        pages.append(page(items[100:], size))
                    pages.append({"totalCount": size})
                    result, calls = self.run_pages(pages, kind)
                    self.assertEqual(result["status"], "checked")
                    self.assertEqual(len(result["items"]), size)
                    self.assertEqual(result["total"], size)
                    self.assertEqual(len(calls), 3 if size > 100 else 2)
                    if size > 100:
                        self.assertEqual(calls[1][3], "cursor-100")

    def test_partial_failure_never_means_empty_success(self):
        first = page([node(i) for i in range(1, 101)], 101, True, "next")
        for failure in (SCOUT.ScoutError("HTTP failed"), None, {},
                        page([node(101)], 102), page([node(1)], 101),
                        page([], 101, True, "next")):
            with self.subTest(failure=failure):
                result, _ = self.run_pages([first, failure])
                self.assertEqual(result["status"], "not_checked")
                self.assertEqual(len(result["items"]), 100)
                self.assertIn("error", result)

    def test_bad_server_shape_and_pr_in_issue_connection(self):
        cases = [None, {}, page(None, 0), page([], None), page([], True),
                 page([node(1, "pullRequests")], 1),
                 page([node(1)], 2), page([], 0, True, "same")]
        missing = page([node(1)], 1)
        del missing["nodes"][0]["author"]
        cases.append(missing)
        for value in cases:
            with self.subTest(value=value):
                result, _ = self.run_pages([value])
                self.assertEqual(result["status"], "not_checked")

    def test_duplicate_cursor_and_final_total_drift(self):
        result, _ = self.run_pages([page([node(1)], 3, True, "same"),
                                    page([node(2)], 3, True, "same")])
        self.assertEqual(result["status"], "not_checked")
        self.assertIn("cursor", result["error"])
        result, _ = self.run_pages([page([node(1)], 1), {"totalCount": 2}])
        self.assertEqual(result["status"], "not_checked")
        self.assertIn("changed after", result["error"])

    def test_gh_json_failures_and_argument_binding(self):
        for result in (subprocess.CompletedProcess([], 1, "{}", "failure"),
                       subprocess.CompletedProcess([], 0, "{broken", "")):
            with patch.object(SCOUT.subprocess, "run", return_value=result):
                with self.assertRaises(SCOUT.ScoutError):
                    SCOUT.gh_json(["api", "graphql"])
        response = {"data": {"repository": {"issues": {"totalCount": 0}}}}
        with patch.object(SCOUT.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(response), "")) as runner:
            SCOUT.graphql("sample-owner", "sample-repo", "query", "cursor;echo inert")
            command = runner.call_args.args[0]
            self.assertIsInstance(command, list)
            self.assertIn("endCursor=cursor;echo inert", command)
            self.assertNotIn("shell", runner.call_args.kwargs)
        for response in ({}, {"errors": [{"message": "synthetic"}], "data": {}},
                         {"data": {"repository": None}}):
            with patch.object(SCOUT, "gh_json", return_value=response):
                with self.assertRaises(SCOUT.ScoutError):
                    SCOUT.graphql("sample-owner", "sample-repo", "query")

    def test_json_layout_and_normal_marker_free_clone(self):
        identity = {"nameWithOwner": "sample-owner/sample-repo", "isPrivate": False,
                    "stargazerCount": 0}
        inventory = {"status": "checked", "total": 0, "items": []}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".claude-plugin").mkdir()
            manifest = {"plugins": [{"name": "single"}, {"name": "suite", "skills": ["a", "b"]}],
                        "metadata": {"description": "layout varies", "version": "2.3.4"}}
            for text in (json.dumps(manifest), json.dumps(manifest, indent=4)):
                (root / ".claude-plugin/marketplace.json").write_text(text)
                with patch.object(SCOUT, "gh_json", return_value=identity), \
                        patch.object(SCOUT, "inventory", return_value=inventory):
                    result = SCOUT.scout(root, "sample-owner/sample-repo")
                self.assertTrue(result["complete"])
                self.assertEqual(result["marketplace"]["version"], "2.3.4")
                self.assertEqual(result["marketplace"]["skill_count"], 3)
                self.assertFalse(list(root.rglob(".security-scan-passed")))


class CliTests(unittest.TestCase):
    def test_real_cli_exit_and_json_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin/marketplace.json").write_text(json.dumps({
                "metadata": {"version": "1.2.3"}, "plugins": []}))
            binary = root / "gh"
            binary.write_text("#!" + sys.executable + "\n" + r'''
import json, os, sys
if sys.argv[1:3] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner":"sample-owner/sample-repo","isPrivate":False,"stargazerCount":0}))
else:
    query = next(arg[6:] for arg in sys.argv if arg.startswith("query="))
    kind = "pullRequests" if "pullRequests(" in query else "issues"
    if os.environ.get("SYNTHETIC_GH_FAILURE") and kind == "issues":
        print("synthetic request failure", file=sys.stderr)
        sys.exit(1)
    connection = {"totalCount": 0}
    if "pageInfo" in query:
        connection.update({"pageInfo":{"hasNextPage":False,"endCursor":None},"nodes":[]})
    print(json.dumps({"data":{"repository":{kind:connection}}}))
''')
            binary.chmod(0o755)
            command = [sys.executable, str(SKILL / "scripts/scout_repository.py"),
                       "--repo", "sample-owner/sample-repo", "--root", str(root)]
            environment = {**os.environ, "PATH": str(root) + os.pathsep + os.environ.get("PATH", "")}
            for failure in (False, True):
                with self.subTest(failure=failure):
                    current = {**environment}
                    if failure:
                        current["SYNTHETIC_GH_FAILURE"] = "1"
                    result = subprocess.run(command, env=current, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1 if failure else 0, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report["complete"], not failure)
                    self.assertEqual(report["open_prs"]["status"], "checked")
                    self.assertEqual(report["open_issues"]["status"], "not_checked" if failure else "checked")
                    if failure:
                        self.assertIsNone(report["open_issues"]["total"])
                        self.assertIn("error", report["open_issues"])
            bad = subprocess.run(command[:-4] + ["--repo", "invalid-target"],
                                 env=environment, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)


class WorkflowBodyTests(unittest.TestCase):
    def test_shipped_body_preserves_every_expected_dimension(self):
        # Only adapt the documented loader seam: remove export and allow top-level return.
        # Stand-ins implement agent/parallel/phase; this is not native Workflow E2E.
        program = r"""
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8').replace('export const meta =', 'const meta =');
const run = new (Object.getPrototypeOf(async function(){}).constructor)('args','phase','parallel','agent',source);
const expected = ['code-and-script-safety','doc-consistency','security-pii','pull-requests','issues','marketplace-integrity'];
const assert = require('assert').strict;
function valid(key) { return { dimension:key, status:'checked', health:'good', summary:'Synthetic completed check', findings:[], stats:'1 sample checked' }; }
function partial(key, prefixed=false) {
 return { dimension:key, status:'not_checked', health:'needs-attention',
  summary:(prefixed?'Audit incomplete; overall repository health not determined: ':'')+'Known synthetic observations; required scan unavailable.',
  findings:[
   {severity:'critical',title:'Synthetic critical exposure',detail:'Observed synthetic fixture exposure',location:'sample.md:1',recommendation:'Sanitize the fixture'},
   {severity:'high',title:'Synthetic unsafe command',detail:'Observed missing fixture guard',location:'sample.py:2',recommendation:'Add the guard'}
  ], stats:'2 files checked; required scanner unavailable' };
}
(async () => {
 let cases = 0;
 for (const variant of ['good','critical','partial_findings','partial_prefixed','null','undefined','throw','not_checked','invalid_partial','empty','array','wrong_dimension','bad_health','missing_status','bad_findings','all_null']) {
   const labels = [];
   let taskRows;
   const result = await run(undefined, () => {}, async tasks => { taskRows=await Promise.all(tasks.map(t=>t())); return taskRows; }, async (prompt, options) => {
     const key = options.label.slice(6); labels.push(key);
     assert.deepEqual(options.schema.properties.dimension.enum, [key]);
     assert.deepEqual(options.schema.properties.status.enum, ['checked','not_checked']);
     assert(options.schema.required.includes('status'));
     let value = valid(key);
     if (variant === 'critical') { value.health='critical'; value.findings=[{severity:'critical',title:'Synthetic failure',detail:'Known failing control',location:'sample.py:1',recommendation:'Repair control'}]; }
     if (variant === 'all_null') return null;
     if (key !== 'security-pii') return value;
     if (variant === 'null') return null;
     if (variant === 'undefined') return undefined;
     if (variant === 'throw') throw new Error('Synthetic failure');
     if (variant === 'not_checked') { value.status='not_checked'; value.health='needs-attention'; value.summary='Required scanner unavailable'; }
     if (variant === 'partial_findings' || variant === 'partial_prefixed') return partial(key,variant === 'partial_prefixed');
     if (variant === 'invalid_partial') { value=partial(key); value.findings.push({severity:'panic'}); }
     if (variant === 'empty') return {};
     if (variant === 'array') return [];
     if (variant === 'wrong_dimension') value.dimension='issues';
     if (variant === 'bad_health') value.health='unknown';
     if (variant === 'missing_status') delete value.status;
     if (variant === 'bad_findings') value.findings=[{severity:'panic'}];
     return value;
   });
   assert.deepEqual(labels, expected); assert.deepEqual(result.checks.map(c=>c.dimension), expected);
   assert.equal(result.checks.length, expected.length);
   const complete = ['good','critical'].includes(variant); assert.equal(result.complete, complete);
   if (!complete) {
     const incomplete=result.checks.filter(c=>c.status==='not_checked');
     assert.equal(incomplete.length, variant==='all_null'?expected.length:1);
     for(const row of incomplete) {
       assert.equal(row.health,'needs-attention');
       assert.match(row.summary,/overall repository health not determined/);
       if (variant === 'partial_findings' || variant === 'partial_prefixed') {
         const original=partial(row.dimension);
         assert.deepEqual(row.findings,original.findings);
         assert.equal(row.stats,original.stats);
         assert(row.summary.endsWith(original.summary));
       } else {
         assert.deepEqual(row.findings,[]);
         if (variant === 'not_checked') assert.equal(row.stats,'1 sample checked');
         if (variant === 'invalid_partial') assert.equal(row.stats,'Coverage not established for this dimension.');
       }
     }
   } else { assert(result.checks.every(c=>c.status==='checked')); }
   // Both production normalization boundaries must preserve the same evidence and summary.
   assert.deepEqual(result.checks,taskRows);
   cases++;
 }
 // Add a synthetic task to the actual body; leave its budget guard untouched.
 const guard = 'if (dims.length > 6)';
 assert(source.includes(guard));
 const expanded = source.replace(guard, "dims.push({key:'synthetic-extra',prompt:'Synthetic extra task'});\n" + guard);
 const runExpanded = new (Object.getPrototypeOf(async function(){}).constructor)('args','phase','parallel','agent',expanded);
 let dispatched = 0;
 await assert.rejects(() => runExpanded({},()=>{},async()=>{dispatched++;return []},async()=>{dispatched++;return null}), /maximum task budget/);
 assert.equal(dispatched,0);
 const failedParallel = await run({},()=>{},async()=>{throw new Error('parallel failed')},async()=>null);
 assert.equal(failedParallel.complete,false); assert.equal(failedParallel.checks.length,expected.length);
 assert(failedParallel.checks.every(c=>c.status==='not_checked'));
 console.log(JSON.stringify({cases:cases+2, dimensions:expected.length, nativeWorkflow:false}));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result = subprocess.run(["node", "-e", program, str(SKILL / "scripts/repo-health-check.workflow.js")],
                                text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["cases"], 18)
        self.assertEqual(report["dimensions"], 6)
        self.assertFalse(report["nativeWorkflow"])


if __name__ == "__main__":
    unittest.main()
