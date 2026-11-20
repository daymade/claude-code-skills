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
 *     [--allow-origin <http(s)-origin>]... [--allow-target <host>]...
 *     [--probe <url>]... [--probe-expected-status <100-599>]
 *     [--route-timeout-ms <1000-300000>]
 *
 * --url resolves sitemap.xml relative to the supplied site path. --sitemap
 * accepts an explicit HTTP(S) URL, file URL, or local XML path. Sitemap indexes
 * are followed recursively without crossing the root's file/HTTP boundary.
 * Routes retain sitemap order and are de-duplicated by absolute URL before
 * --limit is applied. Discovery stops at --limit and is marked truncated.
 *
 * Exit: 0 clean or warning-only · 1 confirmed route errors · 2 invalid input or
 * runtime/setup failure. This is a Level C census, not visual acceptance; any
 * screenshots used for an appearance claim must still be opened and inspected.
 */
import { createHash } from "node:crypto";
import dns from "node:dns/promises";
import fs from "node:fs";
import { createRequire } from "node:module";
import { isIP } from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

export const MAX_SITEMAP_BYTES = 10 * 1024 * 1024;
export const MAX_SITEMAP_DEPTH = 5;
export const MAX_SITEMAP_DOCUMENTS = 100;
export const MAX_DISCOVERED_ROUTES = 10_000;
export const MAX_PROBES = 100;
export const MAX_VIEWPORTS = 20;
export const NAVIGATION_TIMEOUT_MS = 30_000;
export const DEFAULT_ROUTE_DEADLINE_MS = 45_000;
export const PATH_STYLE_HASH_PREFIXES = ["#!", "#/"];
const SETTLE_MS = 500;
const DNS_POLICY_CACHE = new Map();
const DEFAULT_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true },
];

const usage = [
  "Usage: route_census.mjs (--url <site-url> | --sitemap <sitemap-url-or-file>)",
  "  [--viewport <WIDTH>x<HEIGHT>]... (default: 1440x900 and 390x844)",
  "  [--limit <positive-int>] [--out <new-empty-directory>]",
  "  [--allow-origin <http(s)-origin>]... [--allow-target <host>]...",
  "  [--probe <url>]... [--probe-expected-status <100-599>]",
  "  [--route-timeout-ms <1000-300000>]",
  "",
  "--url resolves sitemap.xml relative to the supplied site path.",
  "--sitemap accepts an explicit HTTP(S) URL, file URL, or local XML path.",
  "Sitemap indexes stay within the root scheme; local file roots are directory-confined.",
  "Discovery is capped at 100 documents/10,000 routes; at most 20 viewports and 100 probes are accepted.",
  "Canonical routes are same-origin by default; private/loopback/link-local targets require --allow-target.",
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
    allowOrigins: [],
    allowTargets: [],
    probes: [],
    probeExpectedStatus: 404,
    routeTimeoutMs: DEFAULT_ROUTE_DEADLINE_MS,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      return { help: true };
    }
    const arrayFlags = new Set(["--viewport", "--allow-origin", "--allow-target", "--probe"]);
    if (!arrayFlags.has(arg) && !["--url", "--sitemap", "--out", "--limit", "--probe-expected-status", "--route-timeout-ms"].includes(arg)) {
      if (arg.startsWith("-")) throw new CensusInputError(`Unknown option: ${arg}`);
      throw new CensusInputError(`Unexpected positional argument: ${arg}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new CensusInputError(`Missing value for ${arg}.`);
    index += 1;
    if (arg === "--viewport") options.viewports.push(parseViewport(value));
    else if (arg === "--limit") options.limit = parsePositiveInteger(value, "--limit");
    else if (arg === "--allow-origin") options.allowOrigins.push(normalizeAllowedOrigin(value));
    else if (arg === "--allow-target") options.allowTargets.push(normalizeAllowedTarget(value));
    else if (arg === "--probe") options.probes.push(value);
    else if (arg === "--probe-expected-status") options.probeExpectedStatus = parseHttpStatus(value, "--probe-expected-status");
    else if (arg === "--route-timeout-ms") options.routeTimeoutMs = parseBoundedInteger(value, "--route-timeout-ms", 1_000, 300_000);
    else options[arg.slice(2)] = value;
  }

  if (Boolean(options.url) === Boolean(options.sitemap)) {
    throw new CensusInputError("Provide exactly one of --url or --sitemap.");
  }
  if (options.probes.length > MAX_PROBES) {
    throw new CensusInputError(`At most ${MAX_PROBES} --probe routes are supported.`);
  }
  if (options.viewports.length > MAX_VIEWPORTS) {
    throw new CensusInputError(`At most ${MAX_VIEWPORTS} --viewport entries are supported.`);
  }
  return options;
}

function parseBoundedInteger(value, flagName, minimum, maximum) {
  const parsed = parsePositiveInteger(value, flagName);
  if (parsed < minimum || parsed > maximum) {
    throw new CensusInputError(`Invalid ${flagName} value: ${value}. Expected ${minimum}-${maximum}.`);
  }
  return parsed;
}

function parseHttpStatus(value, flagName) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 100 || parsed > 599 || String(parsed) !== String(value).trim()) {
    throw new CensusInputError(`Invalid ${flagName} value: ${value}. Expected an integer from 100 to 599.`);
  }
  return parsed;
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

function normalizeAllowedOrigin(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new CensusInputError("--allow-origin must be an absolute HTTP(S) origin, for example https://example.com.");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new CensusInputError("--allow-origin must use HTTP or HTTPS.");
  }
  if (parsed.username || parsed.password || (parsed.pathname && parsed.pathname !== "/") || parsed.search || parsed.hash) {
    throw new CensusInputError("--allow-origin must contain only a scheme and host (an origin), without credentials, path, query or fragment.");
  }
  return parsed.origin;
}

function normalizeAllowedTarget(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) throw new CensusInputError("--allow-target must not be empty.");
  try {
    const parsed = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`);
    if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
      throw new Error("unsupported target");
    }
    return parsed.hostname.replace(/^\[|\]$/g, "").split("%")[0].toLowerCase();
  } catch {
    throw new CensusInputError(`Invalid --allow-target value: ${value}. Expected a hostname or IP address.`);
  }
}

function ipv4ToInteger(hostname) {
  const parts = hostname.split(".").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return null;
  return ((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3];
}

function inIpv4Range(hostname, base, prefixLength) {
  const address = ipv4ToInteger(hostname);
  if (address === null || prefixLength <= 0) return address !== null && prefixLength === 0;
  const mask = prefixLength === 32 ? 0xffffffff : ((0xffffffff << (32 - prefixLength)) >>> 0);
  return (address & mask) === (base & mask);
}

function isRestrictedHostname(hostname) {
  const host = String(hostname || "").replace(/^\[|\]$/g, "").toLowerCase().replace(/\.$/, "").split("%")[0];
  if (!host) return false;
  if (host === "localhost" || host.endsWith(".localhost")) return true;
  if (isIP(host) === 4) {
    return [
      [0x00000000, 8],       // current network / unspecified
      [0x0a000000, 8],       // private
      [0x64400000, 10],      // carrier-grade NAT
      [0x7f000000, 8],       // loopback
      [0xa9fe0000, 16],      // link-local
      [0xac100000, 12],      // private
      [0xc0000000, 24],      // IETF protocol assignments
      [0xc0000200, 24],      // documentation
      [0xc6120000, 15],      // benchmarking
      [0xc6336400, 24],      // documentation
      [0xcb007100, 24],      // documentation
      [0xe0000000, 4],       // multicast
      [0xf0000000, 4],       // reserved
    ].some(([base, prefix]) => inIpv4Range(host, base, prefix));
  }
  if (isIP(host) === 6) {
    return host === "::"
      || host === "::1"
      || host.startsWith("::ffff:")
      || /^f[cd][0-9a-f]{2}:/.test(host)
      || /^fe[89ab][0-9a-f]:/.test(host)
      || /^ff[0-9a-f]{2}:/.test(host);
  }
  return false;
}

function assertTargetAllowed(url, allowedTargets, label) {
  if (!/^https?:$/i.test(url.protocol)) return;
  const hostname = url.hostname.replace(/^\[|\]$/g, "").split("%")[0].toLowerCase();
  if (isRestrictedHostname(hostname) && !allowedTargets.has(hostname)) {
    throw new CensusInputError(
      `${label} targets restricted host ${hostname}. Add --allow-target ${hostname} only when that exact target is intended.`,
    );
  }
}

async function assertTargetAllowedAsync(url, allowedTargets, label) {
  assertTargetAllowed(url, allowedTargets, label);
  const hostname = url.hostname.replace(/^\[|\]$/g, "").split("%")[0].toLowerCase();
  if (!hostname) return;
  const documentationHost = hostname === "example.com"
    || hostname === "example.org"
    || hostname === "example.net"
    || hostname.endsWith(".test")
    || hostname.endsWith(".invalid");
  if (isIP(hostname) || documentationHost || allowedTargets.has(hostname) || DNS_POLICY_CACHE.has(hostname)) return;
  try {
    const addresses = await dns.lookup(hostname, { all: true });
    const restricted = addresses.some((entry) => isRestrictedHostname(entry.address));
    DNS_POLICY_CACHE.set(hostname, restricted);
    if (restricted) {
      throw new CensusInputError(
        `${label} resolves to a restricted address. Add --allow-target ${hostname} only when that exact target is intended.`,
      );
    }
  } catch (error) {
    if (error instanceof CensusInputError) throw error;
    // DNS failure stays unknown; the literal hostname policy still applies.
    DNS_POLICY_CACHE.set(hostname, false);
  }
}

function assertFileWithinRoot(source, rootDirectory, label) {
  if (!/^file:/i.test(source)) throw new CensusInputError(`${label} must use a file URL under the local sitemap root.`);
  let filePath;
  try {
    filePath = fileURLToPath(source);
  } catch {
    throw new CensusInputError(`${label} is not a valid local file URL.`);
  }
  const rootPath = fs.existsSync(rootDirectory)
    ? fs.realpathSync(rootDirectory)
    : path.resolve(rootDirectory);
  const candidatePath = fs.existsSync(filePath) ? fs.realpathSync(filePath) : path.resolve(filePath);
  let relative = path.relative(rootPath, candidatePath);
  if (process.platform === "win32") relative = relative.toLowerCase();
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new CensusInputError(`${label} resolves outside the local sitemap root directory.`);
  }
}

function resolveSitemapReference(value, baseSource, policy = {}) {
  const trimmed = String(value || "").trim();
  if (!trimmed) throw new CensusInputError("Sitemap contains an empty <loc>.");

  let resolved;
  try {
    resolved = new URL(trimmed, baseSource || undefined);
  } catch {
    if (baseSource) throw new CensusInputError("Sitemap contains an invalid child reference.");
    return pathToFileURL(path.resolve(trimmed)).href;
  }
  if (!["http:", "https:", "file:"].includes(resolved.protocol)) {
    throw new CensusInputError("Sitemap references must use HTTP(S) or file URLs.");
  }
  assertNoEmbeddedCredentials(resolved, "sitemap");

  const rootProtocol = policy.rootProtocol || (baseSource ? new URL(baseSource).protocol : null);
  if (rootProtocol === "http:" || rootProtocol === "https:") {
    if (resolved.protocol === "file:") {
      throw new CensusInputError("An HTTP(S) root sitemap must not follow file: child references.");
    }
  } else if (rootProtocol === "file:") {
    if (resolved.protocol !== "file:") {
      throw new CensusInputError("A local file sitemap root may only follow file: child references.");
    }
    assertFileWithinRoot(resolved.href, policy.rootDirectory, "Local sitemap child");
  }

  if (resolved.protocol === "http:" || resolved.protocol === "https:") {
    assertTargetAllowed(resolved, policy.allowedTargets || new Set(), "Sitemap reference");
  }
  return resolved.href;
}

function assertNoEmbeddedCredentials(url, label) {
  if (url.username || url.password) {
    throw new CensusInputError(`${label} must not contain embedded credentials.`);
  }
}

async function readSitemap(source, policy = {}) {
  if (/^https?:\/\//i.test(source)) {
    let current = source;
    let response;
    for (let hop = 0; hop <= 5; hop += 1) {
      const currentUrl = new URL(current);
      await assertTargetAllowedAsync(currentUrl, policy.allowedTargets || new Set(), "Sitemap reference");
      if (policy.rootOrigin && currentUrl.origin !== policy.rootOrigin && !(policy.allowedOrigins || new Set()).has(currentUrl.origin)) {
        throw new CensusInputError(`Sitemap redirect origin ${currentUrl.origin} does not match ${policy.rootOrigin}.`);
      }
      try {
        response = await fetch(current, {
          redirect: "manual",
          signal: AbortSignal.timeout(NAVIGATION_TIMEOUT_MS),
          headers: { Accept: "application/xml,text/xml;q=0.9,*/*;q=0.8" },
        });
      } catch (error) {
        throw new CensusInputError(`Could not fetch sitemap: ${redactText(error?.message || String(error))}`);
      }
      if (response.status >= 300 && response.status < 400 && response.headers.get("location")) {
        await response.body?.cancel().catch(() => {});
        current = new URL(response.headers.get("location"), current).href;
        continue;
      }
      break;
    }
    if (!response) throw new CensusInputError("Sitemap redirect chain did not produce a response.");
    if (!response.ok) throw new CensusInputError(`Sitemap returned HTTP ${response.status}.`)
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

export function isPathStyleHash(hash) {
  const value = String(hash || "");
  return PATH_STYLE_HASH_PREFIXES.some((prefix) => value.startsWith(prefix));
}

export function selectRoutes(routes, limit = null) {
  const ordered = Array.isArray(routes) ? routes : [];
  if (limit === null || limit === undefined) return ordered.slice();
  const parsed = Number.parseInt(limit, 10);
  if (!Number.isInteger(parsed) || parsed <= 0 || String(parsed) !== String(limit).trim()) {
    throw new CensusInputError(`Invalid route limit: ${limit}. Expected a positive integer.`);
  }
  return ordered.slice(0, parsed);
}

export async function discoverRoutes(sitemapSource, read = readSitemap, options = {}) {
  const rootUrl = new URL(sitemapSource);
  const allowedTargets = new Set(options.allowedTargets || []);
  const allowedOrigins = new Set(options.allowedOrigins || []);
  const routeLimit = options.routeLimit ?? options.limit ?? null;
  const maxSitemapDocuments = options.maxSitemapDocuments ?? MAX_SITEMAP_DOCUMENTS;
  const maxRoutes = options.maxRoutes ?? MAX_DISCOVERED_ROUTES;
  if (!Number.isInteger(routeLimit) || routeLimit <= 0) {
    if (routeLimit !== null) throw new CensusInputError("routeLimit must be a positive integer or null.");
  }
  if (!Number.isInteger(maxSitemapDocuments) || maxSitemapDocuments <= 0) {
    throw new CensusInputError("maxSitemapDocuments must be a positive integer.");
  }
  if (!Number.isInteger(maxRoutes) || maxRoutes <= 0) {
    throw new CensusInputError("maxRoutes must be a positive integer.");
  }

  await assertTargetAllowedAsync(rootUrl, allowedTargets, "Root sitemap");
  const policy = {
    rootProtocol: rootUrl.protocol,
    rootOrigin: rootUrl.protocol === "http:" || rootUrl.protocol === "https:" ? rootUrl.origin : null,
    rootDirectory: rootUrl.protocol === "file:" ? path.dirname(fileURLToPath(rootUrl)) : null,
    allowedTargets,
    allowedOrigins,
  };
  const routes = [];
  const seenRoutes = new Set();
  const seenSitemaps = new Set();
  let canonicalOrigin = rootUrl.protocol === "http:" || rootUrl.protocol === "https:"
    ? rootUrl.origin
    : null;
  let sitemapDocumentsRead = 0;
  let truncated = false;
  let truncationReason = null;
  const stop = (reason) => {
    truncated = true;
    truncationReason = reason;
  };
  const isStopped = () => truncated;

  async function visit(source, depth) {
    if (isStopped()) return;
    if (depth > MAX_SITEMAP_DEPTH) throw new CensusInputError("Sitemap index nesting exceeds the supported depth.");
    if (seenSitemaps.has(source)) return;
    if (sitemapDocumentsRead >= maxSitemapDocuments) {
      stop("sitemap-document-cap");
      return;
    }
    if (policy.rootProtocol === "file:") assertFileWithinRoot(source, policy.rootDirectory, "Sitemap document");
    seenSitemaps.add(source);
    sitemapDocumentsRead += 1;
    const parsed = parseSitemapXml(await read(source, policy));
    if (parsed.kind === "index") {
      for (const location of parsed.locations) {
        if (isStopped()) return;
        const child = resolveSitemapReference(location, source, policy);
        if (seenSitemaps.has(child)) continue;
        if (sitemapDocumentsRead >= maxSitemapDocuments) {
          stop("sitemap-document-cap");
          return;
        }
        await visit(child, depth + 1);
      }
      return;
    }

    for (const location of parsed.locations) {
      if (isStopped()) return;
      if (routeLimit !== null && routes.length >= routeLimit) {
        stop("requested-limit");
        return;
      }
      if (routes.length >= maxRoutes) {
        stop("route-cap");
        return;
      }
      let routeUrl;
      try {
        routeUrl = new URL(location, source);
      } catch {
        throw new CensusInputError("Sitemap contains an invalid route URL.");
      }
      if (routeUrl.protocol !== "http:" && routeUrl.protocol !== "https:") {
        throw new CensusInputError("Canonical routes must use HTTP or HTTPS.");
      }
      assertNoEmbeddedCredentials(routeUrl, "canonical route");
      await assertTargetAllowedAsync(routeUrl, allowedTargets, "Canonical route");
      if (canonicalOrigin === null) canonicalOrigin = routeUrl.origin;
      if (routeUrl.origin !== canonicalOrigin && !allowedOrigins.has(routeUrl.origin)) {
        throw new CensusInputError(
          `Canonical route origin ${routeUrl.origin} does not match ${canonicalOrigin}. Add --allow-origin ${routeUrl.origin} only when cross-origin routes are intended.`,
        );
      }
      const route = routeUrl.href;
      if (seenRoutes.has(route)) continue;
      seenRoutes.add(route);
      routes.push(route);
      if (routeLimit !== null && routes.length >= routeLimit) {
        stop("requested-limit");
        return;
      }
    }
  }

  await visit(sitemapSource, 0);
  if (!routes.length) throw new CensusInputError("Sitemap produced no canonical HTTP(S) routes.");
  return {
    routes,
    discovery: {
      truncated,
      reason: truncationReason,
      sitemapDocumentsRead,
      maxSitemapDocuments,
      maxRoutes,
      requestedLimit: routeLimit,
      canonicalOrigin,
    },
  };
}

export async function collectRoutes(sitemapSource, read = readSitemap, options = {}) {
  const result = await discoverRoutes(sitemapSource, read, options);
  return result.routes;
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

export async function withDeadline(operation, deadline, label) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) {
    const error = new Error(`${label} exceeded its hard deadline.`);
    error.name = "CensusDeadlineError";
    throw error;
  }
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const error = new Error(`${label} exceeded its hard deadline.`);
      error.name = "CensusDeadlineError";
      reject(error);
    }, remaining);
    Promise.resolve().then(() => (typeof operation === "function" ? operation() : operation)).then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error) => { clearTimeout(timer); reject(error); },
    );
  });
}

async function auditRouteViewport(browser, descriptor, routeIndex, viewport, routeTimeoutMs, policy = {}) {
  const route = descriptor.route;
  const deadline = Date.now() + routeTimeoutMs;
  let context = null;
  let page = null;
  const consoleErrors = [];
  const pageErrors = [];
  let crashed = false;
  let response = null;
  let navigationError = null;
  let deadlineError = null;
  let policyError = null;
  let finalUrl = route;
  let census = { metrics: {}, issues: [] };

  try {
    context = await withDeadline(browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: viewport.deviceScaleFactor,
      isMobile: viewport.isMobile,
      hasTouch: viewport.hasTouch,
    }), deadline, "Browser context creation");
    page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Fetch.enable", {
      patterns: [{ urlPattern: "*", requestStage: "Request", resourceType: "Document" }],
    });
    cdp.on("Fetch.requestPaused", async (event) => {
      try {
        const target = new URL(event.request.url);
        await assertTargetAllowedAsync(target, policy.allowedTargets || new Set(), "Navigation target");
        if (policy.canonicalOrigin && target.origin !== policy.canonicalOrigin && !(policy.allowedOrigins || new Set()).has(target.origin)) {
          throw new CensusInputError(`Navigation origin ${target.origin} does not match ${policy.canonicalOrigin}.`);
        }
        await cdp.send("Fetch.continueRequest", { requestId: event.requestId });
      } catch (error) {
        policyError = error;
        await cdp.send("Fetch.failRequest", {
          requestId: event.requestId,
          errorReason: "AccessDenied",
        }).catch(() => {});
      }
    });
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push({ text: message.text(), url: message.location()?.url || "" });
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error?.message || String(error)));
    page.on("crash", () => { crashed = true; });

    await withDeadline((async () => {
      response = await page.goto(route, { waitUntil: "domcontentloaded", timeout: NAVIGATION_TIMEOUT_MS });
      await waitForCensusReadiness(page);
      census = await page.evaluate(censusPage, { pathStyleHashPrefixes: PATH_STYLE_HASH_PREFIXES });
      finalUrl = page.url();
    })(), deadline, `Route ${routeIndex + 1} at ${viewport.name}`);
  } catch (error) {
    if (error?.name === "CensusDeadlineError") deadlineError = error;
    else navigationError = error;
    try { if (page) finalUrl = page.url(); } catch { /* retain the requested route */ }
  } finally {
    await context?.close().catch(() => {});
  }

  const issues = [...census.issues];
  const observedStatus = response?.status() ?? null;
  const expectedStatusMatched = observedStatus === descriptor.expectedStatus;
  if (response && !expectedStatusMatched) {
    issues.push({
      type: "non-200",
      severity: "error",
      detail: `Navigation returned HTTP ${observedStatus}; expected ${descriptor.expectedStatus}.`,
      httpStatus: observedStatus,
      expectedStatus: descriptor.expectedStatus,
    });
  }
  if (deadlineError) {
    issues.push({
      type: "route-deadline",
      severity: "error",
      detail: `The route exceeded the ${routeTimeoutMs}ms hard deadline covering navigation, readiness and evaluation.`,
      deadlineMs: routeTimeoutMs,
    });
  }
  if (policyError) {
    issues.push({
      type: "navigation-policy",
      severity: "error",
      detail: "A main-frame navigation violated the target or origin policy.",
      errorEvidence: textEvidence(policyError?.message || String(policyError)),
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
  const expectedProbe = descriptor.routeKind === "localized-404-probe" && expectedStatusMatched;
  const relevantConsoleErrors = consoleErrors.filter((entry) => {
    if (!expectedProbe || entry.url !== route) return true;
    return !/Failed to load resource/i.test(entry.text)
      || !new RegExp(`\\b${descriptor.expectedStatus}\\b`).test(entry.text);
  });
  if (relevantConsoleErrors.length) {
    issues.push({
      type: "console-error",
      severity: "error",
      count: relevantConsoleErrors.length,
      detail: "The page emitted console errors while rendering.",
      evidence: relevantConsoleErrors.slice(0, 20).map((entry) => textEvidence(entry.text)),
    });
  }

  const hasErrors = issues.some((issue) => issue.severity === "error");
  const hasWarnings = issues.some((issue) => issue.severity === "warning");
  return {
    routeIndex: routeIndex + 1,
    routeKind: descriptor.routeKind,
    expectedStatus: descriptor.expectedStatus,
    expectedStatusMatched: response ? expectedStatusMatched : null,
    routeEvidence: routeEvidence(route),
    finalUrlEvidence: routeEvidence(finalUrl),
    redirected: finalUrl !== route,
    viewport: {
      name: viewport.name,
      width: viewport.width,
      height: viewport.height,
      isMobile: viewport.isMobile,
    },
    httpStatus: observedStatus,
    deadlineMs: routeTimeoutMs,
    status: hasErrors ? "findings" : hasWarnings ? "warning" : "healthy",
    metrics: census.metrics,
    issues,
  };
}

function censusPage({ pathStyleHashPrefixes }) {
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
    const style = getComputedStyle(element);
    if (style.display === "none"
      || style.visibility === "hidden"
      || Number.parseFloat(style.opacity || "1") <= 0) {
      return false;
    }
    if (style.display === "contents") return hasVisibleContents(element, new Set());
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    if (typeof element.checkVisibility === "function") {
      return element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    }
    return true;
  }

  function hasVisibleContents(root, seen) {
    if (!root || seen.has(root)) return false;
    seen.add(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeType === Node.TEXT_NODE) {
        if (!node.nodeValue?.trim()) continue;
        const parentStyle = getComputedStyle(node.parentElement);
        if (parentStyle.display === "none"
          || parentStyle.visibility === "hidden"
          || Number.parseFloat(parentStyle.opacity || "1") <= 0) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        const hasTextBox = [...range.getClientRects()].some((rect) => rect.width > 0 && rect.height > 0);
        range.detach?.();
        if (hasTextBox) return true;
        continue;
      }
      const style = getComputedStyle(node);
      if (style.display === "none"
        || style.visibility === "hidden"
        || Number.parseFloat(style.opacity || "1") <= 0) continue;
      const rect = node.getBoundingClientRect();
      if (style.display !== "contents" && rect.width > 0 && rect.height > 0) return true;
      if (hasVisibleContents(node, seen)) return true;
    }
    return false;
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
    return pathStyleHashPrefixes.some((prefix) => hash.startsWith(prefix));
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

    const allowedTargets = new Set(options.allowTargets);
    const allowedOrigins = new Set(options.allowOrigins);
    const sitemapSource = options.sitemap
      ? resolveSitemapReference(options.sitemap, null, { allowedTargets })
      : normalizeSiteSitemap(options.url);
    const discovered = await discoverRoutes(sitemapSource, readSitemap, {
      routeLimit: options.limit,
      allowedTargets,
      allowedOrigins,
    });
    const canonicalRoutes = selectRoutes(discovered.routes, options.limit);
    const descriptors = canonicalRoutes.map((route) => ({
      route,
      routeKind: "canonical",
      expectedStatus: 200,
    }));
    for (const probe of options.probes) {
      let probeUrl;
      try {
        probeUrl = new URL(probe);
      } catch {
        throw new CensusInputError(`Invalid --probe URL: ${probe}`);
      }
      if (probeUrl.protocol !== "http:" && probeUrl.protocol !== "https:") {
        throw new CensusInputError("--probe must use HTTP or HTTPS.");
      }
      assertNoEmbeddedCredentials(probeUrl, "probe route");
      await assertTargetAllowedAsync(probeUrl, allowedTargets, "Probe route");
      if (probeUrl.origin !== discovered.discovery.canonicalOrigin && !allowedOrigins.has(probeUrl.origin)) {
        throw new CensusInputError(
          `Probe origin ${probeUrl.origin} does not match ${discovered.discovery.canonicalOrigin}. Add --allow-origin ${probeUrl.origin} only when intended.`,
        );
      }
      descriptors.push({
        route: probeUrl.href,
        routeKind: "localized-404-probe",
        expectedStatus: options.probeExpectedStatus,
      });
    }

    const viewports = options.viewports.length ? options.viewports : DEFAULT_VIEWPORTS;
    const { chromium } = loadPlaywright();
    const executablePath = findChrome();
    browser = await chromium.launch({
      ...(executablePath ? { executablePath } : {}),
      headless: true,
    });

    for (let routeIndex = 0; routeIndex < descriptors.length; routeIndex += 1) {
      for (const viewport of viewports) {
        const record = await auditRouteViewport(
          browser,
          descriptors[routeIndex],
          routeIndex,
          viewport,
          options.routeTimeoutMs,
          {
            allowedTargets,
            allowedOrigins,
            canonicalOrigin: discovered.discovery.canonicalOrigin,
          },
        );
        records.push(record);
        const issueSummary = record.issues.length
          ? record.issues.map((issue) => `${issue.severity}:${issue.type}`).join(",")
          : "healthy";
        console.log(`route ${routeIndex + 1}/${descriptors.length} ${record.routeKind} ${viewport.name}: ${issueSummary}`);
      }
    }

    const summary = summarizeRecords(records, {
      startedAt,
      finishedAt: new Date().toISOString(),
      input: {
        mode: options.url ? "url" : "sitemap",
        sitemapEvidence: routeEvidence(sitemapSource),
        discoveredRoutes: discovered.routes.length,
        examinedCanonicalRoutes: canonicalRoutes.length,
        probeRoutes: options.probes.length,
        probeExpectedStatus: options.probes.length ? options.probeExpectedStatus : null,
        limited: discovered.discovery.truncated,
        limit: options.limit,
        discovery: discovered.discovery,
        routeTimeoutMs: options.routeTimeoutMs,
        allowedOrigins: [...allowedOrigins],
        allowedTargets: [...allowedTargets],
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
