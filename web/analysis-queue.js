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

if (typeof module !== "undefined") module.exports = {runAnalysisQueue};
