import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { collectRoutes, summarizeRecords } from "../../scripts/route_census.mjs";

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const SCRIPT = resolve(TEST_DIR, "../../scripts/route_census.mjs");

function runScript(args, options = {}) {
  return new Promise((resolveRun) => {
    const child = spawn(process.execPath, [SCRIPT, ...args], {
      cwd: options.cwd || process.cwd(),
      env: { ...process.env, ...options.env },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("close", (code) => resolveRun({ code, stdout, stderr }));
  });
}

function projectHasPlaywright() {
  const require = createRequire(join(process.cwd(), "package.json"));
  for (const name of ["playwright", "@playwright/test", "playwright-core"]) {
    try {
      if (require(name)?.chromium) return true;
    } catch { /* try the next installed layout */ }
  }
  return false;
}

function listen(server) {
  return new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
}

test("summary aggregation distinguishes healthy, warning and confirmed-error records", () => {
  const healthy = summarizeRecords([
    { routeIndex: 1, issues: [] },
  ]);
  assert.equal(healthy.status, "pass");
  assert.equal(healthy.exitCode, 0);
  assert.deepEqual(healthy.totals, {
    records: 1,
    healthy: 1,
    withWarnings: 0,
    withErrors: 0,
    errorOccurrences: 0,
    warningOccurrences: 0,
  });
  assert.deepEqual(healthy.issuesByType, {});

  const findings = summarizeRecords([
    {
      routeIndex: 1,
      issues: [
        { type: "console-error", severity: "error", count: 2 },
        { type: "pending-visible-image", severity: "warning" },
      ],
    },
  ], { input: { mode: "test" } });
  assert.equal(findings.status, "findings");
  assert.equal(findings.exitCode, 1);
  assert.equal(findings.totals.withErrors, 1);
  assert.equal(findings.totals.errorOccurrences, 2);
  assert.equal(findings.totals.warningOccurrences, 1);
  assert.deepEqual(findings.issuesByType, {
    "console-error": { severity: "error", records: 1, occurrences: 2 },
    "pending-visible-image": { severity: "warning", records: 1, occurrences: 1 },
  });
  assert.deepEqual(findings.input, { mode: "test" });
});

test("summary aggregation handles an empty record set without inventing findings", () => {
  const empty = summarizeRecords([]);
  assert.equal(empty.status, "empty");
  assert.equal(empty.exitCode, 0);
  assert.deepEqual(empty.totals, {
    records: 0,
    healthy: 0,
    withWarnings: 0,
    withErrors: 0,
    errorOccurrences: 0,
    warningOccurrences: 0,
  });
  assert.deepEqual(empty.issuesByType, {});
});

test("sitemap indexes recurse in order and de-duplicate canonical routes before limiting", async () => {
  const sources = new Map([
    ["https://example.com/sitemap.xml", `<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/a.xml</loc></sitemap>
      <sitemap><loc>https://example.com/b.xml</loc></sitemap>
      <sitemap><loc>https://example.com/a.xml</loc></sitemap>
    </sitemapindex>`],
    ["https://example.com/a.xml", `<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/one</loc></url>
      <url><loc>https://example.com/two</loc></url>
      <url><loc>https://example.com/one</loc></url>
    </urlset>`],
    ["https://example.com/b.xml", `<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/two</loc></url>
      <url><loc>https://example.com/three</loc></url>
    </urlset>`],
  ]);
  const routes = await collectRoutes("https://example.com/sitemap.xml", async (source) => {
    if (!sources.has(source)) throw new Error(`unexpected sitemap read: ${source}`);
    return sources.get(source);
  });
  assert.deepEqual(routes, [
    "https://example.com/one",
    "https://example.com/two",
    "https://example.com/three",
  ]);
  assert.deepEqual(routes.slice(0, 2), ["https://example.com/one", "https://example.com/two"]);
});

test("--help documents inputs, outputs and exit contract without launching Playwright", async () => {
  const result = await runScript(["--help"]);
  assert.equal(result.code, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /--sitemap/);
  assert.match(result.stdout, /records\.jsonl/);
  assert.match(result.stdout, /summary\.json/);
  assert.match(result.stdout, /Exit: 0 clean\/warnings/);
});

test("sitemap census writes JSONL and summary for healthy and error routes", async (t) => {
  if (!projectHasPlaywright()) {
    return t.skip("Run from the audited project that supplies Playwright; browser behavior is unverified here.");
  }
  const root = await mkdtemp(join(os.tmpdir(), "route-census-"));
  const out = join(root, "evidence");
  const server = http.createServer((request, response) => {
    if (request.url === "/sitemap.xml") {
      const port = server.address().port;
      response.writeHead(200, { "Content-Type": "application/xml" });
      response.end(`<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">`
        + `<url><loc>http://127.0.0.1:${port}/healthy</loc></url>`
        + `<url><loc>http://127.0.0.1:${port}/errors</loc></url>`
        + `<url><loc>http://127.0.0.1:${port}/blank</loc></url></urlset>`);
      return;
    }
    if (request.url === "/blank") {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Blank</title><div></div>");
      return;
    }
    if (request.url === "/favicon.ico") {
      response.writeHead(204).end();
      return;
    }
    if (request.url === "/healthy") {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Healthy</title><main><h1>Healthy route</h1><p>Ready for review.</p></main>");
      return;
    }
    if (request.url === "/errors") {
      response.writeHead(404, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Error route</title><style>main{width:1200px}</style><main id='dup'><h1>First</h1><h1>Second</h1><div id='dup'>Duplicate</div><img src='/missing.png'><a href='#missing'>Missing target</a><script>console.error('synthetic console failure')</script></main>");
      return;
    }
    response.writeHead(404).end("missing");
  });
  await listen(server);
  try {
    const result = await runScript([
      "--sitemap", `http://127.0.0.1:${server.address().port}/sitemap.xml`,
      "--viewport", "1000x700",
      "--out", out,
    ]);
    assert.equal(result.code, 1, result.stdout + result.stderr);
    const recordsText = await readFile(join(out, "records.jsonl"), "utf8");
    const records = recordsText.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(records.length, 3);
    assert.equal(records[0].status, "healthy");
    assert.equal(records[1].httpStatus, 404);
    assert.ok(records[1].issues.some((issue) => issue.type === "non-200"));
    assert.ok(records[1].issues.some((issue) => issue.type === "duplicate-h1"), JSON.stringify(records[1].issues));
    assert.ok(records[1].issues.some((issue) => issue.type === "duplicate-id"), JSON.stringify(records[1].issues));
    for (const type of ["horizontal-overflow", "console-error", "broken-image", "missing-alt", "broken-hash-anchor"]) {
      assert.ok(records[1].issues.some((issue) => issue.type === type), `${type}: ${JSON.stringify(records[1].issues)}`);
    }
    for (const type of ["missing-h1", "missing-main", "empty-text"]) {
      assert.ok(records[2].issues.some((issue) => issue.type === type), `${type}: ${JSON.stringify(records[2].issues)}`);
    }
    assert.doesNotMatch(recordsText, /\/healthy|\/errors|\/blank/);

    const summary = JSON.parse(await readFile(join(out, "summary.json"), "utf8"));
    assert.equal(summary.status, "findings");
    assert.equal(summary.exitCode, 1);
    assert.equal(summary.input.discoveredRoutes, 3);
    assert.equal(summary.totals.records, 3);
    assert.equal(summary.totals.healthy, 1);
    assert.equal(summary.totals.withErrors, 2);
    assert.ok(summary.issuesByType["non-200"]);
  } finally {
    server.close();
    await rm(root, { recursive: true, force: true });
  }
});
