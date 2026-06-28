#!/usr/bin/env node
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

function loadPlaywright() {
  const requireFromProject = createRequire(`${process.cwd()}/package.json`);
  try {
    return requireFromProject("playwright-core");
  } catch (projectError) {
    try {
      const requireFromSkill = createRequire(import.meta.url);
      return requireFromSkill("playwright-core");
    } catch {
      throw new Error(
        "playwright-core not found. Run `npm install -D playwright-core` in the frontend project, then re-run this script.\n" +
        `Original error: ${projectError.message}`
      );
    }
  }
}

function getArg(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error("Chrome/Chromium not found. Set CHROME_PATH to the browser executable.");
  }
  return found;
}

const target = getArg("--url") || getArg("--file");
const outDir = getArg("--out", "/tmp/frontend-visual-qa");
const forbidPattern = getArg("--forbid", "");
const requirePattern = getArg("--require", "");
const pageType = getArg("--page-type", "auto");
const expectedWindowWidth = parsePositiveInt(getArg("--expected-window-width", ""));
const contentSelector = getArg("--content-selector", "");
const mediaSelector = getArg("--media-selector", "");
const sectionSelector = getArg("--section-selector", "section,[role='region'],main > div,main > article");
const maxSectionScreenshots = parsePositiveInt(getArg("--max-section-screenshots", "4"));
const screenshotSections = process.argv.includes("--screenshot-sections");
const failOnWarning = process.argv.includes("--fail-on-warning");

if (!target || process.argv.includes("--help")) {
  console.error("Usage: visual_layout_audit.mjs --url <http://localhost:port/|local.html> [--page-type design-system|live-artifact-design-system|dashboard|app|landing|auto] [--forbid \"Old Name|Bad Term\"] [--require \"Required Term\"] [--expected-window-width 1920] [--content-selector main] [--media-selector .hero] [--section-selector \"section\"] [--screenshot-sections] [--max-section-screenshots 4] [--out /tmp/dir] [--fail-on-warning]");
  process.exit(2);
}

const url = normalizeTarget(target);
validateForbidPattern(forbidPattern);
validateForbidPattern(requirePattern);
validatePageType(pageType);
validateSelector(sectionSelector, "--section-selector");

const { chromium } = loadPlaywright();

fs.mkdirSync(outDir, { recursive: true });

const viewports = [
  { name: "desktop-wide", width: 1700, height: 1000, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

const browser = await chromium.launch({
  executablePath: findChrome(),
  headless: true,
});

const report = {
  url,
  createdAt: new Date().toISOString(),
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
  await page.goto(url, { waitUntil: "networkidle", timeout: 30_000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  const screenshot = `${outDir}/${viewport.name}.png`;
  await page.screenshot({ path: screenshot, fullPage: false });
  const result = await page.evaluate(auditPage, {
    viewportName: viewport.name,
    forbidPattern,
    requirePattern,
    pageType,
    expectedWindowWidth,
    contentSelector,
    mediaSelector,
    sectionSelector,
  });
  const sectionScreenshots = screenshotSections
    ? await captureSectionScreenshots(page, viewport, outDir, sectionSelector, maxSectionScreenshots)
    : [];
  report.viewports.push({ ...result.meta, screenshot, sectionScreenshots });
  report.issues.push(...result.issues);
  await page.close();
}

await browser.close();

const reportPath = `${outDir}/frontend-visual-qa-report.json`;
fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));

const errors = report.issues.filter((issue) => issue.severity === "error");
const warnings = report.issues.filter((issue) => issue.severity === "warning");

for (const viewport of report.viewports) {
  const visual = viewport.visualViewport ? `, visual=${viewport.visualViewport.width}x${viewport.visualViewport.height}@${viewport.visualViewport.scale}` : "";
  const content = viewport.firstViewportContent
    ? `, firstViewportBlank=${viewport.firstViewportContent.leftBlank}/${viewport.firstViewportContent.rightBlank}, contentRatio=${viewport.firstViewportContent.widthRatio}`
    : "";
  const primaryImage = viewport.primaryImage
    ? `, primaryImage=${viewport.primaryImage.displayedWidth}x${viewport.primaryImage.displayedHeight} ratio=${viewport.primaryImage.displayedRatio}/${viewport.primaryImage.naturalRatio} fit=${viewport.primaryImage.objectFit}`
    : "";
  const typography = viewport.typography
    ? `, type=${viewport.typography.bodySize}/${viewport.typography.h1Size}, minText=${viewport.typography.smallestImportantTextSize}, minCol=${viewport.typography.narrowestTextColumnWidth}`
    : "";
  const sections = viewport.sections
    ? `sections=${viewport.sections.count}, worstSectionOverflowX=${viewport.sections.worstOverflowX}`
    : "";
  console.log(`${viewport.viewport}: outer=${viewport.outerWidth}x${viewport.outerHeight}, inner=${viewport.width}x${viewport.height}, outerMinusInner=${viewport.outerMinusInner}, client=${viewport.clientWidth}, scroll=${viewport.scrollWidth}, overflowX=${viewport.overflowX}${visual}${content}${primaryImage}${typography}, title="${viewport.title}", h1="${viewport.h1}", screenshot=${viewport.screenshot}`);
  if (sections) console.log(`  sectionAudit: ${sections}`);
  if (viewport.sectionScreenshots?.length) {
    console.log(`  sectionScreenshots: ${viewport.sectionScreenshots.map((item) => item.screenshot).join(", ")}`);
  }
}

if (report.issues.length) {
  console.log(`\nIssues: ${errors.length} error(s), ${warnings.length} warning(s). Report: ${reportPath}`);
  for (const issue of report.issues) {
    console.log(`- ${issue.severity.toUpperCase()} ${issue.viewport} ${issue.type} ${issue.selector || ""}`);
    if (issue.text) console.log(`  text: ${issue.text}`);
    if (issue.detail) console.log(`  ${issue.detail}`);
  }
} else {
  console.log(`\nNo mechanical layout issues found. Screenshots still require human visual review. Report: ${reportPath}`);
}

process.exit(errors.length || (failOnWarning && warnings.length) ? 1 : 0);

function normalizeTarget(value) {
  if (/^(https?:|file:)/i.test(value)) return value;
  const resolved = path.resolve(value);
  if (fs.existsSync(resolved)) return pathToFileURL(resolved).href;
  return value;
}

function validateForbidPattern(pattern) {
  if (!pattern) return;
  try {
    new RegExp(pattern, "g");
  } catch (error) {
    console.error(`Invalid --forbid regular expression: ${error.message}`);
    process.exit(2);
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

function validatePageType(value) {
  const allowed = new Set(["auto", "design-system", "live-artifact-design-system", "dashboard", "app", "landing"]);
  if (!allowed.has(value)) {
    console.error(`Invalid --page-type "${value}". Expected one of: ${[...allowed].join(", ")}`);
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

async function captureSectionScreenshots(page, viewport, outDir, sectionSelector, maxCount) {
  const sections = await page.evaluate(collectScreenshotSections, {
    sectionSelector,
    maxCount: maxCount || 4,
  });
  const captures = [];
  for (let index = 0; index < sections.length; index += 1) {
    const section = sections[index];
    const scrolled = await page.evaluate(({ selector, domIndex }) => {
      const el = document.querySelectorAll(selector)[domIndex];
      if (!el) return null;
      el.scrollIntoView({ block: "start", inline: "nearest" });
      return Math.round(window.scrollY);
    }, { selector: sectionSelector, domIndex: section.domIndex });
    if (scrolled === null) continue;
    await page.waitForTimeout(80);
    const file = `${outDir}/${viewport.name}-section-${String(index + 1).padStart(2, "0")}-${section.slug}.png`;
    await page.screenshot({ path: file, fullPage: false });
    captures.push({ ...section, scrollY: scrolled, screenshot: file });
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return captures;
}

function collectScreenshotSections({ sectionSelector, maxCount }) {
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
        height: Math.round(rect.height),
        width: Math.round(rect.width),
        preferredIndex,
        label: label.slice(0, 80),
        slug: slugify(label) || `section-${domIndex + 1}`,
        visible: rect.width > 100 && rect.height > 80 && style.display !== "none" && style.visibility !== "hidden",
      };
    })
    .filter((item) => item.visible)
    .filter((item) => item.top > window.innerHeight * 0.25);

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

function auditPage({ viewportName, forbidPattern, requirePattern, pageType, expectedWindowWidth, contentSelector, mediaSelector, sectionSelector }) {
  const issues = [];
  const forbiddenTerms = forbidPattern ? new RegExp(forbidPattern, "g") : null;
  const requiredTerms = requirePattern ? new RegExp(requirePattern, "g") : null;
  const textSelector = [
    "h1", "h2", "h3", "h4", "p", "button", "a", "strong", "em", "td", "th",
    "[class*='tag']", "[class*='badge']", "[class*='pill']", "[class*='nav']",
    "[class*='title']", "[class*='label']", "[class*='note']", "[class*='eyebrow']",
  ].join(",");

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
    visualViewport: window.visualViewport ? {
      width: Math.round(window.visualViewport.width),
      height: Math.round(window.visualViewport.height),
      scale: window.visualViewport.scale,
    } : null,
  };

  meta.firstViewportContent = measureFirstViewportContent(contentSelector);
  meta.primaryImage = measurePrimaryImage(mediaSelector);
  meta.typography = measureTypography();
  const sectionAudit = auditSections(sectionSelector);
  meta.sections = sectionAudit.meta;
  issues.push(...sectionAudit.issues);

  if (meta.overflowX > 1) {
    issues.push({ viewport: viewportName, type: "page-horizontal-overflow", severity: "error", detail: `Page overflows by ${meta.overflowX}px.` });
  }

  if (/^desktop/.test(viewportName) && Math.abs(meta.outerMinusInner) > 120) {
    issues.push({
      viewport: viewportName,
      type: "viewport-emulation-mismatch",
      severity: "warning",
      detail: `outerWidth (${meta.outerWidth}) differs from innerWidth (${meta.width}) by ${meta.outerMinusInner}px. In user-visible Chrome, verify the emulated viewport matches the actual window before judging blank space.`,
    });
  }

  if (/^desktop/.test(viewportName) && expectedWindowWidth && Math.abs(expectedWindowWidth - meta.width) > 120) {
    issues.push({
      viewport: viewportName,
      type: "expected-window-viewport-mismatch",
      severity: "warning",
      detail: `Expected visible Chrome width is ${expectedWindowWidth}px, but this audit rendered a ${meta.width}px CSS viewport. Reproduce the user's real viewport before judging wide-screen blank space.`,
    });
  }

  if (/^desktop/.test(viewportName) && meta.firstViewportContent) {
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

  if (forbiddenTerms) {
    const badMatches = [...(document.body.innerText || "").matchAll(forbiddenTerms)].map((match) => match[0]);
    for (const term of [...new Set(badMatches)]) {
      issues.push({ viewport: viewportName, type: "forbidden-rendered-term", severity: "error", text: term, detail: "A project-specific forbidden term appears in rendered UI." });
    }
  }

  if (requiredTerms && !(document.body.innerText || "").match(requiredTerms)) {
    issues.push({ viewport: viewportName, type: "required-rendered-term-missing", severity: "error", detail: `No rendered text matches required pattern: ${requiredTerms.source}` });
  }

  issues.push(...auditPageType({ viewportName, pageType }));

  for (const el of [...document.querySelectorAll(textSelector)].filter(isVisible)) {
    const text = clean(el.textContent || "");
    if (!text || text.length < 2 || text.length > 180) continue;
    const selector = describe(el);
    const style = getComputedStyle(el);
    const overflowX = el.scrollWidth - el.clientWidth;
    const overflowY = el.scrollHeight - el.clientHeight;

    if (overflowX > 2 && style.overflowX !== "visible") {
      issues.push({ viewport: viewportName, selector, type: "element-horizontal-overflow", severity: "error", text, detail: `Element overflows by ${Math.round(overflowX)}px.` });
    }
    if (overflowY > 2 && style.overflowY !== "visible" && style.maxHeight !== "none") {
      issues.push({ viewport: viewportName, selector, type: "text-clipped", severity: "error", text, detail: `Element is clipped by ${Math.round(overflowY)}px.` });
    }

    const lines = renderedLines(el);
    if (lines.length < 2) continue;
    const lastLine = lines.at(-1);
    const lastCharCount = [...lastLine.replace(/\s+/g, "")].length;
    const className = typeof el.className === "string" ? el.className : "";
    const classTokens = className.split(/\s+/).filter(Boolean);
    const isHeading = /^H[1-4]$/.test(el.tagName) || classTokens.some((token) => /(^|[-_])(title|heading)([-_]|$)/i.test(token));
    const role = el.getAttribute("role") || "";
    const isInteractiveAnchor = el.tagName === "A" && /button|tab|nav|menu|link/i.test(classTokens.join(" ") + " " + role);
    const isControlClass = classTokens.some((token) => /^(tag|badge|pill|btn|button|tab|nav|seg__opt|qbadge|tier)$/.test(token));
    const isControlRole = /^(button|tab|menuitem|switch|checkbox|radio|link)$/.test(role);
    const isControl = el.tagName === "BUTTON" || isInteractiveAnchor || isControlRole || isControlClass;
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

  for (const img of selectedImages(mediaSelector).filter(isVisible)) {
    if (!img.complete || img.naturalWidth === 0) {
      issues.push({ viewport: viewportName, selector: describe(img), type: "image-not-loaded", severity: "error", text: img.alt || img.src });
      continue;
    }

    const imageMetrics = measureImage(img);
    if (!imageMetrics || imageMetrics.area < 10_000) continue;

    const ratioDelta = Math.abs(imageMetrics.displayedRatio / imageMetrics.naturalRatio - 1);
    if (!["cover", "contain", "scale-down"].includes(imageMetrics.objectFit) && ratioDelta > 0.08) {
      issues.push({
        viewport: viewportName,
        selector: describe(img),
        type: "image-aspect-mismatch",
        severity: "error",
        text: img.alt || img.src,
        detail: `Image displays at ratio ${imageMetrics.displayedRatio} but natural ratio is ${imageMetrics.naturalRatio}; object-fit is "${imageMetrics.objectFit}".`,
      });
    } else if (imageMetrics.objectFit === "cover" && ratioDelta > 0.25) {
      issues.push({
        viewport: viewportName,
        selector: describe(img),
        type: "image-heavy-crop",
        severity: "warning",
        text: img.alt || img.src,
        detail: `Image container ratio ${imageMetrics.displayedRatio} differs from natural ratio ${imageMetrics.naturalRatio}. Inspect whether important content is cropped.`,
      });
    }
  }

  issues.push(...auditImageOverlays({ viewportName, mediaSelector }));

  return { meta, issues };

  function clean(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function isVisible(el) {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function selectedImages(selector) {
    if (!selector) return [...document.images];
    try {
      const roots = [...document.querySelectorAll(selector)].filter(isVisible);
      return [...new Set(roots.flatMap((root) => {
        if (root.tagName === "IMG") return [root];
        return [...root.querySelectorAll("img")];
      }))];
    } catch {
      return [...document.images];
    }
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
      bodyLineHeight: bodyStyle.lineHeight,
      h1Size: h1Style?.fontSize || null,
      h1LineHeight: h1Style?.lineHeight || null,
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
    if (el.id) return `${el.tagName.toLowerCase()}#${el.id}`;
    const className = typeof el.className === "string"
      ? el.className.split(/\s+/).filter(Boolean).slice(0, 2).join(".")
      : "";
    return `${el.tagName.toLowerCase()}${className ? `.${className}` : ""}`;
  }

  function auditPageType({ viewportName, pageType }) {
    const found = [];
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

    return found;
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
