function __bijuxScrollCurrentFragment(hash) {
  // Restoration owns the current entry, never an additional native navigation.
  if (!hash || hash[0] !== "#") return;
  const expected = new URL(hash, location.href);
  if (expected.href !== location.href) return;
  let id = hash.slice(1);
  try { id = decodeURIComponent(id); } catch (_) {}
  const target = document.getElementById(id) ||
    Array.from(document.getElementsByName(id)).find(node => node.tagName === "A");
  if (!target) return;

  // Fragment navigation reveals until-found ancestors before moving the reader.
  for (let node = target; node; node = node.parentElement) {
    if (node.getAttribute("hidden") === "until-found") {
      node.dispatchEvent(new Event("beforematch", { bubbles: true }));
      node.removeAttribute("hidden");
    }
  }
  if (expected.href !== location.href || !target.isConnected) return;
  for (let node = target.parentElement; node; node = node.parentElement) {
    if (node.tagName === "DETAILS" && !node.open) {
      const summary = Array.from(node.children).find(child => child.tagName === "SUMMARY");
      if (!summary || !summary.contains(target)) node.open = true;
    }
  }
  target.scrollIntoView();

  // Preserve the browser's sequential focus starting point without retaining a tab stop.
  const authoredTabIndex = target.getAttribute("tabindex");
  target.focus({ preventScroll: true });
  if (document.activeElement !== target && authoredTabIndex === null) {
    target.setAttribute("tabindex", "-1");
    const restore = () => {
      target.removeEventListener("blur", restore);
      if (target.getAttribute("tabindex") === "-1") target.removeAttribute("tabindex");
    };
    target.addEventListener("blur", restore, { once: true });
    try {
      target.focus({ preventScroll: true });
    } finally {
      if (document.activeElement !== target) restore();
    }
  }
}
