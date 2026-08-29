#!/usr/bin/env node
/**
 * Repository action gate for daymade/claude-code-skills.
 *
 * Local main is a read-only runtime mirror. Commits must be made on feature
 * branches, and every push must be compared with freshly fetched current main
 * so a stale manifest cannot lower another plugin or reuse its release number.
 */

import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ZERO_SHA = "0000000000000000000000000000000000000000";
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.dirname(SCRIPT_DIR);
const CHECKER = path.join(SCRIPT_DIR, "ci", "check_version_progression.py");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: REPO_ROOT,
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
  });
  if (result.error) {
    throw new Error(`${command} could not start: ${result.error.message}`);
  }
  return result;
}

function gitCapture(...args) {
  const result = run("git", args, { capture: true });
  if (result.status !== 0) {
    throw new Error(
      `git ${args.join(" ")} failed: ${(result.stderr || result.stdout).trim()}`,
    );
  }
  return result.stdout.trim();
}

function canonicalRemote(raw) {
  const value = String(raw || "").trim().toLowerCase().replace(/\/+$/, "");
  return [
    "git@github.com:daymade/claude-code-skills.git",
    "git@github.com:daymade/claude-code-skills",
    "ssh://git@github.com/daymade/claude-code-skills.git",
    "ssh://git@github.com/daymade/claude-code-skills",
    "https://github.com/daymade/claude-code-skills.git",
    "https://github.com/daymade/claude-code-skills",
  ].includes(value);
}

function isCanonical(remoteUrl) {
  // Test mode can only make the policy stricter by applying it to a local
  // fixture. It cannot disable any check in a real canonical checkout.
  return (
    canonicalRemote(remoteUrl) ||
    process.env.GIT_MAINLINE_GUARD_TEST_CANONICAL === "1"
  );
}

function findCanonicalRemote() {
  let names = [];
  try {
    names = gitCapture("remote").split(/\r?\n/).filter(Boolean);
  } catch {
    names = [];
  }
  for (const name of names) {
    try {
      const urls = [
        ...gitCapture("remote", "get-url", "--all", name).split(/\r?\n/),
        ...gitCapture("remote", "get-url", "--push", "--all", name).split(/\r?\n/),
      ].filter(Boolean);
      const url = urls.find(canonicalRemote);
      if (url) return { name, url };
    } catch {
      // One malformed remote must not hide another canonical one.
    }
  }
  if (process.env.GIT_MAINLINE_GUARD_TEST_CANONICAL === "1") {
    return { name: names[0] || "origin", url: "test-fixture" };
  }
  return null;
}

function fail(message, code = 1) {
  process.stderr.write(`claude-code-skills guard blocked: ${message}\n`);
  process.exit(code);
}

function runProgression(base, candidateArgs) {
  const result = run("python3", [
    CHECKER,
    "--repo",
    REPO_ROOT,
    "--base",
    base,
    ...candidateArgs,
  ]);
  if (result.status !== 0) {
    fail("marketplace release state is stale or incomplete; use current origin/main and bump only the plugin(s) you changed.");
  }
}

function preCommit() {
  const canonical = findCanonicalRemote();
  if (!canonical) return;

  let branch = "";
  try {
    branch = gitCapture("symbolic-ref", "--quiet", "--short", "HEAD");
  } catch {
    fail("committing from detached HEAD is not allowed; create a feature branch from current origin/main.");
  }
  if (branch === "main") {
    fail("local main is a read-only runtime mirror; commit on a feature branch and ship through a PR.");
  }

  try {
    gitCapture(
      "rev-parse",
      "--verify",
      `refs/remotes/${canonical.name}/main^{commit}`,
    );
  } catch {
    fail(`${canonical.name}/main is unavailable; fetch it before committing.`);
  }
  runProgression(`refs/remotes/${canonical.name}/main`, ["--candidate-index"]);
}

function parsePushInput(input) {
  return input
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => {
      const fields = line.trim().split(/\s+/);
      if (fields.length !== 4) {
        fail(`malformed pre-push input: ${line}`, 2);
      }
      return {
        localRef: fields[0],
        localSha: fields[1],
        remoteRef: fields[2],
        remoteSha: fields[3],
      };
    });
}

function prePush() {
  const remoteName = process.argv[3] || "origin";
  let remoteUrl = process.argv[4] || "";
  if (!remoteUrl) {
    try {
      remoteUrl = gitCapture("remote", "get-url", "--push", remoteName);
    } catch {
      fail("could not resolve the push destination.", 2);
    }
  }
  if (!isCanonical(remoteUrl)) return;

  const updates = parsePushInput(fs.readFileSync(0, "utf8"));
  if (updates.length === 0) return;
  if (updates.some((update) => update.remoteRef === "refs/heads/main")) {
    fail("direct pushes to main are forbidden; merge a reviewed feature PR instead.");
  }

  const featureUpdates = updates.filter(
    (update) =>
      update.remoteRef.startsWith("refs/heads/") &&
      update.localSha !== ZERO_SHA,
  );
  if (featureUpdates.length === 0) return;

  const fetchResult = run("git", [
    "fetch",
    "--quiet",
    "--no-tags",
    remoteName,
    "refs/heads/main:refs/remotes/" + remoteName + "/main",
  ]);
  if (fetchResult.status !== 0) {
    fail("could not refresh current main; refusing to judge a push against stale authority.", 2);
  }
  const base = `refs/remotes/${remoteName}/main`;
  const seen = new Set();
  for (const update of featureUpdates) {
    if (!/^[0-9a-f]{40}$/.test(update.localSha)) {
      fail(`candidate SHA is not a full commit identity: ${update.localSha}`, 2);
    }
    if (seen.has(update.localSha)) continue;
    seen.add(update.localSha);
    runProgression(base, ["--candidate", update.localSha]);
  }
}

const mode = process.argv[2];
try {
  if (mode === "pre-commit") {
    preCommit();
  } else if (mode === "pre-push") {
    prePush();
  } else {
    fail(`unknown mode ${JSON.stringify(mode)}`, 2);
  }
} catch (error) {
  fail(error instanceof Error ? error.message : String(error), 2);
}
