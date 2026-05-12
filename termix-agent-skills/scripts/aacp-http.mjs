#!/usr/bin/env node

const DEFAULT_BASE_URL = "https://aacp-backend.termix.live";

export function usage(message, examples = []) {
  if (message) console.error(message);
  if (examples.length > 0) {
    console.error("");
    for (const example of examples) console.error(example);
  }
  process.exit(2);
}

export function buildUrl(target) {
  const rawBase = process.env.AACP_BASE_URL || DEFAULT_BASE_URL;
  const base = rawBase.replace(/\/+$/, "");
  const originBase = base.replace(/\/api\/v1$/, "");
  const apiBase = `${originBase}/api/v1`;

  if (/^https?:\/\//i.test(target)) return target;
  if (target.startsWith("/api/")) return `${originBase}${target}`;
  if (target.startsWith("/")) return `${apiBase}${target}`;
  return `${apiBase}/${target}`;
}

export async function getJson(target) {
  const url = buildUrl(target);
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  const text = await response.text();

  let body;
  try {
    body = text.length > 0 ? JSON.parse(text) : null;
  } catch {
    throw new Error(`GET ${url} -> ${response.status} ${response.statusText}\n${text}`);
  }

  if (!response.ok) {
    const detail = body?.message || body?.error || JSON.stringify(body);
    throw new Error(`GET ${url} -> ${response.status} ${response.statusText}\n${detail}`);
  }

  if (body && body.success === false) {
    throw new Error(`GET ${url} failed\n${body.message || JSON.stringify(body)}`);
  }

  return body;
}

export function printJson(value) {
  console.log(JSON.stringify(value, null, 2));
}

export async function main(run) {
  try {
    await run();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
