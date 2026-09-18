import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const VERSION = 1;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const now = () => new Date().toISOString();
export const digest = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function fail(message) { throw new Error(message); }
export function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
export function atomicJson(file, value) {
  fs.mkdirSync(path.dirname(file), {recursive: true, mode: 0o700});
  const temp = `${file}.${crypto.randomUUID()}.tmp`;
  const fd = fs.openSync(temp, 'wx', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fs.fsyncSync(fd); }
  finally { fs.closeSync(fd); }
  fs.renameSync(temp, file);
}
export function relayUrl(raw) {
  const u = new URL(raw);
  if (u.username || u.password || u.search || u.hash) fail('Relay URL must not contain credentials, a query, or a fragment');
  if (u.protocol !== 'https:' && !(u.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname))) {
    fail('Use HTTPS for a remote relay; HTTP is allowed only on loopback (including an SSH tunnel)');
  }
  return u.href.replace(/\/$/, '');
}
export function decodeInvite(value) {
  const prefix = 'peer-message:v1:';
  if (!value.startsWith(prefix) || value.length > 8192) fail('Invalid peer-message invitation');
  const d = JSON.parse(Buffer.from(value.slice(prefix.length), 'base64url').toString('utf8'));
  if (d.version !== VERSION || typeof d.code !== 'string' || typeof d.peer !== 'string' || typeof d.name !== 'string') fail('Incomplete invitation');
  if (!Number.isFinite(d.expires_at) || d.expires_at <= Date.now()) fail('Invitation expired; ask its owner for a new invitation');
  d.relay = relayUrl(d.relay);
  return d;
}
export function encodeInvite(value) { return 'peer-message:v1:' + Buffer.from(JSON.stringify(value)).toString('base64url'); }
export function shareFiles(names = []) {
  if(names.length>20)fail('Share at most 20 explicit documents per endpoint');
  const seen = new Set();
  return names.map(raw => {
    const absolute = path.resolve(raw);
    const stat = fs.lstatSync(absolute);
    if (!stat.isFile() || stat.isSymbolicLink()) fail('Share only explicit regular files, not directories or symlinks');
    const name = path.basename(absolute);
    if (seen.has(name)) fail('Shared files must have distinct names');
    seen.add(name);
    if (!/\.(md|txt|json|csv|yaml|yml)$/i.test(name)) fail('Share text documents only');
    if (stat.size > 128 * 1024) fail(`Shared file is too large: ${name}`);
    return {path: absolute, realpath: fs.realpathSync(absolute), name};
  });
}
export function snapshotDocuments(files) {
  let total = 0;
  return files.map(file => {
    const before=fs.lstatSync(file.path);
    if(!before.isFile() || before.isSymbolicLink())fail('Shared path is no longer a regular document');
    const canonical=fs.realpathSync(file.path);
    if(canonical!==(file.realpath || path.resolve(file.path)))fail('Shared document path now resolves elsewhere');
    const nofollow=fs.constants.O_NOFOLLOW;
    if(typeof nofollow!=='number' && (!Number.isSafeInteger(before.ino)||before.ino===0))fail('This filesystem cannot enforce the shared-document identity check');
    const fd = fs.openSync(file.path, fs.constants.O_RDONLY | (nofollow ?? 0));
    let content;
    try {
      const st = fs.fstatSync(fd);
      if (!st.isFile() || st.size > 128 * 1024) fail('Shared document no longer meets the file policy');
      if(st.dev!==before.dev || st.ino!==before.ino)fail('Shared document changed during open');
      content = fs.readFileSync(fd, 'utf8');
      const after=fs.lstatSync(file.path);
      if(after.isSymbolicLink() || after.dev!==st.dev || after.ino!==st.ino || fs.realpathSync(file.path)!==canonical)fail('Shared document changed while reading');
    } finally { fs.closeSync(fd); }
    total += Buffer.byteLength(content);
    if (total > 256 * 1024) fail('Approved document set exceeds 256 KiB');
    return {name: file.name, content, sha256: crypto.createHash('sha256').update(content).digest('hex')};
  });
}
export function validMessage(d) {
  return d && d.protocol === 'peer-message' && d.version === VERSION && UUID.test(d.id) &&
    ['question', 'answer'].includes(d.type) &&
    (d.type === 'question' ? typeof d.question === 'string' && d.question.length > 0 && d.question.length <= 12000 :
      UUID.test(d.in_reply_to) && typeof d.answer === 'string' && d.answer.trim().length>0 && d.answer.length <= 50000 &&
      ['answered', 'needs_owner', 'failed'].includes(d.status) && validAnswerEvidence(d));
}
export function validAnswerEvidence(d) {
  const filename=s=>typeof s==='string' && s.length>0 && s.length<=255 && !/[\\/]/.test(s) && s!=='.' && s!=='..';
  if(!Array.isArray(d.citations)||d.citations.length>20||!Array.isArray(d.evidence)||d.evidence.length>20)return false;
  if(d.evidence.some(e=>!e || !filename(e.file)||typeof e.sha256!=='string'||!/^[0-9a-f]{64}$/.test(e.sha256) || !Number.isSafeInteger(e.lines)||e.lines<1||e.lines>131073))return false;
  const files=new Map(d.evidence.map(e=>[e.file,e.lines]));
  if(files.size!==d.evidence.length)return false;
  if(d.citations.some(c=>!c || !filename(c.file)||!files.has(c.file)||!Number.isSafeInteger(c.line)||c.line<1||c.line>files.get(c.file)))return false;
  return d.status!=='answered' || d.citations.length>0;
}
