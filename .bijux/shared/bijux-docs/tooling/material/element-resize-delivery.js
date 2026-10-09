/* Native measurements remain unchanged; deliver resize batches outside observer notification. */
function __bijuxElementResizeObserver(deliver) {
  const active = new Map();
  const pending = new Map();
  let generation = 0;
  let frame;
  const observer = new ResizeObserver(entries => {
    for (const entry of entries) {
      const token = active.get(entry.target);
      if (token !== undefined) pending.set(entry.target, {entry, token});
    }
    if (pending.size && frame === undefined) {
      frame = requestAnimationFrame(() => {
        frame = undefined;
        const batch = [...pending.values()];
        pending.clear();
        for (const {entry, token} of batch) {
          if (active.get(entry.target) === token) deliver(entry);
        }
      });
    }
  });
  const observe = observer.observe.bind(observer);
  const unobserve = observer.unobserve.bind(observer);
  const disconnect = observer.disconnect.bind(observer);
  const cancelEmpty = () => {
    if (!pending.size && frame !== undefined) {
      cancelAnimationFrame(frame);
      frame = undefined;
    }
  };
  observer.observe = (target, options) => {
    if (!active.has(target)) active.set(target, ++generation);
    return observe(target, options);
  };
  observer.unobserve = target => {
    active.delete(target);
    pending.delete(target);
    cancelEmpty();
    return unobserve(target);
  };
  observer.disconnect = () => {
    active.clear();
    pending.clear();
    cancelEmpty();
    return disconnect();
  };
  return observer;
}
