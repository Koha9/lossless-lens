"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {selectionSummary, toggleSelection, clearSelection, invertSelection, meetsSuspiciousThreshold, resultLabel, summarizeResults} = require("../web/library-model.js");
const {readFileSync} = require("node:fs");
const vm = require("node:vm");

test("clear selection preserves the shared Set and safely repeats on an empty library", () => {
  const selected = new Set(["album/one", "album/disc/two"]);
  const alias = selected;
  assert.equal(clearSelection(selected), undefined);
  assert.strictEqual(selected, alias);
  assert.equal(alias.size, 0);
  clearSelection(selected);
  assert.equal(alias.size, 0);
  assert.deepEqual(selectionSummary([], selected), {count: 0, checked: false, indeterminate: false});
  toggleSelection(["new-scan"], alias, true);
  assert.equal(selected.has("new-scan"), true);
  clearSelection(alias);
  assert.equal(selected.size, 0);
});

test("invert selection complements the scanned scope and restores membership on a second inversion", () => {
  const ids = Object.freeze(["a", "b", "c"]);
  for (const initial of [[], ["a", "b", "c"], ["b"]]) {
    const selected = new Set([...initial, "outside"]);
    const alias = selected;
    assert.equal(invertSelection(ids, selected), undefined);
    assert.strictEqual(selected, alias);
    assert.deepEqual(new Set(selected), new Set([...ids.filter((id) => !initial.includes(id)), "outside"]));
    invertSelection(ids, selected);
    assert.deepEqual(selected, new Set([...initial, "outside"]));
  }
  const selected = new Set(["outside"]);
  invertSelection([], selected);
  assert.deepEqual(selected, new Set(["outside"]));
  assert.deepEqual(ids, ["a", "b", "c"]);
});

test("whole-library operations include search-hidden tracks and keep nested folder summaries consistent", () => {
  const tracks = ["album/root.flac", "album/disc/one.flac", "album/disc/bonus/two.flac", "other/three.flac"];
  const album = tracks.slice(0, 3);
  const disc = album.slice(1);
  const bonus = disc.slice(1);
  const visible = tracks.filter((id) => id.endsWith("root.flac"));
  const selected = new Set();
  const none = {count: 0, checked: false, indeterminate: false};
  const all = (count) => ({count, checked: true, indeterminate: false});
  const partial = (count) => ({count, checked: false, indeterminate: true});
  const summaries = () => [tracks, album, disc, bonus, visible].map((ids) => selectionSummary(ids, selected));
  assert.deepEqual(summaries(), [none, none, none, none, none]);
  toggleSelection(tracks, selected, true);
  assert.deepEqual(summaries(), [all(4), all(3), all(2), all(1), all(1)]);
  toggleSelection([disc[0]], selected, false);
  assert.deepEqual(summaries(), [partial(3), partial(2), partial(1), all(1), all(1)]);
  invertSelection(tracks, selected);
  assert.deepEqual(selected, new Set([disc[0]]));
  assert.deepEqual(summaries(), [partial(1), partial(1), partial(1), none, none]);
  invertSelection(tracks, selected);
  assert.deepEqual(summaries(), [partial(3), partial(2), partial(1), all(1), all(1)]);
  clearSelection(selected);
  assert.deepEqual(summaries(), [none, none, none, none, none]);
  invertSelection(tracks, selected);
  assert.deepEqual(summaries(), [all(4), all(3), all(2), all(1), all(1)]);
  toggleSelection(album, selected, false);
  assert.deepEqual(selected, new Set([tracks[3]]));
  assert.deepEqual(summaries(), [partial(1), none, none, none, none]);
});

test("classic browser script exposes the same pure API without DOM or Node globals", () => {
  const context = vm.createContext({});
  vm.runInContext(readFileSync(require.resolve("../web/library-model.js"), "utf8"), context);
  for (const name of ["clearSelection", "invertSelection", "selectionSummary", "toggleSelection",
    "meetsSuspiciousThreshold", "resultLabel", "summarizeResults"]) {
    assert.equal(typeof context[name], "function", name);
  }
  const selected = new Set(["a"]);
  context.invertSelection(["a", "b"], selected);
  assert.deepEqual(selected, new Set(["b"]));
  const summary = context.selectionSummary(["a", "b"], selected);
  assert.equal(summary.count, 1);
  assert.equal(summary.checked, false);
  assert.equal(summary.indeterminate, true);
  context.clearSelection(selected);
  assert.equal(selected.size, 0);
});

test("suspicious selection uses an inclusive adjustable score threshold and completed evidence", () => {
  assert.equal(meetsSuspiciousThreshold({status: "suspicious", score: 35}, 35), true);
  assert.equal(meetsSuspiciousThreshold({status: "suspicious", score: 75}, 80), false);
  assert.equal(meetsSuspiciousThreshold({status: "clear", score: 25}, 20), true);
  assert.equal(meetsSuspiciousThreshold({status: "clear", score: 0}, 0), true);
  for (const status of ["error", "queued", "running", "lossy", "inconclusive", "unanalysed"]) {
    assert.equal(meetsSuspiciousThreshold({status, score: 95}, 35), false);
    assert.equal(meetsSuspiciousThreshold({status, score: null}, 0), false);
  }
});
test("folder selection supports all descendants, mixed state and more than 8 files", () => {
  const ids = Array.from({length: 20}, (_, i) => String(i));
  const selected = new Set(["outside"]);
  toggleSelection(ids, selected, true);
  assert.deepEqual(selectionSummary(ids, selected), {count: 20, checked: true, indeterminate: false});
  toggleSelection(["1"], selected, false);
  assert.equal(selectionSummary(ids, selected).indeterminate, true);
  toggleSelection(ids, selected, false);
  assert.deepEqual([...selected], ["outside"]);
  assert.equal(selectionSummary([], selected).checked, false);
});
test("folder summary reports worst score without hiding unfinished or failed children", () => {
  const result = summarizeResults([{status: "clear", score: 0}, {status: "suspicious", score: 75},
    {status: "unanalysed", score: null}, {status: "error", score: null}]);
  assert.equal(result.score, 75);
  assert.equal(result.status, "suspicious");
  assert.match(result.label, /已分析 2\/4/);
  assert.match(result.label, /失败 1/);
  assert.match(result.label, /可疑 1/);
});
test("unknown, failed and unanalysed results do not become a zero score", () => {
  for (const status of ["inconclusive", "lossy", "error", "unanalysed", "queued", "running"]) {
    assert.equal(summarizeResults([{status, score: null}]).score, null);
    assert.doesNotMatch(resultLabel({status, score: null}), /0\/100/);
  }
  assert.match(resultLabel({status: "clear", score: 0}), /0\/100/);
});
