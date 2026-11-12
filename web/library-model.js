"use strict";
// Shared pure selection/result rules; also exercised in Node without a browser.
function selectionSummary(ids, selected) {
  const count = ids.filter((id) => selected.has(id)).length;
  return {count, checked: ids.length > 0 && count === ids.length, indeterminate: count > 0 && count < ids.length};
}
function toggleSelection(ids, selected, checked) {
  for (const id of ids) { if (checked) selected.add(id); else selected.delete(id); }
}
function clearSelection(selected) {
  selected.clear();
}
function invertSelection(ids, selected) {
  for (const id of ids) { if (selected.has(id)) selected.delete(id); else selected.add(id); }
}
function meetsSuspiciousThreshold(result, threshold) {
  return ["clear", "suspicious"].includes(result.status) && Number.isFinite(result.score) && result.score >= threshold;
}
function resultLabel(result) {
  const labels = {unanalysed: "未分析", queued: "等待分析", running: "正在分析…", error: "分析失败 · 可重试",
    inconclusive: "证据不足", lossy: "已知有损格式 · 不适用", clear: "未检测出明显特征", suspicious: "检测出可疑特征"};
  return `${labels[result.status] || "未知状态"}${Number.isFinite(result.score) ? ` · ${result.score}/100` : ""}`;
}
function summarizeResults(results) {
  const completed = results.filter((r) => ["clear", "suspicious", "lossy", "inconclusive"].includes(r.status));
  const scored = completed.filter((r) => Number.isFinite(r.score));
  const worst = scored.reduce((a, b) => !a || b.score > a.score ? b : a, null);
  const failures = results.filter((r) => r.status === "error").length;
  const suspicious = results.filter((r) => r.status === "suspicious").length;
  const pending = results.some((r) => ["queued", "running"].includes(r.status));
  const status = worst?.status || (pending ? "running" : failures ? "error" : completed.length ? "inconclusive" : "unanalysed");
  return {status, score: worst?.score ?? null,
    label: `已分析 ${completed.length}/${results.length}${suspicious ? ` · 可疑 ${suspicious}` : ""}${worst ? ` · 最高 ${worst.score}` : ""}${failures ? ` · 失败 ${failures}` : ""}${pending ? " · 分析中" : ""}`};
}
if (typeof module !== "undefined") module.exports = {selectionSummary, toggleSelection, clearSelection, invertSelection, meetsSuspiciousThreshold, resultLabel, summarizeResults};
