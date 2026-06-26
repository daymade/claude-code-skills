import { copyFile, mkdir, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_BUTTON_SELECTOR = 'button[aria-label="Show the uploaded image in a lightbox"]';
const DEFAULT_SELECTED_SELECTOR = 'img[alt="Selected image presented in a lightbox."]';

function pad2(value) {
  return String(value).padStart(2, "0");
}

function defaultDateStamp() {
  return new Date().toISOString().slice(0, 10).replaceAll("-", "");
}

function normalizeExtension(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".jpeg") return ".jpg";
  if ([".jpg", ".png", ".webp", ".gif"].includes(ext)) return ext;
  return ".jpg";
}

async function pathExists(filePath) {
  try {
    await stat(filePath);
    return true;
  } catch {
    return false;
  }
}

async function newestMatchingFile(directory, predicate) {
  const names = await readdir(directory);
  const candidates = [];

  for (const name of names) {
    if (!predicate(name)) continue;
    const filePath = path.join(directory, name);
    const info = await stat(filePath);
    if (info.isFile()) {
      candidates.push({ filePath, mtimeMs: info.mtimeMs, size: info.size });
    }
  }

  candidates.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return candidates[0] || null;
}

async function waitForDownloadedMedia(downloadsDir, uuid, startedAtMs, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const extensions = [".jpeg", ".jpg", ".png", ".webp"];

  while (Date.now() < deadline) {
    if (uuid) {
      for (const ext of extensions) {
        const exactPath = path.join(downloadsDir, `${uuid}${ext}`);
        if (await pathExists(exactPath)) return exactPath;
      }
    }

    const newest = await newestMatchingFile(downloadsDir, (name) => {
      if (!extensions.some((ext) => name.toLowerCase().endsWith(ext))) return false;
      if (uuid && !name.includes(uuid)) return false;
      return true;
    });

    if (newest && newest.mtimeMs >= startedAtMs - 2000 && newest.size > 0) {
      return newest.filePath;
    }

    await new Promise((resolve) => setTimeout(resolve, 200));
  }

  throw new Error(`Timed out waiting for downloaded Gemini media ${uuid || ""}`.trim());
}

async function selectedImageInfo(tab, selector) {
  return await tab.playwright.evaluate((selectedSelector) => {
    const img = document.querySelector(selectedSelector);
    if (!img) return null;
    const src = img.currentSrc || img.src || "";
    return {
      src,
      naturalWidth: img.naturalWidth || 0,
      naturalHeight: img.naturalHeight || 0,
      renderedWidth: img.width || 0,
      renderedHeight: img.height || 0
    };
  }, selector);
}

async function waitForSelectedImage(tab, selector, previousSrc, timeoutMs) {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const info = await selectedImageInfo(tab, selector);
    if (
      info &&
      info.src.startsWith("blob:") &&
      info.naturalWidth > 0 &&
      info.naturalHeight > 0 &&
      (!previousSrc || info.src !== previousSrc)
    ) {
      return info;
    }

    await tab.playwright.waitForTimeout(150);
  }

  throw new Error("Timed out waiting for Gemini lightbox image");
}

async function claimGeminiTab(browser, tabUrlIncludes) {
  const openTabs = await browser.user.openTabs();
  const matches = openTabs.filter((tabInfo) => {
    const url = tabInfo.url || "";
    const title = tabInfo.title || "";
    return url.includes(tabUrlIncludes) || (url.includes("gemini.google.com") && title.includes("Gemini"));
  });

  if (matches.length === 0) {
    throw new Error(`No open Gemini tab matched ${tabUrlIncludes}`);
  }

  return await browser.user.claimTab(matches[0]);
}

export async function downloadGeminiImagesFromChrome(options = {}) {
  const browser = options.browser || globalThis.browser;
  if (!browser) throw new Error("Chrome browser runtime is not initialized");

  const homeDir = globalThis.nodeRepl?.homeDir || ".";
  const downloadsDir = options.downloadsDir || path.join(homeDir, "Downloads");
  const outputDir =
    options.outputDir ||
    path.join(downloadsDir, `gemini_conversation_images_${defaultDateStamp()}`);
  const tabUrlIncludes = options.tabUrlIncludes || "gemini.google.com/app";
  const imageButtonSelector = options.imageButtonSelector || DEFAULT_BUTTON_SELECTOR;
  const selectedImageSelector = options.selectedImageSelector || DEFAULT_SELECTED_SELECTOR;
  const expectedCount = options.expectedCount;
  const lightboxTimeoutMs = options.lightboxTimeoutMs || 15000;
  const downloadTimeoutMs = options.downloadTimeoutMs || 20000;

  const tab = options.tab || (await claimGeminiTab(browser, tabUrlIncludes));
  const pageUrl = await tab.url();
  const pageTitle = await tab.title();

  await mkdir(outputDir, { recursive: true });

  let buttons = tab.playwright.locator(imageButtonSelector);
  const initialCount = await buttons.count();
  if (initialCount === 0) {
    throw new Error(`No Gemini image lightbox buttons found with selector ${imageButtonSelector}`);
  }
  if (expectedCount != null && initialCount !== expectedCount) {
    throw new Error(`Expected ${expectedCount} Gemini images, found ${initialCount}`);
  }

  const selected = tab.playwright.locator(selectedImageSelector);
  const files = [];
  let previousBlobSrc = "";

  for (let index = 0; index < initialCount; index += 1) {
    try {
      await tab.cua.keypress({ keys: ["ESC"] });
    } catch {
      // The lightbox may already be closed.
    }
    await tab.playwright.waitForTimeout(150);

    buttons = tab.playwright.locator(imageButtonSelector);
    const currentCount = await buttons.count();
    if (currentCount !== initialCount) {
      throw new Error(`Gemini image button count changed from ${initialCount} to ${currentCount}`);
    }

    await buttons.nth(index).click({ timeoutMs: 10000 });
    const imageInfo = await waitForSelectedImage(
      tab,
      selectedImageSelector,
      previousBlobSrc,
      lightboxTimeoutMs
    );
    previousBlobSrc = imageInfo.src;

    const selectedCount = await selected.count();
    if (selectedCount !== 1) {
      throw new Error(`Expected exactly one selected lightbox image, found ${selectedCount}`);
    }

    const uuid = imageInfo.src.match(/\/([0-9a-f-]{36})$/i)?.[1] || null;
    const downloadStartedAt = Date.now();
    await selected.downloadMedia({ timeoutMs: downloadTimeoutMs });
    const downloadedPath = await waitForDownloadedMedia(
      downloadsDir,
      uuid,
      downloadStartedAt,
      downloadTimeoutMs
    );

    const outputName = `image_${pad2(index + 1)}${normalizeExtension(downloadedPath)}`;
    const outputPath = path.join(outputDir, outputName);
    await copyFile(downloadedPath, outputPath);

    files.push({
      index: index + 1,
      outputName,
      outputPath,
      downloadedPath,
      uuid,
      naturalWidth: imageInfo.naturalWidth,
      naturalHeight: imageInfo.naturalHeight
    });
  }

  const manifest = {
    generatedAt: new Date().toISOString(),
    pageTitle,
    pageUrl,
    outputDir,
    imageCount: files.length,
    files
  };
  const manifestPath = path.join(outputDir, "manifest.json");
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

  return {
    pageTitle,
    pageUrl,
    outputDir,
    manifestPath,
    imageCount: files.length,
    files
  };
}
