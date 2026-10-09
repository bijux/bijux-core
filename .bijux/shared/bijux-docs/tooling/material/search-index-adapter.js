/* Native search owns ranking/results; this boundary owns bounded, intent-driven index transport. */
(function () {
  "use strict";
  let state = Object.freeze({ stage: "index-idle", attempt: 0 });
  const totalDeadline = 45000;
  const stallDeadline = 8000;

  function publish(stage, attempt, reason, progress) {
    state = Object.freeze({ stage, attempt, ...(reason ? { reason } : {}), ...(progress || {}) });
    window.dispatchEvent(new CustomEvent("bijux:search-index-status", { detail: state }));
  }

  function admitted(index) {
    if (!index || typeof index.config !== "object" || !index.config || Array.isArray(index.config) || !Array.isArray(index.docs) || index.docs.length > 50000) return false;
    let characters = 0;
    for (const doc of index.docs) {
      if (!doc || typeof doc.location !== "string" || typeof doc.title !== "string" || typeof doc.text !== "string") return false;
      characters += doc.location.length + doc.title.length + doc.text.length;
      if (characters > 40 * 1024 * 1024) return false;
    }
    return true;
  }

  function observe(factory, shareReplay) {
    const model = factory();
    const Observable = model.constructor;
    let indexURL;
    try {
      const config = JSON.parse(document.getElementById("__config").textContent);
      indexURL = new URL("search/search_index.json", new URL(config.base + "/", location.href));
      if (!/^https?:$/.test(indexURL.protocol) || indexURL.origin !== location.origin) indexURL = null;
    } catch (_) { indexURL = null; }
    return new Observable(observer => {
      let disposed = false, generation = 0, attempt = null, totalTimer = null, stallTimer = null;
      let cached = false, intended = false, resumeInterrupted = false, starting = false;
      function clearTimers() {
        clearTimeout(totalTimer); totalTimer = null;
        clearTimeout(stallTimer); stallTimer = null;
      }
      function detach(request) {
        request.onload = request.onerror = request.ontimeout = request.onabort = request.onprogress = null;
      }
      function cancel() {
        starting = false;
        clearTimers();
        if (attempt) { const request = attempt; attempt = null; detach(request); request.abort(); }
      }
      function request() {
        if (disposed || cached || attempt || starting) return;
        const current = ++generation;
        starting = true;
        publish("index-loading", current, null, { received_bytes: 0 });
        if (disposed || current !== generation || !starting) return;
        const startedAt = Date.now();
        let settled = false, loaded = 0, announcedAt = 0;
        function unavailable(reason) {
          if (disposed || current !== generation || settled) return;
          settled = true;
          cancel();
          publish("index-unavailable", current, reason, { received_bytes: loaded });
        }
        function resetStall() {
          clearTimeout(stallTimer);
          stallTimer = setTimeout(() => unavailable("stalled"), stallDeadline);
        }
        if (!indexURL) { unavailable("scope"); return; }
        // Actual operation age never renews on input, progress, headers or queued Retry.
        totalTimer = setTimeout(() => unavailable("timeout"), totalDeadline);
        resetStall();
        try {
          const xhr = new XMLHttpRequest();
          attempt = xhr; starting = false;
          xhr.open("GET", indexURL.href, true);
          xhr.responseType = "text";
          xhr.timeout = totalDeadline;
          xhr.onload = () => {
            if (disposed || current !== generation || settled) return;
            if (Date.now() - startedAt >= totalDeadline) { unavailable("timeout"); return; }
            if (xhr.status < 200 || xhr.status >= 300) { unavailable("network"); return; }
            if (xhr.responseText.length > 40 * 1024 * 1024) { unavailable("index-size"); return; }
            let index;
            try { index = JSON.parse(xhr.responseText); } catch (_) { unavailable("invalid-index"); return; }
            if (!admitted(index)) { unavailable("invalid-index"); return; }
            if (Date.now() - startedAt >= totalDeadline) { unavailable("timeout"); return; }
            settled = true; cached = true;
            clearTimers(); detach(xhr); attempt = null;
            publish("index-ready", current);
            if (!disposed && current === generation) observer.next(index);
          };
          xhr.onerror = () => unavailable("network");
          xhr.ontimeout = () => unavailable("timeout");
          xhr.onabort = () => unavailable("aborted");
          xhr.onprogress = event => {
            if (disposed || current !== generation || settled) return;
            if (Date.now() - startedAt >= totalDeadline) { unavailable("timeout"); return; }
            if (!Number.isFinite(event.loaded) || event.loaded < loaded) { unavailable("invalid-progress"); return; }
            if (event.loaded > 80 * 1024 * 1024) { unavailable("index-size"); return; }
            if (event.loaded > loaded) {
              loaded = event.loaded;
              resetStall();
              // ProgressEvent byte accounting differs for compressed responses across engines.
              // Preserve browser-reported bytes without inventing an encoded percentage.
              const now = Date.now();
              if (now - announcedAt >= 1000) {
                announcedAt = now;
                publish("index-loading", current, null, { received_bytes: loaded });
              }
            }
          };
          xhr.send();
        } catch (_) { unavailable("setup"); }
      }
      function intent(event) {
        const target = event?.target;
        if (event && !((target?.matches?.("[data-md-component='search-query']")) || (target?.id === "__search" && target.checked))) return;
        intended = true;
        // Focus/input/checkbox repetition cannot replace a transfer or renew its deadline.
        if (state.stage !== "index-unavailable") request();
      }
      function retry() { intended = true; request(); }
      function locationIntent() {
        try {
          const url = new URL(location.href);
          // Native highlighting needs the same admitted index on a shared result link.
          if (url.searchParams.has("q") || url.searchParams.get("h")) intent();
        } catch (_) { /* An invalid document URL cannot establish search intent. */ }
      }
      function userCancel() {
        if ((!attempt && !starting) || disposed) return;
        generation += 1;
        cancel(); resumeInterrupted = false;
        publish("index-unavailable", generation, "cancelled");
      }
      function suspend() {
        resumeInterrupted = !!attempt || starting;
        generation += 1; cancel();
      }
      function resume(event) {
        if (event.persisted && resumeInterrupted && intended && !cached) {
          resumeInterrupted = false; request();
        }
      }
      window.addEventListener("bijux:search-index-retry", retry);
      window.addEventListener("bijux:search-index-cancel", userCancel);
      window.addEventListener("pagehide", suspend);
      window.addEventListener("pageshow", resume);
      window.addEventListener("popstate", locationIntent);
      window.addEventListener("bijux:search-location", locationIntent);
      document.addEventListener("focusin", intent, true);
      document.addEventListener("input", intent, true);
      document.addEventListener("change", intent, true);
      try {
        const query = document.querySelector("[data-md-component='search-query']");
        if (query?.value || document.activeElement === query || document.getElementById("__search")?.checked) intent();
        locationIntent();
      } catch (_) { /* An invalid document URL cannot establish search intent. */ }
      return () => {
        disposed = true; generation += 1; cancel();
        window.removeEventListener("bijux:search-index-retry", retry);
        window.removeEventListener("bijux:search-index-cancel", userCancel);
        window.removeEventListener("pagehide", suspend);
        window.removeEventListener("pageshow", resume);
        window.removeEventListener("popstate", locationIntent);
        window.removeEventListener("bijux:search-location", locationIntent);
        document.removeEventListener("focusin", intent, true);
        document.removeEventListener("input", intent, true);
        document.removeEventListener("change", intent, true);
      };
    }).pipe(shareReplay({ bufferSize: 1, refCount: true }));
  }

  window.bijuxSearchIndex = Object.freeze({ get state() { return state; }, observe });
})();
