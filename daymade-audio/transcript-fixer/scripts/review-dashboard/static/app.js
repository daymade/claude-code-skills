/* 转写修正审核台 — Prodigy-style single-focus review.
 * Reads /api/queue; every verdict POSTs /api/resolve which shells to the CLI
 * (the state SSOT). Keyboard: A accept / R keep original / O override /
 * S skip / U undo last / ↑↓ or J K navigate. */

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

const state = {
  items: [],
  stats: {},
  filters: { domains: [], kinds: [], sources: [] },
  status: "pending",
  domain: "",
  selectedId: null,
  undoStack: [],   // ids resolved this session, most recent last
  doneCount: 0,
};

const $ = (sel) => document.querySelector(sel);

// kind/status arrive from DB CHECK-constrained columns, but never trust a class
// name interpolation anyway: whitelist, unknown values fall back to a neutral class.
const KIND_CLASSES = ["entity", "unknown", "homophone", "wording"];
const kindClass = (k) => (KIND_CLASSES.includes(k) ? k : "wording");

async function fetchQueue() {
  const params = new URLSearchParams({ status: state.status });
  if (state.domain) params.set("domain", state.domain);
  const res = await fetch(`/api/queue?${params}`);
  const data = await res.json();
  state.items = data.items;
  state.stats = data.stats;
  state.filters = data.filters;
  if (!state.items.find((i) => i.id === state.selectedId)) {
    state.selectedId = state.items.length ? state.items[0].id : null;
  }
  render();
}

function selected() {
  return state.items.find((i) => i.id === state.selectedId) || null;
}

/* ── rendering ── */

function render() {
  renderStats();
  renderDomainChips();
  renderRail();
  renderCard();
}

function renderStats() {
  const s = state.stats.by_status || {};
  $("#header-stats").innerHTML = `
    <div class="stat"><b>${s.pending || 0}</b><br>待裁定</div>
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
  const it = selected();
  if (!it) {
    area.innerHTML = `<div class="empty-state">${
      state.status === "pending" ? "队列为空 — 没有待裁定的修正 🎉" : "该筛选下没有条目"
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
      <span>${SOURCE_LABEL[it.source] || it.source}</span>
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
      <button class="btn" data-decide="override"><kbd>O</kbd>改成…</button>
      <button class="btn" data-decide="skipped"><kbd>S</kbd>跳过/不认识</button>
      <button class="btn" data-decide="undo" ${state.undoStack.length ? "" : "disabled"}><kbd>U</kbd>撤销上次</button>
    </div>
    <div class="override-row" id="override-row">
      <input id="override-input" placeholder="正确写法…（回车确认，Esc 取消）">
      <button class="btn accept" data-decide="overridden">确认改写</button>
    </div>
    <div class="note-row">
      <input id="note-input" placeholder="备注（可选，随裁定记录）">
    </div>` : `
    <div class="decide-bar">
      <button class="btn" data-decide="reopen"><kbd>U</kbd>撤销此裁定（reopen）</button>
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

async function loadContext(id) {
  const box = $("#context-box");
  try {
    const res = await fetch(`/api/context/${id}`);
    const data = await res.json();
    renderAudio(id, data.audio);
    if (!data.lines || !data.lines.length) {
      box.innerHTML = `<div class="ctx-note">${esc(data.note || "无上下文")}</div>`;
      return;
    }
    const it = selected();
    box.innerHTML = data.lines.map((l) => {
      let text = esc(l.text);
      if (l.is_anchor && it) {
        text = text.split(esc(it.original_text)).join(`<mark>${esc(it.original_text)}</mark>`);
      }
      return `<div class="ctx-line ${l.is_anchor ? "anchor" : ""}"><span class="no">${l.no}</span><span>${text || "&nbsp;"}</span></div>`;
    }).join("");
    const anchor = box.querySelector(".anchor");
    if (anchor) anchor.scrollIntoView({ block: "center" });
  } catch {
    box.innerHTML = `<div class="ctx-note">上下文加载失败</div>`;
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
    <button class="btn play" data-audio="toggle" id="play-btn"><kbd>P</kbd>▶ 听这句</button>
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
    if (audioState.el) { audioState.el.pause(); audioState.el.remove(); }
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
  if (btn) btn.innerHTML = playing ? `<kbd>P</kbd>⏸ 停` : `<kbd>P</kbd>▶ 听这句`;
}

function stopAudio() {
  if (audioState.el) { audioState.el.pause(); setPlayLabel(false); }
}

/* ── actions ── */

async function resolve(id, decision, overrideTo) {
  stopAudio();
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
      toast(`已撤销 #${id}${logs.length ? " · " + logs.join("；") : ""}`);
    } else {
      state.undoStack.push(id);
      state.doneCount += 1;
      toast(`#${id} ${STATUS_LABEL[decision] || decision}${logs.length ? " · " + logs.join("；") : ""}`);
    }
    await advanceAfter(id, decision);
  } catch (e) {
    toast(`请求失败：${e}`, true);
  }
}

async function advanceAfter(id, decision) {
  // Refresh, then focus the next pending item after the one just decided.
  const prevIndex = state.items.findIndex((i) => i.id === id);
  await fetchQueue();
  if (decision === "reopen") { state.selectedId = id; render(); return; }
  if (state.status === "pending") {
    const next = state.items[Math.min(prevIndex, state.items.length - 1)];
    state.selectedId = next ? next.id : null;
    render();
  }
}

function showOverride() {
  const row = $("#override-row");
  if (!row) return;
  row.classList.add("visible");
  const input = $("#override-input");
  input.value = selected()?.suggested_text || "";
  input.focus();
  input.select();
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
    state.status = chip.dataset.status;
    document.querySelectorAll("#status-chips .chip").forEach((c) =>
      c.classList.toggle("active", c === chip));
    fetchQueue();
    return;
  }
  const dchip = e.target.closest("[data-domain]");
  if (dchip) { state.domain = dchip.dataset.domain; fetchQueue(); return; }
  const rail = e.target.closest(".rail-item");
  if (rail) { stopAudio(); state.selectedId = parseInt(rail.dataset.id, 10); render(); return; }
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
  else if (key === "o" && it && it.status === "pending") { e.preventDefault(); showOverride(); }
  else if (key === "s" && it && it.status === "pending") resolve(it.id, "skipped");
  else if (key === "u") undoLast();
  else if (key === "p") { e.preventDefault(); toggleClip(); }
  else if (key === "arrowdown" || key === "j") { e.preventDefault(); stopAudio(); move(1); }
  else if (key === "arrowup" || key === "k") { e.preventDefault(); stopAudio(); move(-1); }
});

fetchQueue();
setInterval(() => { if (!document.hidden) fetchQueue(); }, 30000);
