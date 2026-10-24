#!/usr/bin/env node
'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const file=path.join(__dirname,'../static/app.js');
const ref=process.env.CLIENT_INTEGRITY_TEST_REV;
const input=ref?execFileSync('git',['-C',__dirname,'show',`${ref}:daymade-audio/asr-transcribe-to-text/scripts/review-workbench/static/app.js`],{encoding:'utf8'}):fs.readFileSync(file,'utf8');
const source=input.replace(/bindEvents\(\);loadProject\(\);\s*$/,'');
assert.notEqual(source,input);
const fp='synthetic-project-fingerprint';
function response(value,status=200){return {ok:status<400,status,json:async()=>structuredClone(value)};}
function app(fetch=async()=>{throw new Error('Unexpected request');}){
  const nodes=new Map(),timers=new Map(),windowEvents=new Map();let sequence=0,timerId=0;
  const node=id=>({id,innerHTML:'',textContent:'',value:'',hidden:false,dataset:{},style:{},scrollTop:0,clientHeight:600,scrollHeight:100,
    classList:{toggle(){},add(){},remove(){}},addEventListener(){},setAttribute(){},querySelector(){return null;},querySelectorAll(){return [];},closest(){return this;},focus(){},close(){}});
  const document={activeElement:null,getElementById(id){if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id);},querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context=vm.createContext({document,fetch,window:{crypto:{randomUUID:()=>`synthetic-${++sequence}`},addEventListener(type,fn){windowEvents.set(type,fn);}},Map,Set,Date,Math,Number,String,Promise,console,
    setTimeout(fn,ms){const id=++timerId;timers.set(id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);},requestAnimationFrame(){},ResizeObserver:class{observe(){}},localStorage:{getItem(){return null;},setItem(){}}});
  const run=code=>vm.runInContext(code,context,{filename:file});run(source);
  run(`view.project={project_id:'synthetic',fingerprint:'${fp}',sources:[{id:'main',label:'Synthetic recorder',duration:200,clock:{offset:0,scale:1}}],people:[],items:[{id:'turn',source_id:'main',kind:'transcript',start:10,end:12,text:'Original synthetic text',identity_status:'unknown'}]};view.selectedId='turn';view.sourceId='main';view.state={fingerprint:'${fp}',revision:0,decisions:{}};drawTracks=()=>{};drawOverview=()=>{};bindEvents();`);
  return {run,nodes,timers,unload(){const e={prevented:false,preventDefault(){this.prevented=true;}};windowEvents.get('beforeunload')(e);return e;},expire(ms){for(const [id,timer]of [...timers])if(timer.ms===ms){timers.delete(id);timer.fn();}}};
}
async function settle(){for(let i=0;i<30;i++)await Promise.resolve();}
function deferredServer(){
  const requests=[];let state={fingerprint:fp,revision:0,decisions:{}};
  const fetch=(url,options)=>new Promise(resolve=>requests.push({url,body:JSON.parse(options.body),commit(){state={...state,revision:state.revision+1,decisions:{...state.decisions,turn:{...state.decisions.turn,...this.body.changes}}};resolve(response(state));}}));
  return {requests,fetch};
}
for(const finalText of ['A','C'])test(`older A acknowledgement preserves the latest ${finalText} edit and every queued/timer save`,async()=>{
  const server=deferredServer(),a=app(server.fetch);
  const first=a.run("saveDecision('turn',{text:'A'},{quiet:true})");await settle();
  const second=a.run("saveDecision('turn',{text:'B'},{quiet:true})");
  a.run(`scheduleDraft('turn','text','${finalText}')`);
  assert.equal(a.run('unsavedCount()'),1);
  server.requests[0].commit();await first;await settle();
  assert.equal(a.run("view.drafts.get('turn')?.text"),finalText,'A value match must not acknowledge a later editing generation');
  assert.equal(server.requests.length,2,'B is still a real queued write');
  assert.equal(a.unload().prevented,true);
  assert.match(a.nodes.get('saveStatus').className,/saving/);
  server.requests[1].commit();await second;
  assert.equal(a.run('unsavedCount()'),1,'The debounce timer remains dirty after queued writes settle');
  assert.equal(a.run("effectiveItem(currentItem()).text"),finalText);
  a.expire(700);await settle();assert.equal(server.requests.length,3);
  assert.equal(server.requests[2].body.changes.text,finalText);
  server.requests[2].commit();await a.run('view.saveChain');
  assert.equal(a.run('unsavedCount()'),0);assert.equal(a.unload().prevented,false);
  assert.equal(a.run("view.state.decisions.turn.text"),finalText);
  assert.doesNotMatch(a.nodes.get('saveStatus').className,/saving|error/);
});
test('all-queued ABA retains the latest A through both older receipts',async()=>{
  const server=deferredServer(),a=app(server.fetch);
  const saves=['A','B','A'].map(value=>a.run(`saveDecision('turn',{text:'${value}'},{quiet:true})`));
  await settle();
  for(let index=0;index<3;index++){
    if(index<2){assert.equal(a.run("view.drafts.get('turn').text"),'A');assert.equal(a.unload().prevented,true);}
    server.requests[index].commit();await saves[index];await settle();
  }
  assert.equal(a.run('unsavedCount()'),0);assert.equal(a.run('view.state.decisions.turn.text'),'A');
});
test('independent field ownership acknowledges text while preserving a newer note',async()=>{
  const server=deferredServer(),a=app(server.fetch);
  const save=a.run("saveDecision('turn',{text:'Corrected text',note:'Old note'},{quiet:true})");await settle();
  a.run("scheduleDraft('turn','note','New note')");server.requests[0].commit();await save;
  assert.equal(a.run("view.drafts.get('turn').text"),undefined);
  assert.equal(a.run("view.drafts.get('turn').note"),'New note');
});
test('dirty truth includes a queue or timer independently of the draft map',async()=>{
  const server=deferredServer(),a=app(server.fetch);
  const save=a.run("saveDecision('turn',{text:'Pending'},{quiet:true})");await settle();a.run('view.drafts.clear()');
  assert.ok(a.run('unsavedCount()'));assert.equal(a.unload().prevented,true);
  server.requests[0].commit();await save;
  a.run("scheduleDraft('turn','note','Pending note');view.drafts.clear()");
  assert.ok(a.run('unsavedCount()'));assert.equal(a.unload().prevented,true);
});
test('foreign project conflicts keep drafts and never rebind an explicit retry',async()=>{
  const posts=[];let foreign=true;
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response({fingerprint:foreign?'foreign-project':fp,revision:4,decisions:{turn:{text:'Other persisted text'}}});
    const request=JSON.parse(options.body);posts.push(request);
    if(foreign)return response({error:{code:'revision_conflict',message:'Synthetic conflict'}},409);
    return response({fingerprint:fp,revision:5,decisions:{turn:request.changes}});
  });
  assert.equal(await a.run("saveDecision('turn',{text:'My pending text'})"),false);
  assert.equal(a.run('view.state.revision'),0,'Foreign state must never be adopted');
  assert.equal(a.run('view.state.fingerprint'),fp);
  await a.run('retryUnsaved()');assert.equal(posts.length,1,'Retry while another project is served cannot write');
  assert.equal(a.run("view.drafts.get('turn').text"),'My pending text');assert.equal(a.unload().prevented,true);
  foreign=false;await a.run('retryUnsaved()');assert.equal(posts.length,2);
  assert.equal(posts[1].project_fingerprint,fp);assert.equal(posts[1].base_revision,4);
  assert.equal(a.run('unsavedCount()'),0);
});
test('a foreign successful response cannot acknowledge the pending edit',async()=>{
  const a=app(async()=>response({fingerprint:'foreign-project',revision:1,decisions:{turn:{text:'Mine'}}}));
  assert.equal(await a.run("saveDecision('turn',{text:'Mine'})"),false);
  assert.equal(a.run("view.drafts.get('turn').text"),'Mine');assert.equal(a.run('view.state.revision'),0);
});
test('missing project binding rejects mutation construction',()=>{
  const a=app();a.run('delete view.project.fingerprint');
  assert.throws(()=>a.run("saveDecision('turn',{text:'Mine'})"),/校验标识/);
});
test('undo remains dirty in flight and retries an uncertain response with the same binding and id',async()=>{
  const requests=[];let first=true;
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response({fingerprint:fp,revision:2,decisions:{}});
    requests.push(JSON.parse(options.body));
    if(first){first=false;throw new Error('Synthetic lost response');}
    return response({fingerprint:fp,revision:1,decisions:{}});
  });
  const undo=a.run('undoDecision()');assert.equal(a.unload().prevented,true);await undo;
  assert.equal(a.run('unsavedCount()'),1);await a.run('retryUnsaved()');
  assert.deepEqual(requests[1],requests[0]);assert.equal(requests[0].project_fingerprint,fp);
  assert.equal(a.run('view.state.revision'),2);assert.equal(a.run('unsavedCount()'),0);
});
test('context uses nearby continuous coverage and retains simultaneous devices',()=>{
  const a=app();a.run(`view.project.sources=[
    {id:'A',duration:100,clock:{offset:0,scale:1}},
    {id:'B',duration:100,clock:{offset:2,scale:1}},
    {id:'gap',duration:5,clock:{offset:110,scale:1}},
    {id:'later',duration:100,clock:{offset:7200,scale:1}}
  ];view.project.items=[
    {id:'selected',kind:'speaker_sample',source_id:'A',start:90,end:92},
    {id:'same',kind:'transcript',source_id:'A',start:85,end:88,text:'Nearby same recorder'},
    {id:'overlap',kind:'transcript',source_id:'B',start:90,end:93,text:'Simultaneous device'},
    {id:'early',kind:'transcript',source_id:'A',start:2,end:4,text:'Far same recorder'},
    {id:'gap',kind:'transcript',source_id:'gap',start:111,end:113,text:'After uncovered gap'},
    {id:'later',kind:'transcript',source_id:'later',start:7201,end:7204,text:'Hours away'}
  ];view.selectedId='selected';`);
  assert.deepEqual(JSON.parse(a.run('JSON.stringify(contextItems().transcript.map(i=>i.id))')),['same','overlap']);
  a.run('renderContext()');assert.doesNotMatch(a.nodes.get('fullContext').innerHTML,/Hours away|Far same|uncovered gap/);
  a.run("view.project.items=view.project.items.filter(i=>!['same','overlap'].includes(i.id));renderContext()");
  assert.match(a.nodes.get('contextPreview').innerHTML,/没有逐字稿/);
  a.run('openNearbyTranscript()');assert.equal(a.run('view.selectedId'),'selected','A sample must not jump across hours to unrelated text');
});
test('coverage ignores floating-point roundoff but reports a missing sample and three-second context',()=>{
  const a=app();a.run("view.project.sources[0]={id:'main',duration:0.3,clock:{offset:0.1,scale:1}};view.project.items[0].start=0.1;view.project.items[0].end=0.4");
  assert.equal(a.run('sourceCoverage(currentSource()).partial'),false);
  a.run('view.project.items[0].end=0.4+1/48000');assert.equal(a.run('sourceCoverage(currentSource()).partial'),true);
  a.run('view.project.items[0].end=0.4;view.context=true');assert.equal(a.run('sourceCoverage(currentSource()).partial'),true);
  for(const phase of ['idle','loading','playing','paused','ended']){
    a.run(`setAudioPhase('${phase}')`);assert.match(a.nodes.get('audioMessage').textContent,/只覆盖本段部分原音/);
  }
});

test('the actual flat server error retains project mismatch even when state readback is unavailable',async()=>{
  let reads=0;const a=app(async(url)=>{
    if(url==='/api/state'){reads++;throw new Error('Synthetic disconnected service');}
    return response({error:'project_mismatch',message:'Synthetic project changed'},409);
  });
  assert.equal(await a.run("saveDecision('turn',{text:'Pending'})"),false);
  assert.equal(a.run("view.failedRequests.get('turn').kind"),'project');assert.equal(reads,0);
  assert.match(a.nodes.get('toast').textContent,/另一份录音/);assert.doesNotMatch(a.nodes.get('toast').textContent,/已读取最新/);
  assert.equal(a.run("view.drafts.get('turn').text"),'Pending');
  const e=await a.run("fetchJSON('/api/decision').catch(error=>({code:error.code,message:error.message}))");
  assert.equal(e.code,'project_mismatch');assert.equal(e.message,'Synthetic project changed');
});

test('a choice queued before conflict is not treated as informed conflict confirmation',async()=>{
  let rejectFirst;const writes=[];
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response({fingerprint:fp,revision:2,decisions:{}});
    writes.push(JSON.parse(options.body));
    if(writes.length===1)return new Promise(resolve=>{rejectFirst=()=>resolve(response({error:'revision_conflict',message:'Synthetic conflict'},409));});
    return response({fingerprint:fp,revision:3,decisions:{turn:writes.at(-1).changes}});
  });
  const first=a.run("saveDecision('turn',{text:'A'})");await settle();
  const queued=a.run("saveDecision('turn',{text:'B'})");rejectFirst();await first;await queued;
  assert.equal(writes.length,1);assert.equal(a.run("view.drafts.get('turn').text"),'B');
  await a.run('retryUnsaved()');assert.equal(writes.length,2);assert.equal(a.run('unsavedCount()'),0);
});

test('typing after an uncertain undo stays pending and one retry resolves undo before saving text',async()=>{
  const writes=[];let first=true;
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response({fingerprint:fp,revision:1,decisions:{}});
    const body=JSON.parse(options.body);writes.push({url,body});
    if(first){first=false;throw new Error('Synthetic lost undo response');}
    return response({fingerprint:fp,revision:url==='/api/undo'?1:2,decisions:url==='/api/undo'?{}:{turn:body.changes}});
  });
  await a.run('undoDecision()');a.run("scheduleDraft('turn','text','Typed after undo')");a.expire(700);await a.run('view.saveChain');
  assert.equal(writes.length,1,'New text must not race an unresolved undo');
  await a.run('retryUnsaved()');assert.deepEqual(writes.map(r=>r.url),['/api/undo','/api/undo','/api/decision']);
  assert.deepEqual(writes[1].body,writes[0].body);assert.equal(a.run('unsavedCount()'),0);
  assert.equal(a.run('view.state.decisions.turn.text'),'Typed after undo');
});

for(const pendingKind of ['queued','timer'])test(`a conflict blocks a different item's pre-conflict ${pendingKind} edit until explicit retry`,async()=>{
  const writes=[];let release,state={fingerprint:fp,revision:1,decisions:{other:{text:'Other reviewer B'}}};
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response(state);
    const request=JSON.parse(options.body);writes.push(request);
    if(writes.length===1)return new Promise(resolve=>{release=()=>resolve(response({error:'revision_conflict',message:'Synthetic other reviewer update'},409));});
    assert.equal(request.base_revision,state.revision);
    state={...state,revision:state.revision+1,decisions:{...state.decisions,[request.item_id]:request.changes}};return response(state);
  });
  a.run("view.project.items.push({...view.project.items[0],id:'other',start:20,end:22,text:'Original B'})");
  const first=a.run("saveDecision('turn',{text:'My A'})");await settle();
  let second;if(pendingKind==='queued')second=a.run("saveDecision('other',{text:'My stale B'})");else a.run("scheduleDraft('other','text','My stale B')");
  release();await first;if(pendingKind==='timer'){a.expire(700);second=a.run('view.saveChain');}await second;
  assert.equal(writes.length,1,'No stale B request may adopt the externally refreshed revision');
  assert.equal(state.decisions.other.text,'Other reviewer B');assert.equal(a.run("view.drafts.get('other').text"),'My stale B');
  assert.equal(a.run("view.failedRequests.get('other').kind"),'conflict');assert.equal(a.unload().prevented,true);
  await a.run('retryUnsaved()');assert.equal(writes.length,3);assert.equal(state.decisions.other.text,'My stale B');assert.equal(a.run('unsavedCount()'),0);
});

test('ordinary cross-item sequential writes advance their own revision without conflict consent',async()=>{
  const writes=[];let state={fingerprint:fp,revision:0,decisions:{}};
  const a=app(async(url,options)=>{
    assert.equal(url,'/api/decision');const request=JSON.parse(options.body);writes.push(request);
    assert.equal(request.base_revision,state.revision);
    state={...state,revision:state.revision+1,decisions:{...state.decisions,[request.item_id]:request.changes}};return response(state);
  });
  const first=a.run("saveDecision('turn',{text:'A'},{quiet:true})");const second=a.run("saveDecision('other',{text:'B'},{quiet:true})");
  await first;await second;assert.deepEqual(writes.map(r=>r.base_revision),[0,1]);assert.equal(a.run('unsavedCount()'),0);
});

test('lost-ack replay reads external work without rebasing another queued item',async()=>{
  const writes=[];let first=true,release;
  const a=app(async(url,options)=>{
    if(url==='/api/state')return response({fingerprint:fp,revision:2,decisions:{turn:{text:'A'},other:{text:'Other reviewer B'}}});
    const request=JSON.parse(options.body);writes.push(request);
    if(first){first=false;throw new Error('Synthetic lost acknowledgement');}
    return new Promise(resolve=>{release=()=>resolve(response({fingerprint:fp,revision:1,decisions:{turn:{text:'A'}}}));});
  });
  await a.run("saveDecision('turn',{text:'A'})");
  const replay=a.run('retryUnsaved()');await settle();const queued=a.run("saveDecision('other',{text:'Stale B'},{quiet:true})");
  release();await replay;await queued;
  assert.deepEqual(writes[1],writes[0]);assert.equal(writes.length,2);
  assert.equal(a.run('view.state.decisions.other.text'),'Other reviewer B');assert.equal(a.run("view.drafts.get('other').text"),'Stale B');
  assert.equal(a.run("view.failedRequests.get('other').kind"),'conflict');
});
