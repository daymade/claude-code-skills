/* The server is the source of truth for judgments; browser storage only remembers the view. */
'use strict';
const $ = id => document.getElementById(id);
const svg = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ROW_HEIGHT = 112;
const view = {project:null,state:null,mode:'samples',selectedId:null,sourceId:null,position:0,navigationGeneration:0,context:false,loop:false,speed:1,pending:false,search:'',person:'',filtered:[],drafts:new Map(),draftVersions:new Map(),draftEpochs:new Map(),draftGeneration:0,conflictEpoch:0,failedRequests:new Map(),pendingSaves:new Map(),failedUndo:null,saveTimers:new Map(),audio:null,playing:false,audioPhase:'idle',audioToken:0,cancelAudioWait:null,volume:1,reference:null,referenceToken:0,saveChain:Promise.resolve(),viewTimer:null,toastTimer:null,resizeObserver:null};

function formatTime(seconds, decimal=false) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600), minutes = Math.floor(value / 60) % 60, secs = Math.floor(value % 60);
  const base = `${hours ? String(hours).padStart(2,'0') + ':' : ''}${String(minutes).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
  return base + (decimal ? '.' + Math.floor((value % 1) * 10) : '');
}
function currentItem() { return view.project?.items.find(item => item.id === view.selectedId); }
function currentSource() { return view.project?.sources.find(source => source.id === view.sourceId); }
function decisionFor(item) { return view.state?.decisions?.[item.id] || {}; }
function effectiveItem(item) {
  const decision = decisionFor(item), draft = view.drafts.get(item.id) || {};
  return {...item,...decision,...draft};
}
function identity(item) {
  const draft=view.drafts.get(item.id);
  if(draft&&('status' in draft||'speaker' in draft))return 'unsaved';
  const data = effectiveItem(item);
  if (data.status === 'confirmed') return 'confirmed';
  if (data.status === 'unknown') return 'unknown';
  if (data.status === 'skipped') return 'skipped';
  if (item.identity_status === 'human_confirmed') return 'confirmed';
  return item.identity_status === 'candidate' ? 'candidate' : 'pending';
}
function personLabel(item) {
  const data = effectiveItem(item);
  if (data.status === 'unknown') return '未辨认';
  if (!data.status && ['待确认','未知','unknown','未识别'].includes(data.speaker)) return '未辨认';
  return data.speaker || '未辨认';
}
function identityLabel(item) { return ({confirmed:'人工确认',unknown:'无法辨认',skipped:'已跳过',candidate:'模型候选',unsaved:'裁决未保存',pending:item.kind === 'speaker_sample' ? '待认声' : '未辨认'})[identity(item)]; }
function sourceClock(source) { return {offset:Number(source.clock?.offset)||0,scale:Number(source.clock?.scale)||1}; }
function sourceTime(source, canonical) { const clock=sourceClock(source); return (canonical-clock.offset)/clock.scale; }
function canonicalTime(source, local) { const clock=sourceClock(source); return clock.offset+local*clock.scale; }
function sourceDuration(source) { return Number(source.bounded_clip===true?source.available_duration:source.duration); }
function meetingEnd() { return Math.max(...view.project.sources.map(s => canonicalTime(s,s.duration)),...view.project.items.map(i => i.end)); }
function clipWindow(item=currentItem(),context=view.context) { const pad=context?3:0; return {start:Math.max(0,item.start-pad),end:item.end+pad}; }
function sourceCoverage(source,item=currentItem(),{context=view.context}={}) {
  if (!source || !item) return null;
  const window=clipWindow(item,context),localStart=sourceTime(source,window.start),localEnd=sourceTime(source,window.end),duration=sourceDuration(source);
  if(!Number.isFinite(duration)||duration<=0)return null;
  const start=Math.max(0,localStart),end=Math.min(duration,localEnd);
  // Only absorb arithmetic roundoff, never a missing sample or a clipped word.
  const epsilon=32*Number.EPSILON*Math.max(1,Math.abs(localStart),Math.abs(localEnd),duration,Math.abs(sourceClock(source).offset)/sourceClock(source).scale);
  return end>start ? {start,end,partial:localStart < -epsilon || localEnd > duration+epsilon} : null;
}
function setSaveStatus(mode,message) {
  const node=$('saveStatus'); node.className='save-status'+(mode?' '+mode:'');
  node.innerHTML='<span class="status-dot"></span><span>'+escapeHTML(message)+'</span>';
  $('retrySaveButton').hidden=mode!=='error'||!unsavedCount();
  $('sessionProgress').textContent=mode==='error'?'尚有改动未保存':mode==='saving'?'正在保存…':'裁决已存于本机';
}
function toast(message,error=false) {
  clearTimeout(view.toastTimer); const node=$('toast'); node.textContent=message; node.className='toast'+(error?' error':''); node.hidden=false;
  view.toastTimer=setTimeout(()=>node.hidden=true,error?6500:3200);
}
async function fetchJSON(url,options={}) {
  const response=await fetch(url,{cache:'no-store',...options});
  let data;
  try { data=await response.json(); } catch { throw new Error(`本地服务返回了无法读取的内容（${response.status}）。`); }
  if (!response.ok) { const error=new Error(data.error?.message || data.message || (typeof data.error==='string'?data.error:null) || `请求失败（${response.status}）`); error.status=response.status; error.code=typeof data.error==='string'?data.error:data.error?.code; throw error; }
  return data;
}
function requestId() { return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`; }
function rememberView() {
  clearTimeout(view.viewTimer);
  view.viewTimer=setTimeout(()=>{ try { localStorage.setItem('listening-desk:view:'+view.project.project_id,JSON.stringify({mode:view.mode,selectedId:view.selectedId,sourceId:view.sourceId,position:view.position,context:view.context,loop:view.loop,speed:view.speed})); } catch {} },200);
}
function unsavedCount() {
  const items=new Set([...view.drafts.keys(),...view.failedRequests.keys()]);
  for(const timer of view.saveTimers.values())items.add(timer.itemId);
  for(const request of view.pendingSaves.values())items.add(request.itemId??'@undo');
  if(view.failedUndo)items.add('@undo');
  return items.size;
}
function refreshSaveStatus() {
  const failures=[...view.failedRequests.values(),...(view.failedUndo?[view.failedUndo]:[])];
  const message=failures.some(f=>f.kind==='project')?'录音项目已变化 · 改动未保存':failures.some(f=>f.kind==='conflict')?'版本冲突 · 等待确认':failures.length?'仍有裁决未保存':unsavedCount()?'仍有改动待保存':'已保存 · 本机';
  setSaveStatus(failures.length?'error':unsavedCount()?'saving':'',message);
}
function retainDraft(itemId,changes) {
  const draft={...(view.drafts.get(itemId)||{})},versions={...(view.draftVersions.get(itemId)||{})},epochs={...(view.draftEpochs.get(itemId)||{})};
  for(const [key,value]of Object.entries(changes)){draft[key]=value;versions[key]=++view.draftGeneration;epochs[key]=view.conflictEpoch;}
  if(Object.keys(draft).length){view.drafts.set(itemId,draft);view.draftVersions.set(itemId,versions);view.draftEpochs.set(itemId,epochs);}
}
function scheduleDraft(itemId,key,value) {
  retainDraft(itemId,{[key]:value});
  const timerKey=itemId+':'+key;
  clearTimeout(view.saveTimers.get(timerKey)?.timer);
  setSaveStatus('saving','正在编辑…');
  view.saveTimers.set(timerKey,{itemId,timer:setTimeout(()=>{view.saveTimers.delete(timerKey);saveDecision(itemId,{}, {quiet:true});},700)});
  if (key==='text') { $('restoreTextButton').hidden=value===currentItem()?.text;renderTextComparison(); }
}
function projectFingerprint() {
  const fingerprint=view.project?.fingerprint;
  if(typeof fingerprint!=='string'||!fingerprint.trim())throw new Error('当前录音项目缺少校验标识，请重新载入。');
  return fingerprint;
}
function acceptState(state,fingerprint=projectFingerprint(),{externalRead=false}={}) {
  if(state.fingerprint!==fingerprint){const error=new Error('录音项目已经变化；当前改动仍保留，请返回原项目保存。');error.status=409;error.code='project_mismatch';throw error;}
  if(externalRead&&view.state&&state.revision>view.state.revision)++view.conflictEpoch;
  view.state=state;
}
function newSaveRequest(itemId,changes,{explicit=false}={}){
  const epochs=view.draftEpochs.get(itemId)||{};
  return {itemId,changes:{...changes},versions:{...(view.draftVersions.get(itemId)||{})},conflictEpoch:explicit?view.conflictEpoch:Math.min(view.conflictEpoch,...Object.keys(changes).map(key=>epochs[key]??0)),projectFingerprint:projectFingerprint(),retryOf:view.failedRequests.get(itemId)?.request.requestId??null,requestId:requestId(),baseRevision:null};
}
function blockChangedQueue(request) {
  if(request.conflictEpoch===view.conflictEpoch)return false;
  if(!view.failedRequests.has(request.itemId))view.failedRequests.set(request.itemId,{kind:'conflict',request});
  refreshSaveStatus();return true;
}
function queueSave(request,operation) {
  const operationId=requestId();view.pendingSaves.set(operationId,request);
  const run=async()=>{try{return await operation();}finally{view.pendingSaves.delete(operationId);refreshSaveStatus();}};
  const result=view.saveChain.then(run,run);view.saveChain=result.then(()=>{},()=>{});return result;
}
async function submitSaveRequest(request,{quiet=false}={}) {
  const {itemId,changes:captured}=request;
  // Retain both the exact id and base revision if the response is lost after a write.
  if(request.baseRevision===null)request.baseRevision=view.state.revision;
  try {
    const next=await fetchJSON('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_id:itemId,changes:captured,base_revision:request.baseRevision,request_id:request.requestId,project_fingerprint:request.projectFingerprint})});
    acceptState(next,request.projectFingerprint);
    const remaining={...(view.drafts.get(itemId)||{})},versions={...(view.draftVersions.get(itemId)||{})},epochs={...(view.draftEpochs.get(itemId)||{})};
    for(const key of Object.keys(captured))if(versions[key]===request.versions[key]){delete remaining[key];delete versions[key];delete epochs[key];}
    if(Object.keys(remaining).length){view.drafts.set(itemId,remaining);view.draftVersions.set(itemId,versions);view.draftEpochs.set(itemId,epochs);}else{view.drafts.delete(itemId);view.draftVersions.delete(itemId);view.draftEpochs.delete(itemId);}
    if(view.failedRequests.get(itemId)?.request.requestId===request.requestId)view.failedRequests.delete(itemId);
    refreshSaveStatus();
    updatePersonFilter();filterItems({preserveScroll:true});renderDecision();renderContext();renderTextComparison();updateProgress();
    if(!quiet&&captured.status)toast(captured.status==='confirmed'?`已确认：${captured.speaker} · 仅当前句`:captured.status==='unknown'?'已记为无法辨认 · 可以稍后再听':'已跳过 · 可在整场目录找回');
    return true;
  } catch(error) {
    let kind=error.code==='project_mismatch'?'project':error.status===409?'conflict':'uncertain',refreshed=false;
    if(kind==='conflict'||kind==='project')++view.conflictEpoch;
    if(kind==='conflict'){
      try{acceptState(await fetchJSON('/api/state'),request.projectFingerprint);refreshed=true;}catch(readError){if(readError.code==='project_mismatch')kind='project';}
    }
    view.failedRequests.set(itemId,{kind,request});
    if(kind==='project'){
      setSaveStatus('error','录音项目已变化 · 改动未保存');toast('服务当前打开了另一份录音。当前文字和判断仍保留；请返回原录音项目后重试保存。',true);
    }else if(kind==='conflict'){
      setSaveStatus('error','版本冲突 · 未覆盖');
      toast('另一窗口已经更新裁决。'+(refreshed?'已读取最新版本；':'最新版本尚未读回；')+'本次判断尚未保存。请检查后点击“重试保存”或重新选择姓名。',true);
    }else{setSaveStatus('error','保存失败 · 请重试');toast('保存失败：'+error.message+'。本次判断仍保留，点击“重试保存”继续。',true);}
    renderDecision();renderList();updateProgress();
    return false;
  }
}
function saveDecision(itemId,changes,{quiet=false,explicit=!quiet}={}) {
  // Every field, including a name-only click, stays pending until the service confirms it.
  retainDraft(itemId,changes);
  const captured={...(view.drafts.get(itemId)||{})};
  for(const key of Object.keys(captured)){const timerKey=itemId+':'+key;clearTimeout(view.saveTimers.get(timerKey)?.timer);view.saveTimers.delete(timerKey);}
  setSaveStatus('saving','正在保存…');renderDecision();renderList();
  const request=newSaveRequest(itemId,captured,{explicit});
  const operation=async()=>{
    if(view.failedUndo){toast('上次撤销的结果尚未确认，当前改动已保留。请点击“重试保存”恢复。',true);return false;}
    if(blockChangedQueue(request))return false;
    const failed=view.failedRequests.get(itemId);
    if(failed){
      if(!explicit||request.retryOf!==failed.request.requestId){setSaveStatus('error',failed.kind==='conflict'?'版本冲突 · 等待确认':'仍有裁决未保存');return false;}
      if(failed.kind==='conflict'||failed.kind==='project'){
        // A new revision requires an explicit human retry and a new logical request.
        try{acceptState(await fetchJSON('/api/state'),request.projectFingerprint,{externalRead:true});}catch(error){if(error.code==='project_mismatch')failed.kind='project';toast(error.message,true);return false;}
        // This explicit retry consents to its readback, not to other queued edits.
        request.conflictEpoch=view.conflictEpoch;
        view.failedRequests.delete(itemId);
      }else{
        setSaveStatus('saving','正在重试同一裁决…');
        if(!(await submitSaveRequest(failed.request,{quiet:true})))return false;
        // An idempotent replay acknowledges an earlier revision. Another
        // window's later work must remain visible before a subsequent edit.
        try{acceptState(await fetchJSON('/api/state'),request.projectFingerprint,{externalRead:true});renderDecision();renderList();updateProgress();}
        catch(error){if(error.code==='project_mismatch')failed.kind='project';view.failedRequests.set(itemId,failed);setSaveStatus('error','已提交，读回待恢复');toast('已收到裁决回执，最新版本尚未读回。请重试恢复。',true);return false;}
        for(const key of Object.keys(request.changes))if(request.versions[key]===failed.request.versions[key])delete request.changes[key];
        if(!Object.keys(request.changes).length)return true;
      }
    }
    if(!Object.keys(request.changes).length)return true;
    if(blockChangedQueue(request))return false;
    return submitSaveRequest(request,{quiet});
  };
  return queueSave(request,operation);
}
async function undoDecision({retry=false}={}) {
  if (!view.state) return;
  // Do not silently discard typing when undoing a persisted decision.
  if (unsavedCount()&&!(retry&&view.failedUndo)) { toast('当前改动尚未保存，请先停笔等候保存，或点击顶部保存提示重试。',true); return; }
  setSaveStatus('saving','正在撤销…');
  const previous=retry?view.failedUndo:null;
  const request=previous&&previous.kind!=='conflict'?previous.request:{requestId:requestId(),projectFingerprint:previous?.request.projectFingerprint??projectFingerprint(),baseRevision:null};
  const operation=async()=>{
    try {
      if(previous&&previous.kind!=='uncertain')acceptState(await fetchJSON('/api/state'),request.projectFingerprint,{externalRead:true});
      if(request.baseRevision===null)request.baseRevision=view.state.revision;
      acceptState(await fetchJSON('/api/undo',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_revision:request.baseRevision,request_id:request.requestId,project_fingerprint:request.projectFingerprint})}),request.projectFingerprint);
      if(previous)acceptState(await fetchJSON('/api/state'),request.projectFingerprint,{externalRead:true});
      view.failedUndo=null;renderSelected({keepPosition:true});renderList();updateProgress();toast('已撤销最近一次裁决');return true;
    }catch(error){
      let kind=error.code==='project_mismatch'?'project':error.status===409?'conflict':'uncertain';
      if(kind==='conflict'||kind==='project')++view.conflictEpoch;
      if(kind==='conflict'){try{acceptState(await fetchJSON('/api/state'),request.projectFingerprint);renderSelected({keepPosition:true});renderList();}catch(readError){if(readError.code==='project_mismatch')kind='project';}}
      view.failedUndo={kind,request};toast('未能确认撤销结果：'+error.message+'。请检查后重试保存。',true);return false;
    }
  };
  return queueSave(request,operation);
}
function updateProgress() {
  const samples=view.mode==='samples',items=view.project.items.filter(i=>(i.kind==='speaker_sample')===samples);
  const count=items.filter(i=>identity(i)==='confirmed').length;
  const done=items.filter(i=>['confirmed','unknown','skipped'].includes(identity(i))).length;
  $('queueCount').textContent=items.length.toLocaleString();
  $('progressText').textContent=samples?`本轮 ${done} / ${items.length} 段已处理 · ${count} 段认出`:`已认人 ${count.toLocaleString()} / ${items.length.toLocaleString()} 句`;
}
function updatePersonFilter() {
  const names=[...new Set([...view.project.people.map(person=>person.name),...view.project.items.map(item=>personLabel(item))])].filter(name=>name&&name!=='未辨认');
  $('personFilter').innerHTML='<option value="">所有说话人</option>'+names.map(name=>`<option value="${escapeHTML(name)}">${escapeHTML(name)}</option>`).join('')+'<option value="__unknown">未知 / 无法辨认</option>';
  $('personFilter').value=view.person;
}
function roster() {
  const people=[...view.project.people],names=new Set(people.map(person=>person.name));
  for(const decision of Object.values(view.state.decisions||{})){if(decision.status==='confirmed'&&decision.speaker&&!names.has(decision.speaker)){people.push({name:decision.speaker,color:'#7b8069'});names.add(decision.speaker);}}
  return people;
}
function filterItems({preserveScroll=false}={}) {
  const previousScroll=$('itemList').scrollTop;
  const query=view.search.trim().toLocaleLowerCase();
  view.filtered=view.project.items.filter(item=>{
    if((view.mode==='samples')!==(item.kind==='speaker_sample')) return false;
    const data=effectiveItem(item), status=identity(item);
    if(view.person && (view.person==='__unknown' ? status!=='unknown'&&status!=='pending' : personLabel(item)!==view.person)) return false;
    if(view.pending && (status==='confirmed'||status==='skipped')) return false;
    return !query || [data.text,data.speaker,data.note,item.title].some(value=>String(value||'').toLocaleLowerCase().includes(query));
  }).sort((a,b)=>view.mode==='samples'?(Number(b.priority)||0)-(Number(a.priority)||0)||a.start-b.start:a.start-b.start);
  $('samplesTab').setAttribute('aria-selected',view.mode==='samples'); $('transcriptTab').setAttribute('aria-selected',view.mode==='transcript');
  $('pendingFilter').setAttribute('aria-pressed',view.pending);
  $('filteredCount').textContent=view.filtered.length.toLocaleString();
  $('listDescription').textContent=view.mode==='samples'?'声音需要一个名字':'让每一句回到说话人';
  updateProgress();
  $('listSpacer').style.height=view.filtered.length*ROW_HEIGHT+'px';
  $('emptyList').hidden=Boolean(view.filtered.length);
  $('itemList').scrollTop=preserveScroll?previousScroll:0;
  renderList();
}
function highlighted(value) {
  const text=String(value||''), query=view.search.trim(); if(!query) return escapeHTML(text);
  const index=text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
  return index<0?escapeHTML(text):escapeHTML(text.slice(0,index))+'<mark>'+escapeHTML(text.slice(index,index+query.length))+'</mark>'+escapeHTML(text.slice(index+query.length));
}
function renderList() {
  if (!view.project) return;
  const list=$('itemList'), start=Math.max(0,Math.floor(list.scrollTop/ROW_HEIGHT)-3),end=Math.min(view.filtered.length,start+Math.ceil(list.clientHeight/ROW_HEIGHT)+7);
  const rows=view.filtered.slice(start,end);
  $('listRows').style.transform=`translateY(${start*ROW_HEIGHT}px)`;
  $('listRows').innerHTML=rows.map((item,index)=>{
    const data=effectiveItem(item), active=item.id===view.selectedId, state=identity(item);
    return `<button class="queue-item${active?' active':''}" data-item-id="${escapeHTML(item.id)}" role="listitem"${active?' aria-current="true"':''} aria-label="${escapeHTML(formatTime(item.start)+' '+data.text)}"><span class="queue-item-top"><span class="queue-number">${view.mode==='samples'?'声样 '+String(start+index+1).padStart(2,'0'):String(start+index+1).padStart(4,'0')}</span><span>${formatTime(item.start)}</span><span class="item-state ${state}" title="${identityLabel(item)}"></span></span><span class="queue-item-text">${highlighted(data.text)}</span><span class="queue-item-person"><span class="candidate-dot"></span>${escapeHTML(personLabel(item))}<span>· ${identityLabel(item)}</span></span></button>`;
  }).join('');
}
function scrollToSelected() {
  const index=view.filtered.findIndex(i=>i.id===view.selectedId); if(index<0)return;
  const list=$('itemList'),top=index*ROW_HEIGHT;
  if(top<list.scrollTop||top+ROW_HEIGHT>list.scrollTop+list.clientHeight) list.scrollTop=Math.max(0,top-list.clientHeight/2+ROW_HEIGHT/2);
  renderList();
}
function chooseItem(itemId,{position=null,autoplay=false}={}) {
  const item=view.project.items.find(i=>i.id===itemId); if(!item)return;
  ++view.navigationGeneration;
  stopReference();pauseAudio({phase:'idle'});view.selectedId=itemId;view.position=position??item.start;
  if(!sourceCoverage(currentSource(),item)) view.sourceId=view.project.sources.find(s=>sourceCoverage(s,item))?.id||view.sourceId;
  renderSelected();renderList();rememberView();
  if(autoplay) playAudio();
}
function navigate(direction) {
  if(!view.filtered.length)return;
  const index=view.filtered.findIndex(i=>i.id===view.selectedId), next=index<0?0:Math.min(view.filtered.length-1,Math.max(0,index+direction));
  chooseItem(view.filtered[next].id);scrollToSelected();
}
function renderDecision() {
  const item=currentItem(); if(!item)return;
  const data=effectiveItem(item),state=identity(item);
  $('peopleChoices').innerHTML=roster().map((person,index)=>{
    const selected=state==='confirmed'&&data.speaker===person.name,candidate=state==='candidate'&&data.speaker===person.name;
    return `<button class="person-choice${selected?' selected':''}${candidate?' candidate':''}" data-person="${escapeHTML(person.name)}" aria-pressed="${selected}" style="--person-color:${escapeHTML(person.color||'#647a69')}"><span class="person-avatar">${escapeHTML(person.name.slice(-1))}</span><span class="person-name">${escapeHTML(person.name)}</span><svg class="person-check" aria-hidden="true"><use href="#i-check"/></svg>${index<4?'<kbd>'+(index+1)+'</kbd>':''}</button>`;
  }).join('');
  $('unknownButton').classList.toggle('selected',state==='unknown');$('unknownButton').setAttribute('aria-pressed',state==='unknown');
  $('skipButton').classList.toggle('selected',state==='skipped');$('skipButton').setAttribute('aria-pressed',state==='skipped');
  const status=$('currentStatus');status.textContent=state==='confirmed'?`${data.speaker} · 人工确认`:state==='candidate'?`${data.speaker} · 模型候选`:identityLabel(item);status.className='identity-badge '+state;
  const explanation=state==='unsaved'?`待保存：${escapeHTML(data.status==='unknown'?'无法辨认':data.status==='skipped'?'跳过这一句':data.speaker||'当前判断')}。尚未写入本机。`:state==='confirmed'?`<strong>${escapeHTML(data.speaker||'已确认')}</strong> · 人工确认，仅当前句`:state==='candidate'?`${escapeHTML(data.speaker||'未辨认')} · 模型候选，尚未人工确认`:state==='unknown'?'已记为无法辨认，可继续保留待审':state==='skipped'?'已跳过，原始候选与文字保留':'尚未裁决，原始身份保持未知';
  $('judgmentSummary').innerHTML='<span class="eyebrow">当前判断</span><p>'+explanation+'</p>';
  $('decisionHint').textContent='选一个名字，即保存当前'+(item.kind==='speaker_sample'?'声样':'句')+'。';
  const note=$('noteEditor');
  if(document.activeElement!==note||note.dataset.itemId!==item.id){note.value=data.note||'';note.dataset.itemId=item.id;}
  renderReferences();
}
function renderSelected({keepPosition=false}={}) {
  const item=currentItem();if(!item)return;
  const data=effectiveItem(item),index=view.filtered.findIndex(i=>i.id===item.id);
  const isSample=item.kind==='speaker_sample';
  $('currentKind').textContent=isSample?'声样 · '+(item.title||'为这段声音确认身份'):'逐句听音 · 文字校勘';
  $('currentOrdinal').textContent=index<0?'当前句在筛选之外':`${String(index+1).padStart(2,'0')} / ${view.filtered.length.toLocaleString()}`;
  $('currentTime').textContent=`${formatTime(item.start)} — ${formatTime(item.end)}`;
  $('currentDuration').textContent=Math.max(0,item.end-item.start).toFixed(1)+' s';
  const editor=$('transcriptEditor');
  if(isSample||document.activeElement!==editor||editor.dataset.itemId!==item.id){editor.value=data.text||'';editor.dataset.itemId=item.id;}
  $('transcriptEditor').readOnly=isSample;
  $('transcriptEditor').closest('.sentence-paper').classList.toggle('is-sample',isSample);
  $('transcriptEditorLabel').textContent=isSample?'声样定位提示，非逐字稿，只读':'当前句文字，可直接修改';
  $('editNearbyTranscript').hidden=!isSample;
  $('restoreTextButton').hidden=isSample||(data.text||'')===(item.text||'');
  $('editorHint').textContent=isSample?'定位提示（只读）· 以原音认声':(item.text_note||'停笔保存 · Esc 返回听音');
  $('editorObjectLabel').textContent=isSample?'声样定位提示 · 只读':'逐字稿原句 · 可编辑';
  $('returnSampleButton').hidden=isSample||!view.returnSampleId;
  sizeEditor();
  renderDecision();renderTextComparison();renderWaveTracks();renderContext();drawOverview();
  $('previousButton').disabled=!view.filtered.length||index===0;$('nextButton').disabled=!view.filtered.length||index===view.filtered.length-1;
  $('contextButton').setAttribute('aria-pressed',view.context);$('loopButton').setAttribute('aria-pressed',view.loop);$('speedSelect').value=String(view.speed);
  updatePosition();
}
function sizeEditor(){const editor=$('transcriptEditor');editor.style.height='auto';editor.style.height=Math.min(190,Math.max(64,editor.scrollHeight))+'px';}
function renderTextComparison(){
  const item=currentItem();if(!item)return;
  const changed=item.kind==='transcript'&&effectiveItem(item).text!==item.text;
  $('textComparison').hidden=!changed;
  if(changed){$('originalText').textContent=item.text;$('revisedText').textContent=effectiveItem(item).text;}
}
function contextItems() {
  const item=currentItem();if(!item)return {transcript:[],index:0};
  const intervals=view.project.sources.map(source=>({start:canonicalTime(source,0),end:canonicalTime(source,sourceDuration(source))})).filter(interval=>Number.isFinite(interval.end)).sort((a,b)=>a.start-b.start);
  const regions=[];
  for(const interval of intervals){const previous=regions.at(-1);if(previous&&interval.start<=previous.end)previous.end=Math.max(previous.end,interval.end);else regions.push({...interval});}
  const region=regions.find(range=>range.start<=item.start&&range.end>=item.end);
  const start=Math.max(item.start-30,region?.start??item.start),end=Math.min(item.end+30,region?.end??item.end);
  const transcript=view.project.items.filter(i=>i.kind==='transcript'&&i.end>=start&&i.start<=end&&i.start>= (region?.start??item.start)&&i.end<= (region?.end??item.end)).sort((a,b)=>a.start-b.start);
  let index=transcript.findIndex(i=>i.id===item.id);
  if(index<0)index=transcript.findIndex(i=>i.start>=item.start);
  if(index<0)index=transcript.length-1;
  return {transcript,index};
}
function contextHTML(items,includeCurrent=true) {
  return items.map(item=>`<div class="context-row${item.id===view.selectedId?' current':''}"><button data-context-id="${escapeHTML(item.id)}" title="跳到这句原音">${formatTime(item.start)}</button><p><span class="context-person">${escapeHTML(personLabel(item))}</span>${escapeHTML(effectiveItem(item).text)}</p></div>`).join('');
}
function renderContext() {
  const {transcript,index}=contextItems();
  let rows=transcript.slice(Math.max(0,index-1),Math.min(transcript.length,index+2));
  $('contextPreview').innerHTML=rows.length?contextHTML(rows):'<div class="context-row"><p>这段录音附近没有逐字稿。</p></div>';
  $('fullContext').innerHTML=transcript.length?contextHTML(transcript):'<div class="context-row"><p>这段录音附近没有逐字稿。</p></div>';
}
function canvasContext(canvas) {
  const bounds=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio||1;
  const width=Math.max(1,bounds.width),height=Math.max(1,bounds.height);
  if(canvas.width!==Math.round(width*ratio)||canvas.height!==Math.round(height*ratio)){canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);}
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
  return {ctx,width,height};
}
function peakAt(source,start,end) {
  const peaks=source.peaks||[]; if(!peaks.length)return null;
  const duration=Number(source.duration),from=Math.max(0,Math.floor(start/duration*peaks.length)),to=Math.min(peaks.length,Math.ceil(end/duration*peaks.length));
  let value=0;
  for(let i=from;i<to;i++){const peak=Array.isArray(peaks[i])?Math.max(...peaks[i].map(Math.abs)):Math.abs(Number(peaks[i]));if(Number.isFinite(peak))value=Math.max(value,peak);}
  return Math.min(1,value);
}
function renderWaveTracks() {
  const item=currentItem(),window=clipWindow(item);
  const availableSources=view.project.sources.filter(source=>sourceCoverage(source,item));
  $('syncSummary').textContent=availableSources.length>1?'同一录音时刻 · 可切换对听':`此处仅 ${availableSources.map(source=>source.id).join('、')} 有录音`;
  $('waveTracks').innerHTML=view.project.sources.map((source,index)=>{
    const available=Boolean(sourceCoverage(source,item)),letter=source.id.length===1?source.id.toUpperCase():String.fromCharCode(65+index);
    return `<div class="wave-track${available?'':' unavailable'}" data-track="${escapeHTML(source.id)}"><button class="source-button${source.id===view.sourceId?' active':''}" data-source="${escapeHTML(source.id)}"${available?'':' disabled'} aria-label="切换到${escapeHTML(source.label||'来源 '+letter)}" aria-pressed="${source.id===view.sourceId}"><span class="device-letter">${escapeHTML(letter)}</span><span class="device-label">来源 ${escapeHTML(letter)}</span></button><canvas data-wave-source="${escapeHTML(source.id)}" tabindex="${available?'0':'-1'}" role="slider" aria-label="${escapeHTML(source.label||'来源 '+letter)}当前片段原音波形" aria-valuemin="${window.start}" aria-valuemax="${window.end}" aria-valuenow="${view.position}"></canvas></div>`;
  }).join('');
  $('timeRuler').innerHTML=Array.from({length:5},(_,i)=>`<span>${formatTime(window.start+(window.end-window.start)*i/4,true)}</span>`).join('');
  $('sessionSource').textContent=currentSource()?.label||'原始录音';
  drawTracks();
  $('playButton').disabled=!sourceCoverage(currentSource());
  const coverage=sourceCoverage(currentSource());
  if(!coverage)audioMessage('该来源未覆盖这段录音，请切换其他来源。',true);
  else if(view.audioPhase==='idle')setAudioPhase('idle');
}
function drawTracks() {
  if(!view.project||!currentItem())return;
  const item=currentItem(),window=clipWindow(item),span=Math.max(.01,window.end-window.start);
  document.querySelectorAll('[data-wave-source]').forEach(canvas=>{
    const source=view.project.sources.find(s=>s.id===canvas.dataset.waveSource),{ctx,width,height}=canvasContext(canvas),active=source.id===view.sourceId;
    ctx.strokeStyle='#d8dcd0';ctx.lineWidth=.5;ctx.beginPath();ctx.moveTo(0,height/2+.5);ctx.lineTo(width,height/2+.5);ctx.stroke();
    for(let x=0;x<width;x+=3){
      const a=window.start+x/width*span,b=window.start+(x+3)/width*span,localA=sourceTime(source,a),localB=sourceTime(source,b);
      if(localB<0||localA>source.duration){if(x%9===0){ctx.strokeStyle='#d3d6c9';ctx.beginPath();ctx.moveTo(x,height-6);ctx.lineTo(x+12,6);ctx.stroke();}continue;}
      const peak=peakAt(source,Math.max(0,localA),Math.min(source.duration,localB));
      if(peak===null)continue;
      const h=Math.max(1.2,Math.pow(peak,.68)*(height-5));
      ctx.fillStyle=active?(a<view.position?'#b45032':'#8c9b86'):'#b6bfb0';ctx.fillRect(x,(height-h)/2,1.5,h);
    }
    if(!(source.peaks||[]).length){ctx.fillStyle='#81847b';ctx.font='10px sans-serif';ctx.fillText('尚无波形数据 · 原音仍可播放',12,height/2+3);}
    const selectionStart=(item.start-window.start)/span*width,selectionEnd=(item.end-window.start)/span*width;
    if(view.context){ctx.fillStyle='#b4503209';ctx.fillRect(selectionStart,0,selectionEnd-selectionStart,height);}
    const playhead=(view.position-window.start)/span*width;
    if(playhead>=0&&playhead<=width){ctx.strokeStyle=active?'#b45032':'#8b9686';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(playhead+.5,0);ctx.lineTo(playhead+.5,height);ctx.stroke();if(active){ctx.fillStyle='#b45032';ctx.beginPath();ctx.moveTo(playhead-3,0);ctx.lineTo(playhead+3,0);ctx.lineTo(playhead,4);ctx.fill();}}
    if(!sourceCoverage(source,item)){ctx.fillStyle='#777f70';ctx.font='11px sans-serif';ctx.fillText(sourceTime(source,window.end)<=0?'此来源尚未开始录音':'此来源已结束录音',12,height/2+3);}
    canvas.setAttribute('aria-valuenow',view.position.toFixed(2));
  });
}
function drawOverview() {
  if(!view.project)return;
  const source=currentSource()||view.project.sources[0],canvas=$('overviewCanvas'),{ctx,width,height}=canvasContext(canvas),duration=meetingEnd(),item=currentItem();
  for(let x=0;x<width;x+=3){const start=sourceTime(source,x/width*duration),end=sourceTime(source,(x+3)/width*duration);if(end<0||start>source.duration)continue;const peak=peakAt(source,Math.max(0,start),Math.min(source.duration,end));if(peak===null)continue;const h=Math.max(1,Math.pow(peak,.8)*(height-12));ctx.fillStyle=x/width*duration<view.position?'#8c9a83':'#cbd1c2';ctx.fillRect(x,(height-h)/2,1.3,h);}
  if(item){const x=item.start/duration*width,w=Math.max(3,(item.end-item.start)/duration*width);ctx.fillStyle='#b4503323';ctx.fillRect(x,0,w,height);ctx.fillStyle='#b45032';ctx.fillRect(x,0,Math.max(2,w),2);}
  const x=view.position/duration*width;ctx.strokeStyle='#b45032';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();
  ctx.fillStyle='#b45032';ctx.beginPath();ctx.moveTo(x-3,0);ctx.lineTo(x+3,0);ctx.lineTo(x,5);ctx.fill();
  canvas.setAttribute('aria-valuemax',duration);canvas.setAttribute('aria-valuenow',view.position.toFixed(2));canvas.setAttribute('aria-valuetext',formatTime(view.position));
}
function updatePosition() { $('positionLabel').textContent='录音 '+formatTime(view.position,true);drawTracks();drawOverview();rememberView(); }
function audioMessage(message,warning=false){$('audioMessage').textContent=message;$('audioMessage').classList.toggle('warning',warning);}
function playbackActive(){return ['loading','buffering','playing'].includes(view.audioPhase);}
function updatePlayButton(){
  const button=$('playButton'),active=playbackActive();
  const label=({loading:'取消读取',buffering:'暂停',playing:'暂停',error:'重试原音',ended:'再听一次'})[view.audioPhase]||'听原音';
  button.classList.toggle('playing',active);button.innerHTML=svg(active?'pause':'play')+'<span>'+label+'</span><kbd>Q</kbd>';
  button.setAttribute('aria-label',label+' · 当前片段 · Q 或空格');
}
function setAudioPhase(phase,message=null){
  view.audioPhase=phase;view.playing=phase==='playing';
  const labels={idle:'准备就绪',loading:'正在读取',buffering:'等待缓冲',playing:'播放中',paused:'已暂停',ended:'片段结束',error:'读取失败'};
  $('playbackStatus').textContent=labels[phase]||labels.idle;$('audioDesk').dataset.phase=phase;
  const source=currentSource(),label=source?.label||'原音';
  const clip=view.audio?.reviewClip;
  const matchesClip=clip?.bounded&&clip.project_fingerprint===view.project?.fingerprint&&clip.item_id===view.selectedId&&clip.source_id===view.sourceId&&clip.context===(view.context?3:0)&&clip.reference===0;
  const coverage=sourceCoverage(source),isPartial=matchesClip?!clip.coverage_complete:Boolean(coverage?.partial);
  const messages={idle:'点「听原音」开始；Q 或空格可播放与暂停。',loading:'正在读取 '+label+'…',buffering:'原音正在缓冲；可暂停或切换来源。',playing:'正在播放 '+label+(view.loop?' · 循环片段':isPartial?' · 到可用原音末尾停止':' · 到句尾停止'),paused:'已暂停 · 继续会从当前时刻播放。',ended:(isPartial?'可用原音已播完':'本段已播完')+' · 可以重听或确认说话人。',error:'原音读取失败 · 点「重试原音」重新加载。'};
  const partial=isPartial?' · 此来源只覆盖本段部分原音':'';
  const approximate=source?.bounded_clip===false?' · 此格式按播放进度停止，句尾可能有延迟':'';
  audioMessage((message||messages[phase]||messages.idle)+partial+approximate,phase==='error'||Boolean(partial));updatePlayButton();
}
function pauseAudio({phase='paused',message=null}={}) {
  ++view.audioToken;
  if(view.cancelAudioWait)view.cancelAudioWait();
  if(view.audio)view.audio.pause();
  setAudioPhase(phase,message);
}
function audioIsCurrent(audio){
  const binding=audio.reviewBinding;
  return audio===view.audio&&binding?.token===view.audioToken&&binding.itemId===view.selectedId&&binding.sourceId===view.sourceId;
}
function legacyPlayback(source) {
  if(source.bounded_clip!==false)throw new Error('原音缺少片段播放信息，请重新载入项目。');
  return {bounded:false,local_start:0,local_end:Number(source.duration),duration:Number(source.duration),media_url:source.media_url||'/media/'+encodeURIComponent(source.id)};
}
async function requestBoundedClip(source,item,{reference=false,holder=view,cancelKey='cancelAudioWait'}={}) {
  const fingerprint=projectFingerprint(),context=reference?0:view.context?3:0;
  const query=new URLSearchParams({project_fingerprint:fingerprint,item_id:item.id,source_id:source.id,context:String(context),reference:reference?'1':'0'});
  const url='/api/clip?'+query;
  if(!reference&&view.audio?.reviewClip?.requestURL===url&&!view.audio.reviewFailed&&!view.audio.error)return view.audio.reviewClip;
  const controller=new AbortController();let cancel,timeout;
  const interrupted=new Promise((resolve,reject)=>{
    cancel=()=>{controller.abort();const error=new Error('播放已取消');error.name='AbortError';reject(error);};
    timeout=setTimeout(()=>{controller.abort();reject(new Error('读取音频片段超时'));},10000);
    holder[cancelKey]=cancel;
  });
  try{
    const clip=await Promise.race([fetchJSON(url,{signal:controller.signal}),interrupted]);
    const close=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=32*Number.EPSILON*Math.max(1,Math.abs(a),Math.abs(b));
    if(clip.project_fingerprint!==fingerprint||clip.item_id!==item.id||clip.source_id!==source.id||clip.context!==context||clip.reference!==Number(reference)||
      !Number.isInteger(clip.start_frame)||!Number.isInteger(clip.end_frame)||clip.start_frame<0||clip.end_frame<=clip.start_frame||
      !Number.isInteger(clip.sample_rate)||clip.sample_rate<=0||clip.sample_rate!==source.sample_rate||
      !close(clip.local_start,clip.start_frame/clip.sample_rate)||!close(clip.local_end,clip.end_frame/clip.sample_rate)||
      !close(clip.duration,(clip.end_frame-clip.start_frame)/clip.sample_rate)||
      !close(clip.canonical_start,canonicalTime(source,clip.local_start))||!close(clip.canonical_end,canonicalTime(source,clip.local_end))||
      typeof clip.coverage_complete!=='boolean'||typeof clip.media_url!=='string'||!clip.media_url.startsWith('/clip?'))throw new Error('音频片段信息与当前录音不匹配，请重新载入项目。');
    return {...clip,bounded:true,requestURL:url};
  }finally{clearTimeout(timeout);if(holder[cancelKey]===cancel)holder[cancelKey]=null;}
}
function createAudio(source,clip) {
  if(view.audio&&view.audio.dataset.sourceId===source.id&&view.audio.reviewClip.media_url===clip.media_url&&!view.audio.reviewFailed&&!view.audio.error)return view.audio;
  const previous=view.audio;view.audio=null;
  if(previous){previous.pause();previous.removeAttribute('src');previous.load();}
  const audio=new Audio();audio.dataset.sourceId=source.id;audio.reviewClip=clip;audio.preload='metadata';audio.playbackRate=view.speed;audio.volume=view.volume;view.audio=audio;
  audio.addEventListener('playing',()=>{if(audioIsCurrent(audio)&&!audio.paused)setAudioPhase('playing');});
  audio.addEventListener('waiting',()=>{if(audioIsCurrent(audio)&&!audio.paused)setAudioPhase('buffering');});
  audio.addEventListener('pause',()=>{if(audioIsCurrent(audio)&&audio.paused&&!['ended','error'].includes(view.audioPhase))setAudioPhase('paused');});
  audio.addEventListener('timeupdate',()=>{
    // Pause/navigation invalidates the binding before any queued event can run.
    if(!audioIsCurrent(audio)||audio.paused||audio.seeking)return;
    const coverage=sourceCoverage(source);if(!coverage)return;
    const local=audio.reviewClip.local_start+audio.currentTime;
    view.position=canonicalTime(source,Math.max(coverage.start,Math.min(coverage.end,local)));
    if(!clip.bounded&&local>=coverage.end-.025){if(view.loop){audio.currentTime=coverage.start;view.position=canonicalTime(source,coverage.start);}else{pauseAudio({phase:'ended'});}}
    updatePosition();
  });
  audio.addEventListener('ended',()=>{if(!audioIsCurrent(audio))return;view.position=canonicalTime(source,clip.bounded?clip.local_end:sourceCoverage(source).end);updatePosition();if(view.loop)playAudio({restart:true});else pauseAudio({phase:'ended'});});
  audio.addEventListener('error',()=>{audio.reviewFailed=true;if(audio===view.audio&&source.id===view.sourceId&&(audioIsCurrent(audio)||view.audioPhase==='loading'))pauseAudio({phase:'error'});});
  audio.src=clip.media_url;
  return audio;
}
function waitForAudio(audio,event,ready,token){
  if(ready())return Promise.resolve();
  return new Promise((resolve,reject)=>{
    const done=()=>{cleanup();resolve();},fail=()=>{cleanup();reject(new Error('无法读取原音'));};
    const cancel=()=>{cleanup();const error=new Error('播放已取消');error.name='AbortError';reject(error);};
    const timeout=setTimeout(()=>{cleanup();audio.reviewFailed=true;reject(new Error('读取原音超时'));},10000);
    function cleanup(){clearTimeout(timeout);audio.removeEventListener(event,done);audio.removeEventListener('error',fail);if(view.cancelAudioWait===cancel)view.cancelAudioWait=null;}
    audio.addEventListener(event,done,{once:true});audio.addEventListener('error',fail,{once:true});view.cancelAudioWait=cancel;
    if(token!==view.audioToken)cancel();else if(ready())done();
  });
}
async function seekAudio(audio,time,token) {
  await waitForAudio(audio,'loadedmetadata',()=>audio.readyState>=1,token);
  if(token!==view.audioToken)return false;
  audio.currentTime=Math.min(Math.max(0,time),Number.isFinite(audio.duration)?Math.max(0,audio.duration-.02):time);
  await waitForAudio(audio,'seeked',()=>!audio.seeking,token);
  return token===view.audioToken;
}
async function playAudio({restart=false}={}) {
  const source=currentSource(),coverage=sourceCoverage(source);if(!coverage){audioMessage('该来源未覆盖这段录音，请切换其他来源。',true);return;}
  stopReference();pauseAudio({phase:'loading'});
  const token=view.audioToken,item=currentItem();let audio;
  let local=sourceTime(source,view.position);if(restart||local<coverage.start||local>=coverage.end-.06)local=coverage.start;
  try{
    const clip=source.bounded_clip===true?await requestBoundedClip(source,item):legacyPlayback(source);
    if(token!==view.audioToken)return;
    audio=createAudio(source,clip);audio.playbackRate=view.speed;
    if(!(await seekAudio(audio,local-clip.local_start,token)))return;
    audio.reviewBinding={token,itemId:view.selectedId,sourceId:source.id};
    await audio.play();
    if(token!==view.audioToken){if(audio.reviewBinding?.token===token)audio.pause();return;}
    // A fulfilled play promise confirms playback started, not audible output.
    if(!audio.paused)setAudioPhase('playing');
  }catch(error){if(token!==view.audioToken||error.name==='AbortError')return;if(audio)audio.reviewFailed=error.name!=='NotAllowedError';pauseAudio({phase:'error',message:error.name==='NotAllowedError'?'浏览器阻止播放 · 请直接点击「重试原音」。':'原音读取失败：'+error.message+' · 可重试。'});}
}
function togglePlayback(){playbackActive()?pauseAudio():playAudio();}
async function switchSource(sourceId,{position=null,autoplay=null}={}) {
  const source=view.project.sources.find(s=>s.id===sourceId);if(!source||!sourceCoverage(source))return;
  ++view.navigationGeneration;
  const wasPlaying=autoplay??playbackActive();
  pauseAudio({phase:'idle'});stopReference();if(position!==null)view.position=position;
  view.sourceId=sourceId;renderWaveTracks();updatePosition();rememberView();
  if(wasPlaying)await playAudio();
}
function waveformSeek(canvas,event){
  const source=view.project.sources.find(s=>s.id===canvas.dataset.waveSource);if(!sourceCoverage(source))return;
  const rect=canvas.getBoundingClientRect(),window=clipWindow(),canonical=window.start+Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*(window.end-window.start),wasPlaying=playbackActive();
  switchSource(source.id,{position:canonical,autoplay:wasPlaying});
}
function timelineSeek(position) {
  const items=view.project.items.filter(i=>i.kind==='transcript').sort((a,b)=>a.start-b.start);if(!items.length)return;
  let best=items[0],distance=Infinity;
  for(const item of items){const d=position>=item.start&&position<=item.end?0:Math.min(Math.abs(item.start-position),Math.abs(item.end-position));if(d<distance){best=item;distance=d;}if(item.start>position&&d>distance)break;}
  const wasPlaying=playbackActive();view.mode='transcript';filterItems();chooseItem(best.id,{position,autoplay:wasPlaying});scrollToSelected();
}
function openNearbyTranscript(){
  const sample=currentItem(),center=(sample.start+sample.end)/2;
  view.returnSampleId=sample.id;
  const items=contextItems().transcript;
  if(!items.length){toast('这段录音附近没有可校对的逐字稿。',true);return;}
  const nearest=items.reduce((best,item)=>{const distance=center>=item.start&&center<=item.end?0:Math.min(Math.abs(item.start-center),Math.abs(item.end-center));return !best||distance<best.distance?{item,distance}:best;},null).item;
  view.mode='transcript';view.search='';view.person='';view.pending=false;$('searchInput').value='';$('personFilter').value='';filterItems();chooseItem(nearest.id);scrollToSelected();$('transcriptEditor').focus();toast('已定位到真实逐字稿。可直接修改文字，停笔后保存。');
}
function referenceExcerpt(item){
  const sources=[...view.project.sources].sort((a,b)=>Number(b.id===item.source_id)-Number(a.id===item.source_id));
  for(const source of sources){
    // PCM references use the server's canonical interval; ordinary media
    // retains its eight audio-second cap. Require that entire excerpt.
    const end=source.bounded_clip===true?Math.min(item.end,item.start+8):Math.min(item.end,canonicalTime(source,sourceTime(source,item.start)+8));
    const coverage=sourceCoverage(source,{...item,end},{context:false});
    if(coverage&&!coverage.partial)return {source,start:coverage.start,end:coverage.end};
  }
  return null;
}
function confirmedReferences(){
  const byName=new Map();
  for(const item of view.project?.items||[]){
    if(identity(item)!=='confirmed'||item.id===view.selectedId)continue;
    const name=personLabel(item);if(!name||name==='未辨认')continue;
    const excerpt=referenceExcerpt(item);if(!excerpt)continue;
    const old=byName.get(name);
    // Prefer a useful spoken phrase over a very short acknowledgement.
    const previous=old&&referenceExcerpt(old);
    if(!previous||excerpt.end-excerpt.start>previous.end-previous.start)byName.set(name,item);
  }
  return [...byName.values()];
}
function renderReferences(){
  const items=confirmedReferences(),active=view.reference;
  $('referenceCount').textContent=items.length?items.length+' 人':'暂无';
  $('referenceChoices').innerHTML=items.map(item=>{
    const playing=active?.itemId===item.id;
    return `<button class="reference-choice${playing?' active':''}" data-reference-id="${escapeHTML(item.id)}" aria-pressed="${playing}">${svg(playing?'pause':'play')}<span>${escapeHTML(personLabel(item))}</span><span class="mono">${formatTime(item.start)}</span></button>`;
  }).join('');
  if(active&&!items.some(i=>i.id===active.itemId)){stopReference();return;}
  if(!active)$('referenceMessage').textContent=items.length?'只听已确认的原音，不改变当前判断。':'确认一段原音后，可在这里与其他片段对听。';
  $('resumeCurrentButton').hidden=!active;
}
function stopReference(){
  ++view.referenceToken;const active=view.reference;view.reference=null;
  if(active){active.cancel?.();if(active.audio){active.audio.pause();active.audio.removeAttribute('src');active.audio.load();}}
  if(view.project)renderReferences();
}
async function playReference(itemId){
  if(view.reference?.itemId===itemId){stopReference();return;}
  const item=confirmedReferences().find(i=>i.id===itemId);if(!item)return;
  pauseAudio();stopReference();
  const excerpt=referenceExcerpt(item);
  if(!excerpt){$('referenceMessage').textContent='这段参照音没有完整音频覆盖。';return;}
  const {source,start,end}=excerpt;
  const token=view.referenceToken;
  let audio;const active={itemId,sourceId:source.id,audio:null,cancel:null};view.reference=active;
  const current=()=>view.reference===active&&token===view.referenceToken;
  const finish=message=>{if(!current())return;stopReference();$('referenceMessage').textContent=message;};
  renderReferences();$('referenceMessage').textContent='正在读取参照音…';
  async function wait(event,ready){
    if(ready())return;
    await new Promise((resolve,reject)=>{
      const done=()=>{cleanup();resolve();},fail=()=>{cleanup();reject(new Error('无法读取参照音'));};
      const cancel=()=>{cleanup();reject(new Error('已取消'));};
      const timer=setTimeout(fail,10000);
      function cleanup(){clearTimeout(timer);audio.removeEventListener(event,done);audio.removeEventListener('error',fail);if(active.cancel===cancel)active.cancel=null;}
      audio.addEventListener(event,done,{once:true});audio.addEventListener('error',fail,{once:true});active.cancel=cancel;
      if(!current())cancel();else if(ready())done();
    });
  }
  try{
    const clip=source.bounded_clip===true?await requestBoundedClip(source,item,{reference:true,holder:active,cancelKey:'cancel'}):legacyPlayback(source);
    if(!current())return;
    if(clip.bounded&&!clip.coverage_complete){finish('这段参照音没有完整音频覆盖，未开始播放。');return;}
    audio=new Audio();active.audio=audio;audio.volume=view.volume;audio.preload='metadata';
    audio.addEventListener('playing',()=>{if(current())$('referenceMessage').textContent='参照音：'+personLabel(item)+' · '+(source.label||source.id)+' · 最多 8 秒'+(clip.bounded?'':' · 此格式停止可能有延迟');});
    audio.addEventListener('timeupdate',()=>{if(current()&&!clip.bounded&&audio.currentTime>=end)finish('参照音已播完 · 当前句和判断都保留。');});
    audio.addEventListener('ended',()=>finish('参照音已播完 · 当前句和判断都保留。'));
    audio.addEventListener('error',()=>finish('参照音读取失败 · 点击姓名可重新加载。'));
    audio.src=clip.media_url;
    await wait('loadedmetadata',()=>audio.readyState>=1);if(!current())return;
    audio.currentTime=Math.max(0,start-clip.local_start);await wait('seeked',()=>!audio.seeking);if(!current())return;
    await audio.play();if(!current()){audio.pause();return;}
  }catch(error){finish('参照音未开始播放：'+error.message+' · 点击姓名重试。');}
}
function setVolume(value){
  view.volume=Math.max(0,Math.min(1,Number(value)||0));
  for(const audio of [view.audio,view.reference?.audio])if(audio){audio.volume=view.volume;audio.muted=view.volume===0;}
  $('volumeValue').textContent=view.volume===0?'静音':Math.round(view.volume*100)+'%';
}
function handleShortcut(event){
  if(event.defaultPrevented||event.metaKey||event.ctrlKey||event.altKey||event.isComposing)return;
  const editing=event.target.closest('input,textarea,select,[contenteditable="true"]');
  if(editing&&!editing.readOnly){
    if(event.key==='Escape'&&editing.matches('textarea,input[type="text"],input:not([type])')){event.preventDefault();$('playButton').focus();}
    return;
  }
  if(document.querySelector('dialog[open]'))return;
  const key=event.key.toLowerCase();if(event.repeat&&['1','2','3','4','u','s','z'].includes(key))return;
  if(key==='q'||event.code==='Space'){event.preventDefault();togglePlayback();}
  else if(/^[1-4]$/.test(key)){const person=view.project?.people[Number(key)-1];if(person){event.preventDefault();confirmPerson(person.name);}}
  else if(key==='u'){event.preventDefault();markUnknown();}else if(key==='s'){event.preventDefault();skipItem();}
  else if(key==='j'){event.preventDefault();navigate(1);scrollToSelected();}else if(key==='k'){event.preventDefault();navigate(-1);scrollToSelected();}
  else if(key==='z'){event.preventDefault();undoDecision();}else if(key==='/'){event.preventDefault();$('searchInput').focus();}
}
function confirmPerson(name){const item=currentItem();if(item)saveDecision(item.id,{speaker:name,status:'confirmed'});}
function markUnknown(){const item=currentItem();if(item)saveDecision(item.id,{speaker:'',status:'unknown'});}
function skipItem(){const item=currentItem();if(!item)return;const generation=view.navigationGeneration,index=view.filtered.findIndex(i=>i.id===item.id),next=view.filtered[index+1]||view.filtered[index-1];saveDecision(item.id,{status:'skipped'}).then(ok=>{if(ok&&next&&view.selectedId===item.id&&view.navigationGeneration===generation){chooseItem(next.id);scrollToSelected();}});}
async function retryUnsaved(){if(view.failedUndo&&!(await undoDecision({retry:true})))return false;const operations=[];for(const id of new Set([...view.drafts.keys(),...view.failedRequests.keys()]))operations.push(saveDecision(id,{}, {quiet:true,explicit:true}));return Promise.all(operations);}
function flushBeforeExport(){const operations=[];for(const id of view.drafts.keys())if(!view.failedRequests.has(id))operations.push(saveDecision(id,{}, {quiet:true,explicit:false}));return Promise.all(operations);}
function bindEvents(){
  $('listRows').addEventListener('click',event=>{const button=event.target.closest('[data-item-id]');if(button)chooseItem(button.dataset.itemId);});
  $('itemList').addEventListener('scroll',()=>requestAnimationFrame(renderList),{passive:true});
  document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{view.mode=button.dataset.mode;filterItems();if(view.filtered.length&&!view.filtered.some(i=>i.id===view.selectedId))chooseItem(view.filtered[0].id);else renderSelected({keepPosition:true});rememberView();}));
  $('searchInput').addEventListener('input',event=>{view.search=event.target.value;filterItems();renderSelected({keepPosition:true});});
  $('personFilter').addEventListener('change',event=>{view.person=event.target.value;filterItems();renderSelected({keepPosition:true});});
  $('pendingFilter').addEventListener('click',()=>{view.pending=!view.pending;filterItems();renderSelected({keepPosition:true});});
  $('clearFilters').addEventListener('click',()=>{view.search='';view.person='';view.pending=false;$('searchInput').value='';$('personFilter').value='';filterItems();renderSelected({keepPosition:true});});
  $('transcriptEditor').addEventListener('input',event=>{sizeEditor();const item=currentItem();if(item&&item.kind==='transcript')scheduleDraft(item.id,'text',event.target.value);});
  $('noteEditor').addEventListener('input',event=>{const item=currentItem();if(item)scheduleDraft(item.id,'note',event.target.value);});
  $('restoreTextButton').addEventListener('click',()=>{const item=currentItem();$('transcriptEditor').value=item.text;scheduleDraft(item.id,'text',item.text);});
  $('editNearbyTranscript').addEventListener('click',openNearbyTranscript);
  $('returnSampleButton').addEventListener('click',()=>{if(!view.returnSampleId)return;view.mode='samples';view.search='';view.person='';view.pending=false;$('searchInput').value='';filterItems();chooseItem(view.returnSampleId);scrollToSelected();});
  $('peopleChoices').addEventListener('click',event=>{const button=event.target.closest('[data-person]');if(button)confirmPerson(button.dataset.person);});
  $('unknownButton').addEventListener('click',markUnknown);$('skipButton').addEventListener('click',skipItem);
  $('otherPersonToggle').addEventListener('click',()=>{$('otherPersonForm').hidden=!$('otherPersonForm').hidden;if(!$('otherPersonForm').hidden)$('otherPersonInput').focus();});
  $('otherPersonForm').addEventListener('submit',event=>{event.preventDefault();const name=$('otherPersonInput').value.trim();if(!name)return;confirmPerson(name);$('otherPersonForm').hidden=true;$('otherPersonInput').value='';});
  $('playButton').addEventListener('click',togglePlayback);$('previousButton').addEventListener('click',()=>navigate(-1));$('nextButton').addEventListener('click',()=>navigate(1));
  $('volumeControl').addEventListener('input',event=>setVolume(event.target.value));
  $('referenceChoices').addEventListener('click',event=>{const button=event.target.closest('[data-reference-id]');if(button)playReference(button.dataset.referenceId);});
  $('resumeCurrentButton').addEventListener('click',()=>{stopReference();$('playButton').focus();playAudio();});
  $('waveTracks').addEventListener('click',event=>{const source=event.target.closest('[data-source]');if(source)switchSource(source.dataset.source);const canvas=event.target.closest('[data-wave-source]');if(canvas)waveformSeek(canvas,event);});
  $('waveTracks').addEventListener('keydown',event=>{const canvas=event.target.closest('[data-wave-source]');if(!canvas)return;if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();const window=clipWindow();switchSource(canvas.dataset.waveSource,{position:Math.max(window.start,Math.min(window.end,view.position+(event.key==='ArrowRight'?1:-1))),autoplay:false});}});
  $('overviewCanvas').addEventListener('click',event=>{const rect=event.currentTarget.getBoundingClientRect();timelineSeek(Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*meetingEnd());});
  $('overviewCanvas').addEventListener('keydown',event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();timelineSeek(Math.max(0,Math.min(meetingEnd(),view.position+(event.key==='ArrowRight'?10:-10))));}});
  $('contextButton').addEventListener('click',()=>{const active=playbackActive();pauseAudio({phase:'idle'});view.context=!view.context;renderWaveTracks();$('contextButton').setAttribute('aria-pressed',view.context);rememberView();if(active)playAudio();});
  $('loopButton').addEventListener('click',()=>{view.loop=!view.loop;$('loopButton').setAttribute('aria-pressed',view.loop);if(view.audioPhase==='playing')setAudioPhase('playing');rememberView();});
  $('speedSelect').addEventListener('change',event=>{view.speed=Number(event.target.value);if(view.audio)view.audio.playbackRate=view.speed;rememberView();});
  $('undoButton').addEventListener('click',()=>undoDecision());
  $('saveStatus').addEventListener('click',()=>{if(unsavedCount())retryUnsaved();});
  $('retrySaveButton').addEventListener('click',retryUnsaved);
  $('exportButton').addEventListener('click',()=>{$('exportMenu').hidden=!$('exportMenu').hidden;});
  $('exportMenu').addEventListener('click',async event=>{const link=event.target.closest('a');if(!link)return;event.preventDefault();$('exportMenu').hidden=true;if(view.failedRequests.size){toast('有保存失败或版本冲突。请先检查并点击“重试保存”，再导出。',true);return;}await flushBeforeExport();await view.saveChain;if(unsavedCount()||view.failedRequests.size){toast('仍有改动未保存，暂未导出。请先检查并重试保存。',true);return;}const download=document.createElement('a');download.href=link.href;download.download='';document.body.append(download);download.click();download.remove();});
  document.addEventListener('click',event=>{if(!event.target.closest('.export-wrap'))$('exportMenu').hidden=true;});
  $('shortcutsButton').addEventListener('click',()=>$('helpDialog').showModal());
  $('fullContextButton').addEventListener('click',()=>{renderContext();$('contextDialog').showModal();$('fullContext').querySelector('.current')?.scrollIntoView({block:'center'});});
  document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(button.dataset.close).close()));
  ['contextPreview','fullContext'].forEach(id=>$(id).addEventListener('click',event=>{const button=event.target.closest('[data-context-id]');if(!button)return;$('contextDialog').close();view.mode='transcript';filterItems();chooseItem(button.dataset.contextId);scrollToSelected();}));
  document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}}));
  document.addEventListener('keydown',handleShortcut);
  $('retryLoad').addEventListener('click',loadProject);
  window.addEventListener('beforeunload',event=>{if(unsavedCount()){event.preventDefault();event.returnValue='';}});
  view.resizeObserver=new ResizeObserver(()=>requestAnimationFrame(()=>{drawTracks();drawOverview();renderList();}));view.resizeObserver.observe($('workbench'));
}
async function loadProject(){
  $('loadError').hidden=true;$('workbench').setAttribute('aria-busy','true');
  try{
    const [project,state]=await Promise.all([fetchJSON('/api/project'),fetchJSON('/api/state')]);
    if(!project?.items?.length||!project.sources?.length)throw new Error('项目没有可读取的片段或原音来源。');
    if(typeof project.fingerprint!=='string'||!project.fingerprint.trim()||state.fingerprint!==project.fingerprint)throw new Error('裁决文件与当前录音项目不匹配，未载入旧判断。');
    if(unsavedCount()&&view.project?.fingerprint!==project.fingerprint)throw new Error('仍有属于原录音项目的改动未保存。请先恢复原项目，当前草稿已保留。');
    view.project=project;acceptState(state,project.fingerprint,{externalRead:true});view.project.people ||= [];view.state.decisions ||= {};
    try{const saved=JSON.parse(localStorage.getItem('listening-desk:view:'+project.project_id)||'null');if(saved){for(const key of ['mode','selectedId','sourceId','position','context','loop','speed'])if(saved[key]!==undefined)view[key]=saved[key];}}catch{}
    if(!['samples','transcript'].includes(view.mode))view.mode='samples';
    if(!project.items.some(i=>i.kind==='speaker_sample'))view.mode='transcript';
    if(!project.sources.some(s=>s.id===view.sourceId))view.sourceId=project.sources.find(s=>s.id.toUpperCase()==='B')?.id||project.sources[0].id;
    $('projectTitle').textContent=project.title||'录音校勘';$('projectSubtitle').textContent=project.subtitle||'多来源对听 · 逐句校勘 · 裁决留存';document.title=(project.title||'声间')+' · 声音校勘台';
    $('sampleCount').textContent=project.items.filter(i=>i.kind==='speaker_sample').length;$('transcriptCount').textContent=project.items.filter(i=>i.kind==='transcript').length.toLocaleString();
    updatePersonFilter();
    filterItems();if(!project.items.some(i=>i.id===view.selectedId))view.selectedId=view.filtered[0]?.id||project.items[0].id;
    const item=currentItem();if(!Number.isFinite(view.position)||view.position<item.start-3||view.position>item.end+3)view.position=item.start;
    if(!sourceCoverage(currentSource(),item))view.sourceId=project.sources.find(s=>sourceCoverage(s,item))?.id||view.sourceId;
    $('sessionDuration').textContent=formatTime(meetingEnd());$('overviewTicks').innerHTML=Array.from({length:7},(_,i)=>'<span>'+formatTime(meetingEnd()*i/6)+'</span>').join('');
    renderSelected();scrollToSelected();updateProgress();refreshSaveStatus();$('workbench').setAttribute('aria-busy','false');
    requestAnimationFrame(()=>{drawTracks();drawOverview();renderList();});
  }catch(error){$('loadErrorText').textContent=error.message;$('loadError').hidden=false;setSaveStatus('error','未连接');}
}
bindEvents();loadProject();
