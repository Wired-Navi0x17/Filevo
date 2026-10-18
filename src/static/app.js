/* ==========================================================================
   SORTWISE — UI controller
   Filelight-style radial disk map (HTML5 canvas) + inspector + ledger.
   Vanilla JS. No build step. No external requests.
   ========================================================================== */
"use strict";

/* ───────────────────────────── tiny DOM helpers ───────────────────────── */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const API = {
  config: "/api/config",
  configReset: "/api/config/reset",
  subjects: "/api/subjects",
  scan: "/api/scan",
  route: "/api/route",
  suggest: "/api/rename/suggest",
  history: "/api/history",
  health: "/api/health",
};

/* ───────────────────────────── palette ────────────────────────────────── */
const COLORS = {
  bg: "#121316",
  surface: "#181a1f",
  surface2: "#1c1e23",
  elevated: "#202228",
  ring: "#202228",
  border: "#2c2e36",
  text: "#e9ebee",
  dim: "#a3a9b4",
  faint: "#6f7683",
  ghost: "#565c67",
  accent: "#3b82f6",
  ok: "#10b981",
  warn: "#f59e0b",
  danger: "#ef4444",
};

/* Muted graphite-blue tints — monochrome base for destination folders. */
const FOLDER_TINTS = [
  "#5c6675", "#6a7482", "#525c6b", "#727c8b",
  "#4f5a69", "#67707e", "#5a6473", "#767f8d",
];
const INCOMING_TINT = "#4d5563";

const ENTROPY_MAX = 3.0;     // full scale for the entropy gauge, in bits
const MIN_WEIGHT = 4096;     // minimum angular weight for an empty node (bytes)
const SEG_GAP = 0.012;       // radians between sibling arcs
const LABEL_MIN_PX = 58;     // need at least this arc length to draw a label

/* ───────────────────────────── application state ──────────────────────── */
const state = {
  config: null,
  subjects: [],
  queue: [],
  subjectFiles: {},        // folder -> [file]
  calibrations: {},        // path -> calibration result
  selected: null,
  preview: null,
  override: null,
  checked: new Set(),
  history: [],
  health: null,
  busy: false,
  tree: null,
  currentRootId: "root",
  arcs: [],
  geom: null,
  hover: null,
  ws: null,
  wsRetry: 0,
  pollTimer: null,
};

/* ═════════════════════════════ helpers ════════════════════════════════ */
async function api(path, options = {}) {
  const opts = { headers: { "Content-Type": "application/json" }, ...options };
  if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
  const res = await fetch(path, opts);
  const type = res.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail : payload;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

function toast(message, kind = "info", ttl = 4200) {
  const box = document.createElement("div");
  box.className = `toast ${kind}`;
  box.textContent = message;
  $("#toasts").appendChild(box);
  setTimeout(() => box.remove(), ttl);
}

function humanBytes(value) {
  if (value == null) return "—";
  let size = Number(value);
  const units = ["B", "KB", "MB", "GB", "TB"];
  for (let i = 0; i < units.length; i += 1) {
    if (size < 1024 || i === units.length - 1) {
      return i === 0 ? `${Math.round(size)} B` : `${size.toFixed(1)} ${units[i]}`;
    }
    size /= 1024;
  }
  return `${size.toFixed(1)} TB`;
}

function basename(path) {
  if (!path) return "";
  const clean = String(path).replace(/\/+$/, "");
  const parts = clean.split("/");
  return parts[parts.length - 1] || clean;
}

function shortTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatUptime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/* parse "#rrggbb" into [r,g,b] */
function rgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function hex(r, g, b) {
  const c = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  return `#${c(r)}${c(g)}${c(b)}`;
}
function mix(a, b, t) {
  const [r1, g1, b1] = rgb(a);
  const [r2, g2, b2] = rgb(b);
  return hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t);
}

/* ═════════════════════════════ config ═════════════════════════════════ */
async function loadConfig() {
  state.config = await api(API.config);
  applyConfigToForm();
  renderConfigBits();
}

function applyConfigToForm() {
  const c = state.config;
  if (!c) return;
  $("#cfg-watch").value = c.watch_folder;
  $("#cfg-target").value = c.target_root;
  $("#cfg-conf").value = c.confidence_threshold;
  $("#cfg-conf-val").textContent = Number(c.confidence_threshold).toFixed(2);
  $("#cfg-ent").value = c.entropy_threshold;
  $("#cfg-ent-val").textContent = Number(c.entropy_threshold).toFixed(2);
  $("#cfg-folder-template").value = c.subject_folder_template;
  $("#cfg-rename-template").value = c.rename_template;
  $("#cfg-model").value = c.model_name;
  $("#cfg-temp").value = c.temperature;
  $("#cfg-temp-val").textContent = Number(c.temperature).toFixed(2);
  $("#cfg-auto").checked = !!c.auto_move;
  $("#cfg-recursive").checked = !!c.recursive;
  $$("#cfg-extensions input").forEach((box) => {
    box.checked = (c.extensions || []).includes(box.value);
  });
  updateTargetPreview();
}

function updateTargetPreview() {
  const target = $("#cfg-target").value || "~/Documents/Sortwise";
  const pattern = $("#cfg-folder-template").value || "{label}";
  const example = pattern
    .replace("{label}", "CS2227 - AI and ML")
    .replace("{code}", "CS2227")
    .replace("{name}", "AI and ML")
    .replace("{date}", new Date().toISOString().slice(0, 10));
  $("#cfg-target-preview").textContent = `${target}/${example}`;
}

function renderConfigBits() {
  const c = state.config;
  if (!c) return;
  $("#status-watch").textContent = `watch: ${c.watch_folder}`;
  $("#status-watch").title = c.watch_folder;
  $("#status-target").textContent = `target: ${c.target_root}`;
  $("#status-target").title = c.target_root;
  $("#status-endpoint").textContent = location.host || "127.0.0.1:8765";
  $("#ins-conf-gate").style.left = `${Number(c.confidence_threshold) * 100}%`;
}

function configFromForm() {
  return {
    watch_folder: $("#cfg-watch").value.trim(),
    target_root: $("#cfg-target").value.trim(),
    confidence_threshold: Number($("#cfg-conf").value),
    entropy_threshold: Number($("#cfg-ent").value),
    subject_folder_template: $("#cfg-folder-template").value.trim(),
    rename_template: $("#cfg-rename-template").value.trim(),
    model_name: $("#cfg-model").value.trim(),
    temperature: Number($("#cfg-temp").value),
    auto_move: $("#cfg-auto").checked,
    recursive: $("#cfg-recursive").checked,
    extensions: $$("#cfg-extensions input").filter((b) => b.checked).map((b) => b.value),
  };
}

async function saveConfig() {
  const next = configFromForm();
  if (!next.extensions.length) next.extensions = ["pdf", "docx", "pptx"];
  try {
    state.config = await api(API.config, { method: "POST", body: next });
    applyConfigToForm();
    renderConfigBits();
    await loadSubjects();
    await loadTargetMap();
    rebuildTree();
    closeModal();
    toast("Settings saved", "ok");
  } catch (err) {
    toast(`Settings error: ${err.message}`, "err");
  }
}

async function resetConfig() {
  try {
    state.config = await api(API.configReset, { method: "POST" });
    applyConfigToForm();
    renderConfigBits();
    await loadSubjects();
    await loadTargetMap();
    rebuildTree();
    toast("Defaults restored", "ok");
  } catch (err) {
    toast(`Reset failed: ${err.message}`, "err");
  }
}

function openModal() { applyConfigToForm(); $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; }

/* ═════════════════════════════ subjects ═══════════════════════════════ */
async function loadSubjects() {
  const data = await api(API.subjects);
  state.subjects = data.subjects || [];
  populateOverrideSelect();
}

function populateOverrideSelect() {
  const select = $("#override-select");
  select.innerHTML = '<option value="">Auto (calibrated)</option>';
  for (const subject of state.subjects) {
    const opt = document.createElement("option");
    opt.value = subject.label;
    opt.textContent = `${subject.code} — ${subject.name}`;
    select.appendChild(opt);
  }
  select.value = state.override || "";
}

function subjectFor(label) {
  return state.subjects.find((s) => s.label === label) || null;
}

/* ═════════════════════════════ scanning ═══════════════════════════════ */
async function scan(opts = {}) {
  if (state.busy) return;
  setBusy(true);
  setStatus("Scanning watch directory…", "busy");
  try {
    const data = await api(API.scan, { method: "POST", body: {} });
    state.queue = data.files || [];
    state.checked.clear();
    await loadTargetMap();
    rebuildTree();
    toast(`Scanned ${state.queue.length} document${state.queue.length === 1 ? "" : "s"}`, "ok");
    setStatus(`Scanned ${state.queue.length} document${state.queue.length === 1 ? "" : "s"}`, "online");
    if (opts.rebuildOnly !== true) renderLedger();
  } catch (err) {
    toast(`Scan failed: ${err.message}`, "err");
    setStatus(`Scan failed: ${err.message}`, "error");
  } finally {
    setBusy(false);
  }
}

async function loadTargetMap() {
  const subjects = state.subjects;
  if (!subjects.length) { state.subjectFiles = {}; return; }
  const results = await Promise.allSettled(
    subjects.map((s) => api(API.scan, { method: "POST", body: { path: s.folder } }))
  );
  const map = {};
  results.forEach((result, i) => {
    map[subjects[i].folder] = result.status === "fulfilled" ? (result.value.files || []) : [];
  });
  state.subjectFiles = map;
}

/* ═════════════════════════════ tree model ═════════════════════════════ */
function makeNode(props) {
  return {
    id: props.id,
    name: props.name,
    code: props.code || "",
    path: props.path || "",
    kind: props.kind,               // root | group | folder | file
    file: props.file || null,
    label: props.label || "",
    fileType: props.fileType || "",
    tint: props.tint || INCOMING_TINT,
    size: 0,
    count: 0,
    weight: MIN_WEIGHT,
    children: [],
    parent: null,
  };
}

function fileNode(file, parent, index) {
  const tint = mix(parent.tint, "#ffffff", index % 2 === 0 ? 0.06 : 0.16);
  return makeNode({
    id: `file:${file.path}`,
    name: file.name,
    path: file.path,
    kind: "file",
    file,
    fileType: file.file_type,
    tint,
  });
}

function computeAggregates(node) {
  let size = 0;
  let count = 0;
  for (const child of node.children) {
    child.parent = node;
    computeAggregates(child);
    size += child.size;
    count += child.count;
  }
  if (node.kind === "file") {
    size = Number(node.file?.size || 0);
    count = 1;
    node.weight = Math.max(size, MIN_WEIGHT);
  } else {
    node.size = size;
    node.count = count;
    node.weight = node.children.length
      ? node.children.reduce((sum, c) => sum + c.weight, 0)
      : MIN_WEIGHT;
  }
  node.size = size;
  node.count = count;
  return node;
}

function rebuildTree() {
  const cfg = state.config || {};
  const targetRoot = cfg.target_root || "~/Documents/Sortwise";
  const watch = cfg.watch_folder || "~/Downloads";

  const root = makeNode({ id: "root", name: basename(targetRoot) || "Sortwise", path: targetRoot, kind: "root" });

  const incoming = makeNode({
    id: "incoming",
    name: "Incoming",
    code: "INBOX",
    path: watch,
    kind: "group",
    tint: INCOMING_TINT,
  });
  state.queue.forEach((file, i) => incoming.children.push(fileNode(file, incoming, i)));
  root.children.push(incoming);

  state.subjects.forEach((subject, i) => {
    const folder = makeNode({
      id: `sub:${subject.label}`,
      name: subject.name || subject.label,
      code: subject.code,
      path: subject.folder,
      kind: "folder",
      label: subject.label,
      tint: FOLDER_TINTS[i % FOLDER_TINTS.length],
    });
    const files = state.subjectFiles[subject.folder] || [];
    files.forEach((file, j) => folder.children.push(fileNode(file, folder, j)));
    root.children.push(folder);
  });

  computeAggregates(root);
  state.tree = root;

  // Restore the drill position when the node still exists.
  const found = findNode(root, state.currentRootId);
  setCurrentRoot(found || root, false);
}

function findNode(node, id) {
  if (node.id === id) return node;
  for (const child of node.children) {
    const match = findNode(child, id);
    if (match) return match;
  }
  return null;
}

function totalFiles(node) {
  let n = node.kind === "file" ? 1 : 0;
  for (const c of node.children) n += totalFiles(c);
  return n;
}

/* ═════════════════════════════ breadcrumbs ════════════════════════════ */
function crumbsFor(node) {
  const chain = [];
  let cursor = node;
  while (cursor) { chain.unshift(cursor); cursor = cursor.parent; }
  return chain;
}

function renderBreadcrumbs() {
  const nav = $("#breadcrumbs");
  nav.innerHTML = "";
  if (!state.tree || !state.currentRootId) return;
  const chain = crumbsFor(findNode(state.tree, state.currentRootId) || state.tree);
  chain.forEach((node, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "crumb-sep";
      sep.textContent = "/";
      nav.appendChild(sep);
    }
    const button = document.createElement("button");
    button.className = "crumb" + (i === chain.length - 1 ? " current" : "");
    button.innerHTML = `<span class="icon">${node.kind === "file" ? "·" : "▸"}</span>${escapeHtml(node.name)}`;
    button.addEventListener("click", () => {
      if (node.kind === "file") { selectFile(node.file); return; }
      setCurrentRoot(node, true);
    });
    nav.appendChild(button);
  });
}

function setCurrentRoot(node, redraw = true) {
  state.currentRootId = node.id;
  state.hover = null;
  renderBreadcrumbs();
  if (redraw) {
    render();
    updateReadout(node);
  }
}

/* ═════════════════════════════ canvas rendering ═══════════════════════ */
const canvas = $("#filelight-canvas");
const ctx = canvas.getContext("2d");

function resizeCanvas() {
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(10, wrap.clientWidth);
  const h = Math.max(10, wrap.clientHeight);
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  state.view = { w, h };
  render();
}

function layoutArcs(node, a0, a1, depth, out) {
  const children = node.children;
  if (!children.length) return;
  const total = children.reduce((sum, c) => sum + c.weight, 0) || 1;
  let angle = a0;
  const span = a1 - a0;
  for (const child of children) {
    const childAngle = span * (child.weight / total);
    out.push({ node: child, depth, a0: angle + SEG_GAP / 2, a1: angle + childAngle - SEG_GAP / 2 });
    layoutArcs(child, angle, angle + childAngle, depth + 1, out);
    angle += childAngle;
  }
}

function colorFor(node, depth) {
  return node.tint || FOLDER_TINTS[depth % FOLDER_TINTS.length];
}

function fitText(text, maxWidth) {
  if (!text) return "";
  if (ctx.measureText(text).width <= maxWidth) return text;
  let result = text;
  while (result.length > 1 && ctx.measureText(`${result}…`).width > maxWidth) {
    result = result.slice(0, -1);
  }
  return `${result}…`;
}

function render() {
  const view = state.view || { w: canvas.clientWidth, h: canvas.clientHeight };
  const { w, h } = view;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, w, h);

  const root = state.tree ? (findNode(state.tree, state.currentRootId) || state.tree) : null;
  if (!root) { state.arcs = []; state.geom = null; renderOverlay(); return; }

  const arcs = [];
  layoutArcs(root, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2, 1, arcs);
  state.arcs = arcs;

  const cx = w / 2;
  const cy = h / 2;
  const pad = 26;
  const R = Math.max(70, Math.min(w, h) / 2 - pad);
  const maxDepth = Math.max(2, ...arcs.map((a) => a.depth));
  const centerR = R * 0.30;
  const ringW = (R - centerR) / maxDepth;
  state.geom = { cx, cy, R, centerR, ringW, maxDepth };

  // concentric guide lines
  ctx.lineWidth = 1;
  for (let d = 1; d <= maxDepth; d += 1) {
    ctx.strokeStyle = COLORS.ring;
    ctx.beginPath();
    ctx.arc(cx, cy, centerR + d * ringW, 0, Math.PI * 2);
    ctx.stroke();
  }

  const hoverNode = state.hover ? state.hover.node : null;
  const selectedPath = state.selected ? state.selected.path : null;

  arcs.forEach((arc) => {
    const inner = centerR + (arc.depth - 1) * ringW;
    const outer = centerR + arc.depth * ringW;
    const isHover = hoverNode === arc.node;
    const isSelected = selectedPath && arc.node.path === selectedPath && arc.node.kind === "file";

    let fill = colorFor(arc.node, arc.depth);
    if (isSelected) fill = mix(fill, COLORS.accent, 0.42);
    if (isHover) fill = mix(fill, "#ffffff", 0.16);

    ctx.beginPath();
    ctx.arc(cx, cy, outer, arc.a0, arc.a1);
    ctx.arc(cx, cy, inner, arc.a1, arc.a0, true);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.lineWidth = isHover || isSelected ? 1.5 : 1;
    ctx.strokeStyle = isHover || isSelected ? COLORS.accent : COLORS.bg;
    ctx.stroke();

    // labels
    const mid = (arc.a0 + arc.a1) / 2;
    const midR = inner + ringW / 2;
    const arcLen = (arc.a1 - arc.a0) * midR;
    const maxText = Math.min(arcLen - 10, ringW - 12);
    const minLen = arc.depth === 1 ? LABEL_MIN_PX * 0.7 : LABEL_MIN_PX;
    if (arcLen >= minLen && maxText > 26) {
      let label = arc.node.kind === "file" ? arc.node.name : (arc.node.code || arc.node.name);
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(mid);
      let r = midR;
      if (Math.cos(mid) < 0) { ctx.rotate(Math.PI); r = -midR; }
      ctx.font = `${arc.depth === 1 ? "600 " : ""}11.5px "JetBrains Mono", ui-monospace, monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isHover ? "#ffffff" : "rgba(233,235,238,0.86)";
      ctx.fillText(fitText(label, maxText), r, 0);
      ctx.restore();
    }
  });

  drawCenter(root);
  renderOverlay();
}

function drawCenter(root) {
  const g = state.geom;
  if (!g) return;
  const { cx, cy, centerR } = g;
  ctx.beginPath();
  ctx.arc(cx, cy, centerR - 2, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.surface2;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = state.hover ? COLORS.accent : COLORS.border;
  ctx.stroke();

  const maxW = centerR * 1.55;
  let line1;
  let line2;
  let accent = false;

  if (state.hover) {
    const node = state.hover.node;
    line1 = node.kind === "file" ? node.name : (node.code || node.name);
    line2 = humanBytes(node.size);
    accent = true;
  } else {
    line1 = root.name;
    const n = root.kind === "file" ? 1 : root.count;
    line2 = `${n} file${n === 1 ? "" : "s"} · ${humanBytes(root.size)}`;
  }

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = accent ? "#ffffff" : COLORS.text;
  ctx.font = '700 13px "JetBrains Mono", ui-monospace, monospace';
  ctx.fillText(fitText(line1, maxW), cx, cy - 9);
  ctx.fillStyle = COLORS.dim;
  ctx.font = '11px "JetBrains Mono", ui-monospace, monospace';
  ctx.fillText(fitText(line2, maxW), cx, cy + 9);
}

function renderOverlay() {
  const overlay = $("#canvas-overlay");
  const files = state.tree ? totalFiles(state.tree) : 0;
  if (files === 0) {
    overlay.hidden = false;
    $("#canvas-hint").innerHTML = "No documents found. Press <b>Scan Watch Dir</b> to build the map.";
  } else {
    overlay.hidden = true;
  }
  const meta = $("#viz-meta");
  if (state.tree) {
    meta.textContent = `${files} file${files === 1 ? "" : "s"} · ${humanBytes(state.tree.size)}`;
  } else {
    meta.textContent = "—";
  }
}

/* ───────────────────────── hover + hit testing ───────────────────────── */
function hitTest(mx, my) {
  const g = state.geom;
  if (!g) return null;
  const dx = mx - g.cx;
  const dy = my - g.cy;
  const r = Math.hypot(dx, dy);
  if (r <= g.centerR) return { type: "center", node: findNode(state.tree, state.currentRootId) };
  if (r > g.R) return null;
  const depth = Math.floor((r - g.centerR) / g.ringW) + 1;
  if (depth > g.maxDepth) return null;
  let angle = Math.atan2(dy, dx);
  if (angle < -Math.PI / 2) angle += Math.PI * 2;
  const arc = state.arcs.find((a) => a.depth === depth && angle >= a.a0 && angle <= a.a1);
  return arc ? { type: "arc", node: arc.node } : null;
}

let rafPending = false;
function scheduleRender() {
  if (rafPending) return;
  rafPending = true;
  requestAnimationFrame(() => { rafPending = false; render(); });
}

function onMouseMove(event) {
  const rect = canvas.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  const hit = hitTest(mx, my);
  const node = hit && hit.type === "arc" ? hit.node : null;

  if (node !== (state.hover && state.hover.node)) {
    state.hover = node ? { node } : null;
    updateReadout(node || findNode(state.tree, state.currentRootId));
    scheduleRender();
  }
  canvas.style.cursor = hit
    ? (hit.type === "center" || (hit.node && hit.node.kind !== "file") ? "zoom-out" : "pointer")
    : "default";
}

function onMouseLeave() {
  if (state.hover) {
    state.hover = null;
    updateReadout(findNode(state.tree, state.currentRootId));
    scheduleRender();
  }
}

function onClick(event) {
  const rect = canvas.getBoundingClientRect();
  const hit = hitTest(event.clientX - rect.left, event.clientY - rect.top);
  if (!hit) return;
  if (hit.type === "center") {
    const node = findNode(state.tree, state.currentRootId);
    if (node && node.parent) setCurrentRoot(node.parent, true);
    return;
  }
  const node = hit.node;
  if (node.kind === "file") {
    selectFile(node.file);
  } else {
    setCurrentRoot(node, true);
  }
}

/* ───────────────────────── telemetry readout ─────────────────────────── */
function calibrationFor(node) {
  return node && node.path ? state.calibrations[node.path] || null : null;
}

function updateReadout(node) {
  const setV = (id, text, cls) => {
    const el = $(id);
    el.textContent = text;
    el.className = `v${cls ? ` ${cls}` : ""}`;
  };
  if (!node) {
    setV("#tel-name", "—"); setV("#tel-size", "—");
    setV("#tel-subject", "—"); setV("#tel-confidence", "—"); setV("#tel-entropy", "—");
    return;
  }
  setV("#tel-name", node.kind === "file" ? node.name : node.name);
  setV("#tel-size", node.size ? `${humanBytes(node.size)} · ${node.size.toLocaleString()} B` : "—");

  const cal = calibrationFor(node);
  if (cal) {
    setV("#tel-subject", cal.subject || "—");
    const conf = Number(cal.confidence || 0);
    setV("#tel-confidence", `${(conf * 100).toFixed(1)}%`, conf >= (state.config?.confidence_threshold ?? 0.7) ? "ok" : "warn");
    const ent = Number(cal.entropy || 0);
    setV("#tel-entropy", `${ent.toFixed(2)} bits`, ent < (state.config?.entropy_threshold ?? 1.5) ? "ok" : "warn");
  } else if (node.kind === "folder" || node.kind === "group") {
    setV("#tel-subject", node.label || node.name || "—");
    setV("#tel-confidence", `${node.count} file${node.count === 1 ? "" : "s"}`);
    setV("#tel-entropy", "—");
  } else {
    setV("#tel-subject", "uncalibrated");
    setV("#tel-confidence", "—");
    setV("#tel-entropy", "—");
  }
}

/* ═════════════════════════════ selection + inspector ══════════════════ */
async function selectFile(file) {
  state.selected = file;
  state.override = null;
  populateOverrideSelect();
  const select = $("#override-select");
  if (select) select.value = "";
  render();
  renderInspector();
  await calibrate();
}

function clearSelection() {
  state.selected = null;
  state.preview = null;
  state.override = null;
  populateOverrideSelect();
  render();
  renderInspector();
}

function renderInspector() {
  const file = state.selected;
  const empty = $("#inspector-empty");
  const fields = $("#inspector-body-fields");
  const headMeta = $("#inspector-head-meta");

  if (!file) {
    empty.classList.remove("hidden");
    fields.classList.add("hidden");
    headMeta.textContent = "no selection";
    return;
  }
  empty.classList.add("hidden");
  fields.classList.remove("hidden");
  headMeta.textContent = file.file_type ? file.file_type.toUpperCase() : "document";

  $("#ins-name").textContent = file.name;
  $("#ins-path").textContent = file.path;
  const typeTag = $("#ins-type");
  typeTag.textContent = file.file_type || "—";
  typeTag.dataset.ext = file.file_type || "";
  $("#ins-size").textContent = file.size_human || humanBytes(file.size);
  $("#ins-modified").textContent = shortTime(file.modified);

  const rename = $("#rename-input");
  if (!rename.value || rename.dataset.for !== file.path) {
    rename.value = file.name;
    rename.dataset.for = file.path;
  }

  // reset thumbnails of telemetry until calibration returns
  $("#ins-status-pill").textContent = "—";
  $("#ins-status-pill").className = "tag";
}

function renderPreview(result) {
  state.preview = result;
  if (state.selected) state.calibrations[state.selected.path] = result;

  const subject = result.subject || "";
  const meta = subjectFor(subject);

  const statusPill = $("#ins-status-pill");
  const confident = result.status === "CONFIDENT";
  statusPill.textContent = confident ? "Confident" : "Review";
  statusPill.className = `tag ${confident ? "confident" : "review"}`;

  const confidence = Number(result.confidence || 0);
  $("#ins-conf-value").textContent = `${(confidence * 100).toFixed(1)}%`;
  const bar = $("#ins-conf-bar");
  bar.className = `gauge-fill ${confident ? "confident" : "review"}`;
  bar.style.width = `${Math.max(2, confidence * 100)}%`;

  const entropy = Number(result.entropy || 0);
  const entThreshold = Number(state.config?.entropy_threshold ?? 1.5);
  $("#ins-ent-value").textContent = `${entropy.toFixed(2)} bits`;
  const entBar = $("#ins-ent-bar");
  entBar.className = `gauge-fill ${entropy < entThreshold ? "confident" : "review"}`;
  entBar.style.width = `${Math.min(100, (entropy / ENTROPY_MAX) * 100)}%`;

  $("#ins-dist-title").textContent = meta ? `${meta.code}` : subject;
  renderDistribution(result.ranking || []);

  const rename = $("#rename-input");
  if (result.suggested_rename) {
    $("#rename-hint").textContent = `Suggestion: ${result.suggested_rename}`;
    if (!rename.value.trim() || rename.value === state.selected?.name) {
      rename.value = result.suggested_rename;
    }
  }
  const changed = rename.value.trim() && rename.value.trim() !== state.selected?.name;
  $("#ins-rename-state").textContent = changed ? "renamed" : "original";

  $("#route-note").textContent = confident
    ? "Gate passed — safe to route automatically."
    : "Gate not passed — routing needs your approval.";
  $("#route-note").className = `note ${confident ? "ok" : "warn"}`;

  updateRouteButton();
  scheduleRender();
}

function renderDistribution(ranking) {
  const list = $("#distribution-list");
  list.innerHTML = "";
  if (!ranking.length) {
    list.innerHTML = '<p class="note">No distribution available.</p>';
    return;
  }
  const max = Math.max(...ranking.map((r) => r.score), 0.0001);
  ranking.slice(0, 8).forEach((row, index) => {
    const el = document.createElement("div");
    el.className = `dist-row${index === 0 ? " top" : ""}`;
    el.innerHTML = `
      <span class="label">${escapeHtml(row.subject)}</span>
      <span class="score">${(row.score * 100).toFixed(1)}%</span>
      <span class="track"><span class="fill" style="width:${(row.score / max) * 100}%"></span></span>`;
    list.appendChild(el);
  });
}

function updateRouteButton() {
  const button = $("#btn-route");
  const batch = state.checked.size;
  if (batch > 1) {
    button.textContent = `Route ${batch} Files`;
    button.disabled = state.busy;
  } else {
    button.textContent = "Route File";
    button.disabled = state.busy || !state.selected;
  }
}

/* ═════════════════════════════ calibration ════════════════════════════ */
async function calibrate() {
  if (!state.selected || state.busy) return;
  setBusy(true);
  setStatus("Calibrating document…", "busy");
  try {
    const result = await api(API.route, {
      method: "POST",
      body: {
        path: state.selected.path,
        rename: $("#rename-input").value.trim() || null,
        subject: state.override,
        move: false,
        dry_run: true,
      },
    });
    renderPreview(result);
    setStatus(result.status === "CONFIDENT" ? "Gate passed." : "Needs review.", "online");
  } catch (err) {
    $("#ins-status-pill").textContent = "Error";
    $("#ins-status-pill").className = "tag review";
    $("#route-note").textContent = err.message;
    $("#route-note").className = "note err";
    toast(`Calibration failed: ${err.message}`, "err");
    setStatus(`Calibration failed: ${err.message}`, "error");
  } finally {
    setBusy(false);
  }
}

/* ═════════════════════════════ rename ═════════════════════════════════ */
async function suggestRename() {
  if (!state.selected) { toast("Select a document first", "warn"); return; }
  try {
    const data = await api(API.suggest, {
      method: "POST",
      body: { path: state.selected.path, subject: state.override },
    });
    $("#rename-input").value = data.suggested;
    $("#rename-hint").textContent = `Title: ${data.title}`;
    $("#ins-rename-state").textContent = "renamed";
    toast(`Suggested from title: ${data.title}`, "ok");
  } catch (err) {
    toast(`Suggestion failed: ${err.message}`, "err");
  }
}

/* ═════════════════════════════ routing ════════════════════════════════ */
async function routeNow() {
  if (state.busy) return;
  const dryRun = $("#chk-dry").checked;
  const batch = Array.from(state.checked);
  setBusy(true);
  setStatus(dryRun ? "Simulating transfer…" : "Transferring…", "busy");
  try {
    if (batch.length > 1) {
      const result = await api(API.route, {
        method: "POST",
        body: { paths: batch, move: !dryRun, dry_run: dryRun, subject: state.override },
      });
      toast(`Batch: ${result.moved}/${result.count} moved`, "ok");
      state.checked.clear();
    } else if (state.selected) {
      const result = await api(API.route, {
        method: "POST",
        body: {
          path: state.selected.path,
          rename: $("#rename-input").value.trim() || null,
          subject: state.override,
          move: !dryRun,
          dry_run: dryRun,
        },
      });
      renderPreview(result);
      if (result.moved) {
        toast(`Transferred → ${result.destination.name}`, "ok");
        $("#route-note").textContent = `Moved to ${result.destination.path}`;
        $("#route-note").className = "note ok";
      } else {
        toast(result.message || "Preview only", "info");
      }
    } else {
      toast("Nothing selected", "warn");
    }
    if (!dryRun) clearSelection();
    await refreshAfterMutation();
    setStatus("Ready", "online");
  } catch (err) {
    $("#route-note").textContent = err.message;
    $("#route-note").className = "note err";
    toast(`Route failed: ${err.message}`, "err");
    setStatus(`Route failed: ${err.message}`, "error");
  } finally {
    setBusy(false);
  }
}

async function autoRouteConfident() {
  if (state.busy) return;
  const targets = state.queue.slice();
  if (!targets.length) { toast("Incoming queue is empty — scan first", "warn"); return; }
  setBusy(true);
  let moved = 0;
  try {
    for (let i = 0; i < targets.length; i += 1) {
      const file = targets[i];
      setStatus(`Auto-routing ${i + 1}/${targets.length}: ${file.name}`, "busy");
      try {
        const preview = await api(API.route, {
          method: "POST",
          body: { path: file.path, move: false, dry_run: true },
        });
        state.calibrations[file.path] = preview;
        if (preview.status === "CONFIDENT") {
          const done = await api(API.route, {
            method: "POST",
            body: { path: file.path, move: true, dry_run: false },
          });
          if (done.moved) moved += 1;
        }
      } catch (err) {
        console.warn("auto-route skip", file.path, err.message);
      }
    }
    toast(`Auto-route moved ${moved} of ${targets.length}`, moved ? "ok" : "warn");
    setStatus(`Auto-route moved ${moved} file${moved === 1 ? "" : "s"}`, "online");
    await refreshAfterMutation();
  } finally {
    setBusy(false);
  }
}

async function refreshAfterMutation() {
  await Promise.all([loadHistory(), scan({ rebuildOnly: true })]);
}

/* ═════════════════════════════ undo ═══════════════════════════════════ */
async function undoEntry(entryId) {
  try {
    const result = await api(`${API.history}/${entryId}/undo`, { method: "POST" });
    toast(result.message || "Restored", "ok");
    await refreshAfterMutation();
  } catch (err) {
    toast(`Undo failed: ${err.message}`, "err");
  }
}

async function undoLast() {
  const entry = state.history.find((e) => e.action === "move" && !e.undone);
  if (!entry) { toast("Nothing to undo", "warn"); return; }
  await undoEntry(entry.id);
}

async function clearLedger() {
  try {
    const result = await api(API.history, { method: "DELETE" });
    toast(`Cleared ${result.cleared} entries`, "ok");
    await loadHistory();
  } catch (err) {
    toast(`Clear failed: ${err.message}`, "err");
  }
}

/* ═════════════════════════════ ledger table ═══════════════════════════ */
async function loadHistory() {
  try {
    const data = await api(`${API.history}?limit=100`);
    state.history = data.entries || [];
    renderLedger();
  } catch (err) {
    console.warn("history unavailable", err.message);
  }
}

function renderLedger() {
  const body = $("#ledger-body");
  const count = state.history.length;
  $("#ledger-count").textContent = `${count} transfer${count === 1 ? "" : "s"}`;
  $("#pill-ledger").textContent = `LEDGER ${count}`;

  if (!count) {
    body.innerHTML = '<tr><td class="empty-cell" colspan="6">No transfers recorded yet.</td></tr>';
    return;
  }

  body.innerHTML = "";
  for (const entry of state.history) {
    const tr = document.createElement("tr");
    if (entry.undone) tr.className = "undone";
    const from = entry.source ? basename(entry.source) : "—";
    const to = entry.destination ? basename(entry.destination) : "—";
    const conf = Number(entry.confidence || 0);
    const status = entry.status || "";
    tr.innerHTML = `
      <td class="mono nowrap">${escapeHtml(shortTime(entry.timestamp))}</td>
      <td class="flow"><span class="from">${escapeHtml(from)}</span><span class="arrow">→</span><span class="to">${escapeHtml(to)}</span></td>
      <td class="mono nowrap">${escapeHtml(entry.subject || "—")}</td>
      <td class="mono nowrap">${(conf * 100).toFixed(0)}%</td>
      <td><span class="tag ${status === "CONFIDENT" ? "confident" : "review"}">${escapeHtml(status === "CONFIDENT" ? "Confident" : "Review")}</span></td>`;

    const actionCell = document.createElement("td");
    actionCell.style.textAlign = "right";
    if (entry.action === "move" && !entry.undone) {
      const button = document.createElement("button");
      button.className = "btn tiny";
      button.textContent = "Undo";
      button.addEventListener("click", () => undoEntry(entry.id));
      actionCell.appendChild(button);
    } else {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = entry.action === "undo" ? "restored" : entry.action;
      actionCell.appendChild(tag);
    }
    tr.appendChild(actionCell);
    body.appendChild(tr);
  }
}

/* ═════════════════════════════ telemetry / connection ════════════════ */
function applyHealth(health) {
  state.health = health;
  const pill = $("#pill-connection");
  pill.className = "pill is-online";
  $("#pill-connection-text").textContent = "ONLINE";

  $("#pill-model").textContent = health.model_loaded ? "MODEL READY" : "MODEL COLD";
  $("#pill-model").className = "pill" + (health.model_loaded ? " is-online" : " is-idle");
  $("#pill-queue").textContent = `QUEUE ${health.queue_count ?? state.queue.length}`;
  $("#pill-uptime").textContent = `UP ${formatUptime(health.uptime_seconds)}`;
}

async function pollHealth() {
  try {
    applyHealth(await api(API.health));
    setConnectionUi("online", "Connected");
  } catch (err) {
    setConnectionUi("error", "Offline");
  }
}

function setConnectionUi(kind, text) {
  const bar = $("#status-connection");
  bar.className = `sb-item ${kind}`;
  $("#status-connection-text").textContent = text;
  const pill = $("#pill-connection");
  pill.className = `pill is-${kind === "online" ? "online" : kind === "error" ? "error" : "busy"}`;
  $("#pill-connection-text").textContent = text.toUpperCase();
}

function setStatus(message, kind = "") {
  const el = $("#status-message");
  el.textContent = message || "Ready";
  el.style.color =
    kind === "error" ? COLORS.danger : kind === "busy" ? COLORS.accent : "";
}

/* ── websocket with polling fallback ──────────────────────────────────── */
function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let socket;
  try {
    socket = new WebSocket(`${proto}://${location.host}/ws`);
  } catch (err) {
    startPolling();
    return;
  }
  state.ws = socket;

  socket.addEventListener("open", () => {
    state.wsRetry = 0;
    stopPolling();
    setConnectionUi("online", "Live");
  });
  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data && data.health) applyHealth(data.health);
    } catch (err) { /* ignore malformed frames */ }
  });
  socket.addEventListener("close", () => {
    if (state.ws === socket) state.ws = null;
    setConnectionUi("error", "Polling");
    startPolling();
    if (state.wsRetry < 5) {
      state.wsRetry += 1;
      setTimeout(connectWebSocket, 4000);
    }
  });
  socket.addEventListener("error", () => {
    try { socket.close(); } catch (err) { /* noop */ }
  });
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(pollHealth, 5000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

/* ═════════════════════════════ busy state ════════════════════════════ */
function setBusy(flag) {
  state.busy = flag;
  $("#btn-scan").disabled = flag;
  $("#btn-auto-route").disabled = flag;
  $("#btn-refresh").disabled = flag;
  updateRouteButton();
}

/* ═════════════════════════════ wiring ════════════════════════════════ */
function wire() {
  $("#btn-scan").addEventListener("click", () => scan());
  $("#btn-refresh").addEventListener("click", async () => {
    await Promise.all([loadConfig(), loadSubjects()]);
    await Promise.all([loadHistory(), scan()]);
  });
  $("#btn-auto-route").addEventListener("click", autoRouteConfident);
  $("#btn-undo-last").addEventListener("click", undoLast);
  $("#btn-settings").addEventListener("click", openModal);
  $("#btn-clear-ledger").addEventListener("click", clearLedger);

  $("#btn-route").addEventListener("click", routeNow);
  $("#btn-recalibrate").addEventListener("click", calibrate);
  $("#btn-suggest").addEventListener("click", suggestRename);

  $("#rename-input").addEventListener("change", () => {
    const changed = $("#rename-input").value.trim() !== state.selected?.name;
    $("#ins-rename-state").textContent = changed ? "renamed" : "original";
  });
  $("#rename-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") calibrate();
  });
  $("#override-select").addEventListener("change", async (event) => {
    state.override = event.target.value || null;
    if (state.selected) await calibrate();
  });

  canvas.addEventListener("mousemove", onMouseMove);
  canvas.addEventListener("mouseleave", onMouseLeave);
  canvas.addEventListener("click", onClick);
  canvas.addEventListener("dblclick", (event) => {
    const rect = canvas.getBoundingClientRect();
    const hit = hitTest(event.clientX - rect.left, event.clientY - rect.top);
    if (hit && hit.type === "arc" && hit.node.kind !== "file") setCurrentRoot(hit.node, true);
  });

  $("#btn-close-modal").addEventListener("click", closeModal);
  $("#btn-cancel-config").addEventListener("click", closeModal);
  $("#btn-save-config").addEventListener("click", saveConfig);
  $("#btn-reset-config").addEventListener("click", resetConfig);
  $("#modal").addEventListener("click", (event) => {
    if (event.target === $("#modal")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  $("#cfg-conf").addEventListener("input", (e) => { $("#cfg-conf-val").textContent = Number(e.target.value).toFixed(2); });
  $("#cfg-ent").addEventListener("input", (e) => { $("#cfg-ent-val").textContent = Number(e.target.value).toFixed(2); });
  $("#cfg-temp").addEventListener("input", (e) => { $("#cfg-temp-val").textContent = Number(e.target.value).toFixed(2); });
  $("#cfg-target").addEventListener("input", updateTargetPreview);
  $("#cfg-folder-template").addEventListener("input", updateTargetPreview);

  if (window.ResizeObserver) {
    new ResizeObserver(() => resizeCanvas()).observe($("#canvas-wrap"));
  } else {
    window.addEventListener("resize", resizeCanvas);
  }
}

/* ═════════════════════════════ boot ══════════════════════════════════ */
async function boot() {
  wire();
  resizeCanvas();
  try {
    await Promise.all([loadConfig(), loadHistory()]);
    await loadSubjects();
    await scan();
  } catch (err) {
    toast(`Startup error: ${err.message}`, "err");
    setStatus(`Startup error: ${err.message}`, "error");
  }
  await pollHealth();
  connectWebSocket();
  setInterval(() => {
    if (!state.ws) pollHealth();
  }, 15000);
}

document.addEventListener("DOMContentLoaded", boot);
