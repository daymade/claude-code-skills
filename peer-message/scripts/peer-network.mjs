#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {spawn, spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {atomicJson, decodeInvite, fail, readJson, relayUrl, shareFiles} from './network-common.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const script=fileURLToPath(import.meta.url);
const help=`peer-message network preview — ask an approved peer's Agent

Run with Node 22.13+ and the pinned runtime installed.
All commands emit JSON. --state selects one endpoint's private state directory.

init --name NAME --relay HTTPS_URL --host claude|codex [--share FILE ...]
  Create an endpoint. Share only explicitly approved text files; no directories.
  --invite INVITATION can supply the relay instead of --relay.
  --model MODEL selects the existing host's model; --timeout SECONDS defaults to 240.
start                         Start this endpoint's local connector
doctor                        Inspect runtime, host, configuration and connector
invite [--purpose TEXT]       Create a task invitation; keep connector online during pairing
join --invite TEXT --alias NAME
                              Prepare pairing; returns an owner-only approval-file path
approve --pending ID --code OWNER_CODE
                              Use the code supplied by the owner; agents must not read it
contacts                      List approved peers and local names
contact --alias NAME --peer ID Name an already paired identity
ask --to NAME --question TEXT [--id UUID] [--wait SECONDS]
                              Save and send one question; default wait is 45 seconds
status --id UUID               Read this sender's recorded result once
pause | resume                Pause/resume new host work; incoming requests stay durable
host --host claude|codex [--model MODEL]
                              Change the answer host while preserving contacts and identity
retry --id UUID                Retry pending delivery with the same encrypted envelope
stop                          Stop connector; already running read-only workers finish

This preview answers from shared document snapshots. It does not execute a peer's
commands or inject requests into an unrelated active session. Pairing is not
execution authorization. There is no bundled hosted relay or account registration.
`;
function parse(argv) {
  const values={};let action;
  for(let i=0;i<argv.length;i++) {
    const a=argv[i];
    if(a==='--help'||a==='-h')return {action:'help'};
    if(a.startsWith('--')) {
      const key=a.slice(2).replaceAll('-','_');const value=argv[++i];
      if(value===undefined||value.startsWith('--'))fail(`Missing value for ${a}`);
      if(key==='share')(values.share??=[]).push(value);else values[key]=value;
    } else if(!action)action=a;else fail(`Unexpected argument: ${a}`);
  }
  return {action:action||'help',...values};
}
export async function control(directory,action,input={}) {
  let c;
  try {c=readJson(path.join(directory,'control.json'));}catch{fail('Connector is not running; use start');}
  let response;
  try {response=await fetch(`http://127.0.0.1:${c.port}/command`,{method:'POST',headers:{Authorization:`Bearer ${c.token}`,'Content-Type':'application/json'},
    body:JSON.stringify({action,...input}),signal:AbortSignal.timeout(60000)});}catch{fail('Connector is unreachable; inspect daemon.log then use start');}
  const result=await response.json();if(!result.ok)fail(result.error || `Control failed: ${response.status}`);return result;
}
async function main() {
  process.umask(0o077);
  const args=parse(process.argv.slice(2));
  if(args.action==='help'){console.log(help);return;}
  const directory=path.resolve(args.state || path.join(os.homedir(),'.local/share/peer-message/network'));
  const configPath=path.join(directory,'config.json');
  if(args.action==='daemon'){const {serve}=await import('./network-daemon.mjs');await serve(directory);return;}
  if(args.action==='init') {
    if(fs.existsSync(configPath))fail('Endpoint already exists; use doctor or a new state directory. Identity will not be overwritten');
    if(!args.name || args.name.length>60)fail('A name of at most 60 characters is required');
    if(!['claude','codex'].includes(args.host))fail('Choose an installed, logged-in host: claude or codex');
    const invitation=args.invite?decodeInvite(args.invite):null;
    const relay=relayUrl(args.relay || invitation?.relay || fail('Provide a relay URL or invitation'));
    const timeout=Number(args.timeout || 240);if(!Number.isFinite(timeout)||timeout<10||timeout>600)fail('Timeout must be 10–600 seconds');
    const files=shareFiles(args.share || []);
    atomicJson(configPath,{version:1,name:args.name,relay,host:args.host,model:args.model || null,files,timeout_ms:timeout*1000});
    console.log(JSON.stringify({ok:true,state:directory,name:args.name,host:args.host,shared_files:files.map(f=>f.name),next:'start'}));return;
  }
  if(args.action==='doctor') {
    let config=null;try{config=readJson(configPath);}catch{}
    const runtime=fs.existsSync(path.join(here,'../runtime/node_modules/agentpair/dist/index.js'));
    const host=config?spawnSync(config.host,['--version'],{encoding:'utf8',timeout:10000}):null;
    let connector=null;try{connector=await control(directory,'info');}catch{}
    console.log(JSON.stringify({ok:Boolean(runtime && config && host?.status===0),node:process.version,runtime_installed:runtime,
      config_present:Boolean(config),host_version:host?.stdout?.trim() || null,connector,
      note:'Host version is not proof of model login or task success'}));return;
  }
  if(!fs.existsSync(configPath))fail('Initialize this endpoint first');
  if(args.action==='start') {
    try{const active=await control(directory,'info');console.log(JSON.stringify({...active,reused:true}));return;}catch{}
    const log=fs.openSync(path.join(directory,'daemon.log'),'a',0o600);
    const child=spawn(process.execPath,[script,'daemon','--state',directory],{detached:true,stdio:['ignore',log,log]});
    fs.closeSync(log);child.unref();
    const deadline=Date.now()+15000;
    while(Date.now()<deadline) {
      await new Promise(r=>setTimeout(r,250));
      try{const result=await control(directory,'info');console.log(JSON.stringify(result));return;}catch{}
    }
    fail('Connector did not become ready; inspect daemon.log. Do not start another copy until the first process is checked');
  }
  const action=args.action;
  const seconds=Number(args.wait ?? 45);
  if(action==='ask' && (!Number.isFinite(seconds)||seconds<0||seconds>600))fail('Wait must be 0–600 seconds');
  const input={...args};delete input.action;delete input.state;
  if(input.invite){input.invitation=input.invite;delete input.invite;}
  if(input.pending){input.pending_id=input.pending;delete input.pending;}
  let result=await control(directory,action,input);
  if(action==='ask') {
    const deadline=Date.now()+seconds*1000;
    while(Date.now()<deadline) {
      const status=await control(directory,'status',{id:result.request_id});
      if(['answered','needs_owner','failed','conflict','expired'].includes(status.state)){result=status;break;}
      await new Promise(r=>setTimeout(r,1000));
    }
    if(!result.result)result=await control(directory,'status',{id:result.request_id});
  }
  console.log(JSON.stringify(result));
}
if(process.argv[1] && fs.existsSync(process.argv[1]) && fs.realpathSync(process.argv[1])===script)main().catch(error=>{console.error(JSON.stringify({ok:false,error:error.message}));process.exitCode=1;});
