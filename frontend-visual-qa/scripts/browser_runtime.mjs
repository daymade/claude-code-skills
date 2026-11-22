import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const ALLOW_CLONING_ENV = "FRONTEND_VISUAL_QA_ALLOW_CLONING_CHROME";

function canonicalPath(candidate, realpath) {
  try {
    return realpath(candidate);
  } catch {
    return path.resolve(candidate);
  }
}

export function isCloningBrowserPath(candidate, { realpath = fs.realpathSync } = {}) {
  if (!candidate) return false;
  const normalized = canonicalPath(candidate, realpath).normalize("NFC").toLowerCase();
  return /\/google chrome(?: beta| dev| canary)?\.app\/contents\/macos\//u.test(normalized)
    || /\/chromium\.app\/contents\/macos\//u.test(normalized);
}

export function resolveBrowserPath({
  platform = process.platform,
  env = process.env,
  home = os.homedir(),
  exists = fs.existsSync,
  realpath = fs.realpathSync,
} = {}) {
  const explicit = env.CHROME_PATH;
  if (explicit) {
    if (!exists(explicit)) throw new Error(`CHROME_PATH does not exist: ${explicit}`);
    if (platform === "darwin" && isCloningBrowserPath(explicit, { realpath }) && env[ALLOW_CLONING_ENV] !== "1") {
      throw new Error(
        `Regular Chrome is disabled for one-shot QA because terminated launches leave code_sign_clone directories. `
        + `Set CHROME_PATH to Chrome for Testing, or set ${ALLOW_CLONING_ENV}=1 for an explicit override.`,
      );
    }
    return explicit;
  }

  if (platform !== "darwin") {
    const candidates = [
      env.PROGRAMFILES && path.join(env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
      env["PROGRAMFILES(X86)"] && path.join(env["PROGRAMFILES(X86)"], "Google/Chrome/Application/chrome.exe"),
      env.LOCALAPPDATA && path.join(env.LOCALAPPDATA, "Google/Chrome/Application/chrome.exe"),
      env.PROGRAMFILES && path.join(env.PROGRAMFILES, "Microsoft/Edge/Application/msedge.exe"),
      env["PROGRAMFILES(X86)"] && path.join(env["PROGRAMFILES(X86)"], "Microsoft/Edge/Application/msedge.exe"),
      "/usr/bin/google-chrome-stable",
      "/usr/bin/google-chrome",
      "/usr/bin/chromium",
      "/usr/bin/chromium-browser",
      "/snap/bin/chromium",
    ].filter(Boolean);
    return candidates.find((candidate) => exists(candidate)) || null;
  }
  const candidates = [
    "/Applications/Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    path.join(home, "Applications/Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
  ];
  const candidate = candidates.find((item) => exists(item)) || null;
  if (candidate && isCloningBrowserPath(candidate, { realpath }) && env[ALLOW_CLONING_ENV] !== "1") {
    throw new Error(
      `Discovered Chrome for Testing resolves to regular Chrome. `
      + `Set ${ALLOW_CLONING_ENV}=1 only if this cloning-browser override is intentional.`,
    );
  }
  return candidate;
}
