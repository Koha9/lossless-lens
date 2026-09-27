"use strict";

const $ = (id) => document.getElementById(id);
const palette = ["#b8f078", "#68c8f2", "#d7a0ec", "#ffbd7a", "#ff849b", "#65dfcc", "#d7d99c", "#a4afff"];
const colorscale = [[0, "#121725"], [.22, "#20334f"], [.45, "#286686"], [.65, "#37a6a2"], [.84, "#a8dd75"], [1, "#ffe59a"]];
const state = {tracks: [], selected: new Set(), data: new Map(), errors: new Map(), displayed: [], mode: "2d", busy: false, cameraRevision: 0};
state.reports = new Map();
state.pending = new Set();
state.activeId = null;
state.stopRequested = false;
state.analyzing = false;
state.libraryView = "tree";
state.expandedFolders = new Set();
let folderBadges = [];
try { if (localStorage.getItem("flac-library-view") === "list") state.libraryView = "list"; } catch { /* Storage can be disabled. */ }
const plotConfig = {responsive: true, displaylogo: false, scrollZoom: true, modeBarButtonsToRemove: ["select2d", "lasso2d", "toImage"], doubleClick: "reset"};
let renderPending = false;
let renderPromise = null;

function message(text, kind = "") {
  $("status").textContent = text;
  $("status").className = `status ${kind}`;
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function escapePlotText(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
function shortName(name, size = 40) {
  const stem = name.replace(/\.(flac|wav|wave|aiff?|aifc|mp[23]|m4[ab]|aac|og[ag]|opus|wma|ape|wv|caf)$/i, "");
  return stem.length > size ? `${stem.slice(0, size - 1)}…` : stem;
}
function duration(seconds) {
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
function audioDetails(info) {
  const codecs = {MPEG_LAYER_III: "MP3", MPEG_LAYER_II: "MP2", VORBIS: "Vorbis", OPUS: "Opus", WMAV1: "WMA", WMAV2: "WMA", WAVPACK: "WavPack"};
  return `${info.sample_rate / 1000} kHz / ${info.bit_depth ? `${info.bit_depth} bit` : (codecs[info.subtype] || info.subtype)}`;
}
async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `请求失败 (${response.status})`);
  }
  return response.json();
}
function setBusy(value) {
  state.busy = value;
  $("scan-button").disabled = value;
  $("folder").disabled = value;
  $("clear-selection").disabled = value;
  $("mode-2d").disabled = value;
  $("mode-3d").disabled = value;
  updateSelection();
  renderLibrary();
}
function updateSelection() {
  const max = state.mode === "2d" ? 4 : 8;
  $("selection-count").textContent = `已选 ${state.selected.size} 首`;
  $("selection-help").textContent = `批量分析不限数量 · ${state.mode.toUpperCase()} 对比最多 ${max} 首`;
  $("compare").disabled = state.busy || !state.selected.size || state.selected.size > max;
  $("compare").textContent = `生成对比${state.selected.size ? ` · ${state.selected.size} 首` : ""} ↗`;
  $("analyze-selected").disabled = state.busy || !state.selected.size;
  $("analyze-selected").textContent = `分析所选${state.selected.size ? ` · ${state.selected.size} 首` : ""}`;
  $("stop-analysis").hidden = !state.analyzing;
  $("stop-analysis").disabled = state.stopRequested;
  $("stop-analysis").textContent = state.stopRequested ? "完成当前文件后停止…" : "停止后续分析";
  const all = selectionSummary(state.tracks.map((t) => t.id), state.selected);
  $("select-all").checked = all.checked;
  $("select-all").indeterminate = all.indeterminate;
  $("select-all").disabled = state.busy || !state.tracks.length;
  for (const {badge, ids, checkbox} of folderBadges) {
    const selected = selectionSummary(ids, state.selected);
    badge.textContent = `${selected.count}/${ids.length}`;
    badge.classList.toggle("has-selection", selected.count > 0);
    badge.title = `已选 ${selected.count} / ${ids.length} 首（含子文件夹）`;
    checkbox.checked = selected.checked;
    checkbox.indeterminate = selected.indeterminate;
    checkbox.disabled = state.busy;
  }
}
function paintResult(node, result) {
  node.dataset.analysisStatus = result.status;
  if (result.score !== null && result.score !== undefined) {
    const score = Math.max(0, Math.min(100, result.score));
    const hue = score < 35 ? 145 - score : 55 * (100 - score) / 65;
    node.style.setProperty("--result-color", `hsl(${hue} 78% 72%)`);
    node.style.setProperty("--result-bg", `hsl(${hue} 70% 45% / ${.07 + score / 100 * .23})`);
  }
}
function reportFor(id) {
  if (state.activeId === id) return {status: "running", score: null};
  if (state.pending.has(id)) return {status: "queued", score: null};
  if (state.errors.has(id)) return {status: "error", score: null};
  return state.reports.get(id) || {status: "unanalysed", score: null};
}
function showReport(track) {
  const report = state.reports.get(track.id);
  $("report-title").textContent = track.name;
  $("report-path").textContent = track.relative_path;
  $("report-verdict").textContent = resultLabel(reportFor(track.id));
  $("report-reasons").replaceChildren();
  const reasons = state.errors.has(track.id) ? [state.errors.get(track.id)] : (report?.reasons || ["勾选此文件，点击「分析所选」。"]);
  for (const reason of reasons) $("report-reasons").append(element("li", "", reason));
  $("report-dialog").showModal();
}
function trackRow(track, compact = false) {
  const row = element("div", compact ? "track-row compact-track" : "track-row");
  row.dataset.trackId = track.id;
  row.title = track.relative_path;
  const label = element("label", "track-selection");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = state.selected.has(track.id);
  checkbox.disabled = state.busy;
  checkbox.setAttribute("aria-label", track.relative_path);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.selected.add(track.id);
    else state.selected.delete(track.id);
    updateSelection();
  });
  const copy = element("span", "track-copy");
  const name = element("span", "track-name", compact ? track.name : shortName(track.name, 100));
  copy.append(name);
  if (!compact) copy.append(element("span", "track-meta", `${track.name.split(".").pop().toUpperCase()} · ${(track.size_bytes / 1048576).toFixed(1)} MB`));
  const result = reportFor(track.id);
  paintResult(row, result);
  copy.append(element("span", "analysis-badge", resultLabel(result)));
  label.append(checkbox, copy);
  const details = element("button", "evidence-button", "详情");
  details.type = "button";
  details.setAttribute("aria-label", `分析详情：${track.relative_path}`);
  details.addEventListener("click", () => showReport(track));
  row.append(label, details);
  return row;
}
function makeTree(tracks) {
  const root = {folders: new Map(), tracks: [], ids: [], key: ""};
  for (const track of tracks) {
    const parts = track.relative_path.split(/[\\/]/);
    let node = root;
    node.ids.push(track.id);
    for (const part of parts.slice(0, -1)) {
      if (!node.folders.has(part)) node.folders.set(part, {name: part, key: `${node.key}/${part}`, folders: new Map(), tracks: [], ids: []});
      node = node.folders.get(part);
      node.ids.push(track.id);
    }
    node.tracks.push(track);
  }
  return root;
}
function renderLibrary() {
  const query = $("search").value.trim().toLocaleLowerCase();
  const tracks = state.tracks.filter((t) => t.relative_path.toLocaleLowerCase().includes(query));
  const allFolders = new Map();
  function collect(node) { allFolders.set(node.key, node); for (const child of node.folders.values()) collect(child); }
  collect(makeTree(state.tracks));
  const list = $("track-list");
  const scrollTop = list.scrollTop;
  const tree = state.libraryView === "tree";
  list.replaceChildren();
  folderBadges = [];
  list.classList.toggle("tree-view", tree);
  $("tree-actions").hidden = !tree;
  for (const view of ["tree", "list"]) {
    $(`view-${view}`).classList.toggle("active", state.libraryView === view);
    $(`view-${view}`).setAttribute("aria-pressed", String(state.libraryView === view));
  }
  if (!tracks.length) list.append(element("p", "library-empty", state.tracks.length ? "没有匹配的曲目，试试其他关键词。" : "此文件夹内没有可用音频。请检查路径后重新扫描。"));
  if (!tree) {
    tracks.forEach((track) => list.append(trackRow(track)));
  } else {
    function appendNode(node, parent) {
      for (const child of node.folders.values()) {
        const details = element("details", "tree-folder");
        details.open = Boolean(query) || state.expandedFolders.has(child.key);
        const summary = element("summary", "folder-summary");
        summary.title = child.key.slice(1);
        const badge = element("span", "folder-count");
        const ids = allFolders.get(child.key).ids;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.setAttribute("aria-label", `选择文件夹 ${child.key.slice(1)}（含全部子文件）`);
        checkbox.addEventListener("click", (event) => event.stopPropagation());
        checkbox.addEventListener("keydown", (event) => event.stopPropagation());
        checkbox.addEventListener("change", () => {
          toggleSelection(ids, state.selected, checkbox.checked);
          renderLibrary();
        });
        const copy = element("span", "folder-copy");
        copy.append(element("span", "folder-name", child.name));
        const aggregate = summarizeResults(ids.map(reportFor));
        paintResult(summary, aggregate);
        copy.append(element("span", "analysis-badge", aggregate.label));
        summary.title = `${child.key.slice(1)} · 勾选包含全部子文件（含搜索隐藏项）；颜色取已完成文件中的最高评分`;
        summary.append(checkbox, copy, badge);
        folderBadges.push({badge, ids, checkbox});
        details.append(summary);
        const children = element("div", "tree-children");
        appendNode(child, children);
        details.append(children);
        // Register after setting open, and ignore detached nodes' queued events.
        details.addEventListener("toggle", () => {
          if (query || !details.isConnected) return;
          if (details.open) state.expandedFolders.add(child.key);
          else state.expandedFolders.delete(child.key);
        });
        parent.append(details);
      }
      node.tracks.forEach((track) => parent.append(trackRow(track, true)));
    }
    appendNode(makeTree(tracks), list);
  }
  updateSelection();
  list.scrollTop = scrollTop;
}
function setLibraryView(view) {
  state.libraryView = view;
  try { localStorage.setItem("flac-library-view", view); } catch { /* Optional preference only. */ }
  renderLibrary();
}
async function scan() {
  if (state.busy) return;
  setBusy(true);
  message("正在扫描音频文件夹…", "busy");
  try {
    const result = await api("/api/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({folder: $("folder").value.trim()})});
    state.tracks = result.tracks;
    state.selected = new Set();
    state.expandedFolders.clear();
    state.data.clear();
    state.errors.clear();
    state.reports.clear();
    $("analysis-progress").hidden = true;
    state.displayed = [];
    $("folder").value = result.folder;
    $("search").value = "";
    $("track-count").textContent = result.tracks.length;
    await scheduleRender();
    message(result.tracks.length ? `找到 ${result.tracks.length} 首曲目。勾选文件或文件夹，点击「分析所选」。` : "没有找到支持的音频文件，请更换文件夹。");
  } catch (error) {
    message(error.message, "error");
  } finally {
    setBusy(false);
  }
}
async function analyzeSelected() {
  if (state.busy || !state.selected.size) return;
  const tracks = state.tracks.filter((t) => state.selected.has(t.id));
  state.pending = new Set(tracks.map((t) => t.id));
  state.stopRequested = false;
  state.analyzing = true;
  setBusy(true);
  $("analysis-progress").hidden = false;
  $("analysis-meter").max = tracks.length;
  $("analysis-meter").value = 0;
  let completed = 0, failed = 0;
  try {
    for (const track of tracks) {
      if (state.stopRequested) break;
      state.activeId = track.id;
      $("analysis-progress-text").textContent = `${completed} / ${tracks.length} · 正在分析 ${track.name}`;
      message(`正在分析 ${completed + 1} / ${tracks.length}：${track.name}`, "busy");
      renderLibrary();
      try {
        const data = await api(`/api/tracks/${track.id}/analysis`);
        state.reports.set(track.id, data.forensics);
        state.errors.delete(track.id);
      } catch (error) {
        failed++;
        state.reports.delete(track.id);
        state.errors.set(track.id, error.message);
      }
      state.pending.delete(track.id);
      state.activeId = null;
      completed++;
      $("analysis-meter").value = completed;
      renderLibrary();
    }
  } finally {
    state.pending.clear();
    state.activeId = null;
    state.analyzing = false;
    setBusy(false);
    const text = `${completed < tracks.length ? "已停止" : "分析完成"} · 已处理 ${completed} / ${tracks.length} · 失败 ${failed}`;
    $("analysis-progress-text").textContent = text;
    message(`${text}。结果已标在文件树上，点击「详情」查看依据。`, failed ? "error" : "");
  }
}
async function compare() {
  if (state.busy || !state.selected.size) return;
  const ids = [...state.selected];
  if (ids.length > (state.mode === "2d" ? 4 : 8)) return;
  setBusy(true);
  const results = [];
  try {
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      const track = state.tracks.find((t) => t.id === id);
      message(`正在分析 ${i + 1} / ${ids.length}：${track.name} · 首次读取将覆盖整首音频`, "busy");
      try {
        // The server caches by file size and modification time. Request every
        // comparison so replacing a file cannot silently reuse stale plots.
        const data = await api(`/api/tracks/${id}`);
        state.data.set(id, data);
        state.reports.set(id, data.forensics);
        state.errors.delete(id);
        results.push(data);
      } catch (error) {
        state.errors.set(id, error.message);
        state.reports.delete(id);
        state.data.delete(id);
      }
    }
    state.displayed = results;
    state.cameraRevision++;
    // Only retain the active selection in the browser; the server has an LRU.
    for (const id of state.data.keys()) if (!state.selected.has(id)) state.data.delete(id);
    await scheduleRender();
    const failures = ids.length - results.length;
    const silent = results.filter((d) => d.summary.silent).length;
    message(failures ? `${results.length} 首已显示，${failures} 首分析失败。左侧可查看具体原因，重新生成可重试。` : `已显示 ${results.length} 首曲目 · 全曲分析 · ${state.mode === "2d" ? "统一坐标与色阶" : "拖动图表旋转视角"}${silent ? ` · ${silent} 首为静音` : ""}`, failures ? "error" : "");
  } catch (error) {
    message(`图表渲染失败：${error.message}。可尝试 2D 模式。`, "error");
  } finally {
    setBusy(false);
  }
}
function setMode(mode) {
  if (state.busy || state.mode === mode) return;
  if (mode === "2d" && state.displayed.length > 4) {
    message("请先点击「生成对比」更新为当前勾选的最多 4 首，再切换 2D。", "error");
    return;
  }
  state.mode = mode;
  state.cameraRevision++;
  for (const value of ["2d", "3d"]) {
    $(`mode-${value}`).classList.toggle("active", mode === value);
    $(`mode-${value}`).setAttribute("aria-pressed", String(mode === value));
  }
  $("three-controls").hidden = mode !== "3d";
  updateSelection();
  scheduleRender().catch(renderError);
}
function commonLayout() {
  return {paper_bgcolor: "#151c21", plot_bgcolor: "#151c21", font: {family: '"Segoe UI", "Microsoft YaHei", sans-serif', color: "#a8b6b0", size: 10}, margin: {l: 65, r: 30, t: 30, b: 55}, showlegend: false, hoverlabel: {bgcolor: "#202b30", font: {color: "#e5ebe7"}}, uirevision: `${state.mode}-${state.cameraRevision}`, autosize: true};
}
function axis(title, range) {
  return {title: {text: title, font: {size: 11}, standoff: 12}, range, gridcolor: "#2a343a", zerolinecolor: "#39463f", linecolor: "#39463f", tickfont: {size: 10}, automargin: true};
}
function camera() { return {eye: {x: 1.65, y: -2.0, z: 1.15}, projection: {type: "orthographic"}}; }
function ranges() {
  const data = state.displayed;
  const nyquist = Math.max(...data.map((d) => d.info.sample_rate / 2000));
  return {frequency: Number($("frequency-limit").value) ? Math.min(nyquist, Number($("frequency-limit").value)) : nyquist,
    floor: -Number($("db-range").value), relativeTime: $("time-mode").value === "relative",
    time: $("time-mode").value === "relative" ? 100 : Math.max(...data.map((d) => d.info.duration_sec))};
}
function renderLegendAndSummary() {
  $("legend").replaceChildren();
  $("summary-body").replaceChildren();
  state.displayed.forEach((d, i) => {
    const item = element("div", "legend-item");
    const swatch = element("span", "swatch");
    swatch.style.background = palette[i];
    const label = element("span", "", `${String(i + 1).padStart(2, "0")}  ${shortName(d.name, 60)}`);
    item.title = d.name;
    item.append(swatch, label);
    $("legend").append(item);
    const row = document.createElement("tr");
    const name = element("td", "", shortName(d.name, 48));
    name.prepend(swatch.cloneNode());
    name.title = d.name;
    row.append(name, element("td", "", audioDetails(d.info)),
      element("td", "", duration(d.info.duration_sec)),
      element("td", "", d.summary.silent ? "静音" : `${(d.summary.edge_99_hz / 1000).toFixed(2)} kHz`),
      element("td", "", d.summary.cutoff_hz ? `${(d.summary.cutoff_hz / 1000).toFixed(2)} kHz` : "未检测到"));
    $("summary-body").append(row);
  });
}
async function drawSpectrum(context) {
  const r = context.ranges;
  const is3d = context.mode === "3d";
  const traces = context.data.map((d, i) => {
    const basic = {name: escapePlotText(shortName(d.name, 65)), x: d.spectrum.frequency_khz, line: {color: palette[i], width: is3d ? 3 : 1.5}, mode: "lines", connectgaps: false};
    if (is3d) return {...basic, type: "scatter3d", y: d.spectrum.frequency_khz.map(() => i + 1), z: d.spectrum.relative_db, hovertemplate: "%{x:.3f} kHz<br>%{z:.1f} dB<extra>%{fullData.name}</extra>"};
    return {...basic, type: "scatter", y: d.spectrum.relative_db, hovertemplate: "%{x:.3f} kHz<br>%{y:.1f} dB<extra>%{fullData.name}</extra>"};
  });
  const layout = commonLayout();
  if (is3d) {
    layout.scene = {xaxis: axis("Frequency (kHz)", [0, r.frequency]), yaxis: {...axis("曲目", [.5, context.data.length + .5]), tickvals: context.data.map((_, i) => i + 1), ticktext: context.data.map((_, i) => `曲目 ${i + 1}`)}, zaxis: axis("Relative magnitude (dB)", [r.floor, 0]), camera: camera(), aspectmode: "manual", aspectratio: {x: 1.8, y: context.gap, z: .85}, bgcolor: "#151c21"};
    layout.margin = {l: 10, r: 10, t: 5, b: 10};
  } else {
    layout.xaxis = axis("Frequency (kHz)", [0, r.frequency]);
    layout.yaxis = axis("Relative magnitude (dB)", [r.floor, 3]);
    layout.hovermode = "closest";
  }
  $("spectrum-plot").style.height = is3d ? "460px" : "350px";
  await Plotly.react("spectrum-plot", traces, layout, plotConfig);
}
// Peak aggregation for 3D, with no interpolation across missing buckets.
function reduceHeatmap(d, maxRows = 129, maxColumns = 128) {
  const source = d.spectrogram;
  const rows = source.frequency_khz.length, columns = source.time_sec.length;
  const rowStep = Math.ceil(rows / maxRows), columnStep = Math.ceil(columns / maxColumns);
  const z = [], frequencies = [], times = [];
  for (let c = 0; c < columns; c += columnStep) {
    const end = Math.min(columns, c + columnStep) - 1;
    times.push((source.time_sec[c] + source.time_sec[end]) / 2);
  }
  for (let row = 0; row < rows; row += rowStep) {
    const end = Math.min(rows, row + rowStep) - 1;
    frequencies.push((source.frequency_khz[row] + source.frequency_khz[end]) / 2);
    const values = [];
    for (let c = 0; c < columns; c += columnStep) {
      let peak = null;
      for (let y = row; y <= end; y++) for (let x = c; x < Math.min(columns, c + columnStep); x++) {
        const v = source.relative_db[y][x];
        if (v !== null && (peak === null || v > peak)) peak = v;
      }
      values.push(peak);
    }
    z.push(values);
  }
  return {frequency_khz: frequencies, time_sec: times, relative_db: z};
}
async function drawSpectrogram(context) {
  const r = context.ranges, is3d = context.mode === "3d", count = context.data.length;
  const layout = commonLayout(), traces = [];
  const timeTitle = r.relativeTime ? "Track progress (%)" : "Time (s)";
  const mobile = $("spectrogram-plot").clientWidth < 620;
  const columns = mobile || count === 1 ? 1 : 2;
  const rows = Math.ceil(count / columns);
  const colorbar = {title: {text: "dB", side: "top"}, thickness: 9, len: .92, outlinewidth: 0, tickfont: {size: 9}, x: 1.015};
  if (is3d) {
    layout.scene = {xaxis: axis(timeTitle, [0, r.time]), yaxis: axis("Frequency (kHz)", [0, r.frequency]), zaxis: {...axis("曲目层", [.7, count + .35]), tickvals: context.data.map((_, i) => i + 1), ticktext: context.data.map((_, i) => `曲目 ${i + 1}`)}, camera: camera(), aspectmode: "manual", aspectratio: {x: 1.8, y: 1.1, z: context.gap}, bgcolor: "#151c21"};
    layout.margin = {l: 10, r: 55, t: 10, b: 15};
  } else {
    layout.annotations = [];
    layout.margin = {l: 60, r: 66, t: 45, b: 55};
    layout.coloraxis = {colorscale, cmin: r.floor, cmax: 0, colorbar};
  }
  context.data.forEach((d, i) => {
    const s = is3d ? reduceHeatmap(d) : d.spectrogram;
    const times = s.time_sec.map((v) => r.relativeTime ? v / d.info.duration_sec * 100 : v);
    const name = escapePlotText(shortName(d.name, 60));
    if (is3d) {
      traces.push({type: "surface", name, x: times, y: s.frequency_khz,
        z: s.relative_db.map((row) => row.map((v) => v === null ? null : i + 1)), surfacecolor: s.relative_db,
        colorscale, cmin: r.floor, cmax: 0, showscale: i === 0, colorbar,
        opacity: context.opacity, connectgaps: false,
        lighting: {ambient: 1, diffuse: 0, specular: 0, roughness: 1, fresnel: 0},
        hovertemplate: `%{x:.2f} ${r.relativeTime ? "%" : "s"}<br>%{y:.2f} kHz<br>%{surfacecolor:.0f} dB<extra>${name}</extra>`});
    } else {
      const suffix = i === 0 ? "" : String(i + 1);
      const column = i % columns, row = Math.floor(i / columns);
      const xGap = columns === 1 ? 0 : .105, yGap = rows === 1 ? 0 : .20;
      const width = (1 - xGap * (columns - 1)) / columns, height = (1 - yGap * (rows - 1)) / rows;
      const x0 = column * (width + xGap), y1 = 1 - row * (height + yGap);
      layout[`xaxis${suffix}`] = {...axis(timeTitle, [0, r.time]), domain: [x0, x0 + width], anchor: `y${suffix}`, ...(i ? {matches: "x"} : {})};
      layout[`yaxis${suffix}`] = {...axis("Frequency (kHz)", [0, r.frequency]), domain: [y1 - height, y1], anchor: `x${suffix}`, ...(i ? {matches: "y"} : {})};
      layout.annotations.push({text: `${String(i + 1).padStart(2, "0")} · ${escapePlotText(shortName(d.name, mobile ? 36 : 32))}`, x: x0, y: y1 + (rows === 1 ? .045 : .026), xref: "paper", yref: "paper", xanchor: "left", yanchor: "bottom", showarrow: false, font: {size: 10, color: palette[i]}});
      traces.push({type: "heatmap", name, x: times, y: s.frequency_khz, z: s.relative_db,
        xaxis: `x${suffix}`, yaxis: `y${suffix}`, coloraxis: "coloraxis", zsmooth: false, connectgaps: false, hoverongaps: false,
        hovertemplate: `%{x:.2f} ${r.relativeTime ? "%" : "s"}<br>%{y:.2f} kHz<br>%{z:.0f} dB<extra>${name}</extra>`});
    }
  });
  $("spectrogram-plot").style.height = `${is3d ? 570 : rows * 250 + 70}px`;
  $("spectrogram-caption").textContent = is3d ? "Frequency — Time · 高度代表曲目层，颜色代表相对功率" : "Frequency — Time · 相同频率、时间范围与色阶";
  await Plotly.react("spectrogram-plot", traces, layout, plotConfig);
}
async function scheduleRender() {
  renderPending = true;
  if (renderPromise) return renderPromise;
  // All callers await the same completion; each frame keeps one data snapshot.
  renderPromise = Promise.resolve().then(async () => {
    while (renderPending) {
      renderPending = false;
      const hasData = state.displayed.length > 0;
      $("charts").hidden = !hasData;
      $("empty-state").hidden = hasData;
      renderLegendAndSummary();
      if (hasData) {
        const context = {data: [...state.displayed], mode: state.mode,
          ranges: ranges(), gap: Number($("layer-gap").value), opacity: Number($("opacity").value)};
        await drawSpectrum(context);
        await drawSpectrogram(context);
      } else {
        Plotly.purge("spectrum-plot");
        Plotly.purge("spectrogram-plot");
      }
    }
  }).finally(() => { renderPromise = null; });
  return renderPromise;
}
function renderError(error) { message(`图表渲染失败：${error.message}。请尝试切换 2D。`, "error"); }
async function exportChart(id, filename) {
  const button = id === "spectrum-plot" ? $("export-spectrum") : $("export-spectrogram");
  button.disabled = true;
  button.textContent = "生成 PNG…";
  try {
    if (renderPromise) await renderPromise;
    const plot = $(id);
    // Export an independent figure with identifying legends. The live camera
    // and zoom are retained, and the user's active plot is not changed.
    const layout = {...plot.layout, showlegend: true,
      title: {text: `${id === "spectrum-plot" ? "Frequency spectrum" : "Spectrogram"} · ${state.mode.toUpperCase()} · per-track relative dB`, font: {size: 18}, x: .5, y: .99, xanchor: "center", yanchor: "top"},
      margin: {...plot.layout.margin, t: 100, b: 160},
      legend: {orientation: "h", y: -.18, x: 0, font: {size: 11}}};
    if (layout.scene && plot._fullLayout.scene) layout.scene = {...layout.scene, camera: plot._fullLayout.scene.camera};
    const figure = {data: plot.data.map((trace) => ({...trace, showlegend: true})), layout};
    const url = await Plotly.toImage(figure, {format: "png", width: 1600, height: Math.max(850, plot.clientHeight * 1.4 + 180), scale: 1});
    $("export-image").src = url;
    $("export-download").href = url;
    $("export-download").download = `${filename}.png`;
    $("export-title").textContent = `${id === "spectrum-plot" ? "频谱" : "时频图"} · PNG 预览`;
    $("export-dialog").showModal();
  } catch (error) { message(`导出失败：${error.message}`, "error"); }
  finally { button.disabled = false; button.textContent = "导出 PNG ↓"; }
}
$("scan-form").addEventListener("submit", (event) => { event.preventDefault(); scan(); });
$("search").addEventListener("input", renderLibrary);
$("view-tree").addEventListener("click", () => setLibraryView("tree"));
$("view-list").addEventListener("click", () => setLibraryView("list"));
$("expand-folders").addEventListener("click", () => {
  function visit(node) { for (const child of node.folders.values()) { state.expandedFolders.add(child.key); visit(child); } }
  visit(makeTree(state.tracks));
  renderLibrary();
});
$("collapse-folders").addEventListener("click", () => {
  state.expandedFolders.clear();
  $("search").value = "";
  renderLibrary();
});
$("clear-selection").addEventListener("click", () => {
  state.selected.clear();
  renderLibrary();
  updateSelection();
  message("已清空选择，当前图表仍显示上一次对比结果。勾选曲目后可重新生成。");
});
$("select-all").addEventListener("change", () => {
  toggleSelection(state.tracks.map((t) => t.id), state.selected, $("select-all").checked);
  renderLibrary();
});
$("analyze-selected").addEventListener("click", analyzeSelected);
$("stop-analysis").addEventListener("click", () => { state.stopRequested = true; updateSelection(); });
$("close-report").addEventListener("click", () => $("report-dialog").close());
$("compare").addEventListener("click", compare);
$("mode-2d").addEventListener("click", () => setMode("2d"));
$("mode-3d").addEventListener("click", () => setMode("3d"));
for (const id of ["frequency-limit", "db-range", "time-mode", "layer-gap", "opacity"]) {
  $(id).addEventListener("change", () => { state.cameraRevision++; scheduleRender().catch(renderError); });
}
$("reset-camera").addEventListener("click", () => { state.cameraRevision++; scheduleRender().catch(renderError); });
$("export-spectrum").addEventListener("click", () => exportChart("spectrum-plot", `flac-spectrum-${state.mode}`));
$("export-spectrogram").addEventListener("click", () => exportChart("spectrogram-plot", `flac-spectrogram-${state.mode}`));
$("close-export").addEventListener("click", () => $("export-dialog").close());
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => scheduleRender().catch(renderError), 180); });
(async () => {
  try {
    if (!window.Plotly) throw new Error("图表库未能加载。请确认已安装 requirements-web.txt，然后刷新页面。");
    const config = await api("/api/config");
    $("folder").value = config.default_folder;
    $("format-help").title = config.supported_extensions.join(" / ");
    $("format-help").textContent = config.ffmpeg_available ? "包含子文件夹 · 常见无损 / 有损音频" : "包含子文件夹 · M4A / AAC 等格式需安装 FFmpeg";
    await scan();
  } catch (error) { message(error.message, "error"); }
})();
