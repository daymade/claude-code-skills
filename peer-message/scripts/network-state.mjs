import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {digest, now, validMessage} from './network-common.mjs';

export class State {
  constructor(directory) {
    fs.mkdirSync(directory, {recursive: true, mode: 0o700});
    this.db = new DatabaseSync(path.join(directory, 'network.sqlite'));
    fs.chmodSync(path.join(directory, 'network.sqlite'), 0o600);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS contacts (alias TEXT PRIMARY KEY, peer TEXT UNIQUE NOT NULL);
      CREATE TABLE IF NOT EXISTS outbound (id TEXT PRIMARY KEY, peer TEXT NOT NULL, thread TEXT NOT NULL, message TEXT NOT NULL, state TEXT NOT NULL, result TEXT, created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS incoming (sender TEXT NOT NULL,id TEXT NOT NULL,thread TEXT NOT NULL,message TEXT NOT NULL,hash TEXT NOT NULL,state TEXT NOT NULL,pid INTEGER,result TEXT,error TEXT,created TEXT NOT NULL,PRIMARY KEY(sender,id));
      CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY,peer TEXT NOT NULL,thread TEXT NOT NULL,message TEXT NOT NULL,wire TEXT,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,error TEXT);
      CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY,at TEXT NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);`);
  }
  get(key, fallback=null) { const row=this.db.prepare('SELECT value FROM meta WHERE key=?').get(key); return row?JSON.parse(row.value):fallback; }
  set(key,value) { this.db.prepare('INSERT OR REPLACE INTO meta VALUES (?,?)').run(key,JSON.stringify(value)); }
  event(kind,detail) { this.db.prepare('INSERT INTO events(at,kind,detail) VALUES (?,?,?)').run(now(),kind,JSON.stringify(detail)); }
  ingest(envelopes,cursor,sequences=[]) {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      for (const env of envelopes) {
        if (env.type !== 'core.msg' || env.signature_valid !== true) continue;
        const payload=env.payload?.content ?? env.payload;
        let d;
        try { d=JSON.parse(payload.body); } catch { this.event('ignored_message',{envelope:env.id,reason:'not_peer_message'});continue; }
        if (!validMessage(d)) { this.event('ignored_message',{envelope:env.id,reason:'invalid_schema'});continue; }
        if (d.type==='answer') {
          const out=this.db.prepare('SELECT * FROM outbound WHERE id=?').get(d.in_reply_to);
          if (!out || out.peer!==env.from || out.thread!==env.thread) { this.event('ignored_answer',{id:d.id,reason:'unmatched_request_or_sender'});continue; }
          if (out.state==='conflict') { this.event('answer_after_conflict',{request_id:out.id});continue; }
          if (out.state==='expired') { this.event('late_answer',{request_id:out.id});continue; }
          if (out.result && digest(JSON.parse(out.result))!==digest(d)) {
            this.db.prepare("UPDATE outbound SET state='conflict' WHERE id=?").run(out.id);
            this.event('answer_conflict',{request_id:out.id});continue;
          }
          this.db.prepare('UPDATE outbound SET state=?,result=? WHERE id=?').run(d.status,JSON.stringify(d),out.id);
          continue;
        }
        const existing=this.db.prepare('SELECT * FROM incoming WHERE sender=? AND id=?').get(env.from,d.id);
        if (existing) {
          if (existing.hash!==digest(d)) this.event('request_conflict',{sender:env.from,id:d.id});
          else this.event('duplicate_request',{sender:env.from,id:d.id});
          continue;
        }
        if(!Number.isFinite(env.ttl)) {this.event('ignored_message',{id:d.id,reason:'missing_deadline'});continue;}
        const deadline=Number.isFinite(d.expires_at)?Math.min(env.ttl*1000,d.expires_at):env.ttl*1000;
        this.db.prepare('INSERT INTO incoming(sender,id,thread,message,hash,state,created) VALUES(?,?,?,?,?,?,?)')
          .run(env.from,d.id,env.thread,JSON.stringify(d),digest(d),'queued',now());
        this.set(`incoming_deadline:${env.from}:${d.id}`,deadline);
      }
      for (const [key,seq] of sequences) this.set(`seq:${key}`,seq);
      this.set('cursor',cursor);
      this.db.exec('COMMIT');
    } catch(error) { this.db.exec('ROLLBACK');throw error; }
  }
  contacts() { return this.db.prepare('SELECT * FROM contacts ORDER BY alias').all(); }
  jobs() { return this.db.prepare("SELECT * FROM incoming WHERE state IN ('queued','running','interrupted') ORDER BY created").all(); }
  outbox() { return this.db.prepare("SELECT * FROM outbox WHERE state='pending'").all(); }
  summary() { return this.db.prepare('SELECT state,COUNT(*) AS count FROM incoming GROUP BY state').all(); }
  expireWaiting(at=Date.now()) {
    for(const row of this.db.prepare("SELECT id,created FROM outbound WHERE state IN ('queued','waiting')").all()) {
      const deadline=this.get(`deadline:${row.id}`,Date.parse(row.created)+86400000);
      if(at>=deadline) {
        this.db.prepare("UPDATE outbound SET state='expired' WHERE id=?").run(row.id);
        this.db.prepare("UPDATE outbox SET state='expired',error='Request deadline elapsed' WHERE id=? AND state='pending'").run(row.id);
        this.event('request_expired',{request_id:row.id});
      }
    }
  }
}
