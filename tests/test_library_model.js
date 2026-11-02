"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {selectionSummary, toggleSelection, meetsSuspiciousThreshold, resultLabel, summarizeResults} = require("../web/library-model.js");

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
