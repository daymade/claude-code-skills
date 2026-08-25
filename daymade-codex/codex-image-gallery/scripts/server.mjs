#!/usr/bin/env node
import { createReadStream } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HOST = process.env.HOST || "127.0.0.1";
const DEFAULT_PORT = Number(process.env.PORT || process.argv[2] || 8765);
const SKILL_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP_ROOT = path.join(SKILL_ROOT, "assets");
const IMAGE_ROOT = path.resolve(process.env.GALLERY_ROOT || path.join(os.homedir(), ".codex/generated_images"));

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif"
};

function isImage(filePath) {
  return /\.(png|jpe?g|webp|gif)$/i.test(filePath);
}

async function walkImages(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...await walkImages(fullPath));
    } else if (entry.isFile() && isImage(entry.name)) {
      const info = await stat(fullPath);
      out.push({
        path: path.relative(IMAGE_ROOT, fullPath).split(path.sep).join("/"),
        mtime: Math.round(info.mtimeMs),
        size: info.size
      });
    }
  }

  return out;
}

function safePath(root, relativePath) {
  const fullPath = path.resolve(root, relativePath);
  if (fullPath !== root && !fullPath.startsWith(`${root}${path.sep}`)) {
    return null;
  }
  return fullPath;
}

function appPath(urlPath) {
  if (urlPath === "/" || urlPath === "/index.html") {
    return path.join(APP_ROOT, "index.html");
  }
  return null;
}

function imagePath(urlPath) {
  if (!urlPath.startsWith("/images/")) return null;
  try {
    return safePath(IMAGE_ROOT, decodeURIComponent(urlPath.slice("/images/".length)));
  } catch {
    return null;
  }
}

async function handler(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${DEFAULT_PORT}`}`);

  if (url.pathname === "/api/images") {
    const items = (await walkImages(IMAGE_ROOT)).sort((a, b) => b.mtime - a.mtime || a.path.localeCompare(b.path));
    res.writeHead(200, {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    });
    res.end(JSON.stringify({
      rootLabel: path.basename(IMAGE_ROOT),
      rootPath: IMAGE_ROOT,
      items
    }));
    return;
  }

  let fullPath = appPath(url.pathname);
  if (!fullPath && url.pathname.startsWith("/images/")) {
    fullPath = imagePath(url.pathname);
    if (!fullPath) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }
  }

  if (!fullPath) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }

  try {
    const info = await stat(fullPath);
    if (!info.isFile()) throw new Error("Not a file");
    const ext = path.extname(fullPath).toLowerCase();
    res.writeHead(200, {
      "content-type": MIME[ext] || "application/octet-stream",
      "cache-control": ext === ".html" ? "no-store" : "public, max-age=60"
    });
    createReadStream(fullPath).pipe(res);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
}

function listen(port) {
  const server = http.createServer((req, res) => {
    handler(req, res).catch((error) => {
      res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      res.end(error.stack || String(error));
    });
  });

  server.on("error", (error) => {
    if (error.code === "EADDRINUSE" && port < DEFAULT_PORT + 20) {
      listen(port + 1);
      return;
    }
    throw error;
  });

  server.listen(port, HOST, () => {
    console.log(`Codex image gallery: http://${HOST}:${port}/`);
    console.log(`Image root: ${IMAGE_ROOT}`);
  });
}

listen(DEFAULT_PORT);
