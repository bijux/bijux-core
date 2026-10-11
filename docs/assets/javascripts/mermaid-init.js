(function () {
  "use strict";
  const vendor = new URL("./vendor/mermaid-11.17.2.min.js", document.currentScript.src);
  const integrity = "sha384-Y1B9CVhnQzsm0/34uQIbETs2AXzXz2C1uZLiDm51sNcO4xKIMS/Fi8BCpNlIrQy5";
  const sources = new WeakMap();
  let library;
  let generation = 0;
  let sequence = 0;
  let rendering = Promise.resolve();
  // Native history restoration can precede asynchronous diagram layout. Keep the
  // departure position in the owning history entry, never in a URL-wide cache.
  const readerHistoryKey = "bijuxDiagramReaderPosition";
  const navigation = performance.getEntriesByType("navigation")[0];
  function ownedReaderPosition() {
    const state = history.state;
    const saved = Object.prototype.toString.call(state) === "[object Object]" &&
      Object.prototype.hasOwnProperty.call(state, readerHistoryKey) ? state[readerHistoryKey] : null;
    if (Object.prototype.toString.call(saved) !== "[object Object]" ||
        !["owner", "version", "href", "x", "y"].every(key => Object.prototype.hasOwnProperty.call(saved, key)) ||
        saved.owner !== "bijux-docs" || saved.version !== 1 || saved.href !== location.href ||
        !Number.isFinite(saved.x) || saved.x < 0 || !Number.isFinite(saved.y) || saved.y < 0) return null;
    return saved;
  }
  let readerRestoration = navigation?.type === "back_forward" ? ownedReaderPosition() : null;
  let readerPageShown = document.readyState === "complete";
  let pendingReaderGeneration = null;
  let cachedDeparture = null;
  let cachedReader = null;

  function nativeEntryKey() {
    try {
      const key = window.navigation?.currentEntry?.key;
      return typeof key === "string" && key.length > 0 ? key : null;
    } catch (_) { return null; }
  }

  function currentCachedEntry(snapshot) {
    return snapshot && snapshot.href === location.href && snapshot.entryKey === nativeEntryKey();
  }

  function clearCachedReader() {
    cachedDeparture = null;
    cachedReader = null;
  }

  function diagramInventory(nodes) {
    const inventory = nodes.map(node => {
      const state = sources.get(node);
      return state && node.isConnected ? { source: state.source, open: state.details.open } : null;
    });
    return inventory.length && inventory.every(Boolean) ? inventory : null;
  }

  function matchingCachedSources(nodes) {
    const inventory = diagramInventory(nodes);
    return currentCachedEntry(cachedReader) && inventory && inventory.length === cachedReader.diagrams.length &&
      inventory.every((item, index) => item.source === cachedReader.diagrams[index].source);
  }

  function restoreCachedInspection(current, nodes) {
    if (!cachedReader || current !== generation) return;
    if (!matchingCachedSources(nodes)) {
      clearCachedReader();
      readerRestoration = null;
      return;
    }
    for (const [index, node] of nodes.entries()) {
      const state = sources.get(node);
      // Renderer failure keeps its readable fallback open regardless of an older
      // successful inspection. Only this generation's rendered preview may close it.
      if (state.theme !== null && state.preview.children.length) state.details.open = cachedReader.diagrams[index].open;
    }
  }

  function cancelReaderRestoration(event) {
    if (event.isTrusted) {
      readerRestoration = null;
      pendingReaderGeneration = null;
      clearCachedReader();
    }
  }
  for (const type of ["pointerdown", "touchstart", "wheel", "keydown"]) {
    window.addEventListener(type, cancelReaderRestoration, { capture: true, passive: true });
  }

  function readerLinks(context) {
    if (Object.prototype.toString.call(context) !== "[object Object]" ||
        !["href", "text", "top"].every(key => Object.prototype.hasOwnProperty.call(context, key)) ||
        typeof context.href !== "string" || typeof context.text !== "string" ||
        !context.text || !Number.isFinite(context.top)) return [];
    return [...document.querySelectorAll(".md-content article a[href]")].filter(link =>
      link.href === context.href && link.textContent.trim().replace(/\s+/g, " ") === context.text);
  }

  function captureReaderContext(link) {
    const context = {
      href: link.href, text: link.textContent?.trim().replace(/\s+/g, " ") || "",
      top: link.getBoundingClientRect?.().top,
    };
    const links = readerLinks(context);
    return links.length === 1 && links[0] === link ? context : undefined;
  }

  function captureReaderPosition(link) {
    clearCachedReader();
    readerRestoration = null;
    pendingReaderGeneration = null;
    if (!document.querySelector(".md-typeset .bijux-diagram")) return;
    const state = history.state;
    if (state !== null && (Object.prototype.toString.call(state) !== "[object Object]")) return;
    if (state && Object.prototype.hasOwnProperty.call(state, readerHistoryKey) &&
        (state[readerHistoryKey]?.owner !== "bijux-docs" || state[readerHistoryKey]?.version !== 1)) return;
    try {
      history.replaceState({ ...state, [readerHistoryKey]: {
        owner: "bijux-docs", version: 1, href: location.href, x: window.scrollX, y: window.scrollY,
        context: captureReaderContext(link),
      } }, "");
      const entryKey = nativeEntryKey();
      const diagrams = diagramInventory([...document.querySelectorAll(".md-typeset .bijux-diagram")]);
      // A realm-private snapshot supplements this exact native entry only. It is
      // never recovered from storage, a retained receipt or a matching URL alone.
      const position = ownedReaderPosition();
      if (entryKey && diagrams && position) cachedDeparture = {
        entryKey, href: location.href, diagrams,
        position: { ...position, ...(position.context ? { context: { ...position.context } } : {}) }, departed: false,
      };
    } catch (_) {
      // A history entry may become unavailable while its document is leaving.
    }
  }

  function restoreReaderPosition(current) {
    const position = readerRestoration;
    if (!position || current !== generation) return;
    // Native traversal restores its coordinates after pageshow. A diagram may
    // finish earlier, so retain only the owning generation until that boundary.
    if (!readerPageShown) {
      pendingReaderGeneration = current;
      return;
    }
    const cached = cachedReader;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (current !== generation || readerRestoration !== position ||
          cached && (cached !== cachedReader || !matchingCachedSources([...document.querySelectorAll(".md-typeset .bijux-diagram")]))) return;
      readerRestoration = null;
      let top = position.y;
      const links = Object.prototype.hasOwnProperty.call(position, "context") ? readerLinks(position.context) : [];
      if (links.length === 1 && links[0].isConnected) {
        // The reader's anchor survives responsive and asynchronous diagram layout.
        // An ambiguous or removed anchor retains the native coordinate fallback.
        const anchored = window.scrollY + links[0].getBoundingClientRect().top - position.context.top;
        if (Number.isFinite(anchored)) top = Math.max(0, anchored);
      }
      window.scrollTo({ left: position.x, top, behavior: "instant" });
    }));
  }

  // The self-hosted library must never start its own document scan on load.
  window.mermaidConfig = { startOnLoad: false, securityLevel: "strict" };

  function admitSource(source) {
    if (source.length > 50000 || /%%\s*\{|^\s*---/m.test(source)) throw new Error("Diagram source configuration is not admitted");
    // Authored diagrams describe graphs, not network resources or renderer policy.
    if (/<\s*(?:img|image|iframe|object|embed|audio|video|source|link|style)\b|@\{[^}]*\b(?:img|icon)\s*:/i.test(source)) throw new Error("Diagram resource content is not admitted");
    for (const line of source.split(/\r?\n/)) {
      const declaration = line.match(/^\s*(style|classDef|linkStyle)\s+[^\s]+\s+(.+?)\s*;?\s*$/);
      if (!declaration) continue;
      for (const entry of declaration[2].replace(/;$/, "").split(",")) {
        const match = entry.trim().match(/^([a-z-]+)\s*:\s*(.+)$/i);
        if (!match) throw new Error("Diagram style is not admitted");
        const [, property, value] = match;
        const color = /^(?:#[0-9a-f]{3,8}|[a-z]+)$/i;
        const number = /^(?:\d+(?:\.\d+)?(?:px|em|%)?)(?:\s+\d+(?:\.\d+)?)?$/;
        const safe = ["fill", "stroke", "color"].includes(property) ? color.test(value)
          : ["stroke-width", "stroke-dasharray", "opacity", "fill-opacity", "stroke-opacity", "font-size", "font-weight"].includes(property) && number.test(value);
        if (!safe) throw new Error("Diagram style is not admitted");
      }
    }
  }

  function load() {
    if (library) return library;
    library = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = vendor.href;
      script.integrity = integrity;
      script.crossOrigin = "anonymous";
      script.async = true;
      let timer;
      function finish(error) {
        clearTimeout(timer);
        script.onload = script.onerror = null;
        if (error) { script.remove(); library = null; reject(error); }
        else resolve(window.mermaid);
      }
      script.onload = () => finish(window.mermaid ? null : new Error("Diagram renderer unavailable"));
      script.onerror = () => finish(new Error("Diagram renderer unavailable"));
      timer = setTimeout(() => finish(new Error("Diagram renderer timed out")), 8000);
      document.head.appendChild(script);
    });
    return library;
  }

  function prepare(node) {
    if (sources.has(node)) return node;
    const source = (node.querySelector("code") || node).textContent || "";
    const figure = document.createElement("div");
    figure.className = "mermaid bijux-diagram";
    figure.tabIndex = 0;
    figure.setAttribute("role", "region");
    figure.setAttribute("aria-label", "Diagram and source");
    const preview = document.createElement("div");
    preview.className = "bijux-diagram-preview";
    const details = document.createElement("details");
    details.className = "bijux-diagram-source";
    const summary = document.createElement("summary");
    summary.textContent = "Diagram source";
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = source;
    pre.appendChild(code);
    details.append(summary, pre);
    const status = document.createElement("p");
    status.className = "bijux-diagram-status";
    status.setAttribute("role", "status");
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "md-button";
    retry.textContent = "Retry diagram";
    retry.hidden = true;
    retry.addEventListener("click", request);
    details.open = true;
    figure.append(preview, status, retry, details);
    sources.set(figure, { source, preview, details, status, retry, theme: null });
    node.replaceWith(figure);
    return figure;
  }

  async function render(current, nodes, theme) {
    let api;
    try { api = await load(); } catch (_) {}
    if (current !== generation) return;
    for (const node of nodes) {
      if (current !== generation || !node.isConnected) return;
      const state = sources.get(node);
      if (!state || state.theme === theme) continue;
      state.retry.hidden = true;
      state.status.textContent = "";
      try {
        admitSource(state.source);
        if (!api) throw new Error("Diagram renderer unavailable");
        api.initialize({
          startOnLoad: false, securityLevel: "strict", suppressErrorRendering: true,
          secure: ["secure", "securityLevel", "startOnLoad", "maxTextSize", "maxEdges", "suppressErrorRendering", "dompurifyConfig", "themeCSS", "themeVariables"],
          maxTextSize: 50000, maxEdges: 500, theme, fontFamily: "Arial, sans-serif",
          // Label HTML is inserted into Mermaid's measurement DOM before final SVG
          // sanitization. Keep math and harmless markup, but exclude resource tags there.
          dompurifyConfig: { FORBID_TAGS: ["img", "image", "iframe", "object", "embed", "audio", "video", "source", "link", "style"] },
          flowchart: { htmlLabels: false },
        });
        const result = await api.render("bijux-diagram-" + (++sequence), state.source);
        if (current !== generation || !node.isConnected) return;
        // Sanitized Mermaid labels contain HTML void elements inside foreignObject.
        // Parse in an inert HTML document so those labels retain their namespaces.
        const parsed = new DOMParser().parseFromString(result.svg, "text/html");
        const svg = parsed.body.firstElementChild;
        if (!svg || parsed.body.children.length !== 1 || svg.localName !== "svg" || svg.namespaceURI !== "http://www.w3.org/2000/svg" ||
            svg.querySelector("script,img,image,iframe,object,embed,audio,video,source,link")) throw new Error("Invalid diagram output");
        for (const element of [svg, ...svg.querySelectorAll("*")]) {
          for (const attribute of element.attributes) {
            if (/^on/i.test(attribute.name) || /^(?:href|xlink:href|src)$/i.test(attribute.name) && /^\s*(?:javascript|vbscript):/i.test(attribute.value)) throw new Error("Active diagram output is not admitted");
          }
        }
        state.preview.replaceChildren(document.importNode(svg, true));
        state.details.open = false;
        state.theme = theme;
      } catch (_) {
        if (current !== generation || !node.isConnected) return;
        state.preview.replaceChildren();
        state.details.open = true;
        state.status.textContent = "Diagram preview unavailable. The source remains available below.";
        state.retry.hidden = false;
      }
    }
  }

  function request() {
    const current = ++generation;
    const nodes = [...document.querySelectorAll(".md-typeset .bijux-diagram")].map(prepare);
    if (cachedReader && !matchingCachedSources(nodes)) {
      clearCachedReader();
      readerRestoration = null;
    }
    if (!nodes.length) return;
    const theme = document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "default";
    // Mermaid owns shared parser/config state; serialize renders and reject stale completions.
    rendering = rendering.catch(() => {}).then(() => render(current, nodes, theme)).catch(() => {}).then(() => {
      restoreCachedInspection(current, nodes);
      restoreReaderPosition(current);
    });
  }

  if (window.document$ && typeof window.document$.subscribe === "function") window.document$.subscribe(request);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", request, { once: true });
  else request();
  window.addEventListener("bijux:theme-change", request);
  document.addEventListener("click", event => {
    if (!event.isTrusted || event.defaultPrevented || event.button !== 0 ||
        event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const link = event.target.closest?.("a[href]");
    if (!link || link.hasAttribute("download") || link.target && link.target !== "_self") return;
    let destination;
    try { destination = new URL(link.href, location.href); } catch (_) { return; }
    if (!["http:", "https:"].includes(destination.protocol) ||
        destination.origin === location.origin && destination.pathname === location.pathname &&
        destination.search === location.search) return;
    captureReaderPosition(link);
  }, true);
  window.addEventListener("pagehide", event => {
    // A subsequent cached traversal may leave without another authored link.
    // Re-arm only this already proven entry, with no intervening reader input.
    const nodes = [...document.querySelectorAll(".md-typeset .bijux-diagram")];
    if (event?.isTrusted && event.persisted && matchingCachedSources(nodes)) {
      const links = cachedReader.position.context ? readerLinks(cachedReader.position.context) : [];
      cachedDeparture = { ...cachedReader, diagrams: diagramInventory(nodes), departed: false,
        position: { owner: "bijux-docs", version: 1, href: location.href,
          x: window.scrollX, y: window.scrollY,
          context: links.length === 1 ? captureReaderContext(links[0]) : undefined } };
    }
    cachedReader = null;
    if (event?.isTrusted && event.persisted && currentCachedEntry(cachedDeparture)) cachedDeparture.departed = true;
    else cachedDeparture = null;
    readerRestoration = null;
    readerPageShown = false;
    pendingReaderGeneration = null;
    generation += 1;
  });
  window.addEventListener("pageshow", event => {
    readerPageShown = true;
    if (event.persisted) {
      // Browser-owned entry keys distinguish separate same-URL visits. Only an
      // actual cached lifecycle can admit this realm's last native departure.
      cachedReader = event.isTrusted && cachedDeparture?.departed && currentCachedEntry(cachedDeparture)
        ? cachedDeparture : null;
      cachedDeparture = null;
      readerRestoration = ownedReaderPosition() || cachedReader?.position || null;
      request();
    } else {
      clearCachedReader();
      if (pendingReaderGeneration === null) return;
      const current = pendingReaderGeneration;
      pendingReaderGeneration = null;
      restoreReaderPosition(current);
    }
  });
})();
