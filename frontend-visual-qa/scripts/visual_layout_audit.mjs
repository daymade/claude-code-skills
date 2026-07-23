#!/usr/bin/env node
import { createHash } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

function loadPlaywright() {
  // Resolve a Playwright browser driver across install layouts. Under a pnpm workspace,
  // `playwright-core` is a non-hoisted transitive dep of `@playwright/test` and is NOT
  // symlinked into the top-level node_modules, so requiring it by name fails there.
  // The direct dep `@playwright/test` (and `playwright`) re-export `chromium`, so fall
  // back to them — that path resolves cleanly under pnpm, npm, and yarn alike.
  const requirers = [
    createRequire(`${process.cwd()}/package.json`), // the audited project
    createRequire(import.meta.url),                  // the skill's own dir
  ];
  const candidates = ["playwright-core", "playwright", "@playwright/test"];
  const attempts = [];
  for (const requireFrom of requirers) {
    for (const pkg of candidates) {
      try {
        const mod = requireFrom(pkg);
        if (mod && mod.chromium) return mod;
        attempts.push(`${pkg}: resolved but has no .chromium export`);
      } catch (error) {
        attempts.push(`${pkg}: ${String(error.message).split("\n")[0]}`);
      }
    }
  }
  throw new Error(
    "No Playwright browser driver found (tried playwright-core, playwright, @playwright/test).\n" +
    "Run this sweep from a project that already provides one of those packages.\n" +
    "Do not change the audited project's dependencies unless that mutation is explicitly authorized.\n" +
    "In pnpm workspaces, use the direct @playwright/test package or an explicit NODE_PATH to its package directory.\n" +
    `Resolution attempts:\n  - ${attempts.join("\n  - ")}`
  );
}

function getArg(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  if (idx < 0) return fallback;
  const value = process.argv[idx + 1];
  if (!value || value.startsWith("--")) {
    failUsage("Missing value for " + name + ".");
  }
  return value;
}

function getArgs(name) {
  const values = [];
  for (let index = 0; index < process.argv.length; index += 1) {
    if (process.argv[index] !== name) continue;
    const value = process.argv[index + 1];
    if (!value || value.startsWith("--")) {
      failUsage("Missing value for " + name + ".");
    }
    values.push(value);
  }
  return values;
}

const usage = [
  "Usage: visual_layout_audit.mjs (--url <http://localhost:port/> | --file <artifact.html>)",
  "  [--page-type generic|design-system|live-artifact-design-system|dashboard|app|landing|deck|tool|game]",
  "  [--viewport <width>x<height>]... (replaces the default desktop/mobile matrix)",
  "  [--wait-until domcontentloaded|load|networkidle|commit] [--ready-selector <css>]",
  "  [--settle-ms 750] [--forbid <regex>]... [--require <regex>]...",
  "  [--expected-window-width 1920] [--content-selector main] [--media-selector .hero]",
  "  [--scroll-visible-media] (visit rendered media rows to trigger lazy loading)",
  "  [--section-selector section] [--screenshot-sections] [--max-section-screenshots 4]",
  "  [--out <new-empty-directory>] [--fail-on-warning]",
].join("\n");

function failUsage(message) {
  if (message) console.error(message);
  console.error(usage);
  process.exit(2);
}

function validateKnownFlags() {
  const valueFlags = new Set([
    "--url", "--file", "--out", "--forbid", "--require", "--page-type",
    "--wait-until", "--ready-selector", "--settle-ms", "--expected-window-width",
    "--content-selector", "--media-selector", "--section-selector",
    "--max-section-screenshots", "--viewport",
  ]);
  const booleanFlags = new Set([
    "--help", "-h", "--screenshot-sections", "--scroll-visible-media", "--fail-on-warning",
  ]);
  for (let index = 2; index < process.argv.length; index += 1) {
    const arg = process.argv[index];
    if (valueFlags.has(arg)) {
      index += 1;
      continue;
    }
    if (booleanFlags.has(arg)) continue;
    if (arg.startsWith("-")) failUsage("Unknown option: " + arg);
    failUsage("Unexpected positional argument: " + arg);
  }
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

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(usage);
  process.exit(0);
}
validateKnownFlags();

const urlTarget = getArg("--url");
const fileTarget = getArg("--file");
if (Boolean(urlTarget) === Boolean(fileTarget)) {
  failUsage("Provide exactly one of --url or --file.");
}
const target = urlTarget || fileTarget;
const defaultRunName = "frontend-visual-qa-" + new Date().toISOString().replace(/[:.]/g, "-") + "-" + process.pid;
const outDir = getArg("--out", path.join(os.tmpdir(), defaultRunName));
const forbidPatterns = getArgs("--forbid");
const requirePatterns = getArgs("--require");
const requestedPageType = getArg("--page-type", "generic");
const pageType = requestedPageType === "auto" ? "generic" : requestedPageType;
const customViewports = getArgs("--viewport").map(parseViewport);
const waitUntil = getArg("--wait-until", "domcontentloaded");
const readySelector = getArg("--ready-selector", "");
const settleMs = Number.parseInt(getArg("--settle-ms", "750"), 10);
const expectedWindowWidth = parsePositiveInt(getArg("--expected-window-width", ""));
const contentSelector = getArg("--content-selector", "");
const mediaSelector = getArg("--media-selector", "");
const sectionSelector = getArg(
  "--section-selector",
  pageType === "deck"
    ? ".slide,[data-slide],[role='group'][aria-roledescription='slide'],section"
    : "section,[role='region'],main > div,main > article",
);
const maxSectionScreenshots = parsePositiveInt(
  getArg("--max-section-screenshots", pageType === "deck" ? "50" : "4"),
);
const screenshotSections = process.argv.includes("--screenshot-sections");
const scrollVisibleMedia = process.argv.includes("--scroll-visible-media");
const failOnWarning = process.argv.includes("--fail-on-warning");

const url = normalizeTarget(target);
if (fileTarget) {
  try {
    if (!fs.existsSync(fileURLToPath(url))) failUsage("--file target does not exist.");
  } catch {
    failUsage("Invalid --file target.");
  }
}
for (const pattern of forbidPatterns) validatePattern(pattern, "--forbid");
for (const pattern of requirePatterns) validatePattern(pattern, "--require");
validatePageType(pageType);
validateWaitUntil(waitUntil);
if (!Number.isFinite(settleMs) || settleMs < 0) {
  console.error(`Invalid --settle-ms value: ${getArg("--settle-ms")}`);
  process.exit(2);
}
validateSelector(sectionSelector, "--section-selector");

let browser;
let outputPrepared = false;
try {
  const { chromium } = loadPlaywright();

  if (fs.existsSync(outDir) && fs.readdirSync(outDir).length > 0) {
    throw new Error("Output directory is not empty: " + outDir + ". Choose a new directory to avoid stale evidence.");
  }
  fs.mkdirSync(outDir, { recursive: true });
  outputPrepared = true;

const defaultViewports = [
  { name: "desktop-wide", width: 1700, height: 1000, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];
const viewports = customViewports.length ? customViewports : defaultViewports;

  const executablePath = findChrome();
  browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true,
  });

const report = {
  target: targetEvidence(url),
  createdAt: new Date().toISOString(),
  pageType,
  requiredPatterns: requirePatterns,
  forbiddenPatterns: forbidPatterns,
  checked: [
    "navigation status and final URL",
    "effective viewport and meta viewport",
    "page and section overflow",
    "rendered text wrapping and clipping candidates",
    "custom interactive-role focusability candidates",
    "rendered image request/load state and aspect candidates",
    "page-type contract heuristics",
    "viewport and optional section screenshots",
  ],
  notChecked: [
    "real browser chrome and print preview",
    "downloads, clipboard, popup blocking, and native dialogs",
    "keyboard journey and focus appearance",
    "complete WCAG conformance",
    "GIS interaction behavior",
    "subjective reference parity",
    ...(!scrollVisibleMedia ? ["below-the-fold lazy-media activation"] : []),
  ],
  viewports: [],
  issues: [],
};

for (const viewport of viewports) {
  const page = await browser.newPage({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.deviceScaleFactor,
    isMobile: viewport.isMobile,
    hasTouch: viewport.hasTouch,
  });
  try {
    const response = await page.goto(url, { waitUntil, timeout: 30_000 });
    const httpStatus = response?.status() ?? null;
    if (httpStatus !== null && httpStatus >= 400) {
      throw new Error(
        "Navigation returned HTTP " + httpStatus + " for " + targetEvidence(page.url()).redacted,
      );
    }
    await waitForVisualReadiness(page, readySelector, settleMs);
  const mediaPreparation = scrollVisibleMedia
    ? await primeVisibleMedia(page, mediaSelector, settleMs)
    : null;
  await page.evaluate(() => window.scrollTo(0, 0));
  const screenshot = `${outDir}/${viewport.name}.png`;
  await page.screenshot({ path: screenshot, fullPage: false });
  const result = await page.evaluate(auditPage, {
    viewportName: viewport.name,
    requestedWidth: viewport.width,
    isMobile: viewport.isMobile,
    forbidPatterns,
    requirePatterns,
    pageType,
    expectedWindowWidth,
    contentSelector,
    mediaSelector,
    mediaWalkRequested: scrollVisibleMedia,
    sectionSelector,
    screenshotSections,
  });
  result.meta.href = targetEvidence(result.meta.href);
  result.meta.mediaPreparation = mediaPreparation;
  if (mediaPreparation?.truncated) {
    result.issues.push({
      viewport: viewport.name,
      type: "media-scroll-coverage-truncated",
      severity: "warning",
      detail: `Lazy-media preparation visited ${mediaPreparation.visitedRows}/${mediaPreparation.renderedRows} rendered media row(s); narrow the media scope or use the product harness for complete coverage.`,
    });
  }
  if (mediaPreparation?.failures?.length) {
    result.issues.push({
      viewport: viewport.name,
      type: "media-scroll-preparation-failed",
      severity: "warning",
      detail: `${mediaPreparation.failures.length} rendered media row(s) could not be visited before the audit.`,
    });
  }
  const sectionScreenshots = screenshotSections
    ? await captureSectionScreenshots(
      page,
      viewport,
      outDir,
      sectionSelector,
      maxSectionScreenshots,
      pageType === "deck",
    )
    : [];
  if (screenshotSections) {
    const successfulCaptures = sectionScreenshots.filter((item) => item.screenshot);
    if (successfulCaptures.length === 0) {
      result.issues.push({
        viewport: viewport.name,
        type: "section-screenshot-coverage-missing",
        severity: "warning",
        detail: "--screenshot-sections was requested, but no independently reviewable section screenshot was produced.",
      });
    }
    for (const failedCapture of sectionScreenshots.filter((item) => !item.screenshot)) {
      result.issues.push({
        viewport: viewport.name,
        type: "section-screenshot-capture-failed",
        severity: "warning",
        text: failedCapture.label,
        detail: failedCapture.error || "The selected section could not be captured.",
      });
    }
    const expectedSlides = result.meta.pageType?.slideCount || 0;
    if (pageType === "deck" && successfulCaptures.length < expectedSlides) {
      result.issues.push({
        viewport: viewport.name,
        type: "deck-slide-evidence-incomplete",
        severity: "error",
        detail: `Captured ${successfulCaptures.length}/${expectedSlides} slide section(s). Increase --max-section-screenshots or fix the slide selector before claiming full-deck coverage.`,
      });
    }
  }
  const protectedResult = protectRenderedEvidence(result, url);
  const protectedSectionScreenshots = protectSectionEvidence(sectionScreenshots, url);
  report.viewports.push({
    ...protectedResult.meta,
    requestedTarget: targetEvidence(url),
    finalTarget: targetEvidence(page.url()),
    httpStatus,
    redirected: page.url() !== url,
    screenshot,
    sectionScreenshots: protectedSectionScreenshots,
  });
  report.issues.push(...protectedResult.issues);
  } finally {
    await page.close();
  }
}

const reportPath = `${outDir}/frontend-visual-qa-report.json`;
const errors = report.issues.filter((issue) => issue.severity === "error");
const warnings = report.issues.filter((issue) => issue.severity === "warning");
report.status = errors.length || (failOnWarning && warnings.length)
  ? "findings"
  : warnings.length
    ? "warnings"
    : "mechanical-pass";
report.summary = { errors: errors.length, warnings: warnings.length };
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

for (const viewport of report.viewports) {
  const visual = viewport.visualViewport ? `, visual=${viewport.visualViewport.width}x${viewport.visualViewport.height}@${viewport.visualViewport.scale}` : "";
  const content = viewport.firstViewportContent
    ? `, firstViewportBlank=${viewport.firstViewportContent.leftBlank}/${viewport.firstViewportContent.rightBlank}, contentRatio=${viewport.firstViewportContent.widthRatio}`
    : "";
  const primaryImage = viewport.primaryImage
    ? `, primaryImage=${viewport.primaryImage.displayedWidth}x${viewport.primaryImage.displayedHeight} ratio=${viewport.primaryImage.displayedRatio}/${viewport.primaryImage.naturalRatio} fit=${viewport.primaryImage.objectFit}`
    : "";
  const typography = viewport.typography
    ? `, type=${viewport.typography.bodySize}/${viewport.typography.h1Size}, weight=${viewport.typography.bodyWeight}/${viewport.typography.h1Weight}, tracking=${viewport.typography.bodyLetterSpacing}/${viewport.typography.h1LetterSpacing}, minText=${viewport.typography.smallestImportantTextSize}, minCol=${viewport.typography.narrowestTextColumnWidth}`
    : "";
  const sections = viewport.sections
    ? `sections=${viewport.sections.count}, worstSectionOverflowX=${viewport.sections.worstOverflowX}`
    : "";
  const media = viewport.media
    ? `, media=${viewport.media.loaded} loaded/${viewport.media.broken} broken/${viewport.media.stillLoading} loading/${viewport.media.deferredLazy} deferred/${viewport.media.notRendered} not-rendered`
    : "";
  console.log(`${viewport.viewport}: outer=${viewport.outerWidth}x${viewport.outerHeight}, inner=${viewport.width}x${viewport.height}, outerMinusInner=${viewport.outerMinusInner}, client=${viewport.clientWidth}, scroll=${viewport.scrollWidth}, overflowX=${viewport.overflowX}${visual}${content}${primaryImage}${typography}${media}, title=${formatTextEvidence(viewport.titleEvidence)}, h1=${formatTextEvidence(viewport.h1Evidence)}, screenshot=${viewport.screenshot}`);
  if (sections) console.log(`  sectionAudit: ${sections}`);
  if (viewport.sectionScreenshots?.length) {
    const captured = viewport.sectionScreenshots.map((item) => item.screenshot).filter(Boolean);
    const failed = viewport.sectionScreenshots.filter((item) => !item.screenshot);
    if (captured.length) console.log(`  sectionScreenshots: ${captured.join(", ")}`);
    for (const item of failed) console.log(`  sectionScreenshotFailed: ${formatTextEvidence(item.labelEvidence)}: ${item.error}`);
  }
}

if (report.issues.length) {
  console.log(`\nIssues: ${errors.length} error(s), ${warnings.length} warning(s). Report: ${reportPath}`);
  for (const issue of report.issues) {
    console.log(`- ${issue.severity.toUpperCase()} ${issue.viewport} ${issue.type} ${issue.selector || ""}`);
    if (issue.textEvidence) console.log(`  text: ${formatTextEvidence(issue.textEvidence)}`);
    if (issue.detail) console.log(`  ${issue.detail}`);
  }
} else {
  console.log(`\nNo mechanical layout issues found. Screenshots still require human visual review. Report: ${reportPath}`);
}

process.exitCode = errors.length || (failOnWarning && warnings.length) ? 1 : 0;
} catch (error) {
  const safeError = redactUrlsInText(error?.stack || error?.message || String(error));
  console.error("Visual audit failed: " + safeError);
  if (outputPrepared) {
    const errorReport = {
      target: targetEvidence(url, false),
      createdAt: new Date().toISOString(),
      status: "run-error",
      runErrors: [redactUrlsInText(error?.message || String(error))],
    };
    fs.writeFileSync(
      path.join(outDir, "frontend-visual-qa-report.json"),
      JSON.stringify(errorReport, null, 2),
    );
  }
  process.exitCode = 2;
} finally {
  if (browser) await browser.close().catch(() => {});
}

function normalizeTarget(value) {
  if (/^(https?:|file:)/i.test(value)) return value;
  const resolved = path.resolve(value);
  if (fs.existsSync(resolved)) return pathToFileURL(resolved).href;
  return value;
}

function targetEvidence(value, includeFileContent = true) {
  const exactTarget = String(value);
  const targetStringSha256 = createHash("sha256").update(exactTarget).digest("hex");
  try {
    const parsed = new URL(exactTarget);
    if (parsed.protocol === "file:") {
      const canonicalFileUrl = new URL(parsed.href);
      canonicalFileUrl.search = "";
      canonicalFileUrl.hash = "";
      return {
        kind: "single-file",
        redactedCanonicalPath: "file:///<redacted-path>",
        targetStringSha256,
        contentSha256: includeFileContent
          ? createHash("sha256").update(fs.readFileSync(fileURLToPath(canonicalFileUrl))).digest("hex")
          : null,
        rendererScheme: "file:",
      };
    }
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return {
        kind: "web",
        redacted: redactUrlForEvidence(exactTarget),
        targetStringSha256,
        queryKeys: [...new Set(parsed.searchParams.keys())],
        fragmentPresent: Boolean(parsed.hash),
      };
    }
    if (parsed.protocol === "data:") {
      return {
        kind: "inline-data",
        redacted: "data:<redacted>",
        targetStringSha256,
      };
    }
  } catch {
    // The exact target remains represented by a one-way fingerprint while all
    // human-readable evidence fails closed to a generic label.
  }
  return {
    kind: "unknown",
    redacted: "<redacted-target>",
    targetStringSha256,
  };
}

function redactUrlForEvidence(value) {
  try {
    const parsed = new URL(String(value));
    if (parsed.protocol === "data:") return "data:<redacted>";
    if (parsed.protocol === "file:") return "file:///<redacted-path>";
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "<redacted-target>";
    }
    const pathLabel = parsed.pathname === "/" ? "/" : "/<redacted-path>";
    const queryKeys = [...new Set(parsed.searchParams.keys())];
    const query = queryKeys.length
      ? "?" + queryKeys.map((key) => `${encodeURIComponent(key)}=<redacted>`).join("&")
      : "";
    const fragment = parsed.hash ? "#<redacted-fragment>" : "";
    return `${parsed.origin}${pathLabel}${query}${fragment}`;
  } catch {
    return "<redacted-target>";
  }
}

function redactUrlsInText(value) {
  return String(value).replace(
    /\b(?:https?|file|data):[^\s"'<>]+/gi,
    (candidate) => redactUrlForEvidence(candidate),
  );
}

function protectRenderedEvidence(result, exactTarget) {
  const protectedResult = redactTargetValuesDeep(result, exactTarget);
  protectedResult.meta.titleEvidence = textEvidence(protectedResult.meta.title);
  protectedResult.meta.h1Evidence = textEvidence(protectedResult.meta.h1);
  delete protectedResult.meta.title;
  delete protectedResult.meta.h1;
  for (const heading of protectedResult.meta.typography?.keyHeadings || []) {
    heading.textEvidence = textEvidence(heading.text);
    delete heading.text;
  }
  for (const issue of protectedResult.issues || []) {
    if (typeof issue.text !== "string") continue;
    issue.textEvidence = textEvidence(issue.text);
    delete issue.text;
  }
  return protectedResult;
}

function protectSectionEvidence(sections, exactTarget) {
  return redactTargetValuesDeep(sections, exactTarget).map((section) => {
    const protectedSection = {
      ...section,
      labelEvidence: textEvidence(section.label),
    };
    delete protectedSection.label;
    delete protectedSection.slug;
    return protectedSection;
  });
}

function textEvidence(value) {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value);
  return {
    sha256: createHash("sha256").update(text).digest("hex"),
    length: [...text].length,
  };
}

function formatTextEvidence(evidence) {
  return evidence ? `sha256:${evidence.sha256}/length:${evidence.length}` : "none";
}

function redactTargetValuesDeep(value, exactTarget) {
  if (Array.isArray(value)) {
    return value.map((item) => redactTargetValuesDeep(item, exactTarget));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, redactTargetValuesDeep(item, exactTarget)]),
    );
  }
  if (typeof value !== "string") return value;
  let protectedText = redactUrlsInText(value);
  for (const token of targetSensitiveTokens(exactTarget)) {
    const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const tokenPattern = /^[\p{L}\p{N}_-]+$/u.test(token)
      ? `(?<![\\p{L}\\p{N}_-])${escaped}(?![\\p{L}\\p{N}_-])`
      : escaped;
    protectedText = protectedText.replace(new RegExp(tokenPattern, "gu"), "<redacted-target-value>");
  }
  return protectedText;
}

function targetSensitiveTokens(value) {
  const tokens = new Set();
  const add = (candidate) => {
    if (!candidate) return;
    const raw = String(candidate);
    tokens.add(raw);
    try { tokens.add(decodeURIComponent(raw)); } catch {}
    try { tokens.add(encodeURIComponent(raw)); } catch {}
  };
  try {
    const parsed = new URL(String(value));
    add(parsed.username);
    add(parsed.password);
    for (const segment of parsed.pathname.split("/")) add(segment);
    for (const queryValue of parsed.searchParams.values()) add(queryValue);
    if (parsed.hash) {
      const fragment = parsed.hash.slice(1);
      add(fragment);
      const queryIndex = fragment.indexOf("?");
      const route = queryIndex >= 0 ? fragment.slice(0, queryIndex) : fragment;
      for (const segment of route.split("/")) add(segment);
      if (queryIndex >= 0) {
        for (const fragmentValue of new URLSearchParams(fragment.slice(queryIndex + 1)).values()) {
          add(fragmentValue);
        }
      }
    }
  } catch {}
  return [...tokens]
    .filter((token) => token && token !== "/" && token.toUpperCase() !== "%2F")
    .sort((left, right) => right.length - left.length);
}

function validatePattern(pattern, flagName) {
  if (!pattern) return;
  try {
    new RegExp(pattern, "g");
  } catch (error) {
    failUsage("Invalid " + flagName + " regular expression: " + error.message);
  }
}

function parsePositiveInt(value) {
  if (!value) return null;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    console.error(`Invalid positive integer: ${value}`);
    process.exit(2);
  }
  return parsed;
}

function parseViewport(value, index) {
  const match = /^(\d+)x(\d+)$/i.exec(value || "");
  if (!match) failUsage(`Invalid --viewport "${value}". Expected WIDTHxHEIGHT, for example 1920x1080.`);
  const width = Number.parseInt(match[1], 10);
  const height = Number.parseInt(match[2], 10);
  if (width < 240 || height < 240 || width > 10000 || height > 10000) {
    failUsage(`Invalid --viewport "${value}". Width and height must be between 240 and 10000 CSS pixels.`);
  }
  const isMobile = width <= 480;
  return {
    name: `custom-${String(index + 1).padStart(2, "0")}-${width}x${height}`,
    width,
    height,
    deviceScaleFactor: isMobile ? 2 : 1,
    isMobile,
    hasTouch: isMobile,
  };
}

function validatePageType(value) {
  const allowed = new Set(["generic", "design-system", "live-artifact-design-system", "dashboard", "app", "landing", "deck", "tool", "game"]);
  if (!allowed.has(value)) {
    console.error(`Invalid --page-type "${value}". Expected one of: ${[...allowed].join(", ")}`);
    process.exit(2);
  }
}

function validateWaitUntil(value) {
  const allowed = new Set(["domcontentloaded", "load", "networkidle", "commit"]);
  if (!allowed.has(value)) {
    console.error(`Invalid --wait-until "${value}". Expected one of: ${[...allowed].join(", ")}`);
    process.exit(2);
  }
}

function validateSelector(selector, flagName) {
  if (!selector) return;
  try {
    globalThis.document?.querySelectorAll(selector);
  } catch {
    // No document in Node; validate with a tiny browser-side pass in auditPage.
  }
  if (/^\s*,|,\s*,|,\s*$/.test(selector)) {
    console.error(`Invalid ${flagName}: "${selector}"`);
    process.exit(2);
  }
}

async function waitForVisualReadiness(page, selector, delayMs) {
  if (selector) {
    await page.waitForSelector(selector, { state: "visible", timeout: 10_000 });
  }
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const loadedImages = [...document.images].filter((image) => image.complete);
    await Promise.all(loadedImages.map((image) => image.decode?.().catch(() => {})));
  });
  if (delayMs > 0) await page.waitForTimeout(delayMs);
}

async function primeVisibleMedia(page, selector, delayMs) {
  const plan = await page.evaluate(({ selector, maximumRows }) => {
    function isRendered(element) {
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

    let selected;
    try {
      if (!selector) {
        selected = [...document.images];
      } else {
        const roots = [...document.querySelectorAll(selector)];
        selected = [...new Set(roots.flatMap((root) => (
          root.tagName === "IMG" ? [root] : [...root.querySelectorAll("img")]
        )))];
      }
    } catch (error) {
      return {
        renderedImages: 0,
        notRenderedImages: 0,
        renderedRows: 0,
        visitedRows: 0,
        truncated: false,
        indices: [],
        selectorError: error.message,
      };
    }

    const allImages = [...document.images];
    const rendered = selected
      .filter(isRendered)
      .map((image) => {
        const rect = image.getBoundingClientRect();
        return {
          index: allImages.indexOf(image),
          documentTop: Math.round(rect.top + window.scrollY),
        };
      })
      .filter((item) => item.index >= 0)
      .sort((a, b) => a.documentTop - b.documentTop);

    const rows = [];
    for (const item of rendered) {
      const sameRow = rows.find((row) => Math.abs(row.documentTop - item.documentTop) <= 8);
      if (!sameRow) rows.push(item);
    }

    return {
      renderedImages: rendered.length,
      notRenderedImages: selected.length - rendered.length,
      renderedRows: rows.length,
      visitedRows: Math.min(rows.length, maximumRows),
      truncated: rows.length > maximumRows,
      indices: rows.slice(0, maximumRows).map((item) => item.index),
      selectorError: null,
    };
  }, { selector, maximumRows: 200 });

  const failures = [];
  for (const index of plan.indices) {
    try {
      await page.evaluate((imageIndex) => {
        document.images[imageIndex]?.scrollIntoView({ block: "center", inline: "nearest" });
      }, index);
      await page.waitForTimeout(60);
    } catch (error) {
      failures.push({ index, message: error?.message || String(error) });
    }
  }

  await page.evaluate(async () => {
    window.scrollTo(0, 0);
    const completeImages = [...document.images].filter((image) => image.complete && image.naturalWidth > 0);
    await Promise.all(completeImages.map((image) => image.decode?.().catch(() => {})));
  });
  if (delayMs > 0) await page.waitForTimeout(Math.min(Math.max(delayMs, 100), 2_000));

  return {
    renderedImages: plan.renderedImages,
    notRenderedImages: plan.notRenderedImages,
    renderedRows: plan.renderedRows,
    visitedRows: plan.visitedRows,
    truncated: plan.truncated,
    selectorError: plan.selectorError,
    failures,
  };
}

async function captureSectionScreenshots(page, viewport, outDir, sectionSelector, maxCount, includeFirstViewport = false) {
  const sections = await page.evaluate(collectScreenshotSections, {
    sectionSelector,
    maxCount: maxCount || 4,
    includeFirstViewport,
  });
  const captures = [];
  for (let index = 0; index < sections.length; index += 1) {
    const section = sections[index];
    const locator = page.locator(sectionSelector).nth(section.domIndex);
    if (await locator.count() === 0) continue;
    const file = `${outDir}/${viewport.name}-section-${String(index + 1).padStart(2, "0")}.png`;
    try {
      if (section.height > viewport.height * 1.5) {
        const scrollY = await page.evaluate(({ top, height }) => {
          const maxScrollY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          const startsInFirstViewport = top <= window.innerHeight * 0.25;
          const insideOffset = startsInFirstViewport
            ? Math.min(window.innerHeight * 0.75, Math.max(0, height - window.innerHeight))
            : 0;
          const targetY = Math.max(0, Math.min(maxScrollY, top + insideOffset));
          window.scrollTo(0, targetY);
          return Math.round(window.scrollY);
        }, { top: section.top, height: section.height });
        await page.waitForTimeout(80);
        await page.screenshot({ path: file, fullPage: false, animations: "disabled" });
        captures.push({
          ...section,
          viewport: viewport.name,
          scrollY,
          captureMode: "viewport-slice",
          sliceHeight: viewport.height,
          screenshot: file,
        });
      } else {
        await locator.scrollIntoViewIfNeeded();
        await page.waitForTimeout(80);
        const scrollY = await page.evaluate(() => Math.round(window.scrollY));
        await locator.screenshot({ path: file, animations: "disabled" });
        captures.push({ ...section, viewport: viewport.name, scrollY, captureMode: "element", screenshot: file });
      }
    } catch (error) {
      captures.push({
        ...section,
        viewport: viewport.name,
        scrollY: Math.round(await page.evaluate(() => window.scrollY)),
        captureMode: "failed",
        screenshot: null,
        error: error?.message || String(error),
      });
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return captures;
}

function collectScreenshotSections({ sectionSelector, maxCount, includeFirstViewport }) {
  const preferredPatterns = [
    /component|组件|anatomy|解剖|specimen|样本/i,
    /chart|data.?viz|visuali[sz]ation|图表|可视化/i,
    /pattern|模式|state|状态|variant|变体/i,
    /governance|治理|usage|用法|do\/?don't|禁忌|qa|质量/i,
  ];

  let elements = [];
  try {
    elements = [...document.querySelectorAll(sectionSelector)];
  } catch {
    return [];
  }

  const candidates = elements
    .map((el, domIndex) => {
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      const heading = el.querySelector("h1,h2,h3,h4")?.textContent?.replace(/\s+/g, " ").trim() || "";
      const label = heading || el.id || (typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 2).join(" ") : "") || `section ${domIndex + 1}`;
      const haystack = `${label} ${el.id || ""} ${typeof el.className === "string" ? el.className : ""} ${el.textContent || ""}`;
      const preferredIndex = preferredPatterns.findIndex((pattern) => pattern.test(haystack));
      return {
        domIndex,
        top: Math.round(rect.top + window.scrollY),
        bottom: Math.round(rect.bottom + window.scrollY),
        height: Math.round(rect.height),
        width: Math.round(rect.width),
        preferredIndex,
        label: label.slice(0, 80),
        slug: slugify(label) || `section-${domIndex + 1}`,
        visible: rect.width > 100 && rect.height > 80 && style.display !== "none" && style.visibility !== "hidden",
      };
    })
    .filter((item) => item.visible)
    .filter((item) => includeFirstViewport || item.top > window.innerHeight * 0.25 || item.bottom > window.innerHeight * 1.1);

  const selected = [];
  for (let index = 0; index < preferredPatterns.length && selected.length < maxCount; index += 1) {
    const match = candidates.find((item) => item.preferredIndex === index && !selected.some((picked) => picked.domIndex === item.domIndex));
    if (match) selected.push(match);
  }
  for (const item of candidates) {
    if (selected.length >= maxCount) break;
    if (!selected.some((picked) => picked.domIndex === item.domIndex)) selected.push(item);
  }

  return selected.slice(0, maxCount);

  function slugify(value) {
    return value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);
  }
}

function auditPage({ viewportName, requestedWidth, isMobile, forbidPatterns, requirePatterns, pageType, expectedWindowWidth, contentSelector, mediaSelector, mediaWalkRequested, sectionSelector, screenshotSections }) {
  const issues = [];
  const forbiddenTerms = forbidPatterns.map((pattern) => new RegExp(pattern, "g"));
  const requiredTerms = requirePatterns.map((pattern) => new RegExp(pattern, "g"));
  const textSelector = [
    "h1", "h2", "h3", "h4", "p", "button", "a", "strong", "em", "td", "th",
    "[role='button']", "[role='tab']", "[role='menuitem']", "[role='switch']",
    "[role='checkbox']", "[role='radio']", "[role='link']",
    "[class*='tag']", "[class*='badge']", "[class*='pill']", "[class*='nav']",
    "[class*='title']", "[class*='label']", "[class*='note']", "[class*='eyebrow']",
  ].join(",");
  const controlParts = new Set(["tag", "tags", "badge", "badges", "pill", "pills", "button", "btn", "tab", "tabs", "nav", "menu", "link", "chip", "chips", "toggle", "switch", "seg", "opt", "qbadge", "tier"]);
  const headingParts = new Set(["title", "heading", "headline", "eyebrow"]);
  const labelParts = new Set(["label", "title", "name", "caption"]);
  const helperParts = new Set(["helper", "hint", "error", "message", "feedback", "description", "note", "caption"]);

  for (const [selector, flagName] of [[contentSelector, "--content-selector"], [mediaSelector, "--media-selector"], [sectionSelector, "--section-selector"]]) {
    if (!selector) continue;
    try {
      document.querySelectorAll(selector);
    } catch (error) {
      issues.push({
        viewport: viewportName,
        type: "invalid-selector",
        severity: "error",
        detail: `${flagName} is not a valid CSS selector: ${error.message}`,
      });
    }
  }

  const meta = {
    viewport: viewportName,
    requestedWidth,
    href: location.href,
    width: window.innerWidth,
    height: window.innerHeight,
    outerWidth: window.outerWidth,
    outerHeight: window.outerHeight,
    outerMinusInner: window.outerWidth - window.innerWidth,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    title: document.title,
    h1: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() || null,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    dpr: window.devicePixelRatio,
    screenWidth: window.screen.width,
    metaViewport: document.querySelector('meta[name="viewport"]')?.content || null,
    visualViewport: window.visualViewport ? {
      width: Math.round(window.visualViewport.width),
      height: Math.round(window.visualViewport.height),
      scale: window.visualViewport.scale,
    } : null,
  };

  meta.firstViewportContent = measureFirstViewportContent(contentSelector);
  meta.primaryImage = measurePrimaryImage(mediaSelector);
  meta.typography = measureTypography();
  const mediaAudit = auditMedia({ viewportName, mediaSelector, mediaWalkRequested });
  meta.media = mediaAudit.meta;
  issues.push(...mediaAudit.issues);
  const sectionAudit = auditSections(sectionSelector);
  meta.sections = sectionAudit.meta;
  issues.push(...sectionAudit.issues);

  if (meta.overflowX > 1) {
    issues.push({ viewport: viewportName, type: "page-horizontal-overflow", severity: "error", detail: `Page overflows by ${meta.overflowX}px.` });
  }

  if (isMobile) {
    const effectiveVisualWidth = meta.visualViewport?.width || meta.width;
    const widthDelta = Math.abs(meta.width - requestedWidth);
    const visualWidthDelta = Math.abs(effectiveVisualWidth - requestedWidth);
    if (!meta.metaViewport) {
      issues.push({
        viewport: viewportName,
        type: "mobile-viewport-meta-missing",
        severity: "error",
        detail: "No meta viewport is present. The nominal mobile run may be a scaled desktop layout.",
      });
    }
    if (widthDelta > 24 || visualWidthDelta > 24 || Math.abs((meta.visualViewport?.scale || 1) - 1) > 0.08) {
      issues.push({
        viewport: viewportName,
        type: "mobile-effective-viewport-mismatch",
        severity: "error",
        detail: "Requested " + requestedWidth + "px, but innerWidth=" + meta.width
          + ", visualViewport.width=" + effectiveVisualWidth
          + ", scale=" + (meta.visualViewport?.scale || 1) + ".",
      });
    }
  }

  if (!isMobile && Math.abs(meta.outerMinusInner) > 120) {
    issues.push({
      viewport: viewportName,
      type: "viewport-emulation-mismatch",
      severity: "warning",
      detail: `outerWidth (${meta.outerWidth}) differs from innerWidth (${meta.width}) by ${meta.outerMinusInner}px. In user-visible Chrome, verify the emulated viewport matches the actual window before judging blank space.`,
    });
  }

  if (!isMobile && expectedWindowWidth && Math.abs(expectedWindowWidth - meta.width) > 120) {
    issues.push({
      viewport: viewportName,
      type: "expected-window-viewport-mismatch",
      severity: "warning",
      detail: `Expected visible Chrome width is ${expectedWindowWidth}px, but this audit rendered a ${meta.width}px CSS viewport. Reproduce the user's real viewport before judging wide-screen blank space.`,
    });
  }

  if (!isMobile && meta.firstViewportContent) {
    const blankDelta = meta.firstViewportContent.rightBlank - meta.firstViewportContent.leftBlank;
    if (blankDelta > Math.max(160, meta.width * 0.12)) {
      issues.push({
        viewport: viewportName,
        type: "first-viewport-asymmetric-blank",
        severity: "warning",
        detail: `First viewport has ${meta.firstViewportContent.leftBlank}px left blank and ${meta.firstViewportContent.rightBlank}px right blank. Check viewport emulation first, then container/grid sizing.`,
      });
    }
    if (meta.firstViewportContent.widthRatio < 0.62 && meta.firstViewportContent.leftBlank > 180 && meta.firstViewportContent.rightBlank > 180) {
      issues.push({
        viewport: viewportName,
        type: "first-viewport-underfilled",
        severity: "warning",
        detail: `First viewport content uses only ${Math.round(meta.firstViewportContent.widthRatio * 100)}% of the CSS viewport. Inspect whether this is intentional editorial whitespace or a broken container.`,
      });
    }
  }

  const bodyText = visibleRenderedText(document.body);
  for (const forbidden of forbiddenTerms) {
    const matches = [...bodyText.matchAll(forbidden)].map((match) => match[0]);
    for (const term of [...new Set(matches)]) {
      issues.push({ viewport: viewportName, type: "forbidden-rendered-term", severity: "error", text: term, detail: "A project-specific forbidden term appears in rendered UI." });
    }
  }

  for (const required of requiredTerms) {
    if (bodyText.match(required)) continue;
    issues.push({
      viewport: viewportName,
      type: "required-rendered-term-missing",
      severity: "error",
      detail: "No rendered text matches required pattern: " + required.source,
    });
  }

  const pageTypeAudit = auditPageType({ viewportName, pageType, screenshotSections });
  meta.pageType = pageTypeAudit.meta;
  issues.push(...pageTypeAudit.issues);
  issues.push(...auditCardSideRails({ viewportName }));

  const interactiveRoleSelector = [
    "[role='button']", "[role='tab']", "[role='menuitem']", "[role='switch']",
    "[role='checkbox']", "[role='radio']", "[role='link']",
  ].join(",");
  for (const el of [...document.querySelectorAll(interactiveRoleSelector)].filter(isVisible)) {
    const selector = describe(el);
    if (isRedundantStepperAffordance(el)) {
      issues.push({
        viewport: viewportName,
        selector,
        type: "non-focusable-stepper-affordance",
        severity: "warning",
        text: clean(el.textContent || "").slice(0, 120),
        detail: "Mouse-only stepper affordance has an adjacent number/spinbutton input. Confirm the input performs the same action with ArrowUp/ArrowDown; this warning is not a WCAG verdict.",
      });
      continue;
    }
    if (el.getAttribute("aria-hidden") === "true") {
      issues.push({
        viewport: viewportName,
        selector,
        type: "aria-hidden-interactive-control",
        severity: "error",
        text: clean(el.textContent || "").slice(0, 120),
        detail: "A visible interactive-role element is hidden from the accessibility tree.",
      });
      continue;
    }
    if (el.matches(":disabled") || el.getAttribute("aria-disabled") === "true") continue;
    const explicitTabIndex = el.getAttribute("tabindex");
    const parsedTabIndex = explicitTabIndex === null
      ? null
      : Number.parseInt(explicitTabIndex, 10);
    const hasExplicitNonnegativeTabIndex = Number.isInteger(parsedTabIndex) && parsedTabIndex >= 0;
    const explicitlyRemovedFromTabOrder = Number.isInteger(parsedTabIndex) && parsedTabIndex < 0;
    const isNativeControl = /^(BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(el.tagName)
      && !el.disabled;
    const isLinkedAnchor = /^(A|AREA)$/.test(el.tagName) && Boolean(el.getAttribute("href"));
    if (hasExplicitNonnegativeTabIndex) continue;
    if (!explicitlyRemovedFromTabOrder && (isNativeControl || isLinkedAnchor)) continue;
    issues.push({
      viewport: viewportName,
      selector,
      type: "non-focusable-custom-button",
      severity: "error",
      text: clean(el.textContent || "").slice(0, 120),
      detail: "Interactive-role element is not in sequential focus order. Use a native control/link or an explicit nonnegative tabindex when appropriate.",
    });
  }

  // Focus indicator + motion fallback: both are invisible in a default screenshot,
  // so they survive every visual pass unless something inspects the stylesheets.
  // A page can pass "is it focusable" (above) and still be unusable by keyboard
  // because the focus ring was suppressed and never replaced.
  {
    let focusRuleCount = 0;
    let outlineSuppressed = 0;
    let reducedMotionQuery = 0;
    let styleSheetsReadable = 0;
    // Do NOT branch on `rule.cssRules` to mean "this is a grouping rule": since CSS
    // Nesting shipped, a plain CSSStyleRule also exposes an (empty) cssRules list,
    // and an empty CSSRuleList is still truthy — that branch silently skips every
    // ordinary rule, so the audit below can never fire. Handle both facets instead.
    const walkRules = (rules) => {
      for (const rule of rules) {
        const sel = rule.selectorText || "";
        if (sel) {
          const text = rule.cssText || "";
          if (/:focus(-visible|-within)?\b/.test(sel)) focusRuleCount += 1;
          if (/outline\s*:\s*(none|0(px)?)\s*[;}]/i.test(text)) outlineSuppressed += 1;
        }
        const cond = rule.conditionText || rule.media?.mediaText || "";
        if (/prefers-reduced-motion/i.test(cond)) reducedMotionQuery += 1;
        if (rule.cssRules && rule.cssRules.length) walkRules(rule.cssRules);
      }
    };
    for (const sheet of document.styleSheets) {
      try {
        if (!sheet.cssRules) continue;
        styleSheetsReadable += 1;
        walkRules(sheet.cssRules);
      } catch { /* cross-origin sheet: unreadable, not a defect */ }
    }

    const focusables = [...document.querySelectorAll(
      'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex^="-"])'
    )].filter(isVisible);

    if (styleSheetsReadable > 0 && focusables.length >= 3 && outlineSuppressed > 0 && focusRuleCount === 0) {
      issues.push({
        viewport: viewportName,
        selector: ":root",
        type: "focus-indicator-suppressed",
        severity: "error",
        text: `${focusables.length} focusable elements`,
        detail: `Stylesheets suppress the outline (${outlineSuppressed} rule(s)) without defining any :focus/:focus-visible replacement. Keyboard users cannot see where focus is. Add a visible focus style distinct from the selected/hover state.`,
      });
    } else if (styleSheetsReadable > 0 && focusables.length >= 8 && focusRuleCount === 0) {
      issues.push({
        viewport: viewportName,
        selector: ":root",
        type: "focus-indicator-default-only",
        severity: "warning",
        text: `${focusables.length} focusable elements`,
        detail: "No :focus/:focus-visible rule exists, so focus relies entirely on the UA default ring, which is often invisible against custom backgrounds. Verify the ring is actually visible on this palette.",
      });
    }

    const animated = [...document.querySelectorAll("*")].filter(isVisible).some((el) => {
      const st = getComputedStyle(el);
      const dur = parseFloat(st.transitionDuration) || 0;
      const anim = st.animationName && st.animationName !== "none";
      return dur > 0.15 || anim;
    });
    if (styleSheetsReadable > 0 && animated && reducedMotionQuery === 0) {
      issues.push({
        viewport: viewportName,
        selector: ":root",
        type: "motion-without-reduced-motion-fallback",
        severity: "warning",
        text: "transitions/animations present",
        detail: "The page animates but defines no @media (prefers-reduced-motion: reduce) block. Degrade transforms/keyframes for users who request reduced motion; keep the end state (e.g. keep the highlight, drop the flash).",
      });
    }
  }

  for (const el of [...document.querySelectorAll(textSelector)].filter(isVisible)) {
    const text = clean(el.textContent || "");
    if (!text || text.length < 2) continue;
    const selector = describe(el);
    const style = getComputedStyle(el);
    const overflowX = el.scrollWidth - el.clientWidth;
    const overflowY = el.scrollHeight - el.clientHeight;

    if (overflowX > 2 && style.overflowX !== "visible") {
      issues.push({ viewport: viewportName, selector, type: "element-horizontal-overflow", severity: "error", text, detail: `Element overflows by ${Math.round(overflowX)}px.` });
    }
    if (overflowY > 2 && ["hidden", "clip"].includes(style.overflowY)) {
      const intentionallyTruncated = (style.webkitLineClamp && style.webkitLineClamp !== "none")
        || style.textOverflow === "ellipsis";
      issues.push({
        viewport: viewportName,
        selector,
        type: intentionallyTruncated ? "text-truncated" : "text-clipped",
        severity: intentionallyTruncated ? "warning" : "error",
        text,
        detail: "Element content exceeds its visible height by " + Math.round(overflowY) + "px.",
      });
    }

    if (text.length > 180) continue;
    const lines = renderedLines(el);
    if (lines.length < 2) continue;
    const lastLine = lines.at(-1);
    const lastCharCount = [...lastLine.replace(/\s+/g, "")].length;
    const className = typeof el.className === "string" ? el.className : "";
    const classTokens = className.split(/\s+/).filter(Boolean);
    const isHeading = /^H[1-4]$/.test(el.tagName) || classTokens.some((token) => /(^|[-_])(title|heading)([-_]|$)/i.test(token)) || hasSemanticPart(el, headingParts);
    const role = el.getAttribute("role") || "";
    const isInteractiveAnchor = el.tagName === "A" && hasSemanticPart(el, controlParts);
    const isControlClass = classTokens.some((token) => /^(tag|badge|pill|btn|button|tab|nav|seg__opt|qbadge|tier)$/.test(token));
    const isControlRole = /^(button|tab|menuitem|switch|checkbox|radio|link)$/.test(role);
    const isControl = el.tagName === "BUTTON" || isInteractiveAnchor || isControlRole || isControlClass || hasSemanticPart(el, controlParts);
    const isTableLabel = /T[HD]/.test(el.tagName);
    const rect = el.getBoundingClientRect();
    const fontSize = Number.parseFloat(style.fontSize) || 0;
    const highVisibilityText = isHeading
      || isControl
      || isTableLabel
      || rect.top < window.innerHeight
      || fontSize >= 16
      || classTokens.some((token) => /(^|[-_])(hero|lead|dek|title|heading|label|spec|caption)([-_]|$)/i.test(token));

    if (isHeading && lastCharCount <= 2 && /[\u4e00-\u9fffA-Za-z0-9]/.test(lastLine)) {
      issues.push({ viewport: viewportName, selector, type: "orphan-heading-line", severity: "error", text, detail: `Last rendered line is "${lastLine}".` });
    }
    const awkwardBoundary = awkwardChineseBoundary(lines);
    if (awkwardBoundary && highVisibilityText) {
      issues.push({
        viewport: viewportName,
        selector,
        type: "awkward-chinese-line-boundary",
        severity: "warning",
        text,
        detail: `Rendered line boundary splits "${awkwardBoundary.pair}" as "${awkwardBoundary.boundary}". Previous line: "${awkwardBoundary.previousLine}". Next line: "${awkwardBoundary.nextLine}".`,
      });
    }
    if (isControl && lines.length > 1) {
      issues.push({ viewport: viewportName, selector, type: "wrapped-control", severity: "error", text, detail: `Control renders on ${lines.length} lines.` });
    }
    if (isTableLabel && text.length <= 12 && lines.length > 1) {
      issues.push({ viewport: viewportName, selector, type: "wrapped-table-label", severity: "warning", text, detail: `Short table label renders on ${lines.length} lines.` });
    }
    if (!isHeading && !isControl && lastCharCount === 1 && text.length <= 40) {
      issues.push({ viewport: viewportName, selector, type: "suspicious-orphan-line", severity: "warning", text, detail: `Last rendered line is "${lastLine}".` });
    }
  }

  auditSameRowFields();

  issues.push(...auditImageOverlays({ viewportName, mediaSelector }));

  return { meta, issues };

  function clean(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function visibleRenderedText(root) {
    const parts = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const parent = node.parentElement;
      if (parent && !/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(parent.tagName) && isVisible(parent)) {
        const visibleText = clean(visibleTextFromNode(node));
        if (visibleText) parts.push(visibleText);
      }
      node = walker.nextNode();
    }
    return parts.join(" ");
  }

  function visibleTextFromNode(node) {
    const rawText = node.nodeValue || "";
    if (!rawText) return "";
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = [...range.getClientRects()]
      .filter((rect) => rect.width > 0 && rect.height > 0);
    if (!rects.length) {
      range.detach?.();
      return "";
    }

    const clips = collectNonScrollableAncestorClips(node.parentElement);
    if (!clips.length) {
      range.detach?.();
      return rawText;
    }

    let visibleText = "";
    for (let index = 0; index < rawText.length; index += 1) {
      const character = rawText[index];
      if (/\s/.test(character)) {
        visibleText += " ";
        continue;
      }
      range.setStart(node, index);
      range.setEnd(node, index + 1);
      const characterVisible = [...range.getClientRects()]
        .filter((rect) => rect.width > 0 && rect.height > 0)
        .some((rect) => rectSurvivesClips(rect, clips));
      visibleText += characterVisible ? character : " ";
    }
    range.detach?.();
    return visibleText;
  }

  function collectNonScrollableAncestorClips(startElement) {
    const clips = [];
    let ancestor = startElement;
    while (ancestor) {
      const style = getComputedStyle(ancestor);
      const clipsX = ["hidden", "clip"].includes(style.overflowX);
      const clipsY = ["hidden", "clip"].includes(style.overflowY);
      if (clipsX || clipsY) {
        clips.push({ rect: ancestor.getBoundingClientRect(), clipsX, clipsY });
      }
      ancestor = ancestor.parentElement;
    }
    return clips;
  }

  function rectSurvivesClips(sourceRect, clips) {
    let visibleRect = {
      left: sourceRect.left,
      right: sourceRect.right,
      top: sourceRect.top,
      bottom: sourceRect.bottom,
    };
    for (const clip of clips) {
      if (clip.clipsX) {
        visibleRect.left = Math.max(visibleRect.left, clip.rect.left);
        visibleRect.right = Math.min(visibleRect.right, clip.rect.right);
      }
      if (clip.clipsY) {
        visibleRect.top = Math.max(visibleRect.top, clip.rect.top);
        visibleRect.bottom = Math.min(visibleRect.bottom, clip.rect.bottom);
      }
      if (visibleRect.right <= visibleRect.left || visibleRect.bottom <= visibleRect.top) return false;
    }
    return true;
  }

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const geometryVisible = rect.width > 0 && rect.height > 0;
    if (!geometryVisible) return false;
    if (typeof el.checkVisibility === "function") {
      return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    }
    return style.display !== "none"
      && style.visibility !== "hidden"
      && Number.parseFloat(style.opacity || "1") > 0;
  }

  function isRedundantStepperAffordance(el) {
    // A role=button that is a decorative number stepper next to a keyboard-operable control
    // (input[type=number] / role=spinbutton). antd/MUI/Chakra number inputs render up/down
    // affordances as mouse-only, non-focusable spans by design: the input itself handles
    // ArrowUp/ArrowDown, so WCAG 2.1.1 is met through the input, not the affordance.
    const cls = typeof el.className === "string" ? el.className : "";
    const looksLikeStepper = /(step|spin|handler|action|caret|chevron|arrow|inc|dec)/i.test(cls)
      && /(up|down|increment|decrement|plus|minus)/i.test(cls);
    if (!looksLikeStepper) return false;
    let ancestor = el.parentElement;
    for (let depth = 0; ancestor && depth < 4; depth += 1) {
      if (ancestor.querySelector("input[type='number'], [role='spinbutton']")) return true;
      ancestor = ancestor.parentElement;
    }
    return false;
  }

  function semanticParts(el) {
    const className = typeof el.className === "string" ? el.className : "";
    const role = el.getAttribute("role") || "";
    return `${className} ${role}`
      .split(/\s+/)
      .filter(Boolean)
      .flatMap((token) => token.split(/[-_:]+/))
      .map((part) => part.toLowerCase())
      .filter(Boolean);
  }

  function hasSemanticPart(el, parts) {
    return semanticParts(el).some((part) => parts.has(part));
  }

  function auditSameRowFields() {
    const fieldRootSelector = [
      "form",
      "[class*='form']",
      "[class*='fields']",
      "[class*='field']",
      "[class*='grid']",
      "[class*='row']",
    ].join(",");
    const roots = [...document.querySelectorAll(fieldRootSelector)].filter(isVisible);
    const seenRows = new Set();

    for (const root of roots) {
      const directFields = [...root.children].filter(isFieldContainer);
      if (directFields.length < 2) continue;

      const rows = [];
      for (const field of directFields) {
        const rect = field.getBoundingClientRect();
        const row = rows.find((candidate) => Math.abs(candidate.top - rect.top) <= 6);
        if (row) {
          row.fields.push(field);
          row.top = (row.top + rect.top) / 2;
        } else {
          rows.push({ top: rect.top, fields: [field] });
        }
      }

      for (const row of rows.filter((candidate) => candidate.fields.length >= 2)) {
        const metrics = row.fields.map(fieldMetric).filter(Boolean).sort((a, b) => a.rect.left - b.rect.left);
        if (metrics.length < 2) continue;
        const rowKey = metrics
          .map((metric) => `${describe(metric.field)}@${Math.round(metric.rect.left)}:${Math.round(metric.rect.top)}`)
          .join("|");
        if (seenRows.has(rowKey)) continue;
        seenRows.add(rowKey);

        const anchor = metrics[0];
        for (const metric of metrics.slice(1)) {
          const labelTopDelta = Math.abs(metric.labelRect.top - anchor.labelRect.top);
          const controlTopDelta = Math.abs(metric.controlRect.top - anchor.controlRect.top);
          const controlBottomDelta = Math.abs(metric.controlRect.bottom - anchor.controlRect.bottom);
          const controlHeightDelta = Math.abs(metric.controlRect.height - anchor.controlRect.height);
          if (labelTopDelta > 3 || controlTopDelta > 3 || controlBottomDelta > 3 || controlHeightDelta > 2) {
            issues.push({
              viewport: viewportName,
              selector: `${describe(root)} > ${describe(metric.field)}`,
              type: "same-row-field-control-misalignment",
              severity: "error",
              text: rowText(metrics),
              detail: `Sibling field axes differ: labelTopDelta=${Math.round(labelTopDelta)}px, controlTopDelta=${Math.round(controlTopDelta)}px, controlBottomDelta=${Math.round(controlBottomDelta)}px, controlHeightDelta=${Math.round(controlHeightDelta)}px.`,
            });
          }

          const fieldHeightDelta = Math.abs(metric.rect.height - anchor.rect.height);
          const fieldBottomDelta = Math.abs(metric.rect.bottom - anchor.rect.bottom);
          const helperPresenceMismatch = Boolean(metric.helperRect) !== Boolean(anchor.helperRect);
          const helperTopDelta = metric.helperRect && anchor.helperRect ? Math.abs(metric.helperRect.top - anchor.helperRect.top) : 0;
          const helperHeightDelta = metric.helperRect && anchor.helperRect ? Math.abs(metric.helperRect.height - anchor.helperRect.height) : 0;
          if (fieldHeightDelta > 4 || fieldBottomDelta > 4 || helperPresenceMismatch || helperTopDelta > 4 || helperHeightDelta > 4) {
            issues.push({
              viewport: viewportName,
              selector: `${describe(root)} > ${describe(metric.field)}`,
              type: "same-row-field-helper-slot-misalignment",
              severity: "error",
              text: rowText(metrics),
              detail: `Sibling field/helper slots differ: fieldHeightDelta=${Math.round(fieldHeightDelta)}px, fieldBottomDelta=${Math.round(fieldBottomDelta)}px, helperPresenceMismatch=${helperPresenceMismatch}, helperTopDelta=${Math.round(helperTopDelta)}px, helperHeightDelta=${Math.round(helperHeightDelta)}px.`,
            });
          }
        }
      }
    }
  }

  function auditCardSideRails({ viewportName }) {
    const candidates = [...document.querySelectorAll([
      "[class*='card']",
      "[class*='panel']",
      "[class*='module']",
      "[class*='shell']",
      "[class*='alert']",
      "[class*='callout']",
      "[class*='evidence']",
      "[class*='spec']",
      "[class*='route']",
      "[class*='kpi']",
      "[class*='bulkbar']",
      "article",
      "section",
    ].join(","))].filter(isVisible);

    return candidates
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width < 160 || rect.height < 58) return false;
        if (isAllowedSideRailElement(el)) return false;
        const style = getComputedStyle(el);
        const borderLeftWidth = Number.parseFloat(style.borderLeftWidth) || 0;
        const borderTopWidth = Number.parseFloat(style.borderTopWidth) || 0;
        const borderLeftColor = style.borderLeftColor || "";
        const hasOpaqueLeftBorder = borderLeftWidth >= 3 && borderTopWidth < borderLeftWidth && !/rgba\([^)]*,\s*0\)/i.test(borderLeftColor);
        const hasLeftInsetShadow = hasInsetLeftRail(style.boxShadow);
        return hasOpaqueLeftBorder || hasLeftInsetShadow;
      })
      .map((el) => ({
        viewport: viewportName,
        selector: describe(el),
        type: "card-side-rail-ai-slop",
        severity: "warning",
        text: clean(el.textContent || "").slice(0, 160),
        detail: "Large card-like container uses a colored left border or inset shadow. Treat this as a design-system/taste candidate, not a deterministic layout failure.",
      }));
  }

  function isAllowedSideRailElement(el) {
    const className = typeof el.className === "string" ? el.className : "";
    const semantic = semanticParts(el).join(" ");
    if (["alert", "status"].includes(el.getAttribute("role"))) return true;
    if (/(tag|badge|pill|qbadge|tier|dot|icon|thumb|avatar|logo|motif|symbol|checkbox|radio|switch|field|input|label|selection|option|row|cell|rail)/i.test(`${className} ${semantic}`)) {
      return true;
    }
    if (/^(BUTTON|INPUT|TEXTAREA|SELECT|LABEL|TH|TD)$/.test(el.tagName)) return true;
    return false;
  }

  function hasInsetLeftRail(boxShadow) {
    if (!boxShadow || boxShadow === "none" || !/inset/i.test(boxShadow)) return false;
    const layers = boxShadow
      .replace(/rgba?\([^)]*\)/gi, "COLOR")
      .split(/\s*,\s*/)
      .filter((layer) => /\binset\b/i.test(layer));
    return layers.some((layer) => {
      const lengths = [...layer
        .replace(/\binset\b/gi, "")
        .matchAll(/-?\d+(?:\.\d+)?px/g)]
        .map((match) => Number.parseFloat(match[0]));
      if (lengths.length < 2) return false;
      const [offsetX, offsetY] = lengths;
      return Math.abs(offsetX) >= 3 && Math.abs(offsetY) <= 1;
    });
  }

  function isFieldContainer(el) {
    if (!isVisible(el)) return false;
    const control = findFieldControl(el);
    if (!control) return false;
    if (el.tagName === "LABEL" || el.querySelector("label")) return true;
    return hasSemanticPart(el, new Set(["field", "input", "control", "form"]));
  }

  function findFieldControl(field) {
    return [...field.querySelectorAll("input, textarea, select, [role='textbox'], [role='combobox'], [contenteditable='true']")]
      .find(isVisible) || null;
  }

  function fieldMetric(field) {
    const control = findFieldControl(field);
    if (!control) return null;
    const rect = field.getBoundingClientRect();
    const controlRect = control.getBoundingClientRect();
    return {
      field,
      rect,
      controlRect,
      labelRect: findLabelRect(field, control, controlRect) || rect,
      helperRect: findHelperRect(field, controlRect),
    };
  }

  function findLabelRect(field, control, controlRect) {
    const labelCandidate = [...field.querySelectorAll("*")]
      .filter((candidate) => candidate !== control && isVisible(candidate))
      .filter((candidate) => hasSemanticPart(candidate, labelParts) || clean(candidate.textContent || "").length > 0)
      .filter((candidate) => candidate.getBoundingClientRect().bottom <= controlRect.top + 6)
      .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0];
    return labelCandidate ? labelCandidate.getBoundingClientRect() : null;
  }

  function findHelperRect(field, controlRect) {
    const helperCandidate = [...field.querySelectorAll("*")]
      .filter((candidate) => isVisible(candidate) && hasSemanticPart(candidate, helperParts))
      .filter((candidate) => candidate.getBoundingClientRect().top >= controlRect.bottom - 6)
      .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
    return helperCandidate ? helperCandidate.getBoundingClientRect() : null;
  }

  function rowText(metrics) {
    return metrics
      .map((metric) => clean(metric.field.textContent || ""))
      .filter(Boolean)
      .join(" | ")
      .slice(0, 180);
  }

  function selectedImages(selector) {
    if (!selector) return [...document.images];
    try {
      const roots = [...document.querySelectorAll(selector)];
      return [...new Set(roots.flatMap((root) => {
        if (root.tagName === "IMG") return [root];
        return [...root.querySelectorAll("img")];
      }))];
    } catch {
      return [...document.images];
    }
  }

  function auditMedia({ viewportName, mediaSelector, mediaWalkRequested }) {
    const found = [];
    const selected = selectedImages(mediaSelector);
    const rendered = selected.filter(isVisible);
    const states = {
      selected: selected.length,
      rendered: rendered.length,
      notRendered: selected.length - rendered.length,
      loaded: 0,
      broken: 0,
      stillLoading: 0,
      deferredLazy: 0,
      missingSource: 0,
    };

    for (const img of rendered) {
      const rect = img.getBoundingClientRect();
      const inViewport = rect.bottom > 0
        && rect.right > 0
        && rect.top < window.innerHeight
        && rect.left < window.innerWidth;
      const source = img.currentSrc || img.getAttribute("src")?.trim() || "";
      const hasDeferredSource = Boolean(
        img.getAttribute("data-src")
        || img.getAttribute("data-lazy-src")
        || img.getAttribute("data-original"),
      );
      const isLazy = img.loading === "lazy" || hasDeferredSource;
      const isDeferred = !mediaWalkRequested
        && !inViewport
        && isLazy
        && (!img.complete || img.naturalWidth === 0 || !source);

      if (isDeferred) {
        states.deferredLazy += 1;
        continue;
      }

      if (!source) {
        states.missingSource += 1;
        found.push({
          viewport: viewportName,
          selector: describe(img),
          type: "image-source-missing",
          severity: "error",
          text: img.alt || "",
          detail: "Rendered image has no requested source. If it is lazy-loaded, visit its visible row before judging the asset.",
        });
        continue;
      }

      if (img.complete && img.naturalWidth === 0) {
        states.broken += 1;
        found.push({
          viewport: viewportName,
          selector: describe(img),
          type: "image-broken",
          severity: "error",
          text: img.alt || source,
          detail: "The image request completed without decodable natural dimensions.",
        });
        continue;
      }

      if (!img.complete || img.naturalWidth === 0) {
        states.stillLoading += 1;
        found.push({
          viewport: viewportName,
          selector: describe(img),
          type: "image-still-loading",
          severity: "error",
          text: img.alt || source,
          detail: "The rendered image had not completed loading when evidence was captured; this is not yet proof of a broken asset.",
        });
        continue;
      }

      states.loaded += 1;
      const imageMetrics = measureImage(img);
      if (!imageMetrics || imageMetrics.area < 10_000) continue;

      const ratioDelta = Math.abs(imageMetrics.displayedRatio / imageMetrics.naturalRatio - 1);
      if (!["cover", "contain", "scale-down"].includes(imageMetrics.objectFit) && ratioDelta > 0.08) {
        found.push({
          viewport: viewportName,
          selector: describe(img),
          type: "image-aspect-mismatch",
          severity: "error",
          text: img.alt || source,
          detail: `Image displays at ratio ${imageMetrics.displayedRatio} but natural ratio is ${imageMetrics.naturalRatio}; object-fit is "${imageMetrics.objectFit}".`,
        });
      } else if (imageMetrics.objectFit === "cover" && ratioDelta > 0.25) {
        found.push({
          viewport: viewportName,
          selector: describe(img),
          type: "image-heavy-crop",
          severity: "warning",
          text: img.alt || source,
          detail: `Image container ratio ${imageMetrics.displayedRatio} differs from natural ratio ${imageMetrics.naturalRatio}. Inspect whether important content is cropped.`,
        });
      }
    }

    return { meta: states, issues: found };
  }

  function measureImage(img) {
    const rect = img.getBoundingClientRect();
    if (!rect.width || !rect.height || !img.naturalWidth || !img.naturalHeight) return null;
    return {
      selector: describe(img),
      displayedWidth: Math.round(rect.width),
      displayedHeight: Math.round(rect.height),
      displayedRatio: +(rect.width / rect.height).toFixed(3),
      naturalRatio: +(img.naturalWidth / img.naturalHeight).toFixed(3),
      objectFit: getComputedStyle(img).objectFit || "fill",
      area: rect.width * rect.height,
    };
  }

  function measurePrimaryImage(selector) {
    const measured = selectedImages(selector)
      .filter(isVisible)
      .filter((img) => img.complete && img.naturalWidth)
      .map((img) => ({ img, metrics: measureImage(img) }))
      .filter((item) => item.metrics)
      .filter(({ img }) => {
        const rect = img.getBoundingClientRect();
        return rect.bottom > 0 && rect.top < window.innerHeight;
      })
      .sort((a, b) => b.metrics.area - a.metrics.area)[0]?.metrics;
    if (!measured) return null;
    delete measured.area;
    return measured;
  }

  function measureFirstViewportContent(selector) {
    let elements = [];
    if (selector) {
      try {
        elements = [...document.querySelectorAll(selector)];
      } catch {
        elements = [];
      }
    }
    if (!elements.length) {
      elements = [...document.querySelectorAll([
        "h1", "h2", "h3", "h4", "p", "a", "button", "img", "canvas", "video",
        "li", "td", "th", "input", "select", "textarea",
        "[role='button']", "[role='tab']", "[class*='card']", "[class*='panel']",
        "[class*='tile']", "[class*='media']", "[class*='hero']", "[class*='cover']",
      ].join(","))];
    }

    const rects = elements
      .filter(isVisible)
      .map((el) => el.getBoundingClientRect())
      .filter((rect) => rect.bottom > 0 && rect.top < window.innerHeight)
      .filter((rect) => rect.width > 1 && rect.height > 1)
      .filter((rect) => !(rect.width >= window.innerWidth * 0.98 && rect.height >= window.innerHeight * 0.98))
      .map((rect) => ({
        left: Math.max(0, rect.left),
        right: Math.min(window.innerWidth, rect.right),
        top: Math.max(0, rect.top),
        bottom: Math.min(window.innerHeight, rect.bottom),
      }));

    if (!rects.length) return null;

    const left = Math.min(...rects.map((rect) => rect.left));
    const right = Math.max(...rects.map((rect) => rect.right));
    const top = Math.min(...rects.map((rect) => rect.top));
    const bottom = Math.max(...rects.map((rect) => rect.bottom));
    const width = Math.max(0, right - left);

    return {
      left: Math.round(left),
      right: Math.round(right),
      top: Math.round(top),
      bottom: Math.round(bottom),
      width: Math.round(width),
      widthRatio: +(width / window.innerWidth).toFixed(3),
      leftBlank: Math.round(Math.max(0, left)),
      rightBlank: Math.round(Math.max(0, window.innerWidth - right)),
    };
  }

  function measureTypography() {
    const bodyStyle = getComputedStyle(document.body);
    const h1 = document.querySelector("h1");
    const h1Style = h1 ? getComputedStyle(h1) : null;
    const textElements = [...document.querySelectorAll("p,dd,li,td,th,button,a,span,strong,em")]
      .filter(isVisible)
      .map((el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return {
          tag: el.tagName.toLowerCase(),
          className: typeof el.className === "string" ? el.className : "",
          width: Math.round(rect.width),
          fontSize: Number.parseFloat(style.fontSize) || 0,
          text: clean(el.textContent || ""),
        };
      })
      .filter((item) => item.text.length >= 4 && item.width >= 20 && item.fontSize > 0);

    const importantText = textElements.filter((item) => !/(eyebrow|mono|tag|badge|pill|qbadge|tier)/i.test(item.className));
    const narrowTextColumns = importantText
      .filter((item) => item.text.length >= 16)
      .map((item) => item.width)
      .sort((a, b) => a - b);
    const smallestImportantTextSize = importantText
      .map((item) => item.fontSize)
      .sort((a, b) => a - b)[0] || null;

    return {
      bodyFont: bodyStyle.fontFamily,
      bodySize: bodyStyle.fontSize,
      bodyWeight: bodyStyle.fontWeight,
      bodyLineHeight: bodyStyle.lineHeight,
      bodyLetterSpacing: bodyStyle.letterSpacing,
      h1Font: h1Style?.fontFamily || null,
      h1Size: h1Style?.fontSize || null,
      h1Weight: h1Style?.fontWeight || null,
      h1LineHeight: h1Style?.lineHeight || null,
      h1LetterSpacing: h1Style?.letterSpacing || null,
      keyHeadings: [...document.querySelectorAll("h1,h2,h3")]
        .filter(isVisible)
        .slice(0, 12)
        .map((heading) => {
          const style = getComputedStyle(heading);
          return {
            tag: heading.tagName.toLowerCase(),
            text: clean(heading.textContent || "").slice(0, 120),
            fontFamily: style.fontFamily,
            fontSize: style.fontSize,
            fontWeight: style.fontWeight,
            lineHeight: style.lineHeight,
            letterSpacing: style.letterSpacing,
          };
        }),
      smallestImportantTextSize,
      narrowestTextColumnWidth: narrowTextColumns[0] || null,
    };
  }

  function auditImageOverlays({ viewportName, mediaSelector }) {
    const found = [];
    const images = selectedImages(mediaSelector)
      .filter(isVisible)
      .filter((img) => img.complete && img.naturalWidth)
      .map((img) => ({ img, rect: img.getBoundingClientRect() }))
      .filter((item) => item.rect.width * item.rect.height >= 10_000);

    if (!images.length) return found;

    const textElements = [...document.querySelectorAll("body *")]
      .filter(isVisible)
      .filter((el) => el.tagName !== "SCRIPT" && el.tagName !== "STYLE" && el.tagName !== "IMG")
      .map((el) => ({ el, text: ownText(el), rect: el.getBoundingClientRect(), style: getComputedStyle(el) }))
      .filter((item) => item.text.length > 0 && item.rect.width > 0 && item.rect.height > 0)
      .filter((item) => ["absolute", "fixed", "sticky"].includes(item.style.position) || item.style.zIndex !== "auto");

    for (const { img, rect: imageRect } of images) {
      for (const item of textElements) {
        if (item.el.contains(img) || img.contains(item.el)) continue;
        const overlap = intersectionRatio(imageRect, item.rect);
        if (overlap < 0.18) continue;
        found.push({
          viewport: viewportName,
          selector: describe(item.el),
          type: "image-overlay-collision",
          severity: "warning",
          text: clean(item.text).slice(0, 120),
          detail: `Text overlays ${Math.round(overlap * 100)}% of its own box on image ${describe(img)}. Inspect whether it covers important image content.`,
        });
      }
    }

    return found;
  }

  function auditSections(selector) {
    const found = [];
    let sections = [];
    try {
      sections = [...document.querySelectorAll(selector)];
    } catch {
      return { meta: { count: 0, worstOverflowX: 0, widest: null }, issues: found };
    }

    const measured = sections
      .filter(isVisible)
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.width > 100 && rect.height > 40;
      })
      .map((el) => {
        const rect = el.getBoundingClientRect();
        const overflowX = Math.max(0, Math.round(el.scrollWidth - el.clientWidth));
        const widthOverflow = Math.max(0, Math.round(rect.width - document.documentElement.clientWidth));
        return {
          selector: describe(el),
          top: Math.round(rect.top + window.scrollY),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          overflowX,
          widthOverflow,
          text: clean(el.querySelector("h1,h2,h3,h4")?.textContent || ownText(el) || "").slice(0, 120),
        };
      });

    for (const item of measured) {
      if (item.overflowX > 2) {
        found.push({
          viewport: viewportName,
          selector: item.selector,
          type: "section-horizontal-overflow",
          severity: "error",
          text: item.text,
          detail: `Section at y=${item.top} has internal horizontal overflow of ${item.overflowX}px.`,
        });
      }
      if (item.widthOverflow > 2) {
        found.push({
          viewport: viewportName,
          selector: item.selector,
          type: "section-wider-than-viewport",
          severity: "warning",
          text: item.text,
          detail: `Section box is ${item.widthOverflow}px wider than documentElement.clientWidth.`,
        });
      }
    }

    const worst = measured
      .slice()
      .sort((a, b) => b.overflowX - a.overflowX)[0] || null;
    const widest = measured
      .slice()
      .sort((a, b) => b.width - a.width)[0] || null;

    return {
      meta: {
        count: measured.length,
        worstOverflowX: worst?.overflowX || 0,
        worstOverflowSelector: worst?.overflowX ? worst.selector : null,
        widest: widest ? { selector: widest.selector, width: widest.width } : null,
      },
      issues: found,
    };
  }

  function ownText(el) {
    return [...el.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.nodeValue || "")
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function intersectionRatio(a, b) {
    const left = Math.max(a.left, b.left);
    const right = Math.min(a.right, b.right);
    const top = Math.max(a.top, b.top);
    const bottom = Math.min(a.bottom, b.bottom);
    if (right <= left || bottom <= top) return 0;
    const intersectionArea = (right - left) * (bottom - top);
    const bArea = b.width * b.height || 1;
    return intersectionArea / bArea;
  }

  function describe(el) {
    const tag = el.tagName.toLowerCase();
    if (el.id) return tag + "#" + CSS.escape(el.id);
    const testId = el.getAttribute("data-testid");
    if (testId) return tag + "[data-testid=\"" + CSS.escape(testId) + "\"]";
    const className = typeof el.className === "string"
      ? el.className.split(/\s+/).filter(Boolean).slice(0, 2).map((name) => CSS.escape(name)).join(".")
      : "";
    return tag + (className ? "." + className : "");
  }

  function auditPageType({ viewportName, pageType, screenshotSections }) {
    const found = [];
    const pageTypeMeta = { kind: pageType };
    const isDesignSystemLike = pageType === "design-system" || pageType === "live-artifact-design-system";
    const isLiveArtifactDesignSystem = pageType === "live-artifact-design-system";
    const bodyText = clean(document.body.innerText || "");
    const headingText = [...document.querySelectorAll("h1,h2,h3,h4")]
      .map((el) => clean(el.textContent || ""))
      .join(" ");
    const cardLike = [...document.querySelectorAll("article, section, div")]
      .filter(isVisible)
      .filter((el) => {
        const className = typeof el.className === "string" ? el.className : "";
        return /\b(card|panel|tile|module|widget)\b/i.test(className) || /(^|[-_])(card|panel|tile|module|widget)([-_]|$)/i.test(className);
      });

    const visibleInteractive = [...document.querySelectorAll(
      "a[href],button,input,select,textarea,[role='button'],[role='tab'],[tabindex]:not([tabindex='-1'])",
    )].filter(isVisible);
    const taskSurfaces = [...document.querySelectorAll(
      "table,form,canvas,svg,[role='grid'],[role='treegrid'],[class*='chart'],[class*='timeline'],[class*='queue'],[class*='map']",
    )].filter(isVisible);

    if (pageType === "landing") {
      const firstViewportText = visibleTextInViewport(0, window.innerHeight);
      const hasHeading = [...document.querySelectorAll("h1")].some(isVisible);
      const hasPrimaryAction = visibleInteractive.some((element) => {
        const rect = element.getBoundingClientRect();
        return rect.top < window.innerHeight && clean(element.textContent || "").length > 0;
      });
      pageTypeMeta.firstViewportHasHeading = hasHeading;
      pageTypeMeta.firstViewportHasPrimaryAction = hasPrimaryAction;
      if (!hasHeading || !hasPrimaryAction || !firstViewportText) {
        found.push({
          viewport: viewportName,
          type: "landing-first-viewport-contract-thin",
          severity: "warning",
          detail: `Landing first viewport: heading=${hasHeading}, primaryAction=${hasPrimaryAction}. Inspect whether identity, value, and the main action are legible before decorative depth.`,
        });
      }
    }

    if (pageType === "dashboard" && taskSurfaces.length === 0) {
      found.push({
        viewport: viewportName,
        type: "dashboard-task-surface-missing",
        severity: "warning",
        detail: "No visible table, form, chart, grid, timeline, queue, or map-like task surface was found. Confirm this is an operational dashboard rather than explanatory card copy.",
      });
    }

    if (["app", "tool", "game"].includes(pageType) && visibleInteractive.length === 0) {
      found.push({
        viewport: viewportName,
        type: `${pageType}-primary-interaction-missing`,
        severity: "warning",
        detail: `No visible interactive control was found for the ${pageType} profile. Confirm the primary work/play path exists and can recover from failure.`,
      });
    }

    if (pageType === "deck") {
      const slides = [...document.querySelectorAll(
        ".slide,[data-slide],[role='group'][aria-roledescription='slide'],section",
      )].filter(isVisible);
      pageTypeMeta.slideCount = slides.length;
      pageTypeMeta.slideGeometry = slides.slice(0, 100).map((slide, index) => {
        const rect = slide.getBoundingClientRect();
        return { index: index + 1, width: Math.round(rect.width), height: Math.round(rect.height) };
      });
      if (slides.length === 0) {
        found.push({
          viewport: viewportName,
          type: "deck-slide-structure-missing",
          severity: "error",
          detail: "No .slide, [data-slide], ARIA slide, or section element was found for the deck profile.",
        });
      }
      const geometryMismatch = pageTypeMeta.slideGeometry.filter(
        (slide) => Math.abs(slide.width - window.innerWidth) > 4 || Math.abs(slide.height - window.innerHeight) > 4,
      );
      if (geometryMismatch.length) {
        found.push({
          viewport: viewportName,
          type: "deck-slide-canvas-mismatch",
          severity: "warning",
          detail: `${geometryMismatch.length}/${slides.length} slide(s) do not match the ${window.innerWidth}x${window.innerHeight} audit canvas.`,
        });
      }
      if (!screenshotSections) {
        found.push({
          viewport: viewportName,
          type: "deck-slide-evidence-not-requested",
          severity: "warning",
          detail: "Use --screenshot-sections so every slide can be opened and inspected before claiming full-deck coverage.",
        });
      }
    }

    if (isDesignSystemLike) {
      const designSignals = [
        /principle|原则/i,
        /foundation|token|基础|变量|颜色|字体|间距/i,
        /component|组件/i,
        /pattern|模式/i,
        /state|variant|状态|变体/i,
        /governance|accessibility|do\/?don't|治理|可访问性|禁忌|用法/i,
      ];
      const signalCount = designSignals.filter((pattern) => pattern.test(headingText + " " + bodyText)).length;
      if (signalCount < 4) {
        found.push({
          viewport: viewportName,
          type: "design-system-structure-missing",
          severity: "error",
          detail: `Only ${signalCount}/6 design-system signals found. Expected principles, foundations/tokens, components, patterns, states/variants, and governance/usage guidance.`,
        });
      }

      const appDriftPattern = /工作台|真实工作台|数据大盘|运营大屏|dashboard|workbench|analytics workspace|control center/i;
      const firstViewportText = visibleTextInViewport(0, window.innerHeight);
      const hasSpecimenContext = /specimen|artifact|样本|规范|组件|状态|变体|pattern|模式|contract|anatomy|解剖|Design System|Live Artifact/i.test(firstViewportText);
      const hardAppDrift = /真实工作台|运营大屏|数据大盘|production dashboard|real workbench/i.test(firstViewportText);
      if (appDriftPattern.test(firstViewportText) && !(isLiveArtifactDesignSystem && hasSpecimenContext && !hardAppDrift)) {
        found.push({
          viewport: viewportName,
          type: "page-type-drift",
          severity: "warning",
          text: firstViewportText.slice(0, 180),
          detail: "A design-system artifact contains app/dashboard/workbench language in the first viewport.",
        });
      }

      if (isLiveArtifactDesignSystem) {
        const liveSignals = [
          /live artifact|interactive|交互|可交互|状态切换/i,
          /specimen|样本|pattern|模式|contract|anatomy|解剖/i,
          /variant|state|状态|变体/i,
          /usage|用法|do\/?don't|禁忌|治理/i,
        ];
        const liveSignalCount = liveSignals.filter((pattern) => pattern.test(headingText + " " + bodyText)).length;
        const interactiveCount = [...document.querySelectorAll([
          "button",
          "select",
          "input",
          "textarea",
          "details",
          "summary",
          "a[href]",
          "[role='button']",
          "[role='tab']",
          "[role='switch']",
          "[role='checkbox']",
          "[tabindex]:not([tabindex='-1'])",
        ].join(","))].filter(isVisible).length;

        if (liveSignalCount < 2) {
          found.push({
            viewport: viewportName,
            type: "live-artifact-framing-missing",
            severity: "warning",
            detail: `Only ${liveSignalCount}/4 live-artifact framing signals found. Interactive design systems should label specimens, states/variants, usage rules, or contracts so controls are not mistaken for a fake app.`,
          });
        }

        if (interactiveCount < 3) {
          found.push({
            viewport: viewportName,
            type: "live-artifact-interaction-thin",
            severity: "warning",
            detail: `${interactiveCount} visible interactive element(s) found. If this is intended as a live artifact, inspect whether reviewers can actually exercise component states and patterns.`,
          });
        }
      }
    }

    if (cardLike.length >= 40) {
      found.push({
        viewport: viewportName,
        type: "repeated-card-density",
        severity: isDesignSystemLike ? "warning" : "info",
        detail: `${cardLike.length} visible card/panel/tile-like containers found. Inspect whether cards express real structure or replace information architecture.`,
      });
    }

    pageTypeMeta.visibleInteractiveCount = visibleInteractive.length;
    pageTypeMeta.taskSurfaceCount = taskSurfaces.length;
    return { issues: found, meta: pageTypeMeta };
  }

  function visibleTextInViewport(top, bottom) {
    return [...document.querySelectorAll("body *")]
      .filter(isVisible)
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.bottom >= top && rect.top <= bottom;
      })
      .map((el) => clean(el.textContent || ""))
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function renderedLines(el) {
    const chars = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.nodeValue && node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });

    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const value = node.nodeValue || "";
      for (let offset = 0; offset < value.length;) {
        const char = Array.from(value.slice(offset))[0];
        const next = offset + char.length;
        if (!/\s/.test(char)) {
          const range = document.createRange();
          range.setStart(node, offset);
          range.setEnd(node, next);
          const rect = range.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) chars.push({ char, top: rect.top, left: rect.left });
          range.detach();
        }
        offset = next;
      }
    }

    if (!chars.length) return [];
    chars.sort((a, b) => a.top - b.top || a.left - b.left);
    const rows = [];
    for (const item of chars) {
      const row = rows.find((candidate) => Math.abs(candidate.top - item.top) <= 3);
      if (row) {
        row.items.push(item);
        row.top = (row.top + item.top) / 2;
      } else {
        rows.push({ top: item.top, items: [item] });
      }
    }
    return rows
      .sort((a, b) => a.top - b.top)
      .map((row) => row.items.sort((a, b) => a.left - b.left).map((item) => item.char).join(""));
  }

  function awkwardChineseBoundary(lines) {
    const commonPairs = new Set([
      "这里", "这个", "这种", "这些", "这样",
      "那个", "那些", "那种", "那样", "哪里",
      "我们", "你们", "他们", "她们", "它们",
      "不是", "不能", "不要", "不会", "不用",
      "应该", "必须", "可以", "需要", "还有",
      "以及", "因为", "所以", "如果", "但是",
    ]);

    for (let index = 0; index < lines.length - 1; index += 1) {
      const previousLine = lines[index].trim();
      const nextLine = lines[index + 1].trim();
      if (!previousLine || !nextLine) continue;
      const left = Array.from(previousLine).at(-1);
      const right = Array.from(nextLine)[0];
      const pair = `${left}${right}`;
      if (commonPairs.has(pair) || (/^[这那哪]$/.test(left) && /^[个些种样里]$/.test(right))) {
        return {
          pair,
          boundary: `${left}|${right}`,
          previousLine,
          nextLine,
        };
      }
    }
    return null;
  }
}
