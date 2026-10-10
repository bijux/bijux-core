function __bijuxWatchViewportHistory(observe) {
  // Native viewport debounce work belongs only to an active document. A late
  // replaceState commit can evict a realm that has entered the browser cache.
  let subscription, generation = 0, active = false;
  function suspend() {
    active = false;
    generation += 1;
    subscription?.unsubscribe();
    subscription = undefined;
  }
  function resume() {
    if (active) return;
    active = true;
    const current = ++generation;
    subscription = observe().subscribe(({ offset }) => {
      if (!active || current !== generation) return;
      const state = history.state;
      if (state !== null && Object.prototype.toString.call(state) !== "[object Object]") return;
      // Material owns x/y, while another reader owner may retain entry context.
      history.replaceState({ ...state, ...offset }, "");
    });
  }
  function departing(event) {
    if (!event.isTrusted || event.destination.sameDocument) return;
    suspend();
    const current = generation;
    const cancelled = () => { if (current === generation && !active) resume(); };
    event.signal?.addEventListener("abort", cancelled, { once: true });
    queueMicrotask(() => { if (event.defaultPrevented || event.signal?.aborted) cancelled(); });
  }
  if (window.navigation) window.navigation.addEventListener("navigate", departing);
  else document.addEventListener("click", event => {
    if (!event.isTrusted || event.defaultPrevented || event.button !== 0 ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const link = event.target.closest?.('a[target="_self"][href]');
    if (!link || link.hasAttribute("download")) return;
    let destination;
    try { destination = new URL(link.href, location.href); } catch (_) { return; }
    if (!/^https?:$/.test(destination.protocol) ||
        destination.origin === location.origin && destination.pathname === location.pathname &&
        destination.search === location.search) return;
    suspend();
    const current = generation;
    queueMicrotask(() => { if (event.defaultPrevented && current === generation) resume(); });
  }, true);
  window.addEventListener("pagehide", event => { if (event.isTrusted) suspend(); });
  window.addEventListener("pageshow", event => { if (event.isTrusted && event.persisted) resume(); });
  resume();
}
