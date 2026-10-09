(function () {
  "use strict";
  const shell = (window.bijuxShell = window.bijuxShell || {});
  if (shell.searchRecovery) return;

  function bind(signal) {
    const output = document.querySelector(".md-search__output");
    const query = document.querySelector("[data-md-component='search-query']");
    if (!output || !query) return;
    let panel = output.querySelector(".bijux-search-recovery");
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "bijux-search-recovery";
      panel.hidden = true;
      const status = document.createElement("p");
      status.setAttribute("role", "status");
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "md-button";
      retry.textContent = "Retry search";
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "md-button";
      cancel.dataset.bijuxIndexCancel = "true";
      cancel.textContent = "Cancel download";
      cancel.hidden = true;
      panel.append(status, retry, cancel);
      output.prepend(panel);
    }
    const status = panel.querySelector("[role='status']");
    const retry = panel.querySelector("button");
    const cancel = panel.querySelector("[data-bijux-index-cancel]");
    const nativeResults = output.querySelector(".md-search-result");
    let preservedResults;
    function excludeResults(exclude) {
      if (!nativeResults) return;
      if (exclude && !preservedResults) {
        preservedResults = { hidden: nativeResults.hidden, inert: nativeResults.inert };
        nativeResults.hidden = true;
        nativeResults.inert = true;
      } else if (!exclude && preservedResults) {
        nativeResults.hidden = preservedResults.hidden;
        nativeResults.inert = preservedResults.inert;
        preservedResults = undefined;
      }
    }
    function sync() {
      const state = window.bijuxSearchIndex?.state;
      if (!state) return;
      const worker = window.bijuxSearchWorker?.state;
      const failed = state.stage === "index-unavailable" || worker?.stage === "worker-unavailable";
      const searching = worker?.stage === "worker-searching";
      const loading = state.stage === "index-loading" || worker?.stage === "worker-loading" || searching;
      excludeResults(failed || loading);
      const cancelOwnedFocus = cancel && document.activeElement === cancel;
      if (cancel) {
        cancel.hidden = state.stage !== "index-loading";
        cancel.disabled = state.stage !== "index-loading";
      }
      if (failed || loading) {
        panel.hidden = false;
        const retrying = Math.max(state.attempt || 0, worker?.attempt || 0) > 1;
        status.textContent = failed ? state.reason === "cancelled" ? "Search download canceled. Retry when you are ready."
          : state.reason === "stalled" ? "Search download stalled. Check the connection and retry."
          : state.reason === "timeout" ? "Search download timed out. Check the connection and retry."
          : "Search is unavailable. Browse the navigation or retry."
          : state.stage === "index-loading" ? "Downloading search index…" : searching ? "Searching…" : retrying ? "Retrying search…" : "Preparing search…";
        retry.disabled = !failed && loading;
        if (cancelOwnedFocus && failed) retry.focus();
        panel.setAttribute("aria-busy", String(!failed && loading));
      } else if (state.stage === "index-ready" && (!worker || worker.stage === "worker-ready")) {
        if (panel.contains(document.activeElement)) query.focus();
        panel.hidden = true;
        status.textContent = "";
        panel.setAttribute("aria-busy", "false");
        // The admitted native worker announces indexing/readiness and returns results.
      }
    }
    retry.addEventListener("click", () => {
      // Disabling the focused Retry button must preserve the reader's editing intent.
      if (document.activeElement === retry && document.getElementById("__search")?.checked &&
          query.getClientRects().length && getComputedStyle(query).visibility !== "hidden") {
        query.focus();
      }
      if (window.bijuxSearchIndex?.state.stage === "index-unavailable") {
        window.dispatchEvent(new Event("bijux:search-index-retry"));
      }
      if (window.bijuxSearchWorker?.state.stage === "worker-unavailable") {
        window.dispatchEvent(new Event("bijux:search-worker-retry"));
      }
    }, { signal });
    cancel?.addEventListener("click", () => {
      window.dispatchEvent(new Event("bijux:search-index-cancel"));
    }, { signal });
    if (!document.querySelector("[data-bijux-header-control='search-toggle']")) {
      // Native Material closes search on Tab. Busy/failure controls need keyboard
      // access; healthy native search retains its ordinary keyboard behavior.
      document.addEventListener("keydown", event => {
        if (event.key !== "Tab" || panel.hidden || !document.getElementById("__search")?.checked) return;
        if (document.activeElement !== query && !panel.contains(document.activeElement)) return;
        const nodes = [query, retry, cancel].filter(node => node && !node.hidden && !node.disabled && node.getClientRects().length && getComputedStyle(node).visibility !== "hidden");
        if (!nodes.length) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const index = nodes.indexOf(document.activeElement);
        const next = (Math.max(0, index) + nodes.length + (event.shiftKey ? -1 : 1)) % nodes.length;
        nodes[next].focus();
      }, { capture: true, signal });
    }
    window.addEventListener("bijux:search-index-status", sync, { signal });
    window.addEventListener("bijux:search-worker-status", sync, { signal });
    signal.addEventListener("abort", () => excludeResults(false), { once: true });
    sync();
  }

  shell.searchRecovery = { bind };
})();
