#!/usr/bin/env node
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function application(fetch) {
  const file = path.join(__dirname, '../static/app.js');
  const input = fs.readFileSync(file, 'utf8');
  const source = input.replace(/bindEvents\(\);loadProject\(\);\s*$/, '');
  assert.notEqual(source, input, 'Application bootstrap must be isolated from the test');
  const nodes = new Map();
  function node() {
    return {innerHTML:'', textContent:'', value:'', hidden:false, style:{}, dataset:{},
      scrollTop:0, clientHeight:600, classList:{toggle(){},add(){},remove(){}},
      setAttribute(){}, querySelector(){return null;}, querySelectorAll(){return [];}};
  }
  let request = 0;
  const document = {activeElement:null, getElementById(id){
    if(!nodes.has(id)) nodes.set(id, node()); return nodes.get(id);
  }, querySelector(){return null;}, querySelectorAll(){return [];}};
  const context = vm.createContext({document, window:{crypto:{randomUUID:()=>`request-${++request}`}},
    fetch, setTimeout:()=>1, clearTimeout(){}, Map, Set, Date, Math, Number, String, Promise, console});
  vm.runInContext(source, context, {filename:file});
  vm.runInContext(`view.project={project_id:'synthetic',fingerprint:'synthetic-fingerprint',sources:[],people:[],items:[
    {id:'sample',kind:'speaker_sample',start:2,end:4,text:'Synthetic sample',speaker:'',identity_status:'unknown'}
  ]};view.selectedId='sample';view.state={fingerprint:'synthetic-fingerprint',revision:0,decisions:{}};`, context);
  return {context, nodes, run:code=>vm.runInContext(code, context)};
}

test('failed name-only choice retains the exact pending intent and visible retry', async()=>{
  const app=application(async()=>{throw new Error('Synthetic connection failure');});
  const saved=await app.run("saveDecision('sample',{speaker:'Participant A',status:'confirmed'})");
  assert.equal(saved,false);
  assert.equal(app.run('unsavedCount()'),1);
  assert.equal(app.run('effectiveItem(currentItem()).speaker'),'Participant A');
  assert.equal(app.run('identity(currentItem())'),'unsaved');
  assert.equal(app.nodes.get('retrySaveButton').hidden,false);
});

test('lost response reuses the request and reads later work after idempotent replay',async()=>{
  let first=true;
  const requests=[];
  const original={fingerprint:'synthetic-fingerprint',revision:1,decisions:{sample:{speaker:'Participant A',status:'confirmed'}}};
  const latest={fingerprint:'synthetic-fingerprint',revision:2,decisions:{...original.decisions,other:{note:'Later work',status:'unknown'}}};
  const app=application(async(url,options)=>{
    if(url==='/api/state')return {ok:true,json:async()=>latest};
    const request=JSON.parse(options.body);requests.push(request);
    if(first){first=false;throw new Error('Response lost after commit');}
    return {ok:true,json:async()=>original};
  });
  assert.equal(await app.run("saveDecision('sample',{speaker:'Participant A',status:'confirmed'})"),false);
  await app.run('retryUnsaved()');
  assert.equal(requests.length,2);
  assert.deepEqual(requests[1],requests[0]);
  assert.equal(app.run('view.state.revision'),2);
  assert.equal(app.run('view.state.decisions.other.note'),'Later work');
  assert.equal(app.run('unsavedCount()'),0);
});
