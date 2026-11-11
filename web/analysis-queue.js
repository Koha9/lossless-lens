"use strict";

// Workers claim the next item only after finishing the previous one. Stopping
// leaves active requests to finish and never submits the remaining queue.
async function runAnalysisQueue(items, workers, visit, shouldStop = () => false) {
  let next = 0;
  await Promise.all(Array.from({length: Math.min(workers, items.length)}, async () => {
    while (!shouldStop() && next < items.length) {
      const index = next++;
      await visit(items[index], index);
    }
  }));
}

// One controller owns one round. Only claimed requests contribute to active;
// stopping preserves queued items as notStarted until the round is discarded.
function createAnalysisRun(items, workers, visit, onUpdate = () => {}) {
  const queue = items.slice();
  const active = new Map();
  let status = "idle", next = 0, succeeded = 0, failed = 0;
  let stopped = false, completion, resolveCompletion;

  function getSnapshot() {
    return {
      status, total: queue.length, completed: succeeded + failed,
      succeeded, failed, notStarted: queue.length - next,
      active: Array.from(active, ([index, item]) => ({index, item}))
        .sort((a, b) => a.index - b.index),
    };
  }

  function publish() { onUpdate(getSnapshot()); }

  function finishIfDrained() {
    if (active.size || (!stopped && next < queue.length)) return;
    const terminal = next < queue.length ? "stopped" : "completed";
    if (status !== terminal) {
      status = terminal;
      publish();
    }
    if (resolveCompletion) resolveCompletion(getSnapshot());
  }

  function settle(index, success) {
    active.delete(index);
    if (success) succeeded++;
    else failed++;
    publish();
    pump();
  }

  function pump() {
    while (!stopped && next < queue.length && active.size < workers) {
      const index = next++;
      active.set(index, queue[index]);
      publish();
      // The claim is already active even if an observer calls stop here.
      // Normalize synchronous throws so settlement never recursively pumps.
      let request;
      try { request = visit(queue[index], index); }
      catch (error) { request = Promise.reject(error); }
      Promise.resolve(request).then(
        () => settle(index, true), () => settle(index, false));
    }
    finishIfDrained();
  }

  function start() {
    if (completion) return completion;
    completion = new Promise((resolve) => { resolveCompletion = resolve; });
    if (status === "idle" && queue.length) {
      status = "running";
      publish();
    }
    pump();
    return completion;
  }

  function stop() {
    if (stopped || status === "completed" || status === "stopped") return;
    stopped = true;
    if (active.size) {
      status = "stopping";
      publish();
    }
    finishIfDrained();
  }

  return {start, stop, getSnapshot};
}

if (typeof module !== "undefined") module.exports = {runAnalysisQueue, createAnalysisRun};
