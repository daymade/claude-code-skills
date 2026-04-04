#!/usr/bin/env node
/**
 * Douban RSS → CSV incremental sync
 *
 * Pulls the public RSS feed, parses new entries, appends to CSV files.
 * No login required. Returns only the ~10 most recent items.
 * Best used for daily sync after a full Frodo API export.
 *
 * Usage:
 *   DOUBAN_USER=<user_id> node douban-rss-sync.mjs
 *
 * Environment:
 *   DOUBAN_USER (required): Douban user ID
 *   DOUBAN_OUTPUT_DIR (optional): Override output directory
 */

import https from 'node:https';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

let DOUBAN_USER = process.env.DOUBAN_USER;
if (!DOUBAN_USER) { console.error('Error: DOUBAN_USER env var is required'); process.exit(1); }
// Extract ID from full URL if provided (e.g., https://www.douban.com/people/foo/)
const urlMatch = DOUBAN_USER.match(/douban\.com\/people\/([A-Za-z0-9._-]+)/);
if (urlMatch) DOUBAN_USER = urlMatch[1];
if (!/^[A-Za-z0-9._-]+$/.test(DOUBAN_USER)) { console.error('Error: DOUBAN_USER contains invalid characters'); process.exit(1); }

function getDownloadDir() {
  if (process.platform === 'win32') {
    return path.join(process.env.USERPROFILE || os.homedir(), 'Downloads');
  }
  return path.join(os.homedir(), 'Downloads');
}

const BASE_DIR = process.env.DOUBAN_OUTPUT_DIR || path.join(getDownloadDir(), 'douban-sync');
const DOUBAN_OUTPUT_DIR = path.join(BASE_DIR, DOUBAN_USER);
const STATE_FILE = path.join(DOUBAN_OUTPUT_DIR, '.douban-rss-state.json');
const RSS_URL = `https://www.douban.com/feed/people/${DOUBAN_USER}/interests`;

const CATEGORY_MAP = [
  { pattern: /^读过/, file: '书.csv', status: '读过' },
  { pattern: /^(?:在读|最近在读)/, file: '书.csv', status: '在读' },
  { pattern: /^想读/, file: '书.csv', status: '想读' },
  { pattern: /^看过/, file: '影视.csv', status: '看过' },
  { pattern: /^(?:在看|最近在看)/, file: '影视.csv', status: '在看' },
  { pattern: /^想看/, file: '影视.csv', status: '想看' },
  { pattern: /^听过/, file: '音乐.csv', status: '听过' },
  { pattern: /^(?:在听|最近在听)/, file: '音乐.csv', status: '在听' },
  { pattern: /^想听/, file: '音乐.csv', status: '想听' },
  { pattern: /^玩过/, file: '游戏.csv', status: '玩过' },
  { pattern: /^(?:在玩|最近在玩)/, file: '游戏.csv', status: '在玩' },
  { pattern: /^想玩/, file: '游戏.csv', status: '想玩' },
];

const CSV_HEADER = '\ufefftitle,url,date,rating,status,comment\n';
const RATING_MAP = { '力荐': '★★★★★', '推荐': '★★★★', '还行': '★★★', '较差': '★★', '很差': '★' };

function httpGet(url, redirects = 0) {
  if (redirects > 5) return Promise.reject(new Error('Too many redirects'));
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 15000 }, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return httpGet(new URL(res.headers.location, url).href, redirects + 1).then(resolve, reject);
      }
      if (res.statusCode >= 400) return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });
  });
}

function csvEscape(str) {
  if (!str) return '';
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

function parseItems(xml) {
  const items = [];
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  let match;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block = match[1];
    const get = tag => {
      const m = block.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?<\\/${tag}>`));
      return m ? m[1].trim() : '';
    };
    const title = get('title');
    const link = get('link');
    const guid = get('guid');
    const pubDate = get('pubDate');
    const desc = get('description');
    const ratingMatch = desc.match(/推荐:\s*(力荐|推荐|还行|较差|很差)/);
    const rating = ratingMatch ? RATING_MAP[ratingMatch[1]] || '' : '';
    const commentMatch = desc.match(/短评:\s*([^<]+)/);
    const comment = commentMatch ? commentMatch[1].trim() : '';
    items.push({ title, link, guid, pubDate, rating, comment });
  }
  return items;
}

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); }
  catch { return { lastSyncGuids: [] }; }
}

function saveState(state) { fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2)); }

function extractName(title) {
  for (const { pattern } of CATEGORY_MAP) {
    if (pattern.test(title)) return title.replace(pattern, '');
  }
  return title;
}

function isAlreadyInFile(filePath, link) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    // Exact URL match as CSV field — avoid false positives from substring matches
    // (e.g., /subject/1234/ matching /subject/12345/)
    return content.includes(',' + link + ',') ||
           content.includes(',' + link + '\n') ||
           content.includes(',' + link + '\r');
  } catch { return false; }
}

function formatDate(pubDateStr) {
  try {
    const direct = pubDateStr.match(/(\d{4}-\d{2}-\d{2})/);
    if (direct) return direct[1];
    const d = new Date(pubDateStr);
    const cst = new Date(d.getTime() + 8 * 3600000);
    return cst.toISOString().split('T')[0];
  } catch { return ''; }
}

function ensureCsvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, CSV_HEADER);
  }
}

function appendToCsv(filePath, entry, status) {
  ensureCsvFile(filePath);
  const name = extractName(entry.title);
  const date = formatDate(entry.pubDate);
  const line = [csvEscape(name), csvEscape(entry.link), csvEscape(date),
    csvEscape(entry.rating), csvEscape(status), csvEscape(entry.comment)].join(',') + '\n';
  fs.appendFileSync(filePath, line);
}

async function main() {
  console.log(`Douban RSS Sync for user: ${DOUBAN_USER}`);
  console.log(`Output: ${DOUBAN_OUTPUT_DIR}\n`);
  console.log('Fetching RSS feed...');
  const xml = await httpGet(RSS_URL);
  const items = parseItems(xml);
  console.log(`Found ${items.length} items in feed`);

  const state = loadState();
  const knownGuids = new Set(state.lastSyncGuids || []);
  let newCount = 0;

  for (const item of items) {
    if (knownGuids.has(item.guid)) continue;
    const cat = CATEGORY_MAP.find(c => c.pattern.test(item.title));
    if (!cat) { console.log(`  Skip (unknown category): ${item.title}`); continue; }
    const filePath = path.join(DOUBAN_OUTPUT_DIR, cat.file);
    if (isAlreadyInFile(filePath, item.link)) { console.log(`  Skip (exists): ${item.title}`); continue; }
    console.log(`  + ${item.title} → ${cat.file}`);
    appendToCsv(filePath, item, cat.status);
    newCount++;
  }

  state.lastSyncGuids = items.map(i => i.guid);
  state.lastSync = new Date().toISOString();
  saveState(state);
  console.log(`\nDone. ${newCount} new entries added.`);
}

main().catch(err => { console.error('Error:', err.message); process.exit(1); });
