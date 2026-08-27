/* 转写修正审核台 — Prodigy-style single-focus review.
 * Reads /api/queue; every verdict POSTs /api/resolve which shells to the CLI
 * (the state SSOT). Keyboard: A accept / R keep original / W override /
 * S skip / Z undo last / Q play / ↑↓ or J K navigate. */

const KIND_LABEL = { entity: "实体", unknown: "待认", homophone: "同音", wording: "措辞" };
const SOURCE_LABEL = {
  native_pass: "AI 通读",
  stage1_deferred: "词典缓判",
  learned_suggestion: "学习建议",
  manual: "手动",
};
const STATUS_LABEL = {
  pending: "待裁定", accepted: "已接受", overridden: "已改写",
  kept_original: "原文正确", skipped: "已跳过",
};
const ACTION_LABEL = {
  file_edit: "✏️ 改转写文件",
  dict_add: "📚 进词典（此后自动修）",
  append_note: "📝 补语境注",
};

const initialParams = new URLSearchParams(window.location.search);
const initialItem = Number.parseInt(initialParams.get("item") || "", 10);
const initialFile = initialParams.get("file") || "";

const state = {
  items: [],
  stats: {},
  filters: { domains: [], kinds: [], sources: [] },
  status: initialParams.get("status") || (Number.isFinite(initialItem) ? "all" : "pending"),
  domain: "",
  filePath: initialFile,
  selectedId: Number.isFinite(initialItem) ? initialItem : null,
  itemOnly: Number.isFinite(initialItem) && !initialFile,
  undoStack: [],   // ids resolved this session, most recent last
  doneCount: 0,
  loadError: "",
};

const $ = (sel) => document.querySelector(sel);

// kind/status arrive from DB CHECK-constrained columns, but never trust a class
// name interpolation anyway: whitelist, unknown values fall back to a neutral class.
const KIND_CLASSES = ["entity", "unknown", "homophone", "wording"];
const kindClass = (k) => (KIND_CLASSES.includes(k) ? k : "wording");

async function fetchQueue() {
  const params = new URLSearchParams({ status: state.status });
  if (state.domain) params.set("domain", state.domain);
  if (state.filePath) params.set("file_path", state.filePath);
  if (state.itemOnly && state.selectedId) params.set("item_id", String(state.selectedId));
  const res = await fetch(`/api/queue?${params}`);
  const data = await res.json();
  if (!res.ok) {
    state.items = [];
    state.stats = {};
    state.loadError = data.detail || `审核范围读取失败（HTTP ${res.status}）`;
    render();
    return;
  }
  state.loadError = "";
  if (state.itemOnly && data.items.length && data.items[0].file_path) {
    state.filePath = data.items[0].file_path;
    state.itemOnly = false;
    syncUrl();
    return fetchQueue();
  }
  state.items = data.items;
  state.stats = data.stats;
  state.filters = data.filters;
  if (!state.items.find((i) => i.id === state.selectedId)) {
    state.selectedId = state.items.length ? state.items[0].id : null;
  }
  syncUrl();
  render();
}

function selected() {
  return state.items.find((i) => i.id === state.selectedId) || null;
}

/* ── rendering ── */

function render() {
  renderScope();
  renderStats();
  renderDomainChips();
  renderRail();
  renderCard();
}

function fileName(path) {
  return String(path || "").split(/[\\/]/).filter(Boolean).pop() || "";
}

function renderScope() {
  const banner = $("#scope-banner");
  if (!state.filePath) {
    banner.hidden = true;
    banner.innerHTML = "";
    return;
  }
  if (state.loadError) {
    banner.hidden = false;
    banner.innerHTML = `
      <div class="scope-summary" title="${esc(state.filePath)}">
        <span class="scope-kicker">无法验证</span>
        <span class="scope-file">${esc(fileName(state.filePath))}</span>
        <span class="scope-state">${esc(state.loadError)}</span>
      </div>
      <button class="btn scope-clear" data-clear-scope>查看全部队列</button>`;
    return;
  }
  const pending = Number(state.stats.pending_total || 0);
  banner.hidden = false;
  banner.innerHTML = `
    <div class="scope-summary" title="${esc(state.filePath)}">
      <span class="scope-kicker">本次逐字稿</span>
      <span class="scope-file">${esc(fileName(state.filePath))}</span>
      <span class="scope-state">${pending ? `还剩 ${pending} 条待裁定` : "人审已清零"}</span>
    </div>
    <button class="btn scope-clear" data-clear-scope>查看全部队列</button>`;
}

function syncUrl() {
  const params = new URLSearchParams();
  params.set("status", state.status);
  if (state.filePath) params.set("file", state.filePath);
  if (state.selectedId) params.set("item", String(state.selectedId));
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}

function renderStats() {
  if (state.loadError) {
    $("#header-stats").innerHTML = `<div class="stat"><b>—</b><br>范围无效</div>`;
    return;
  }
  const s = state.stats.by_status || {};
  const scopeLabel = state.filePath ? "本文件" : "全队列";
  $("#header-stats").innerHTML = `
    <div class="stat"><b>${s.pending || 0}</b><br>${scopeLabel}待裁</div>
    <div class="stat"><b>${state.doneCount}</b><br>本次已裁</div>
    <div class="stat"><b>${(s.accepted || 0) + (s.overridden || 0) + (s.kept_original || 0) + (s.skipped || 0)}</b><br>累计已裁</div>`;
}

function renderDomainChips() {
  const wrap = $("#domain-chips");
  const domains = state.filters.domains || [];
  if (!domains.length) { wrap.innerHTML = ""; return; }
  wrap.innerHTML =
    `<span class="chip ${state.domain === "" ? "active" : ""}" data-domain="">全部域</span>` +
    domains.map((d) =>
      `<span class="chip ${state.domain === d ? "active" : ""}" data-domain="${esc(d)}">${esc(d)}</span>`
    ).join("");
}

function renderRail() {
  const rail = $("#queue-rail");
  rail.hidden = !state.items.length;
  if (!state.items.length) { rail.innerHTML = ""; return; }
  rail.innerHTML = state.items.map((it) => {
    const to = it.suggested_text
      ? `<span class="to">${esc(it.suggested_text)}</span>`
      : `<span class="badge unknown">无建议</span>`;
    const ln = Number(it.line_number) || 0;
    const file = it.file_name ? `${esc(it.file_name)}${ln ? ":" + ln : ""}` : "";
    const done = it.status !== "pending" ? "done" : "";
    return `<div class="rail-item ${done} ${it.id === state.selectedId ? "selected" : ""}" data-id="${it.id}">
      <div class="swap"><span class="from">${esc(it.original_text)}</span><span>→</span>${to}</div>
      <div class="meta">
        <span class="badge ${kindClass(it.kind)}">${KIND_LABEL[it.kind] || esc(it.kind)}</span>
        ${it.status !== "pending" ? `<span class="badge status">${STATUS_LABEL[it.status] || esc(it.status)}</span>` : ""}
        <span>${esc(it.domain)}</span><span>${file}</span>
      </div>
    </div>`;
  }).join("");
}

async function renderCard() {
  const area = $("#focus-area");
  if (state.loadError) {
    area.innerHTML = `<div class="empty-state">${esc(state.loadError)}</div>`;
    return;
  }
  const it = selected();
  if (!it) {
    const filePending = Number(state.stats.pending_total || 0);
    area.innerHTML = `<div class="empty-state">${
      state.status === "pending"
        ? (state.filePath
            ? (filePending
                ? `当前筛选没有条目；整份逐字稿仍有 ${filePending} 条待裁定`
                : "这份逐字稿已无待裁定项 ✓")
            : "队列为空 — 没有待裁定的修正 🎉")
        : "该筛选下没有条目"
    }</div>`;
    return;
  }
  const actions = (it.actions && it.actions.length)
    ? it.actions
    : (it.file_path && it.suggested_text
        ? [{ type: "file_edit" }] : []);
  const pending = it.status === "pending";
  area.innerHTML = `
  <div class="card">
    <div class="card-head">
      <span>#${it.id}</span>
      <span class="badge ${kindClass(it.kind)}">${KIND_LABEL[it.kind] || esc(it.kind)}</span>
      <span>${esc(it.domain)}</span>
      <span>${SOURCE_LABEL[it.source] || esc(it.source)}</span>
      ${it.file_name ? `<span class="file-chip">${esc(it.file_name)}${Number(it.line_number) ? ":" + Number(it.line_number) : ""}</span>` : ""}
      <span style="margin-left:auto">${STATUS_LABEL[it.status] || esc(it.status)}</span>
    </div>
    <div class="suggest-row">
      <span class="from">${esc(it.original_text)}</span>
      <span class="arrow">→</span>
      ${it.suggested_text
        ? `<span class="to">${esc(it.suggested_text)}</span>`
        : `<span class="to none">无建议 — 请用「改成…」给出正确写法，或跳过</span>`}
    </div>
    <div class="action-chips">
      ${actions.map((a) => `<span class="action-chip">${ACTION_LABEL[a.type] || esc(a.type)}</span>`).join("")}
    </div>
    ${it.evidence ? `<div class="evidence"><b>证据：</b>${esc(it.evidence)}</div>` : ""}
    <div class="audio-row" id="audio-row"></div>
    <div class="context" id="context-box"><div class="ctx-note">加载上下文…</div></div>
    ${!pending ? renderResolved(it) : ""}
    ${pending ? `
    <div class="decide-bar">
      <button class="btn accept" data-decide="accepted" ${it.suggested_text ? "" : "disabled"}><kbd>A</kbd>接受建议</button>
      <button class="btn keep" data-decide="kept_original"><kbd>R</kbd>原文正确</button>
      <button class="btn" data-decide="override"><kbd>W</kbd>改成…</button>
      <button class="btn" data-decide="skipped"><kbd>S</kbd>跳过/不认识</button>
      <button class="btn" data-decide="undo" ${state.undoStack.length ? "" : "disabled"}><kbd>Z</kbd>撤销上次</button>
    </div>
    <div class="override-row" id="override-row">
      <div class="override-scope" id="override-scope"></div>
      <input id="override-input" placeholder="正确写法…（回车确认，Esc 取消）">
      <button class="btn accept" data-decide="overridden">确认改写</button>
    </div>
    <div class="note-row">
      <input id="note-input" placeholder="备注（可选，随裁定记录）">
    </div>` : `
    <div class="decide-bar">
      <button class="btn" data-decide="reopen"><kbd>Z</kbd>撤销此裁定（reopen）</button>
    </div>`}
  </div>`;
  loadContext(it.id);
}

function renderResolved(it) {
  const logs = (it.apply_log || []).map((e) =>
    `<div>${e.ok ? "✓" : "✗"} ${esc(e.msg || "")}</div>`).join("");
  const cls = (it.apply_log || []).every((e) => e.ok) ? "" : "warn";
  return `<div class="resolved-banner ${cls}">
      已裁定：${STATUS_LABEL[it.status]}${it.resolved_text ? ` → ${esc(it.resolved_text)}` : ""}
      ${it.decided_by ? `（by ${esc(it.decided_by)}）` : ""}${it.decision_note ? ` · ${esc(it.decision_note)}` : ""}
    </div>${logs ? `<div class="apply-log">${logs}</div>` : ""}`;
}

let contextSeq = 0;

async function loadContext(id) {
  const box = $("#context-box");
  // Stale-response guard: rapid J/K navigation fires overlapping fetches; a
  // late response for a PREVIOUS card must never paint this card's context —
  // nor rebind audioState to the old item (Q would play the wrong utterance).
  const seq = ++contextSeq;
  try {
    const res = await fetch(`/api/context/${id}`);
    const data = await res.json();
    if (seq !== contextSeq) return;
    renderAudio(id, data.audio);
    if (!data.lines || !data.lines.length) {
      box.innerHTML = `<div class="ctx-note">${esc(data.note || "无上下文")}</div>`;
      return;
    }
    const markText = data.mark_text;
    box.innerHTML = (data.note
      ? `<div class="ctx-note">${esc(data.note)}</div>` : "") + data.lines.map((l) => {
      let text = esc(l.text);
      if (l.is_anchor && markText) {
        text = text.split(esc(markText)).join(`<mark>${esc(markText)}</mark>`);
      }
      return `<div class="ctx-line ${l.is_anchor ? "anchor" : ""}"><span class="no">${l.no}</span><span>${text || "&nbsp;"}</span></div>`;
    }).join("");
    const anchor = box.querySelector(".anchor");
    if (anchor) anchor.scrollIntoView({ block: "center" });
  } catch {
    if (seq === contextSeq) box.innerHTML = `<div class="ctx-note">上下文加载失败</div>`;
  }
}

/* ── audio: play the anchored utterance (timestamps from the transcript) ── */

const audioState = { el: null, itemId: null, clip: null, stopAt: 0, pad: 0 };

function renderAudio(itemId, audio) {
  const row = $("#audio-row");
  if (!row) return;
  if (!audio || !audio.available) {
    row.innerHTML = "";
    audioState.clip = null;
    return;
  }
  audioState.itemId = itemId;
  audioState.clip = audio;
  audioState.pad = 0;
  row.innerHTML = `
    <button class="btn play" data-audio="toggle" id="play-btn"><kbd>Q</kbd>▶ 听这句</button>
    <button class="btn" data-audio="wider">± 前后多听 3s</button>
    <span class="audio-range">${fmtTime(audio.start)} – ${fmtTime(audio.end)}</span>`;
}

function fmtTime(sec) {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? h + ":" : "") + String(m).padStart(2, "0") + ":" + String(x).padStart(2, "0");
}

function toggleClip() {
  if (!audioState.clip) return;
  if (!audioState.el || audioState.el.dataset.itemId !== String(audioState.itemId)) {
    releaseAudio();
    const el = new Audio(`/api/audio/${audioState.itemId}`);
    el.dataset.itemId = String(audioState.itemId);
    el.preload = "auto";
    el.addEventListener("timeupdate", () => {
      if (audioState.stopAt && el.currentTime >= audioState.stopAt) {
        el.pause();
        setPlayLabel(false);
      }
    });
    el.addEventListener("error", () => toast("音频加载失败", true));
    audioState.el = el;
  }
  const el = audioState.el;
  if (!el.paused) { el.pause(); setPlayLabel(false); return; }
  const start = Math.max(0, audioState.clip.start - audioState.pad);
  audioState.stopAt = audioState.clip.end + audioState.pad;
  const kick = () => { el.currentTime = start; el.play(); setPlayLabel(true); };
  if (el.readyState >= 1) kick();
  else el.addEventListener("loadedmetadata", kick, { once: true });
}

function setPlayLabel(playing) {
  const btn = $("#play-btn");
  if (btn) btn.innerHTML = playing ? `<kbd>Q</kbd>⏸ 停` : `<kbd>Q</kbd>▶ 听这句`;
}

function stopAudio() {
  if (audioState.el) { audioState.el.pause(); setPlayLabel(false); }
}

function releaseAudio() {
  if (audioState.el) {
    audioState.el.pause();
    audioState.el.removeAttribute("src");
    audioState.el.load();
    audioState.el = null;
  }
}

function setStatusFilter(status) {
  state.status = status;
  document.querySelectorAll("#status-chips .chip").forEach((c) =>
    c.classList.toggle("active", c.dataset.status === status));
  syncUrl();
}

/* ── actions ── */

async function resolve(id, decision, overrideTo) {
  stopAudio();
  const current = selected();
  const note = $("#note-input") ? $("#note-input").value.trim() : "";
  const body = { id, decision };
  if (overrideTo) body.override_to = overrideTo;
  if (note) body.note = note;
  try {
    const res = await fetch("/api/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast(`${res.status === 409 ? "⚠️ 文件已变化，未做任何修改：" : "出错："}${err.detail || res.statusText}`, true);
      return;
    }
    const data = await res.json();
    const logs = (data.apply_log || data.revert_log || []).map((e) => e.msg).filter(Boolean);
    if (decision === "reopen") {
      state.undoStack = state.undoStack.filter((x) => x !== id);
      state.doneCount = Math.max(0, state.doneCount - 1);
      // A reopened item goes back to pending — if the current filter can't
      // show it, follow it there instead of leaving the user on a blank card.
      if (state.status !== "pending" && state.status !== "all") {
        setStatusFilter("pending");
      }
      toast(`已撤销 #${id}${logs.length ? " · " + logs.join("；") : ""}`);
    } else {
      state.undoStack.push(id);
      state.doneCount += 1;
      toast(`#${id} ${STATUS_LABEL[decision] || decision}${logs.length ? " · " + logs.join("；") : ""}`);
    }
    if (!state.filePath && current?.file_path) state.filePath = current.file_path;
    state.itemOnly = false;
    syncUrl();
    await advanceAfter(id, decision);
  } catch (e) {
    toast(`请求失败：${e}`, true);
  }
}

async function advanceAfter(id, decision) {
  if (decision === "reopen") {
    await fetchQueue();
    state.selectedId = id;
    render();
    return;
  }
  // Pick the next item BEFORE the refresh, so fetchQueue's keep-selection
  // logic lands on it in a single render (no double context fetch).
  const prevIndex = state.items.findIndex((i) => i.id === id);
  const next = state.items[prevIndex + 1] || state.items[prevIndex - 1] || null;
  state.selectedId = next ? next.id : null;
  await fetchQueue();
}

function showOverride() {
  const row = $("#override-row");
  if (!row) return;
  row.classList.add("visible");
  const input = $("#override-input");
  input.value = selected()?.suggested_text || "";
  input.focus();
  input.select();
  updateOverrideScope();
}

/* 整段替换范围明示（2026-07-25 #24 战例：original 拖了整句，
 * 用户 override 一个短品牌名 → 整句被吞。override 的 file_edit 永远把
 * original_text 整段换成输入值，所以输入框上方必须始终显示范围；短替换
 * （输入 ≤ 原文一半）多半是只想换其中一个词，加警告引导输入完整片段。 */
function updateOverrideScope() {
  const el = $("#override-scope");
  const it = selected();
  if (!el || !it) return;
  const orig = it.original_text || "";
  const v = ($("#override-input")?.value || "").trim();
  const risky = orig.length >= 5 && v && v.length <= orig.length / 2;
  el.className = "override-scope" + (risky ? " warn" : "");
  el.innerHTML = `替换范围（整段）：「${esc(orig)}」` +
    (risky ? `<br>⚠️ 你输入的「${esc(v)}」远短于原文，将整段吞掉上下文——只想换其中一个词？请输入替换后的完整片段` : "");
}

function move(delta) {
  if (!state.items.length) return;
  const idx = state.items.findIndex((i) => i.id === state.selectedId);
  const next = state.items[Math.max(0, Math.min(state.items.length - 1, idx + delta))];
  state.selectedId = next.id;
  render();
  const el = document.querySelector(`.rail-item[data-id="${next.id}"]`);
  if (el) el.scrollIntoView({ block: "nearest" });
}

function toast(msg, isErr) {
  const el = document.createElement("div");
  el.className = `toast ${isErr ? "err" : ""}`;
  el.textContent = msg;
  $("#toast-wrap").appendChild(el);
  setTimeout(() => el.remove(), isErr ? 6000 : 3200);
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* ── events ── */

document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-status]");
  if (chip) {
    stopAudio();
    setStatusFilter(chip.dataset.status);
    fetchQueue();
    return;
  }
  const dchip = e.target.closest("[data-domain]");
  if (dchip) { state.domain = dchip.dataset.domain; fetchQueue(); return; }
  const clearScope = e.target.closest("[data-clear-scope]");
  if (clearScope) {
    stopAudio();
    state.filePath = "";
    state.itemOnly = false;
    state.selectedId = null;
    syncUrl();
    fetchQueue();
    return;
  }
  const rail = e.target.closest(".rail-item");
  if (rail) {
    stopAudio();
    state.selectedId = parseInt(rail.dataset.id, 10);
    syncUrl();
    render();
    return;
  }
  const audioBtn = e.target.closest("[data-audio]");
  if (audioBtn) {
    if (audioBtn.dataset.audio === "toggle") toggleClip();
    else if (audioBtn.dataset.audio === "wider") {
      audioState.pad += 3;
      stopAudio();
      toggleClip();
    }
    return;
  }
  const btn = e.target.closest("[data-decide]");
  if (btn && !btn.disabled) {
    const it = selected();
    if (!it) return;
    const d = btn.dataset.decide;
    if (d === "override") { showOverride(); return; }
    if (d === "undo") { undoLast(); return; }
    if (d === "overridden") {
      const v = $("#override-input").value.trim();
      if (!v) { toast("请填写正确写法", true); return; }
      resolve(it.id, "overridden", v);
      return;
    }
    resolve(it.id, d);
  }
});

function undoLast() {
  const last = state.undoStack[state.undoStack.length - 1];
  if (!last) { toast("本次会话还没有可撤销的裁定", true); return; }
  resolve(last, "reopen");
}

document.addEventListener("input", (e) => {
  if (e.target.id === "override-input") updateOverrideScope();
});

document.addEventListener("keydown", (e) => {
  const tag = e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    if (e.key === "Enter" && e.target.id === "override-input") {
      e.preventDefault();
      const it = selected();
      const v = e.target.value.trim();
      if (it && v) resolve(it.id, "overridden", v);
    } else if (e.key === "Escape") {
      e.target.blur();
      const row = $("#override-row");
      if (row) row.classList.remove("visible");
    }
    return;
  }
  const it = selected();
  const key = e.key.toLowerCase();
  if (key === "a" && it && it.status === "pending" && it.suggested_text) resolve(it.id, "accepted");
  else if (key === "r" && it && it.status === "pending") resolve(it.id, "kept_original");
  else if (key === "w" && it && it.status === "pending") { e.preventDefault(); showOverride(); }
  else if (key === "s" && it && it.status === "pending") resolve(it.id, "skipped");
  else if (key === "z") {
    // On a decided item, Z reopens THAT item (works across sessions); the
    // session undo-stack is only the fallback for the pending view.
    if (it && it.status !== "pending") resolve(it.id, "reopen");
    else undoLast();
  }
  else if (key === "q") { e.preventDefault(); toggleClip(); }
  else if (key === "arrowdown" || key === "j") { e.preventDefault(); stopAudio(); move(1); }
  else if (key === "arrowup" || key === "k") { e.preventDefault(); stopAudio(); move(-1); }
});

setStatusFilter(state.status);
fetchQueue();
setInterval(() => {
  if (document.hidden) return;
  // Never repaint under the user's hands: typing a note/override or listening
  // to a clip must not be wiped by the background refresh.
  const ae = document.activeElement;
  if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) return;
  if (audioState.el && !audioState.el.paused) return;
  fetchQueue();
}, 30000);
