#!/usr/bin/env node
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Executes the shipped player, with only bootstrap and canvas drawing isolated.
// Optional immutable-ref replay calibrates these assertions against known bugs.
// No browser, real media, network, sound output, or wall-clock timers are used.
const appPath = 'daymade-audio/asr-transcribe-to-text/scripts/review-workbench/static/app.js';
const file = path.join(__dirname, '../static/app.js');
const revision = process.env.PLAYBACK_TEST_REV;
const input = revision
  ? execFileSync('git', ['-C', __dirname, 'show', `${revision}:${appPath}`], {encoding:'utf8'})
  : fs.readFileSync(file, 'utf8');
const source = input.replace(/bindEvents\(\);loadProject\(\);\s*$/, '');
assert.notEqual(source, input, 'Only the application bootstrap must be removed');

function application({readyState=1, manualSeek=false, deferPlay=false}={}) {
  const nodes = new Map(), timers = new Map(), events = [], audios = [];
  let nextTimer = 0;
  function eventTarget(target) {
    const listeners = new Map();
    return Object.assign(target, {
      addEventListener(type, fn, options={}) {
        const entries = listeners.get(type) || [];
        entries.push({fn, once:Boolean(options.once)}); listeners.set(type, entries);
      },
      removeEventListener(type, fn) {
        listeners.set(type, (listeners.get(type) || []).filter(entry=>entry.fn!==fn));
      },
      dispatch(type, detail={}) {
        const event = {type, target:this, currentTarget:this, ...detail};
        for(const entry of [...(listeners.get(type) || [])]) {
          if(entry.once)this.removeEventListener(type, entry.fn);
          entry.fn(event);
        }
        return event;
      },
      listenerCount(type) { return (listeners.get(type) || []).length; }
    });
  }
  const document = eventTarget({activeElement:null, title:'',
    getElementById(id) {
      if(!nodes.has(id))nodes.set(id, node(id)); return nodes.get(id);
    },
    querySelector(){return null;}, querySelectorAll(){return [];}
  });
  function node(id='') {
    const classes = new Set(), attrs = new Map();
    return eventTarget({id, innerHTML:'', textContent:'', value:'', hidden:false, disabled:false,
      tagName: /Editor$/.test(id)?'TEXTAREA':'DIV', readOnly:false, type:'', isContentEditable:false,
      style:{}, dataset:{}, scrollTop:0, clientHeight:600, scrollHeight:100,
      classList:{toggle(name, on){if(on===undefined)on=!classes.has(name); on?classes.add(name):classes.delete(name);},
        add(name){classes.add(name);}, remove(name){classes.delete(name);}, contains(name){return classes.has(name);}},
      setAttribute(name,value){attrs.set(name,String(value));}, getAttribute(name){return attrs.get(name);},
      querySelector(){return null;}, querySelectorAll(){return [];},
      closest(selector) {
        if(selector==='.sentence-paper')return this;
        if(selector==='input,textarea,select,[contenteditable="true"]')
          return ['INPUT','TEXTAREA','SELECT'].includes(this.tagName)||this.isContentEditable?this:null;
        return null;
      },
      matches(){return this.tagName==='TEXTAREA'||(this.tagName==='INPUT'&&(!this.type||this.type==='text'));},
      focus(){document.activeElement=this;}, close(){this.open=false;}, showModal(){this.open=true;}
    });
  }
  class Audio {
    constructor() {
      eventTarget(this); this.dataset={}; this.readyState=readyState; this.duration=400;
      this._currentTime=0; this.seeking=false; this.paused=true; this.muted=false; this.volume=1;
      this.loads=0; this.plays=0; this.playRequests=[]; this.srcAssignments=0; audios.push(this);
    }
    set src(value){this._src=value; this.srcAssignments++;} get src(){return this._src;}
    set currentTime(value){this._currentTime=value; this.seeking=manualSeek;} get currentTime(){return this._currentTime;}
    play(){
      this.plays++;
      const start=()=>{this.paused=false;events.push(()=>this.dispatch('play'),()=>this.dispatch('playing'));};
      if(deferPlay)return new Promise((resolve,reject)=>this.playRequests.push({resolve:()=>{start();resolve();},reject}));
      start(); return Promise.resolve();
    }
    pause(){if(this.paused)return; this.paused=true; events.push(()=>this.dispatch('timeupdate'),()=>this.dispatch('pause'));}
    removeAttribute(name){if(name==='src')this._src='';}
    load(){this.loads++;}
    metadata(){this.readyState=1; this.dispatch('loadedmetadata');}
    seeked(){this.seeking=false; this.dispatch('seeked');}
    progress(time){this._currentTime=time; this.dispatch('timeupdate');}
  }
  const context = vm.createContext({document, Audio, console, Map, Set, Date, Math, Number, String, Promise,
    window:eventTarget({devicePixelRatio:1}), ResizeObserver:class{observe(){}}, requestAnimationFrame(){},
    setTimeout(fn, ms){const id=++nextTimer; timers.set(id,{fn,ms}); return id;},
    clearTimeout(id){timers.delete(id);}, localStorage:{setItem(){},getItem(){return null;}},
    fetch(){throw new Error('Network is forbidden in player tests');}
  });
  const run = code=>vm.runInContext(code, context, {filename:revision||file});
  run(source);
  run(`drawTracks=()=>{}; drawOverview=()=>{};
    view.project={project_id:'synthetic-player',people:[{name:'Person A'},{name:'Person B'}],sources:[
      {id:'A',label:'Device A',duration:400,clock:{offset:0,scale:1}},
      {id:'B',label:'Device B',duration:400,clock:{offset:2,scale:1}}
    ],items:[
      {id:'early',kind:'transcript',start:10,end:20,text:'Early synthetic phrase'},
      {id:'late',kind:'transcript',start:100,end:110,text:'Late synthetic phrase'},
      {id:'sample',kind:'speaker_sample',start:30,end:34,text:'Synthetic location hint'},
      {id:'confirmed',kind:'speaker_sample',start:40,end:52,text:'Confirmed phrase'},
      {id:'confirmed-b',kind:'transcript',start:60,end:64,text:'Other confirmed phrase'},
      {id:'candidate',kind:'speaker_sample',start:80,end:84,text:'Candidate phrase',speaker:'Model guess',identity_status:'candidate'}
    ]};
    view.state={revision:7,decisions:{confirmed:{speaker:'Person A',status:'confirmed'},'confirmed-b':{speaker:'Person B',status:'confirmed'}}};
    view.mode='transcript'; view.filtered=view.project.items; view.selectedId='early'; view.sourceId='A'; view.position=12;
    bindEvents(); renderSelected();`);
  function flushEvents(){for(let count=0;events.length;count++){assert.ok(count<100,'Synthetic media queue must settle');events.shift()();}}
  async function settle(){for(let i=0;i<8;i++)await Promise.resolve(); flushEvents();}
  function expire(ms=10000){
    const matching=[...timers.entries()].filter(([,timer])=>timer.ms===ms);
    assert.ok(matching.length, `Expected a pending ${ms}ms timeout`);
    for(const [id,timer] of matching){timers.delete(id);timer.fn();}
  }
  function key(target, key, detail={}){
    const event={target,key,code:key===' '?'Space':'',defaultPrevented:false,
      preventDefault(){this.defaultPrevented=true;},...detail};
    return document.dispatch('keydown',event);
  }
  function currentSnapshot(){return JSON.parse(run('JSON.stringify({selectedId:view.selectedId,sourceId:view.sourceId,position:view.position,state:view.state,drafts:[...view.drafts]})'));}
  return {run,nodes,audios,events,timers,document,node,flushEvents,settle,expire,key,currentSnapshot};
}

function assertStatus(app, phase, status, button) {
  assert.equal(app.run('view.audioPhase'),phase);
  assert.equal(app.run('view.playing'),phase==='playing');
  assert.equal(app.nodes.get('audioDesk').dataset.phase,phase);
  assert.equal(app.nodes.get('playbackStatus').textContent,status);
  assert.match(app.nodes.get('playButton').innerHTML,button);
}

test('regression: queued timeupdate from the old sentence cannot move the new selection',async()=>{
  const app=application();
  await app.run('playAudio()'); app.flushEvents();
  app.audios[0].progress(14);
  assert.equal(app.run('view.position'),14,'Positive control: current playback advances');
  app.run("chooseItem('late')");
  assert.equal(app.run('view.position'),100);
  assert.ok(app.events.length,'Pause must leave old media events queued');
  app.flushEvents();
  assert.equal(app.run('view.selectedId'),'late');
  assert.equal(app.run('view.position'),100,'Late pause/timeupdate cannot overwrite the newly selected sentence');
  assert.match(app.nodes.get('positionLabel').textContent,/01:40/);
});

test('regression: paused source switch preserves the requested meeting time through resume',async()=>{
  const app=application(); await app.run('playAudio()'); app.flushEvents();
  app.run('pauseAudio()');
  await app.run("switchSource('B',{position:15,autoplay:false})");
  app.flushEvents();
  assert.equal(app.run('view.sourceId'),'B');
  assert.equal(app.run('view.position'),15,'Queued events from A cannot undo the requested seek');
  await app.run('playAudio()'); app.flushEvents();
  assert.equal(app.audios.length,2);
  assert.equal(app.audios[1].currentTime,13,'Device B clock maps meeting 15s to local 13s');
  assert.equal(app.audios[0].paused,true);
  app.audios[0].progress(19);
  assert.equal(app.run('view.position'),15,'Replaced Audio events stay isolated');
  app.audios[1].progress(14);
  assert.equal(app.run('view.position'),16,'Positive control: current source still advances');
});

test('regression: media error before metadata retries a fresh Audio and recovers',async()=>{
  const app=application({readyState:0});
  const first=app.run('playAudio()');
  const failed=app.audios[0]; failed.dispatch('error'); await first; app.flushEvents();
  assert.equal(failed.plays,0);
  const retry=app.run('playAudio()');
  assert.equal(app.audios.length,2,'Retry must replace the failed media object');
  assert.notEqual(app.audios[1],failed);
  app.audios[1].metadata(); await retry; app.flushEvents();
  assert.equal(app.audios[1].plays,1);
  assertStatus(app,'playing','播放中',/暂停/);
  assert.equal([...app.timers.values()].filter(timer=>timer.ms===10000).length,0,'Recovery clears the media wait timeout');
});

test('metadata timeout is retryable, while cancelled metadata cannot start playback late',async()=>{
  const app=application({readyState:0});
  const first=app.run('playAudio()'); app.expire(); await first; app.flushEvents();
  assertStatus(app,'error','读取失败',/重试原音/);
  const retry=app.run('playAudio()');
  assert.equal(app.audios.length,2);
  app.audios[1].metadata(); await retry; app.flushEvents();
  assertStatus(app,'playing','播放中',/暂停/);

  const cancelled=application({readyState:0});
  const pending=cancelled.run('playAudio()');
  cancelled.run('togglePlayback()');
  assert.equal(cancelled.audios[0].listenerCount('loadedmetadata'),0,'Cancel removes the pending metadata listener');
  assert.equal([...cancelled.timers.values()].filter(timer=>timer.ms===10000).length,0);
  cancelled.audios[0].metadata(); await pending; cancelled.flushEvents();
  assert.equal(cancelled.audios[0].plays,0,'Late metadata cannot resurrect cancelled playback');
  assertStatus(cancelled,'paused','已暂停',/听原音/);
});

test('play waits for metadata and seek completion; navigation cancels a pending seek',async()=>{
  const app=application({readyState:0,manualSeek:true});
  const pending=app.run('playAudio()');
  assertStatus(app,'loading','正在读取',/取消读取/);
  assert.equal(app.audios[0].plays,0);
  app.audios[0].metadata(); await app.settle();
  assert.equal(app.audios[0].currentTime,12);
  assert.equal(app.audios[0].plays,0,'Metadata alone is insufficient while seeking');
  app.audios[0].seeked(); await pending; app.flushEvents();
  assertStatus(app,'playing','播放中',/暂停/);

  const cancelled=application({manualSeek:true});
  const seek=cancelled.run('playAudio()'); await cancelled.settle();
  assert.equal(cancelled.audios[0].listenerCount('seeked'),1);
  cancelled.run("chooseItem('late')");
  cancelled.audios[0].seeked(); await seek; cancelled.flushEvents();
  assert.equal(cancelled.audios[0].plays,0);
  assert.equal(cancelled.run('view.position'),100);
});

test('regression: pause and clip end replace the playing message; replay starts at clip start',async()=>{
  const app=application(); await app.run('playAudio()'); app.flushEvents();
  assert.match(app.nodes.get('audioMessage').textContent,/正在播放|正在听/);
  app.audios[0].progress(16);
  app.run('pauseAudio()'); app.flushEvents();
  assert.match(app.nodes.get('audioMessage').textContent,/已暂停/,'Manual pause cannot leave a playing claim');
  assertStatus(app,'paused','已暂停',/听原音/);
  assert.equal(app.run('view.position'),16);
  await app.run('playAudio()'); app.flushEvents();
  assert.equal(app.audios[0].currentTime,16);
  app.audios[0].progress(20); app.flushEvents();
  assert.match(app.nodes.get('audioMessage').textContent,/播完|结束/,'The clip boundary must visibly stop playback');
  assertStatus(app,'ended','片段结束',/再听一次/);
  assert.equal(app.audios[0].paused,true);
  await app.run('playAudio()'); app.flushEvents();
  assert.equal(app.audios[0].currentTime,10);
  assertStatus(app,'playing','播放中',/暂停/);
});

test('buffering is cancellable and stale waiting/playing events cannot override pause',async()=>{
  const app=application(); await app.run('playAudio()'); app.flushEvents();
  app.audios[0].dispatch('waiting');
  assertStatus(app,'buffering','等待缓冲',/暂停/);
  assert.match(app.nodes.get('audioMessage').textContent,/缓冲/);
  app.audios[0].dispatch('playing');
  assertStatus(app,'playing','播放中',/暂停/);
  app.audios[0].dispatch('waiting'); app.run('togglePlayback()'); app.flushEvents();
  app.audios[0].dispatch('waiting'); app.audios[0].dispatch('playing');
  assertStatus(app,'paused','已暂停',/听原音/);
});

test('late play resolution respects cancellation without pausing a newer playback binding',async()=>{
  const cancelled=application({deferPlay:true});
  const first=cancelled.run('playAudio()'); await cancelled.settle();
  assert.equal(cancelled.audios[0].playRequests.length,1);
  cancelled.run('pauseAudio()'); cancelled.flushEvents();
  cancelled.audios[0].playRequests[0].resolve(); await first; cancelled.flushEvents();
  assert.equal(cancelled.audios[0].paused,true);
  assertStatus(cancelled,'paused','已暂停',/听原音/);

  const renewed=application({deferPlay:true});
  const old=renewed.run('playAudio()'); await renewed.settle();
  renewed.run('pauseAudio()');
  const current=renewed.run('playAudio()'); await renewed.settle();
  assert.equal(renewed.audios.length,1,'Healthy media is reused for the new request');
  assert.equal(renewed.audios[0].playRequests.length,2);
  renewed.audios[0].playRequests[0].resolve(); await old; renewed.flushEvents();
  assert.equal(renewed.audios[0].paused,false,'An old fulfilled promise cannot pause the newer binding');
  renewed.audios[0].playRequests[1].resolve(); await current; renewed.flushEvents();
  assertStatus(renewed,'playing','播放中',/暂停/);
});

test('read-only hint permits Q; editing, space and composition are protected; Escape returns to play',async()=>{
  const app=application(); app.run("chooseItem('sample')");
  const hint=app.nodes.get('transcriptEditor');
  assert.equal(hint.readOnly,true);
  const q=app.key(hint,'q'); await app.settle();
  assert.equal(q.defaultPrevented,true);
  assert.equal(app.audios[0].plays,1,'Q works from the read-only sample hint');
  app.run('pauseAudio()'); app.flushEvents();
  app.run("chooseItem('early')");
  const editor=app.nodes.get('transcriptEditor'); editor.value='Text q stays in the editor'; editor.focus();
  const before=app.audios[0].plays;
  for(const key of ['q',' '])assert.equal(app.key(editor,key).defaultPrevented,false);
  const composition=app.key(app.nodes.get('playButton'),'q',{isComposing:true});
  await app.settle();
  assert.equal(composition.defaultPrevented,false);
  assert.equal(app.audios[0].plays,before);
  assert.equal(editor.value,'Text q stays in the editor');
  assert.equal(app.key(editor,'Escape').defaultPrevented,true);
  assert.equal(app.document.activeElement,app.nodes.get('playButton'));
  assert.equal(app.key(app.nodes.get('playButton'),' ').defaultPrevented,true);
  await app.settle(); assert.equal(app.audios[0].plays,before+1);
});

test('reference choices admit confirmed identities only, including saved human confirmation',async()=>{
  const app=application();
  app.run(`view.project.items.push({id:'human',kind:'transcript',start:90,end:94,text:'Original human confirmation',speaker:'Human',identity_status:'human_confirmed'});
    view.project.items.push({id:'draft-only',kind:'transcript',start:95,end:99,text:'Pending choice'});
    view.drafts.set('draft-only',{speaker:'Uncommitted',status:'confirmed'});renderReferences();`);
  assert.deepEqual(JSON.parse(app.run('JSON.stringify(confirmedReferences().map(item=>item.id))')),['confirmed','confirmed-b','human']);
  const html=app.nodes.get('referenceChoices').innerHTML;
  assert.match(html,/Person A/); assert.match(html,/Human/);
  assert.doesNotMatch(html,/Model guess|Uncommitted/);
  await app.run("playReference('candidate')"); await app.run("playReference('draft-only')");
  assert.equal(app.audios.length,0,'An unconfirmed id cannot bypass the visible chooser');
  assert.equal(app.run('view.reference'),null);
});

test('reference listening preserves current judgment and cursor, never overlaps, and returns to the current sentence',async()=>{
  const app=application(); await app.run('playAudio()'); app.flushEvents();
  app.audios[0].progress(15);
  const before=app.currentSnapshot();
  await app.run("playReference('confirmed')"); app.flushEvents();
  assert.equal(app.audios[0].paused,true);
  assert.equal(app.audios[1].paused,false);
  assert.equal(app.audios[1].currentTime,40);
  assert.deepEqual(app.currentSnapshot(),before);
  assert.equal(app.nodes.get('resumeCurrentButton').hidden,false);
  app.audios[1].progress(45);
  assert.deepEqual(app.currentSnapshot(),before,'Reference timeupdate cannot move the main playhead');
  await app.run("playReference('confirmed-b')"); app.flushEvents();
  assert.equal(app.audios[1].paused,true);
  assert.equal(app.audios.filter(audio=>!audio.paused).length,1);
  app.nodes.get('resumeCurrentButton').dispatch('click'); await app.settle();
  assert.equal(app.run('view.reference'),null);
  assert.equal(app.audios[2].paused,true);
  assert.equal(app.audios[0].paused,false);
  assert.equal(app.audios[0].currentTime,15);
  assert.deepEqual(app.currentSnapshot(),before);
  assert.equal(app.document.activeElement,app.nodes.get('playButton'));
  await app.run("playReference('confirmed')"); app.flushEvents();
  app.run("chooseItem('late')"); app.flushEvents();
  assert.equal(app.run('view.reference'),null);
  assert.equal(app.audios.every(audio=>audio.paused),true);
  assert.equal(app.run('view.position'),100);
});

test('reference clip boundary stops at eight seconds; errors and cancelled metadata can be retried safely',async()=>{
  const app=application(); const before=app.currentSnapshot();
  await app.run("playReference('confirmed')"); app.flushEvents();
  app.audios[0].progress(47.9);
  assert.notEqual(app.run('view.reference'),null,'Positive control: reference is still active before its boundary');
  app.audios[0].progress(48); app.flushEvents();
  assert.equal(app.run('view.reference'),null);
  assert.equal(app.audios[0].paused,true);
  assert.match(app.nodes.get('referenceMessage').textContent,/播完/);
  assert.deepEqual(app.currentSnapshot(),before);
  await app.run("playReference('confirmed')"); app.flushEvents();
  app.audios[1].dispatch('error'); app.flushEvents();
  assert.equal(app.run('view.reference'),null);
  assert.match(app.nodes.get('referenceMessage').textContent,/失败.*重新加载/);
  await app.run("playReference('confirmed')"); app.flushEvents();
  assert.equal(app.audios.length,3);
  assert.equal(app.audios[2].paused,false);
  assert.deepEqual(app.currentSnapshot(),before);

  const cancelled=application({readyState:0});
  const pending=cancelled.run("playReference('confirmed')");
  cancelled.run("chooseItem('late')");
  cancelled.audios[0].metadata(); await pending; cancelled.flushEvents();
  assert.equal(cancelled.audios[0].plays,0);
  assert.equal(cancelled.run('view.reference'),null);
  assert.equal([...cancelled.timers.values()].filter(timer=>timer.ms===10000).length,0);
});

test('volume control affects both players and newly created playback objects',async()=>{
  const app=application(); await app.run('playAudio()'); app.flushEvents();
  app.run('setVolume(0)');
  assert.equal(app.audios[0].muted,true); assert.equal(app.audios[0].volume,0);
  await app.run("playReference('confirmed')"); app.flushEvents();
  assert.equal(app.audios[1].volume,0);
  app.run('setVolume(0.4)');
  for(const audio of app.audios){assert.equal(audio.volume,0.4);assert.equal(audio.muted,false);}
  assert.equal(app.nodes.get('volumeValue').textContent,'40%');
  app.run('setVolume(2)'); assert.equal(app.audios[1].volume,1);
});
