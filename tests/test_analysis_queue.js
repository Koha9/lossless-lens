"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {runAnalysisQueue} = require("../web/analysis-queue.js");

test("queue bounds concurrency and keeps item indexes despite completion order", async () => {
  const releases = [];
  const results = [];
  let active = 0, peak = 0;
  const running = runAnalysisQueue(["a", "b", "c", "d"], 2, async (item, index) => {
    peak = Math.max(peak, ++active);
    await new Promise((resolve) => releases.push(resolve));
    results[index] = item;
    active--;
  });
  assert.equal(releases.length, 2);
  releases[1]();
  await new Promise(setImmediate);
  assert.equal(releases.length, 3);
  releases[2]();
  await new Promise(setImmediate);
  assert.equal(releases.length, 4);
  releases[3]();
  releases[0]();
  await running;
  assert.equal(peak, 2);
  assert.deepEqual(results, ["a", "b", "c", "d"]);
});

test("stop drains active work without starting queued items", async () => {
  let stopped = false;
  const releases = [];
  const completed = [];
  const running = runAnalysisQueue([0, 1, 2, 3], 2, async (item) => {
    await new Promise((resolve) => releases.push(resolve));
    completed.push(item);
  }, () => stopped);
  stopped = true;
  releases.forEach((release) => release());
  await running;
  assert.deepEqual(completed, [0, 1]);
  assert.equal(releases.length, 2);
});

test("one worker is serial and handled per-track failures allow later work", async () => {
  const completed = [];
  await runAnalysisQueue([0, 1, 2], 1, async (item) => {
    try {
      if (item === 1) throw new Error("bad audio");
      completed.push(item);
    } catch { completed.push("error"); }
  });
  assert.deepEqual(completed, [0, "error", 2]);
});
