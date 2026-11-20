import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { collectRoutes, discoverRoutes, isPathStyleHash, selectRoutes, summarizeRecords, withDeadline } from "../../scripts/route_census.mjs";

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

test("hard-deadline wrapper rejects stalled work and preserves successful results", async () => {
  const startedAt = Date.now();
  await assert.rejects(
    () => withDeadline(() => new Promise(() => {}), Date.now() + 20, "synthetic stalled route"),
    /exceeded its hard deadline/,
  );
  assert.ok(Date.now() - startedAt < 1_000, "deadline failure should be prompt");
  assert.equal(await withDeadline(async () => "complete", Date.now() + 1_000, "synthetic route"), "complete");
});

test("path-style hash detection accepts path routes and hashbangs but not element anchors", () => {
  assert.equal(isPathStyleHash("#/app"), true);
  assert.equal(isPathStyleHash("#!/app"), true);
  assert.equal(isPathStyleHash("#section"), false);
  assert.equal(isPathStyleHash("#"), false);
  assert.equal(isPathStyleHash(""), false);
});

test("sitemap indexes recurse in order, read each document once and de-duplicate before limiting", async () => {
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
  const reads = [];
  const routes = await collectRoutes("https://example.com/sitemap.xml", async (source) => {
    reads.push(source);
    if (!sources.has(source)) throw new Error(`unexpected sitemap read: ${source}`);
    return sources.get(source);
  });
  assert.deepEqual(routes, [
    "https://example.com/one",
    "https://example.com/two",
    "https://example.com/three",
  ]);
  assert.deepEqual(reads, [
    "https://example.com/sitemap.xml",
    "https://example.com/a.xml",
    "https://example.com/b.xml",
  ]);
  assert.equal(new Set(reads).size, reads.length, "each sitemap document must be read once");
  assert.deepEqual(selectRoutes(routes, 2), ["https://example.com/one", "https://example.com/two"]);
  assert.throws(() => selectRoutes(routes, "2extra"), /Invalid route limit/);
});

test("route selection preserves sitemap order and stops discovery at the requested limit", async () => {
  const sources = new Map([
    ["https://example.com/root.xml", `<?xml version="1.0"?><sitemapindex><sitemap><loc>https://example.com/a.xml</loc></sitemap><sitemap><loc>https://example.com/b.xml</loc></sitemap></sitemapindex>`],
    ["https://example.com/a.xml", `<?xml version="1.0"?><urlset><url><loc>https://example.com/one</loc></url><url><loc>https://example.com/two</loc></url><url><loc>https://example.com/three</loc></url></urlset>`],
    ["https://example.com/b.xml", `<?xml version="1.0"?><urlset><url><loc>https://example.com/four</loc></url></urlset>`],
  ]);
  const reads = [];
  const result = await discoverRoutes("https://example.com/root.xml", async (source) => {
    reads.push(source);
    return sources.get(source);
  }, { routeLimit: 2 });
  assert.deepEqual(result.routes, ["https://example.com/one", "https://example.com/two"]);
  assert.equal(result.discovery.truncated, true);
  assert.equal(result.discovery.reason, "requested-limit");
  assert.equal(result.discovery.sitemapDocumentsRead, 2);
  assert.deepEqual(reads, ["https://example.com/root.xml", "https://example.com/a.xml"]);
});

test("route discovery enforces total route and sitemap-document caps", async () => {
  const source = `<?xml version="1.0"?><urlset>${["one", "two", "three"]
    .map((route) => `<url><loc>https://example.com/${route}</loc></url>`).join("")}</urlset>`;
  const capped = await discoverRoutes("https://example.com/sitemap.xml", async () => source, { maxRoutes: 2 });
  assert.deepEqual(capped.routes, ["https://example.com/one", "https://example.com/two"]);
  assert.equal(capped.discovery.truncated, true);
  assert.equal(capped.discovery.reason, "route-cap");

  const index = `<?xml version="1.0"?><sitemapindex><sitemap><loc>https://example.com/a.xml</loc></sitemap><sitemap><loc>https://example.com/b.xml</loc></sitemap></sitemapindex>`;
  const documentCapped = await discoverRoutes("https://example.com/root.xml", async (url) => (
    url.endsWith("root.xml")
      ? index
      : `<?xml version="1.0"?><urlset><url><loc>https://example.com/${url.split("/").at(-1)}</loc></url></urlset>`
  ), { maxSitemapDocuments: 2 });
  assert.deepEqual(documentCapped.routes, ["https://example.com/a.xml"]);
  assert.equal(documentCapped.discovery.truncated, true);
  assert.equal(documentCapped.discovery.reason, "sitemap-document-cap");
});

test("URL policy rejects scheme escapes from HTTP and local-file sitemap roots", async () => {
  const httpRoot = "https://example.com/sitemap.xml";
  await assert.rejects(
    () => collectRoutes(httpRoot, async () => (
      `<?xml version="1.0"?><sitemapindex><sitemap><loc>file:///etc/passwd</loc></sitemap></sitemapindex>`
    )),
    /HTTP\(S\) root sitemap must not follow file:/,
  );

  const localRoot = pathToFileURL("/tmp/route-census-safe/root.xml").href;
  await assert.rejects(
    () => collectRoutes(localRoot, async () => (
      `<?xml version="1.0"?><sitemapindex><sitemap><loc>https://example.com/child.xml</loc></sitemap></sitemapindex>`
    )),
    /local file sitemap root may only follow file:/,
  );
  await assert.rejects(
    () => collectRoutes(localRoot, async () => (
      `<?xml version="1.0"?><sitemapindex><sitemap><loc>../secret.xml</loc></sitemap></sitemapindex>`
    )),
    /outside the local sitemap root/,
  );
});

test("canonical routes are same-origin by default and cross-origin requires an allowlist", async () => {
  const source = `<?xml version="1.0"?><urlset><url><loc>https://evil.test/route</loc></url></urlset>`;
  await assert.rejects(
    () => collectRoutes("https://example.com/sitemap.xml", async () => source),
    /does not match https:\/\/example\.com/,
  );
  const allowed = await collectRoutes("https://example.com/sitemap.xml", async () => source, {
    allowedOrigins: ["https://evil.test"],
  });
  assert.deepEqual(allowed, ["https://evil.test/route"]);
});

test("loopback and link-local targets require an explicit target allowlist", async () => {
  const read = async () => (
    `<?xml version="1.0"?><urlset><url><loc>http://127.0.0.1:8080/route</loc></url></urlset>`
  );
  await assert.rejects(
    () => collectRoutes("http://127.0.0.1:8080/sitemap.xml", read),
    /targets restricted host 127\.0\.0\.1/,
  );
  const allowed = await collectRoutes("http://127.0.0.1:8080/sitemap.xml", read, {
    allowedTargets: ["127.0.0.1"],
  });
  assert.deepEqual(allowed, ["http://127.0.0.1:8080/route"]);

  await assert.rejects(
    () => collectRoutes("http://169.254.169.254/sitemap.xml", read),
    /targets restricted host 169\.254\.169\.254/,
  );
});

test("--help documents inputs, outputs and exit contract without launching Playwright", async () => {
  const result = await runScript(["--help"]);
  assert.equal(result.code, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /--sitemap/);
  assert.match(result.stdout, /records\.jsonl/);
  assert.match(result.stdout, /summary\.json/);
  assert.match(result.stdout, /Exit: 0 clean\/warnings/);
});

test("CLI rejects an unbounded viewport matrix before network access", async () => {
  const args = Array.from({ length: 21 }, () => ["--viewport", "1000x700"]).flat();
  const result = await runScript(["--sitemap", "https://example.com/sitemap.xml", ...args]);
  assert.equal(result.code, 2, result.stdout + result.stderr);
  assert.match(result.stderr, /At most 20 --viewport entries/);
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
        + `<url><loc>http://127.0.0.1:${port}/blank</loc></url>`
        + `<url><loc>http://127.0.0.1:${port}/contents</loc></url>`
        + `<url><loc>http://127.0.0.1:${port}/hashbang#!/app</loc></url></urlset>`);
      return;
    }
    if (request.url === "/blank") {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Blank</title><div></div>");
      return;
    }
    if (request.url === "/contents") {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Contents</title><main style='display:contents'><h1 style='display:contents'><span>Visible contents heading</span></h1><p>Visible contents body.</p></main>");
      return;
    }
    if (request.url === "/hashbang") {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<!doctype html><title>Hashbang</title><main><h1>Hashbang route</h1><a href='#!/app'>Open app</a></main>");
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
    if (request.url === "/localized-missing") {
      response.writeHead(404, { "Content-Type": "text/html; charset=utf-8" });
      response.end("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>找不到页面</title></head><body><main><h1>找不到页面</h1><p>请返回首页或使用搜索。</p><a href=\"/\">返回首页</a></main></body></html>");
      return;
    }
    response.writeHead(404).end("missing");
  });
  await listen(server);
  try {
    const result = await runScript([
      "--sitemap", `http://127.0.0.1:${server.address().port}/sitemap.xml`,
      "--allow-target", "127.0.0.1",
      "--probe", `http://127.0.0.1:${server.address().port}/localized-missing`,
      "--probe-expected-status", "404",
      "--viewport", "1000x700",
      "--out", out,
    ]);
    assert.equal(result.code, 1, result.stdout + result.stderr);
    const recordsText = await readFile(join(out, "records.jsonl"), "utf8");
    const records = recordsText.trim().split("\n").map((line) => JSON.parse(line));
    assert.equal(records.length, 6);
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
    for (const type of ["missing-h1", "missing-main"]) {
      assert.doesNotMatch(JSON.stringify(records[3].issues), new RegExp(`"type":"${type}"`));
    }
    assert.doesNotMatch(JSON.stringify(records[4].issues), /broken-hash-anchor/);
    assert.equal(records[5].routeKind, "localized-404-probe");
    assert.equal(records[5].expectedStatus, 404);
    assert.equal(records[5].expectedStatusMatched, true);
    assert.equal(records[5].status, "healthy", JSON.stringify(records[5].issues));
    assert.doesNotMatch(JSON.stringify(records[5].issues), /non-200/);
    assert.doesNotMatch(recordsText, /\/healthy|\/errors|\/blank/);

    const summary = JSON.parse(await readFile(join(out, "summary.json"), "utf8"));
    assert.equal(summary.status, "findings");
    assert.equal(summary.exitCode, 1);
    assert.equal(summary.input.discoveredRoutes, 5);
    assert.equal(summary.input.examinedCanonicalRoutes, 5);
    assert.equal(summary.input.probeRoutes, 1);
    assert.equal(summary.input.discovery.truncated, false);
    assert.equal(summary.totals.records, 6);
    assert.equal(summary.totals.healthy, 4);
    assert.equal(summary.totals.withErrors, 2);
    assert.ok(summary.issuesByType["non-200"]);
  } finally {
    server.close();
    await rm(root, { recursive: true, force: true });
  }
});
