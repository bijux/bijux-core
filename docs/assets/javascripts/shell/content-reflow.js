(function () {
  "use strict";
  const shell = (window.bijuxShell = window.bijuxShell || {});
  if (shell.contentReflow) return;

  function bind(signal) {
    if (signal.aborted) return;
    const article = document.querySelector(".md-content__inner");
    if (!article) return;
    const records = new Map();
    let frame;
    let ordinal = 0;
    let resize;
    let changes;

    function context(surface) {
      const headings = [...article.querySelectorAll("h1, h2, h3, h4, h5, h6")];
      const preceding = headings.filter(
        (heading) =>
          !heading.querySelector("pre, code, svg") &&
          heading.compareDocumentPosition(surface) &
            Node.DOCUMENT_POSITION_FOLLOWING,
      );
      const heading = preceding.at(-1);
      let label = document.title || "Document";
      if (heading) {
        // Permalink glyphs and decorative content are not reader context.
        // Remove them from a detached copy; authored heading text stays intact.
        const readable = heading.cloneNode(true);
        for (const decoration of readable.querySelectorAll(
          '.headerlink, [aria-hidden="true"]',
        )) {
          decoration.remove();
        }
        label = readable.textContent || label;
      }
      return label.trim().replace(/\s+/g, " ").slice(0, 160);
    }

    function write(record, name, value) {
      const previous = record.attributes.get(name);
      if (previous) {
        if (record.surface.getAttribute(name) !== previous.value) return;
        previous.value = value;
      } else {
        if (record.surface.hasAttribute(name)) return;
        record.attributes.set(name, { original: null, value });
      }
      record.surface.setAttribute(name, value);
    }

    function restore(record) {
      for (const [name, owned] of record.attributes) {
        if (record.surface.getAttribute(name) === owned.value) {
          if (owned.original === null) record.surface.removeAttribute(name);
          else record.surface.setAttribute(name, owned.original);
        }
      }
      record.attributes.clear();
      record.hint?.remove();
      record.hint = undefined;
    }

    function qualify(record) {
      const surface = record.surface;
      const wide =
        surface.clientWidth > 0 &&
        surface.scrollWidth > surface.clientWidth + 1;
      if (!wide) {
        // Keep a currently focused region stable until the visitor leaves it.
        if (document.activeElement !== surface) restore(record);
        return;
      }
      const kind = record.kind === "table" ? "table" : "code example";
      const caption = surface.querySelector("caption")?.textContent.trim();
      const label = `Scrollable ${kind} ${record.ordinal}: ${caption || context(surface)}`;
      write(record, "tabindex", "0");
      write(record, "role", "region");
      if (!surface.hasAttribute("aria-labelledby"))
        write(record, "aria-label", label);
      if (!record.hint) {
        const hint = document.createElement("p");
        let identifier = `bijux-content-scroll-${record.ordinal}`;
        while (document.getElementById(identifier)) identifier += "-hint";
        hint.id = identifier;
        hint.className = "bijux-content-scroll-hint";
        hint.textContent = `Scroll horizontally to read the full ${kind}. When focused, use the Left and Right arrow keys. Home and End reach the horizontal edges.`;
        const block =
          record.kind === "code"
            ? surface.closest(".highlight") || surface.parentElement
            : surface;
        const anchor = block.closest("h1, h2, h3, h4, h5, h6") || block;
        anchor.parentNode.insertBefore(hint, anchor);
        record.hint = hint;
      }
      if (!surface.hasAttribute("aria-describedby"))
        write(record, "aria-describedby", record.hint.id);
    }

    function measure() {
      frame = undefined;
      if (signal.aborted) return;
      const surfaces = new Map();
      for (const block of article.querySelectorAll(".highlight")) {
        // Numbered code may scroll inside a fitting native table. Name the actual
        // overflow owner without changing code, line anchors or table cells.
        const numbered = block.querySelector("table.highlighttable");
        const outerOverflows =
          block.clientWidth > 0 && block.scrollWidth > block.clientWidth + 1;
        if (numbered && outerOverflows) surfaces.set(block, "code");
        else
          for (const code of block.querySelectorAll("pre > code"))
            surfaces.set(code, "code");
      }
      for (const table of article.querySelectorAll(".md-typeset__scrollwrap"))
        surfaces.set(table, "table");
      for (const [surface, record] of records) {
        if (!surfaces.has(surface)) {
          resize?.unobserve(surface);
          restore(record);
          records.delete(surface);
        }
      }
      for (const [surface, kind] of surfaces) {
        if (!records.has(surface)) {
          const record = {
            surface,
            kind,
            ordinal: ++ordinal,
            attributes: new Map(),
            hint: undefined,
          };
          records.set(surface, record);
          surface.addEventListener("blur", schedule, { signal });
          surface.addEventListener(
            "keydown",
            (event) => {
              if (
                event.target !== surface ||
                document.activeElement !== surface ||
                !records.has(surface) ||
                event.defaultPrevented ||
                event.altKey ||
                event.ctrlKey ||
                event.metaKey ||
                event.shiftKey ||
                !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
              )
                return;
              const selection = window.getSelection?.();
              if (selection?.rangeCount > 0 && !selection.isCollapsed) return;
              const maximum = surface.scrollWidth - surface.clientWidth;
              if (maximum <= 1) return;
              // Edge navigation belongs only to the explicitly focused horizontal region.
              const rtl = getComputedStyle(surface).direction === "rtl";
              const minimum = rtl ? -maximum : 0;
              const upper = rtl ? 0 : maximum;
              const delta = event.key === "ArrowRight" ? 40 : -40;
              const target =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? rtl
                      ? -maximum
                      : maximum
                    : Math.min(
                        upper,
                        Math.max(minimum, surface.scrollLeft + delta),
                      );
              event.preventDefault();
              surface.scrollTo({ left: target, behavior: "instant" });
            },
            { signal },
          );
          resize?.observe(surface);
        }
        qualify(records.get(surface));
      }
    }

    function schedule() {
      if (!signal.aborted && frame === undefined)
        frame = requestAnimationFrame(measure);
    }

    if (window.ResizeObserver) {
      // Delivery only schedules a frame; changing attributes never occurs inside it.
      resize = new ResizeObserver(schedule);
      resize.observe(article);
    }
    if (window.MutationObserver) {
      changes = new MutationObserver(schedule);
      changes.observe(article, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
    window.addEventListener("resize", schedule, { signal, passive: true });
    document.fonts?.ready.then(schedule);
    signal.addEventListener(
      "abort",
      () => {
        if (frame !== undefined) cancelAnimationFrame(frame);
        frame = undefined;
        resize?.disconnect();
        changes?.disconnect();
        for (const record of records.values()) restore(record);
        records.clear();
      },
      { once: true },
    );
    schedule();
  }

  shell.contentReflow = { bind };
})();
