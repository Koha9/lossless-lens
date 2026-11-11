"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {runAnalysisQueue, createAnalysisRun} = require("../web/analysis-queue.js");
const fs = require("node:fs");
const vm = require("node:vm");

const tick = () => new Promise(setImmediate);

function controlled(items, workers) {
  const requests = [], events = [], saved = [];
  const run = createAnalysisRun(items, workers, (item, index) => {
    return new Promise((resolve, reject) => requests.push({item, index, resolve, reject}));
  }, (snapshot) => {
    assert.deepEqual(Object.keys(snapshot).sort(),
      ["status", "total", "completed", "succeeded", "failed", "notStarted", "active"].sort());
    assert.equal(snapshot.completed, snapshot.succeeded + snapshot.failed);
    assert.equal(snapshot.total, snapshot.completed + snapshot.active.length + snapshot.notStarted);
    for (const key of ["total", "completed", "succeeded", "failed", "notStarted"]) {
      assert.ok(Number.isInteger(snapshot[key]) && snapshot[key] >= 0);
    }
    assert.ok(snapshot.active.length <= workers);
    assert.deepEqual(snapshot.active.map(({index}) => index),
      snapshot.active.map(({index}) => index).sort((a, b) => a - b));
    for (const {index, item} of snapshot.active) assert.equal(item, items[index]);
    events.push(snapshot);
    saved.push(JSON.stringify(snapshot));
  });
  return {run, requests, events, assertStable() {
    assert.deepEqual(events.map((event) => JSON.stringify(event)), saved);
  }};
}

test("run exposes all active identities through out-of-order success and failure", async () => {
  const items = [{id: "same"}, {id: "same"}, {id: "c"}, {id: "d"}];
  const c = controlled(items, 2);
  assert.equal(c.run.getSnapshot().status, "idle");
  assert.equal(c.requests.length, 0);
  const done = c.run.start();
  assert.equal(c.run.start(), done);
  const old = c.run.getSnapshot();
  assert.deepEqual(old.active, [{index: 0, item: items[0]}, {index: 1, item: items[1]}]);
  c.requests[1].resolve();
  await tick();
  assert.deepEqual(c.run.getSnapshot().active.map(({index}) => index), [0, 2]);
  c.requests[2].reject(new Error("bad audio"));
  await tick();
  assert.deepEqual(c.run.getSnapshot().active.map(({index}) => index), [0, 3]);
  c.requests[3].resolve();
  c.requests[0].resolve();
  assert.deepEqual(await done, {status: "completed", total: 4, completed: 4,
    succeeded: 3, failed: 1, notStarted: 0, active: []});
  assert.equal(old.active.length, 2);
  assert.equal(old.completed, 0);
  assert.notEqual(old.active, c.events[2].active);
  assert.notEqual(old.active[0], c.events[2].active[0]);
  c.assertStable();
  const final = c.run.getSnapshot();
  c.run.stop();
  assert.deepEqual(c.run.getSnapshot(), final);
  assert.equal(c.run.start(), done);
});

test("stop drains every claimed request and leaves queued work unstarted", async () => {
  const c = controlled([0, 1, 2, 3], 2);
  let finished = false;
  const done = c.run.start();
  done.then(() => { finished = true; });
  c.run.stop();
  c.run.stop();
  assert.equal(c.run.getSnapshot().status, "stopping");
  c.requests[1].reject(new Error("failed while stopping"));
  await tick();
  assert.equal(finished, false);
  assert.equal(c.run.getSnapshot().status, "stopping");
  assert.equal(c.requests.length, 2);
  c.requests[0].resolve();
  assert.deepEqual(await done, {status: "stopped", total: 4, completed: 2,
    succeeded: 1, failed: 1, notStarted: 2, active: []});
  c.run.stop();
  assert.equal(c.run.getSnapshot().status, "stopped");
  c.assertStable();
});

test("idle stop prevents all claims; empty runs complete even when stopped first", async () => {
  for (const items of [[1, 2], []]) {
    const c = controlled(items, 2);
    c.run.stop();
    const status = items.length ? "stopped" : "completed";
    assert.equal(c.run.getSnapshot().status, status);
    const done = c.run.start();
    assert.equal(c.run.start(), done);
    assert.equal((await done).status, status);
    assert.equal(c.requests.length, 0);
    c.assertStable();
  }
  const empty = controlled([], 2);
  assert.equal((await empty.run.start()).status, "completed");
  assert.equal(empty.events.length, 1);
});

test("stop at the final request boundary ends completed after draining", async () => {
  const c = controlled([0, 1], 2);
  const done = c.run.start();
  c.requests[0].resolve();
  await tick();
  c.run.stop();
  assert.equal(c.run.getSnapshot().status, "stopping");
  c.requests[1].resolve();
  assert.equal((await done).status, "completed");
  c.assertStable();
});

test("synchronous throws and rejected requests are isolated and all-failure rounds complete", async () => {
  const visited = [];
  const run = createAnalysisRun([0, 1, 2], 1, (item, index) => {
    visited.push([item, index]);
    if (item !== 1) throw new Error("sync");
    return Promise.reject(new Error("async"));
  });
  assert.deepEqual(await run.start(), {status: "completed", total: 3, completed: 3,
    succeeded: 0, failed: 3, notStarted: 0, active: []});
  assert.deepEqual(visited, [[0, 0], [1, 1], [2, 2]]);
});

test("new rounds reset counters and stop flags while earlier snapshots remain stable", async () => {
  const first = controlled([0, 1], 1);
  const done = first.run.start();
  first.run.stop();
  first.requests[0].resolve();
  const previous = await done;
  const second = controlled([0, 1], 2);
  assert.deepEqual(second.run.getSnapshot(), {status: "idle", total: 2, completed: 0,
    succeeded: 0, failed: 0, notStarted: 2, active: []});
  const again = second.run.start();
  second.requests.forEach(({resolve}) => resolve());
  assert.equal((await again).completed, 2);
  assert.equal(previous.status, "stopped");
  assert.equal(previous.notStarted, 1);
  first.assertStable();
  second.assertStable();
});

test("observers can stop at running, claim, and settlement boundaries", async () => {
  for (const boundary of ["running", "claim", "settlement"]) {
    let run, samePromise;
    const visited = [];
    run = createAnalysisRun([0, 1, 2], 1, (item) => { visited.push(item); }, (s) => {
      samePromise = run.start();
      if ((boundary === "running" && s.status === "running" && !s.active.length) ||
          (boundary === "claim" && s.active.length) ||
          (boundary === "settlement" && s.completed)) run.stop();
    });
    const done = run.start();
    assert.equal(done, samePromise);
    assert.equal((await done).status, "stopped");
    assert.deepEqual(visited, boundary === "running" ? [] : [0]);
  }
});

test("browser scripts and CommonJS both export the new and legacy APIs", async () => {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(require.resolve("../web/analysis-queue.js"), "utf8"), context);
  assert.equal(typeof context.runAnalysisQueue, "function");
  assert.equal(typeof context.createAnalysisRun, "function");
  assert.equal((await context.createAnalysisRun([], 1, () => {}).start()).status, "completed");
  assert.equal(typeof runAnalysisQueue, "function");
  assert.equal(typeof createAnalysisRun, "function");
});

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
