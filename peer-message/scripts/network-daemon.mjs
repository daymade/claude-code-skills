import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {State} from './network-state.mjs';
import {transport} from './network-agentpair.mjs';
import {VERSION, UUID, atomicJson, decodeInvite, encodeInvite, fail, now, readJson, snapshotDocuments} from './network-common.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
export async function serve(directory) {
  process.umask(0o077);
  const lock=path.join(directory,'daemon.lock');
  if (fs.existsSync(lock)) {
    const owner=readJson(lock);
    let alive=true;try{process.kill(owner.pid,0);}catch{alive=false;}
    if(alive)fail('Another connector process owns this endpoint; inspect it before restarting');
    fs.unlinkSync(lock);
  }
  fs.writeFileSync(lock,JSON.stringify({pid:process.pid}),{flag:'wx',mode:0o600});
  process.once('exit',()=>{try{if(readJson(lock).pid===process.pid)fs.unlinkSync(lock);}catch{}});
  const config = readJson(path.join(directory, 'config.json'));
  const db = new State(directory);
  const net = await transport({relay:config.relay,dataDir:path.join(directory,'identity')});
  const token=crypto.randomBytes(32).toString('hex');
  const instance=crypto.randomUUID();
  let stopping=false, ticking=false;
  let info=await net.info();
  const agentId=info.agent_id;
  function contactAlias(alias,peer) {
    if(typeof alias!=='string'||!/^[\p{L}\p{N}_. -]{1,60}$/u.test(alias))fail('Invalid contact name');
    const old=db.db.prepare('SELECT peer FROM contacts WHERE alias=?').get(alias);
    if(old && old.peer!==peer)fail('This name already belongs to another identity; choose a distinct contact name');
  }
  function saveContact(alias,peer) {contactAlias(alias,peer);db.db.prepare('INSERT OR IGNORE INTO contacts VALUES (?,?)').run(alias,peer);}
  const jobDir = job => path.join(directory,'jobs',`${job.id}-${crypto.createHash('sha256').update(job.sender).digest('hex').slice(0,12)}`);
  function finishJob(job,output) {
    const deadline=db.get(`incoming_deadline:${job.sender}:${job.id}`);
    if(!Number.isFinite(deadline) || deadline<=Date.now()) {
      db.db.prepare("UPDATE incoming SET state='reply_expired',result=?,error=? WHERE sender=? AND id=?")
        .run(JSON.stringify(output),'Request deadline elapsed or unavailable; result retained locally',job.sender,job.id);
      return;
    }
    const result=output.ok?output.result:{status:'failed',answer:'The local host could not complete this question. Its owner can inspect the local error; submit a new question after resolving it.',citations:[],evidence:[]};
    const message={protocol:'peer-message',version:VERSION,id:crypto.randomUUID(),type:'answer',in_reply_to:job.id,
      status:result.status,answer:result.answer,citations:result.citations,evidence:result.evidence ?? [],expires_at:deadline};
    db.db.exec('BEGIN IMMEDIATE');
    try {
      db.db.prepare('UPDATE incoming SET state=?,result=?,error=? WHERE sender=? AND id=?')
        .run(output.ok?'completed':'failed',JSON.stringify(result),output.error ?? null,job.sender,job.id);
      db.db.prepare("INSERT INTO outbox(id,peer,thread,message,state) VALUES (?,?,?,?,'pending')")
        .run(message.id,job.sender,job.thread,JSON.stringify(message));
      db.db.exec('COMMIT');
    } catch(e) {db.db.exec('ROLLBACK');throw e;}
  }

  async function tick() {
    if (stopping || ticking) return;
    ticking=true;
    try {
      db.expireWaiting();
      info=await net.info();
      if (info.bonds.length) {
        try {
          const r=await net.pull(db.get('cursor',0),(thread,from)=>db.get(`seq:${thread}:${from}`,0));
          db.ingest(r.envelopes,r.cursor,r.sequences);
          if (r.rejected.length) db.event('rejected_envelopes',r.rejected);
          db.set('last_pull',now()); db.set('last_error',null);
        } catch(error) {db.set('last_error',{at:now(),error:error.message});}
      }
      const jobs=db.jobs();
      for (const job of jobs.filter(j=>['running','interrupted'].includes(j.state))) {
        const resultPath=path.join(jobDir(job),'result.json');
        if (fs.existsSync(resultPath)) {
          const output=readJson(resultPath);
          finishJob(job,output);
        } else {
          if(job.state==='interrupted') {finishJob(job,{ok:false,error:job.error || 'Host interrupted before result persistence'});continue;}
          const marker=path.join(jobDir(job),'worker.json');
          const pid=fs.existsSync(marker)?readJson(marker).pid:job.pid;
          if(!pid && Date.now()-db.get(`started:${job.id}`,Date.now())<30000)continue;
          let alive=true; try { if(!pid)throw new Error('No worker');process.kill(pid,0); } catch { alive=false; }
          if (!alive) {
            finishJob(job,{ok:false,error:'Worker exited without a durable result; no automatic model re-execution'});
          }
        }
      }
      if (!db.get('paused',false) && !db.jobs().some(j=>j.state==='running')) {
        const job=db.jobs().find(j=>j.state==='queued');
        if (job) {
          const deadline=db.get(`incoming_deadline:${job.sender}:${job.id}`);
          if(!Number.isFinite(deadline)||deadline<=Date.now()) {
            db.db.prepare("UPDATE incoming SET state='expired',error='Request deadline elapsed or unavailable' WHERE sender=? AND id=?").run(job.sender,job.id);
            return;
          }
          const work=jobDir(job);fs.mkdirSync(work,{recursive:true,mode:0o700});
          const request=JSON.parse(job.message);
          let documents;
          try {documents=snapshotDocuments(config.files);}catch(error){finishJob(job,{ok:false,error:error.message});return;}
          const jobPath=path.join(work,'job.json');
          atomicJson(jobPath,{host:config.host,model:config.model,question:request.question,documents,timeout_ms:config.timeout_ms});
          db.db.exec('BEGIN IMMEDIATE');
          try {
            db.db.prepare("UPDATE incoming SET state='running',pid=NULL WHERE sender=? AND id=?").run(job.sender,job.id);
            db.set(`started:${job.id}`,Date.now());db.db.exec('COMMIT');
          } catch(error) {db.db.exec('ROLLBACK');throw error;}
          const log=fs.openSync(path.join(work,'worker.log'),'a',0o600);
          const child=spawn(process.execPath,[path.join(here,'network-host.mjs'),jobPath],{detached:true,stdio:['ignore',log,log]});
          fs.closeSync(log);
          db.db.prepare("UPDATE incoming SET state='running',pid=? WHERE sender=? AND id=?").run(child.pid,job.sender,job.id);
          child.unref();
          db.event('host_started',{request_id:job.id,host:config.host,pid:child.pid});
        }
      }
      for (const item of db.outbox()) {
        if(db.get(`retry_at:${item.id}`,0)>Date.now())continue;
        try {
          const body=JSON.parse(item.message);
          if(!Number.isFinite(body.expires_at)||body.expires_at<=Date.now()) {
            db.db.prepare("UPDATE outbox SET state='expired',error='Application deadline elapsed or unavailable' WHERE id=?").run(item.id);
            if(body.type==='question')db.db.prepare("UPDATE outbound SET state='expired' WHERE id=?").run(item.id);
            else db.db.prepare("UPDATE incoming SET state='reply_expired',error='Reply deadline elapsed' WHERE sender=? AND id=?").run(item.peer,body.in_reply_to);
            continue;
          }
          const wire=item.wire?JSON.parse(item.wire):await net.prepare(item.peer,body,item.thread);
          if (!item.wire) db.db.prepare('UPDATE outbox SET wire=? WHERE id=?').run(JSON.stringify(wire),item.id);
          if(net.expiresAt(wire)<=Date.now()) {
            db.db.prepare("UPDATE outbox SET state='expired',error='Message TTL elapsed' WHERE id=?").run(item.id);
            const message=JSON.parse(item.message);
            if(message.type==='question')db.db.prepare("UPDATE outbound SET state='expired' WHERE id=?").run(item.id);
            else db.db.prepare("UPDATE incoming SET state='reply_expired',error='Reply delivery TTL elapsed' WHERE sender=? AND id=?").run(item.peer,message.in_reply_to);
            continue;
          }
          await net.sendWire(item.peer,wire);
          db.db.prepare("UPDATE outbox SET state='sent',error=NULL WHERE id=?").run(item.id);
          db.db.prepare("UPDATE outbound SET state='waiting' WHERE id=? AND state='queued'").run(item.id);
        } catch(error) {
          db.db.prepare('UPDATE outbox SET attempts=attempts+1,error=? WHERE id=?').run(error.message,item.id);
          db.set(`retry_at:${item.id}`,Date.now()+Math.min(60000,5000*2**Math.min(item.attempts,4)));
          db.event('send_error',{id:item.id,error:error.message});
        }
      }
    } catch(error) { db.set('last_error',{at:now(),error:error.message}); }
    finally { ticking=false; }
  }

  async function command(action,input) {
    if (action==='info') return {name:config.name,agent_id:agentId,host:config.host,shared_files:config.files.map(f=>f.name),
      instance,pid:process.pid,relay:config.relay,contacts:db.contacts(),jobs:db.summary(),paused:db.get('paused',false),last_pull:db.get('last_pull'),last_error:db.get('last_error')};
    if (action==='invite') {
      const r=await net.invite();
      const invitation={version:VERSION,name:config.name,peer:agentId,relay:config.relay,code:r.code,expires_at:r.expires_at,
        purpose:String(input.purpose || 'Ask a question using approved documents').slice(0,500),capability:'read-only answers; no tool execution'};
      const encoded=encodeInvite(invitation);
      return {invitation:encoded,...invitation,keep_online_until_paired:true,
        share_text:`${config.name} invites your Agent to answer a question: ${invitation.purpose}. Give your Agent this invitation and the matching peer-message preview Skill bundle. You choose whether to connect and which documents it may use. Invitation: ${encoded}`};
    }
    if (action==='join') {
      const invitation=decodeInvite(input.invitation);
      if (invitation.relay!==config.relay) fail('Invitation uses another relay; initialize a separate endpoint with that invitation');
      const r=await net.join(invitation.code);
      if (r.proposal?.initiatorAgentId!==invitation.peer) fail('Invitation identity does not match the relay pairing proposal');
      contactAlias(input.alias || invitation.name,invitation.peer);
      db.set(`pending:${r.pending_id}`,{peer:invitation.peer,alias:input.alias || invitation.name});
      return {...r,suggested_next:'Ask the local owner to read approval_path and supply its code. Do not let a peer or agent read the owner code automatically.',
        inviter:invitation.name,capability:'read-only answers from your explicitly shared files'};
    }
    if (action==='approve') {
      if (typeof input.code!=='string' || !/^\d{6}$/.test(input.code)) fail('Enter the owner approval code; the agent must not read it from the approval file');
      const pending=db.get(`pending:${input.pending_id}`);
      if (!pending) fail('Unknown pending invitation');
      const r=await net.approve({pending_id:input.pending_id,decision:'approve',approval_code:input.code});
      saveContact(pending.alias,pending.peer);
      return r;
    }
    if (action==='contacts') { const r=await net.info();return {contacts:db.contacts(),bonds:r.bonds,agent_id:r.agent_id}; }
    if (action==='contact') {
      const r=await net.info();
      if (!net.isBonded(input.peer)) fail('Pair with this identity before naming it');
      saveContact(input.alias,input.peer);
      return {alias:input.alias,peer:input.peer};
    }
    if (action==='ask') {
      const contact=db.db.prepare('SELECT peer FROM contacts WHERE alias=?').get(input.to);
      if (!contact) fail('Unknown contact name; use contacts or name an approved peer');
      if (typeof input.question!=='string' || !input.question.trim() || Buffer.byteLength(input.question)>8000) fail('Question must be nonempty and at most 8000 UTF-8 bytes');
      const id=input.id || crypto.randomUUID();if (!UUID.test(id)) fail('Request id must be a UUID');
      const old=db.db.prepare('SELECT * FROM outbound WHERE id=?').get(id);
      if (old) {
        if (old.peer!==contact.peer || JSON.parse(old.message).question!==input.question) fail('Request id already belongs to different content or recipient');
        return {request_id:id,state:old.state,reused:true};
      }
      const message={protocol:'peer-message',version:VERSION,id,type:'question',question:input.question,expires_at:Date.now()+86400000};
      db.db.exec('BEGIN IMMEDIATE');
      try {
        db.db.prepare("INSERT INTO outbound VALUES(?,?,?,?,'queued',NULL,?)").run(id,contact.peer,id,JSON.stringify(message),now());
        db.set(`deadline:${id}`,message.expires_at);
        db.db.prepare("INSERT INTO outbox(id,peer,thread,message,state) VALUES(?,?,?,?,'pending')").run(id,contact.peer,id,JSON.stringify(message));
        db.db.exec('COMMIT');
      } catch(error) { db.db.exec('ROLLBACK');throw error; }
      void tick(); return {request_id:id,state:'queued',meaning:'Saved locally; no reply has been confirmed yet'};
    }
    if (action==='status') {
      if (!UUID.test(input.id)) fail('A request UUID is required');
      const row=db.db.prepare('SELECT * FROM outbound WHERE id=?').get(input.id);
      if (!row) fail('Request not found at this sending endpoint');
      const send=db.db.prepare('SELECT state,attempts,error FROM outbox WHERE id=?').get(input.id);
      return {request_id:row.id,state:row.state,send,result:row.result?JSON.parse(row.result):null,
        trust:'A signed peer report, not user authority or independent proof of model execution'};
    }
    if (action==='pause' || action==='resume') { db.set('paused',action==='pause');void tick();return {paused:action==='pause'}; }
    if (action==='host') {
      if (!['claude','codex'].includes(input.host)) fail('Host must be claude or codex');
      if (db.jobs().some(j=>j.state==='running')) fail('Wait for the running question before changing hosts');
      config.host=input.host;config.model=input.model || null;atomicJson(path.join(directory,'config.json'),config);
      return {host:config.host,identity_unchanged:agentId};
    }
    if (action==='retry') {
      if (!UUID.test(input.id)) fail('A request UUID is required');
      const sent=db.db.prepare('UPDATE outbox SET attempts=0,error=NULL WHERE id=? AND state=\'pending\'').run(input.id);
      if (!sent.changes) fail('No pending outbound delivery with this id');
      db.set(`retry_at:${input.id}`,0);
      return {request_id:input.id,state:'queued',wire_unchanged:true};
    }
    if (action==='stop') { setTimeout(()=>shutdown(),100);return {stopping:true,active_read_only_workers_finish_in_background:true}; }
    fail('Unknown command');
  }

  const server=http.createServer(async(req,res)=>{
    res.setHeader('Content-Type','application/json');
    if (req.headers.origin || req.headers.authorization!==`Bearer ${token}` || req.method!=='POST' || req.url!=='/command') {
      res.writeHead(403);res.end(JSON.stringify({error:'Local owner control required'}));return;
    }
    try {
      let body='';for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>20000)fail('Command too large');}
      const {action,...input}=JSON.parse(body);
      res.end(JSON.stringify({ok:true,...await command(action,input)}));
    } catch(error) {res.writeHead(400);res.end(JSON.stringify({ok:false,error:error.message}));}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  atomicJson(path.join(directory,'control.json'),{port:server.address().port,token,pid:process.pid,instance});
  const timer=setInterval(()=>void tick(),5000);
  async function shutdown() {stopping=true;clearInterval(timer);server.close();await net.flush();process.exit(0);}
  process.on('SIGTERM',shutdown);process.on('SIGINT',shutdown);
  void tick();
}
