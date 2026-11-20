#!/usr/bin/env node
/**
 * Whole-site route census.
 *
 * Enumerates canonical <loc> routes from sitemap.xml (or an explicit sitemap
 * file/URL), then runs a bounded Playwright structural audit at one or more
 * viewports. It writes one JSON record per route/viewport to records.jsonl and
 * an aggregate summary.json.
 *
 * Usage:
 *   node route_census.mjs --url <site-url>
 *   node route_census.mjs --sitemap <sitemap-url-or-file>
 *     [--viewport <WIDTH>x<HEIGHT>]... [--limit <positive-int>] [--out <new-empty-dir>]
 *
 * --url resolves sitemap.xml relative to the supplied site path. --sitemap
 * accepts an explicit HTTP(S) URL, file URL, or local XML path. Sitemap indexes
 * are followed recursively. Routes retain sitemap order and are de-duplicated by
 * absolute URL before --limit is applied.
 *
 * Exit: 0 clean or warning-only · 1 confirmed route errors · 2 invalid input or
 * runtime/setup failure. This is a Level C census, not visual acceptance; any
 * screenshots used for an appearance claim must still be opened and inspected.
 */
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const MAX_SITEMAP_BYTES = 10 * 1024 * 1024;
const MAX_SITEMAP_DEPTH = 5;
const NAVIGATION_TIMEOUT_MS = 30_000;
const SETTLE_MS = 500;
const DEFAULT_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true },
];

const usage = [
  "Usage: route_census.mjs (--url <site-url> | --sitemap <sitemap-url-or-file>)",
  "  [--viewport <WIDTH>x<HEIGHT>]... (default: 1440x900 and 390x844)",
  "  [--limit <positive-int>] [--out <new-empty-directory>]",
  "",
  "--url resolves sitemap.xml relative to the supplied site path.",
  "--sitemap accepts an explicit HTTP(S) URL, file URL, or local XML path.",
  "Sitemap indexes are followed recursively; canonical routes must be HTTP(S).",
  "Output: <out>/records.jsonl and <out>/summary.json",
  "Exit: 0 clean/warnings · 1 confirmed errors · 2 input/runtime failure.",
].join("\n");

class CensusInputError extends Error {
  constructor(message) {
    super(message);
    this.name = "CensusInputError";
  }
}

export function summarizeRecords(records, context = {}) {
  const issueStats = new Map();
  let healthy = 0;
  let withWarnings = 0;
  let withErrors = 0;
  let errorOccurrences = 0;
  let warningOccurrences = 0;

  for (const record of Array.isArray(records) ? records : []) {
    const issues = Array.isArray(record?.issues) ? record.issues : [];
    const recordErrors = issues.filter((issue) => issue?.severity === "error");
    const recordWarnings = issues.filter((issue) => issue?.severity === "warning");
    if (recordErrors.length) withErrors += 1;
    else if (recordWarnings.length) withWarnings += 1;
    else healthy += 1;

    for (const issue of issues) {
      const severity = issue?.severity === "warning" ? "warning" : "error";
      const occurrences = Number.isFinite(issue?.count) && issue.count > 0 ? issue.count : 1;
      if (severity === "error") errorOccurrences += occurrences;
      else warningOccurrences += occurrences;
      const type = String(issue?.type || "unknown");
      const current = issueStats.get(type) || { severity, records: 0, occurrences: 0 };
      current.records += 1;
      current.occurrences += occurrences;
      issueStats.set(type, current);
    }
  }

  const recordCount = Array.isArray(records) ? records.length : 0;
  const status = recordCount === 0
    ? "empty"
    : errorOccurrences > 0
      ? "findings"
      : warningOccurrences > 0
        ? "warnings"
        : "pass";

  return {
    schemaVersion: 1,
    ...context,
    status,
    exitCode: errorOccurrences > 0 ? 1 : 0,
    totals: {
      records: recordCount,
      healthy,
      withWarnings,
      withErrors,
      errorOccurrences,
      warningOccurrences,
    },
    issuesByType: Object.fromEntries(
      [...issueStats.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([type, stats]) => [type, stats]),
    ),
  };
}

function loadPlaywright() {
  const requirers = [
    createRequire(path.join(process.cwd(), "package.json")),
    createRequire(import.meta.url),
  ];
  const candidates = ["playwright-core", "playwright", "@playwright/test"];
  const attempts = [];
  for (const requireFrom of requirers) {
    for (const pkg of candidates) {
      try {
        const mod = requireFrom(pkg);
        if (mod?.chromium) return mod;
        attempts.push(`${pkg}: resolved without a chromium export`);
      } catch (error) {
        attempts.push(`${pkg}: ${String(error?.message || error).split("\n")[0]}`);
      }
    }
  }
  throw new CensusInputError(
    "No Playwright browser driver found (tried playwright-core, playwright, @playwright/test). "
    + "Run from the audited project that already supplies Playwright; do not install a dependency without authorization.\n"
    + `Resolution attempts:\n  - ${attempts.join("\n  - ")}`,
  );
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Google/Chrome/Application/chrome.exe"),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Google/Chrome/Application/chrome.exe"),
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Microsoft/Edge/Application/msedge.exe"),
    process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Microsoft/Edge/Application/msedge.exe"),
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function parseArgs(argv) {
  const options = {
    url: null,
    sitemap: null,
    out: null,
    limit: null,
    viewports: [],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      return { help: true };
    }
    if (!["--url", "--sitemap", "--out", "--limit", "--viewport"].includes(arg)) {
      if (arg.startsWith("-")) throw new CensusInputError(`Unknown option: ${arg}`);
      throw new CensusInputError(`Unexpected positional argument: ${arg}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new CensusInputError(`Missing value for ${arg}.`);
    index += 1;
    if (arg === "--viewport") options.viewports.push(parseViewport(value));
    else if (arg === "--limit") options.limit = parsePositiveInteger(value, "--limit");
    else options[arg.slice(2)] = value;
  }

  if (Boolean(options.url) === Boolean(options.sitemap)) {
    throw new CensusInputError("Provide exactly one of --url or --sitemap.");
  }
  return options;
}

function parsePositiveInteger(value, flagName) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0 || String(parsed) !== String(value).trim()) {
    throw new CensusInputError(`Invalid ${flagName} value: ${value}. Expected a positive integer.`);
  }
  return parsed;
}

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/i.exec(value || "");
  if (!match) throw new CensusInputError(`Invalid --viewport "${value}". Expected WIDTHxHEIGHT.`);
  const width = Number.parseInt(match[1], 10);
  const height = Number.parseInt(match[2], 10);
  if (width < 240 || height < 240 || width > 10_000 || height > 10_000) {
    throw new CensusInputError(
      `Invalid --viewport "${value}". Width and height must be between 240 and 10000 CSS pixels.`,
    );
  }
  const index = parseViewport.nextIndex++;
  return {
    name: `viewport-${String(index + 1).padStart(2, "0")}-${width}x${height}`,
    width,
    height,
    deviceScaleFactor: 1,
    isMobile: width <= 480,
    hasTouch: width <= 480,
  };
}
parseViewport.nextIndex = 0;

function normalizeSiteSitemap(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new CensusInputError("--url must be an absolute HTTP(S) URL.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new CensusInputError("--url must use HTTP or HTTPS.");
  }
  if (parsed.username || parsed.password) {
    throw new CensusInputError("--url must not contain embedded credentials.");
  }
  parsed.hash = "";
  parsed.search = "";
  if (!parsed.pathname.endsWith("/")) parsed.pathname += "/";
  return new URL("sitemap.xml", parsed).href;
}

function resolveSitemapReference(value, baseSource) {
  const trimmed = String(value || "").trim();
  if (!trimmed) throw new CensusInputError("Sitemap contains an empty <loc>.");
  if (/^https?:\/\//i.test(trimmed)) {
    const resolved = new URL(trimmed, /^https?:\/\//i.test(baseSource || "") ? baseSource : undefined);
    assertNoEmbeddedCredentials(resolved, "sitemap");
    return resolved.href;
  }
  if (/^file:\/\//i.test(trimmed)) return new URL(trimmed).href;
  if (baseSource) {
    if (/^https?:\/\//i.test(baseSource)) return new URL(trimmed, baseSource).href;
    if (/^file:\/\//i.test(baseSource)) return new URL(trimmed, baseSource).href;
    return pathToFileURL(path.resolve(path.dirname(fileURLToPath(baseSource)), trimmed)).href;
  }
  return pathToFileURL(path.resolve(trimmed)).href;
}

function assertNoEmbeddedCredentials(url, label) {
  if (url.username || url.password) {
    throw new CensusInputError(`${label} must not contain embedded credentials.`);
  }
}

async function readSitemap(source) {
  if (/^https?:\/\//i.test(source)) {
    let response;
    try {
      response = await fetch(source, {
        redirect: "follow",
        signal: AbortSignal.timeout(NAVIGATION_TIMEOUT_MS),
        headers: { Accept: "application/xml,text/xml;q=0.9,*/*;q=0.8" },
      });
    } catch (error) {
      throw new CensusInputError(`Could not fetch sitemap: ${redactText(error?.message || String(error))}`);
    }
    if (!response.ok) throw new CensusInputError(`Sitemap returned HTTP ${response.status}.`);
    const declaredLength = Number.parseInt(response.headers.get("content-length") || "", 10);
    if (Number.isFinite(declaredLength) && declaredLength > MAX_SITEMAP_BYTES) {
      throw new CensusInputError("Sitemap exceeds the 10 MiB input limit.");
    }
    if (!response.body) return "";
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let text = "";
    let bytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_SITEMAP_BYTES) {
        await reader.cancel().catch(() => {});
        throw new CensusInputError("Sitemap exceeds the 10 MiB input limit.");
      }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  }

  let filePath;
  try {
    filePath = fileURLToPath(source);
  } catch {
    throw new CensusInputError("--sitemap must be an HTTP(S) URL, file URL, or local XML path.");
  }
  let stat;
  try {
    stat = fs.statSync(filePath);
  } catch {
    throw new CensusInputError("Sitemap file does not exist or is not readable.");
  }
  if (!stat.isFile()) throw new CensusInputError("Sitemap path is not a file.");
  if (stat.size > MAX_SITEMAP_BYTES) throw new CensusInputError("Sitemap exceeds the 10 MiB input limit.");
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch {
    throw new CensusInputError("Sitemap file could not be read.");
  }
}

function decodeXmlEntities(value) {
  return String(value)
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, decimal) => String.fromCodePoint(Number.parseInt(decimal, 10)))
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, "\"")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

function parseSitemapXml(xml) {
  const text = String(xml || "").replace(/^﻿/, "").trim();
  if (!text) throw new CensusInputError("Sitemap is empty.");
  const isIndex = /<sitemapindex\b/i.test(text.slice(0, 2_000));
  const isUrlSet = /<urlset\b/i.test(text.slice(0, 2_000));
  if (!isIndex && !isUrlSet) throw new CensusInputError("XML is neither a sitemap index nor a URL set.");
  const locations = [...text.matchAll(/<loc\b[^>]*>([\s\S]*?)<\/loc>/gi)]
    .map((match) => decodeXmlEntities(match[1]).trim())
    .filter(Boolean);
  if (!locations.length) throw new CensusInputError("Sitemap contains no <loc> entries.");
  return { kind: isIndex ? "index" : "urlset", locations };
}

export async function collectRoutes(sitemapSource, read = readSitemap) {
  const routes = [];
  const seenRoutes = new Set();
  const seenSitemaps = new Set();

  async function visit(source, depth) {
    if (depth > MAX_SITEMAP_DEPTH) throw new CensusInputError("Sitemap index nesting exceeds the supported depth.");
    if (seenSitemaps.has(source)) return;
    seenSitemaps.add(source);
    const parsed = parseSitemapXml(await read(source));
    if (parsed.kind === "index") {
      for (const location of parsed.locations) {
        await visit(resolveSitemapReference(location, source), depth + 1);
      }
      return;
    }
    for (const location of parsed.locations) {
      let routeUrl;
      let route;
      try {
        routeUrl = new URL(location, source);
        route = routeUrl.href;
      } catch {
        throw new CensusInputError("Sitemap contains an invalid route URL.");
      }
      if (routeUrl.protocol !== "http:" && routeUrl.protocol !== "https:") {
        throw new CensusInputError("Canonical routes must use HTTP or HTTPS.");
      }
      assertNoEmbeddedCredentials(route, "canonical route");
      if (seenRoutes.has(route)) continue;
      seenRoutes.add(route);
      routes.push(route);
    }
  }

  await visit(sitemapSource, 0);
  if (!routes.length) throw new CensusInputError("Sitemap produced no canonical HTTP(S) routes.");
  return routes;
}

function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function textEvidence(value) {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value);
  return { sha256: sha256(text), length: [...text].length };
}

function routeEvidence(value) {
  try {
    const parsed = new URL(value);
    return {
      routeSha256: sha256(value),
      redacted: redactUrl(value),
      origin: parsed.origin,
      queryKeys: [...new Set(parsed.searchParams.keys())],
      fragmentPresent: Boolean(parsed.hash),
    };
  } catch {
    return { routeSha256: sha256(value), redacted: "<redacted-route>" };
  }
}

function redactUrl(value) {
  try {
    const parsed = new URL(String(value));
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "<redacted-route>";
    const pathLabel = parsed.pathname === "/" ? "/" : "/<redacted-path>";
    const queryKeys = [...new Set(parsed.searchParams.keys())];
    const query = queryKeys.length
      ? `?${queryKeys.map((key) => `${encodeURIComponent(key)}=<redacted>`).join("&")}`
      : "";
    return `${parsed.origin}${pathLabel}${query}${parsed.hash ? "#<redacted-fragment>" : ""}`;
  } catch {
    return "<redacted-route>";
  }
}

function redactText(value) {
  return String(value).replace(/\b(?:https?|file|data):[^\s"'<>]+/gi, (candidate) => redactUrl(candidate));
}

function prepareOutputDirectory(value) {
  if (fs.existsSync(value)) {
    let entries;
    try {
      entries = fs.readdirSync(value);
    } catch {
      throw new CensusInputError("Output directory is not readable.");
    }
    if (entries.length) throw new CensusInputError("Output directory is not empty; choose a new directory.");
  }
  try {
    fs.mkdirSync(value, { recursive: true });
  } catch {
    throw new CensusInputError("Output directory could not be created.");
  }
}

function writeRecords(filePath, records) {
  const body = records.length
    ? `${records.map((record) => JSON.stringify(record)).join("\n")}\n`
    : "";
  fs.writeFileSync(filePath, body);
}

function writeSummary(filePath, summary) {
  fs.writeFileSync(filePath, `${JSON.stringify(summary, null, 2)}\n`);
}

function writeRunError(outDir, error, records = []) {
  const message = redactText(error?.message || String(error));
  const aggregate = summarizeRecords(records);
  const summary = {
    schemaVersion: 1,
    status: "run-error",
    exitCode: 2,
    error: {
      name: error?.name || "Error",
      message,
    },
    totals: aggregate.totals,
    issuesByType: aggregate.issuesByType,
  };
  writeRecords(path.join(outDir, "records.jsonl"), records);
  writeSummary(path.join(outDir, "summary.json"), summary);
}

async function waitForCensusReadiness(page) {
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const completeImages = [...document.images].filter((image) => image.complete);
    await Promise.all(completeImages.map((image) => image.decode?.().catch(() => {})));
  });
  if (SETTLE_MS > 0) await page.waitForTimeout(SETTLE_MS);
}

async function auditRouteViewport(browser, route, routeIndex, viewport) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.deviceScaleFactor,
    isMobile: viewport.isMobile,
    hasTouch: viewport.hasTouch,
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  let crashed = false;
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error?.message || String(error)));
  page.on("crash", () => { crashed = true; });

  let response = null;
  let navigationError = null;
  let finalUrl = route;
  let census = { metrics: {}, issues: [] };
  try {
    response = await page.goto(route, { waitUntil: "domcontentloaded", timeout: NAVIGATION_TIMEOUT_MS });
    await waitForCensusReadiness(page);
    census = await page.evaluate(censusPage);
    finalUrl = page.url();
  } catch (error) {
    navigationError = error;
    try { finalUrl = page.url(); } catch { /* retain the requested route */ }
  } finally {
    await context.close().catch(() => {});
  }

  const issues = [...census.issues];
  if (response && response.status() !== 200) {
    issues.push({
      type: "non-200",
      severity: "error",
      detail: `Navigation returned HTTP ${response.status()}.`,
      httpStatus: response.status(),
    });
  }
  if (navigationError) {
    issues.push({
      type: "fatal-navigation",
      severity: "error",
      detail: "The route could not be rendered to the census checkpoint.",
      errorEvidence: textEvidence(navigationError?.message || String(navigationError)),
    });
  }
  if (crashed) {
    issues.push({ type: "fatal-page-crash", severity: "error", detail: "The browser page crashed." });
  }
  if (pageErrors.length) {
    issues.push({
      type: "fatal-page-error",
      severity: "error",
      count: pageErrors.length,
      detail: "Uncaught page errors were emitted while rendering the route.",
      evidence: pageErrors.slice(0, 20).map((value) => textEvidence(value)),
    });
  }
  if (consoleErrors.length) {
    issues.push({
      type: "console-error",
      severity: "error",
      count: consoleErrors.length,
      detail: "The page emitted console errors while rendering.",
      evidence: consoleErrors.slice(0, 20).map((value) => textEvidence(value)),
    });
  }

  const hasErrors = issues.some((issue) => issue.severity === "error");
  const hasWarnings = issues.some((issue) => issue.severity === "warning");
  return {
    routeIndex: routeIndex + 1,
    routeEvidence: routeEvidence(route),
    finalUrlEvidence: routeEvidence(finalUrl),
    redirected: finalUrl !== route,
    viewport: {
      name: viewport.name,
      width: viewport.width,
      height: viewport.height,
      isMobile: viewport.isMobile,
    },
    httpStatus: response?.status() ?? null,
    status: hasErrors ? "findings" : hasWarnings ? "warning" : "healthy",
    metrics: census.metrics,
    issues,
  };
}

function censusPage() {
  const issues = [];
  const metrics = {};
  const add = (type, severity, detail, extra = {}) => {
    issues.push({ type, severity, detail, ...extra });
  };
  const browserEvidence = (value) => {
    if (value === null || value === undefined || value === "") return null;
    return { length: [...String(value)].length };
  };

  function isVisible(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    if (typeof element.checkVisibility === "function") {
      return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    }
    const style = getComputedStyle(element);
    return style.display !== "none"
      && style.visibility !== "hidden"
      && Number.parseFloat(style.opacity || "1") > 0;
  }

  function inViewport(rect) {
    return rect.bottom > 0
      && rect.right > 0
      && rect.top < window.innerHeight
      && rect.left < window.innerWidth;
  }

  function isDecorativeImage(image) {
    if (image.getAttribute("aria-hidden") === "true") return true;
    if (["presentation", "none"].includes((image.getAttribute("role") || "").toLowerCase())) return true;
    return Boolean(image.closest('[aria-hidden="true"]'));
  }

  function isPathHash(hash) {
    return hash.startsWith("#/") || hash.startsWith("#!/");
  }

  function hashTargetExists(hash) {
    if (!hash || hash === "#" || isPathHash(hash)) return true;
    let target = hash.slice(1);
    try { target = decodeURIComponent(target); } catch { /* compare the literal fragment */ }
    if (document.getElementById(target)) return true;
    return [...document.querySelectorAll("a[name]")].some((anchor) => anchor.getAttribute("name") === target);
  }

  const overflowX = Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth);
  metrics.horizontalOverflowX = overflowX;
  if (overflowX > 1) {
    add("horizontal-overflow", "error", `Document overflows horizontally by ${overflowX}px.`);
  }

  const renderedImages = [...document.images].filter(isVisible);
  let brokenImages = 0;
  let pendingVisibleImages = 0;
  let missingAltImages = 0;
  for (let index = 0; index < renderedImages.length; index += 1) {
    const image = renderedImages[index];
    const rect = image.getBoundingClientRect();
    const source = image.currentSrc || image.getAttribute("src") || image.getAttribute("data-src") || "";
    if (image.complete && image.naturalWidth === 0) {
      brokenImages += 1;
      add("broken-image", "error", "A rendered image completed without decodable natural dimensions.", {
        count: 1,
        imageIndex: index,
        sourceEvidence: browserEvidence(source),
        altEvidence: browserEvidence(image.getAttribute("alt")),
      });
    } else if ((!image.complete || image.naturalWidth === 0) && inViewport(rect)) {
      pendingVisibleImages += 1;
      add("pending-visible-image", "warning", "A viewport-visible image had not completed when the census checkpoint was captured.", {
        count: 1,
        imageIndex: index,
        sourceEvidence: browserEvidence(source),
      });
    }
    if (!image.hasAttribute("alt") && !isDecorativeImage(image)) {
      missingAltImages += 1;
      add("missing-alt", "error", "A rendered image has no alt attribute and is not marked decorative.", {
        count: 1,
        imageIndex: index,
      });
    }
  }
  metrics.images = {
    rendered: renderedImages.length,
    broken: brokenImages,
    pendingVisible: pendingVisibleImages,
    missingAlt: missingAltImages,
  };

  const idCounts = new Map();
  for (const element of document.querySelectorAll("[id]")) {
    const id = element.getAttribute("id");
    idCounts.set(id, (idCounts.get(id) || 0) + 1);
  }
  const duplicateIds = [...idCounts.entries()].filter(([, count]) => count > 1);
  metrics.duplicateIdCount = duplicateIds.length;
  if (duplicateIds.length) {
    add("duplicate-id", "error", "The document contains duplicate element IDs.", {
      count: duplicateIds.length,
      idEvidence: duplicateIds.map(([id]) => browserEvidence(id)),
    });
  }

  const visibleH1s = [...document.querySelectorAll("h1")].filter(isVisible);
  metrics.h1Count = visibleH1s.length;
  if (!visibleH1s.length) {
    add("missing-h1", "error", "No visible H1 was found.");
  } else if (visibleH1s.length > 1) {
    add("duplicate-h1", "error", "More than one visible H1 was found.", { count: visibleH1s.length });
  }

  const main = [...document.querySelectorAll("main, [role='main']")].find(isVisible);
  metrics.mainCount = main ? 1 : 0;
  if (metrics.mainCount === 0) {
    add("missing-main", "error", "No visible main landmark was found.");
  }

  const bodyText = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
  metrics.visibleTextLength = [...bodyText].length;
  if (!bodyText) {
    add("empty-text", "error", "The rendered document has no visible body text.");
  }

  const brokenHashTargets = new Map();
  if (!hashTargetExists(location.hash)) brokenHashTargets.set(location.hash, null);
  for (const anchor of [...document.querySelectorAll('a[href^="#"]')]) {
    const hash = anchor.getAttribute("href");
    if (!hash || hash === "#" || isPathHash(hash) || hashTargetExists(hash)) continue;
    const current = brokenHashTargets.get(hash);
    brokenHashTargets.set(hash, (current || 0) + 1);
  }
  metrics.brokenHashTargetCount = brokenHashTargets.size;
  if (brokenHashTargets.size) {
    add("broken-hash-anchor", "error", "One or more same-page hash targets do not exist.", {
      count: brokenHashTargets.size,
      targetEvidence: [...brokenHashTargets.keys()].map((hash) => browserEvidence(hash)),
      inboundLinkCount: [...brokenHashTargets.values()].filter((count) => typeof count === "number").length,
    });
  }

  return { metrics, issues };
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`route_census: ${error.message}`);
    console.error(usage);
    return 2;
  }
  if (options.help) {
    console.log(usage);
    return 0;
  }

  const outDir = options.out || path.join(
    os.tmpdir(),
    `route-census-${new Date().toISOString().replace(/[:.]/g, "-")}-${process.pid}`,
  );
  let outputPrepared = false;
  let browser;
  const records = [];
  const startedAt = new Date().toISOString();
  try {
    prepareOutputDirectory(outDir);
    outputPrepared = true;

    const sitemapSource = options.sitemap
      ? resolveSitemapReference(options.sitemap, null)
      : normalizeSiteSitemap(options.url);
    const allRoutes = await collectRoutes(sitemapSource);
    const routes = options.limit ? allRoutes.slice(0, options.limit) : allRoutes;
    const viewports = options.viewports.length ? options.viewports : DEFAULT_VIEWPORTS;
    const { chromium } = loadPlaywright();
    const executablePath = findChrome();
    browser = await chromium.launch({
      ...(executablePath ? { executablePath } : {}),
      headless: true,
    });

    for (let routeIndex = 0; routeIndex < routes.length; routeIndex += 1) {
      for (const viewport of viewports) {
        const record = await auditRouteViewport(browser, routes[routeIndex], routeIndex, viewport);
        records.push(record);
        const issueSummary = record.issues.length
          ? record.issues.map((issue) => `${issue.severity}:${issue.type}`).join(",")
          : "healthy";
        console.log(`route ${routeIndex + 1}/${routes.length} ${viewport.name}: ${issueSummary}`);
      }
    }

    const summary = summarizeRecords(records, {
      startedAt,
      finishedAt: new Date().toISOString(),
      input: {
        mode: options.url ? "url" : "sitemap",
        sitemapEvidence: routeEvidence(sitemapSource),
        discoveredRoutes: allRoutes.length,
        examinedRoutes: routes.length,
        limited: Boolean(options.limit && allRoutes.length > options.limit),
        limit: options.limit,
      },
      viewports,
      output: {
        records: "records.jsonl",
        summary: "summary.json",
      },
      evidenceBoundary: "Level C structural census; screenshots and subjective visual acceptance are not included.",
    });
    writeRecords(path.join(outDir, "records.jsonl"), records);
    writeSummary(path.join(outDir, "summary.json"), summary);
    console.log(
      `Route census ${summary.status}: ${summary.totals.records} record(s), `
      + `${summary.totals.errorOccurrences} error(s), ${summary.totals.warningOccurrences} warning(s). `
      + `Output: ${outDir}`,
    );
    return summary.exitCode;
  } catch (error) {
    if (outputPrepared) writeRunError(outDir, error, records);
    console.error(`route_census: ${redactText(error?.message || String(error))}`);
    return 2;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

function isMainModule() {
  if (!process.argv[1]) return false;
  try {
    return fs.realpathSync(path.resolve(process.argv[1]))
      === fs.realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

const isMain = isMainModule();
if (isMain) {
  main().then((code) => {
    process.exitCode = code;
  }).catch((error) => {
    console.error(`route_census: ${redactText(error?.message || String(error))}`);
    process.exitCode = 2;
  });
}
