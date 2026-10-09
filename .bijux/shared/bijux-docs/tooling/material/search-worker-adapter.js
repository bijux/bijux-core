/* Own only the admitted native search worker channel; Material owns setup, queries and rendering. */
(function () {
  "use strict";
  const deadline = 8000;
  const settle = 150;
  let state = Object.freeze({ stage: "worker-idle", attempt: 0 });
  let active;
  function publish(stage, attempt, phase, reason) {
    state = Object.freeze({ stage, attempt, phase, ...(reason ? { reason } : {}) });
    window.dispatchEvent(new CustomEvent("bijux:search-worker-status", { detail: state }));
  }
  function channel(url, Subject) {
    let workerURL;
    try {
      const config = JSON.parse(document.getElementById("__config").textContent);
      const base = new URL(config.base + "/", location.href);
      workerURL = new URL(url, location.href);
      if (!/^https?:$/.test(workerURL.protocol) || workerURL.origin !== location.origin || !workerURL.pathname.startsWith(base.pathname)) workerURL = null;
    } catch (_) { workerURL = null; }
    if (active && !active.disposed && active.url === workerURL?.href) return active.subject;
    active?.dispose();
    const subject = new Subject();
    const receive = subject.next.bind(subject);
    let worker = null, timer = null, queryTimer = null, generation = 0, attempts = 0, disposed = false;
    let setup = null, query = null, revision = 0, ready = false, inFlight = null, queued = null;
    let phase = "load";
    function cancel() {
      clearTimeout(timer); timer = null;
      clearTimeout(queryTimer); queryTimer = null;
      if (worker) {
        worker.onmessage = worker.onerror = worker.onmessageerror = null;
        worker.terminate(); worker = null;
      }
      ready = false; inFlight = queued = null;
    }
    function unavailable(reason, current = generation) {
      if (disposed || current !== generation) return;
      const failedPhase = phase;
      generation += 1;
      cancel();
      publish("worker-unavailable", attempts, failedPhase, reason);
    }
    function arm(current) {
      clearTimeout(timer);
      timer = setTimeout(() => unavailable("timeout", current), deadline);
    }
    function send(message) {
      if (!worker || disposed) return;
      // Start the actual operation deadline once, before callbacks can reenter.
      if (message.type === 0) { phase = "setup"; arm(generation); }
      if (message.type === 2) { phase = "query"; arm(generation); }
      try {
        worker.postMessage(message);
      } catch (_) { unavailable("post-message"); }
    }
    function drain() {
      if (!ready || !worker || disposed || inFlight || !queued?.eligible) return;
      inFlight = queued; queued = null;
      send(inFlight.message);
    }
    function queue(message) {
      clearTimeout(queryTimer);
      const current = generation;
      const entry = queued = { message, revision, eligible: false };
      // Native QUERY contents stay untouched. This bounds intermediate typing
      // work independently of the deadline of a query already in the worker.
      queryTimer = setTimeout(() => {
        if (disposed || current !== generation || queued !== entry) return;
        queryTimer = null; entry.eligible = true; drain();
      }, settle);
      if (state.stage !== "worker-searching") publish("worker-searching", attempts, "query");
    }
    function start() {
      if (disposed) return;
      cancel();
      const current = ++generation; attempts += 1;
      phase = "load";
      publish("worker-loading", attempts, phase);
      if (!workerURL) { unavailable("scope", current); return; }
      try {
        worker = new Worker(workerURL.href);
        worker.onerror = event => {
          // Handle only this owned resource error. Global page errors remain visible.
          event.preventDefault();
          unavailable("worker-error", current);
        };
        worker.onmessageerror = () => unavailable("message-error", current);
        worker.onmessage = event => {
          if (disposed || current !== generation) return;
          const message = event.data;
          if (message?.type === 1 && setup && !ready) {
            clearTimeout(timer); timer = null; ready = true; phase = "ready";
            // A recovered worker still owes the cached query an actual answer.
            // Keep the result view excluded until native rendering receives it.
            if (query) queue(query);
            else publish("worker-ready", attempts, phase);
            if (disposed || current !== generation) return;
            receive(message);
            // Native query observers retain their first READY. A replacement must
            // replay the latest native query without refetching or changing it.
            if (!disposed && current === generation && query && !queued && !inFlight) queue(query);
          } else if (message?.type === 3 && ready && inFlight && message.data && Array.isArray(message.data.items)) {
            const completed = inFlight;
            clearTimeout(timer); timer = null; inFlight = null; phase = "ready";
            // A newer native QUERY makes this answer obsolete. Never allow it
            // into native rendering while the latest input waits for its turn.
            if (!queued || queued.revision === completed.revision) receive(message);
            drain();
            if (!disposed && current === generation && ready && !inFlight && !queued) {
              publish("worker-ready", attempts, "ready");
            }
          } else { unavailable("protocol", current); }
        };
        if (setup) send(setup);
      } catch (_) { unavailable("worker-construction", current); }
    }
    subject.next = message => {
      if (disposed) return;
      if (message?.type === 0) { setup = message; ready = false; if (worker) send(message); }
      else if (message?.type === 2) { query = message; revision += 1; if (ready) queue(message); }
    };
    function suspend(event) {
      if (!event.persisted) { dispose(); return; }
      generation += 1; cancel();
      publish("worker-loading", attempts, "suspended");
    }
    function resume(event) { if (event.persisted) start(); }
    function dispose() {
      if (disposed) return;
      disposed = true; generation += 1; cancel(); setup = query = null;
      window.removeEventListener("bijux:search-worker-retry", start);
      window.removeEventListener("pagehide", suspend);
      window.removeEventListener("pageshow", resume);
      subject.complete();
    }
    active = { url: workerURL?.href, subject, dispose, get disposed() { return disposed; } };
    window.addEventListener("bijux:search-worker-retry", start);
    window.addEventListener("pagehide", suspend);
    window.addEventListener("pageshow", resume);
    start();
    return subject;
  }
  window.bijuxSearchWorker = Object.freeze({ get state() { return state; }, channel, dispose() { active?.dispose(); } });
})();
