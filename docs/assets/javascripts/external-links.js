(function () {
  "use strict";
  const shell = (window.bijuxShell = window.bijuxShell || {});
  if (shell.externalLinks) return;
  let nextId = 0;
  const attributes = ["href", "target", "download", "rel", "aria-label", "aria-labelledby"];
  const signature = link => attributes.map(name => link.getAttribute(name));
  const same = (left, right) => left.every((value, index) => value === right[index]);
  const set = (node, name, value) => {
    if (value === null) node.removeAttribute(name);
    else if (node.getAttribute(name) !== value) node.setAttribute(name, value);
  };

  function bind(signal) {
    if (signal.aborted) return;
    const records = new Map();
    function restore(link, record) {
      if (link.getAttribute("rel") === record.ownedRel) set(link, "rel", record.rel);
      if (link.getAttribute("data-bijux-external-link") === record.ownedExternal) {
        set(link, "data-bijux-external-link", record.external);
      }
      if (record.warning) {
        record.warning.remove();
        if (record.described) {
          const ids = (link.getAttribute("aria-describedby") || "").split(/\s+/).filter(id => id && id !== record.warning.id);
          set(link, "aria-describedby", link.getAttribute("aria-describedby") === record.ownedDescription
            ? record.description : (ids.length ? ids.join(" ") : null));
        }
      }
    }
    function decorate(link) {
      const prior = records.get(link);
      if (prior && same(prior.signature, signature(link)) && (!prior.warning || prior.warning.parentNode === link)) return;
      if (prior) restore(link, prior);
      const record = { rel: link.getAttribute("rel"), external: link.getAttribute("data-bijux-external-link"), description: link.getAttribute("aria-describedby") };
      let url;
      try { url = new URL(link.getAttribute("href"), document.baseURI); } catch { /* Invalid authored destinations remain validator-owned. */ }
      const external = url && ["https:", "http:"].includes(url.protocol) && url.origin !== location.origin;
      set(link, "data-bijux-external-link", external ? "true" : null);
      const newTab = (link.getAttribute("target") || "").toLowerCase() === "_blank";
      if (newTab) {
        // Preserve relationship and privacy tokens; opener cannot override the shared isolation policy.
        const tokens = (record.rel || "").split(/\s+/).filter(token => token && token.toLowerCase() !== "opener");
        if (!tokens.some(token => token.toLowerCase() === "noopener")) tokens.push("noopener");
        set(link, "rel", tokens.join(" "));
      }
      const download = link.hasAttribute("download");
      if (download || newTab) {
        const text = download ? "Download" : "Opens in new tab";
        const warning = document.createElement("span");
        do { warning.id = "bijux-link-warning-" + (++nextId); } while (document.getElementById(warning.id));
        warning.dataset.bijuxLinkIndication = download ? "download" : "new-tab";
        if (!link.textContent.trim() && link.querySelector("svg, img")) {
          // Icon links keep their compact hit area and expose the warning through text and description.
          const icon = document.createElement("span");
          icon.setAttribute("aria-hidden", "true");
          icon.textContent = download ? " ↓" : " ↗";
          icon.title = text;
          const label = document.createElement("span");
          label.className = "md-visually-hidden";
          label.textContent = " (" + text.toLowerCase() + ")";
          warning.append(icon, label);
        } else warning.textContent = " (" + text.toLowerCase() + ")";
        link.append(warning);
        record.warning = warning;
        if (link.hasAttribute("aria-label") || link.hasAttribute("aria-labelledby")) {
          const ids = (record.description || "").split(/\s+/).filter(Boolean);
          ids.push(warning.id);
          link.setAttribute("aria-describedby", ids.join(" "));
          record.described = true;
          record.ownedDescription = link.getAttribute("aria-describedby");
        }
      }
      record.ownedRel = link.getAttribute("rel");
      record.ownedExternal = link.getAttribute("data-bijux-external-link");
      record.signature = signature(link);
      records.set(link, record);
    }
    function scan() {
      if (signal.aborted) return;
      for (const [link, record] of records) if (!link.isConnected) {
        restore(link, record);
        records.delete(link);
      }
      for (const link of document.querySelectorAll("a[href]")) {
        if (link.namespaceURI === "http://www.w3.org/1999/xhtml") decorate(link);
      }
    }
    scan();
    const observer = typeof MutationObserver === "function" ? new MutationObserver(scan) : null;
    observer?.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: attributes });
    signal.addEventListener("abort", () => {
      observer?.disconnect();
      for (const [link, record] of records) restore(link, record);
      records.clear();
    }, { once: true });
  }
  shell.externalLinks = { bind };
})();
