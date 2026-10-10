(function () {
  "use strict";
  const shell = (window.bijuxShell = window.bijuxShell || {});

  function revealActive(container, selector) {
    if (!container || container.clientWidth === 0) return;
    const active = container.querySelector(selector);
    if (!active) return;
    const bounds = container.getBoundingClientRect();
    const target = active.getBoundingClientRect();
    // Relative scrolling works with both browser RTL scroll-coordinate models.
    if (target.left < bounds.left || target.right > bounds.right) {
      container.scrollBy({ left: target.left - bounds.left - (bounds.width - target.width) / 2, behavior: "instant" });
    }
  }

  function runDesktopNavigationSync() {
    for (const container of document.querySelectorAll(".bijux-hub-strip > .bijux-tabs__list, .bijux-site-tabs .bijux-tabs__list, [data-bijux-detail-strip]:not([hidden]) .bijux-tabs__list, [data-bijux-course-strip]:not([hidden]) .bijux-tabs__list")) {
      revealActive(container, ".bijux-tabs__item--active a");
    }
  }

  function bind(signal) {
    if (signal.aborted) return;
    for (const strip of document.querySelectorAll(".bijux-hub-strip")) {
      const list = strip.querySelector(".bijux-tabs__list");
      const previous = strip.querySelector('[data-bijux-registry-scroll="previous"]');
      const next = strip.querySelector('[data-bijux-registry-scroll="next"]');
      if (!list || !previous || !next) continue;
      let lastFocusedControl;
      for (const button of [previous, next]) {
        button.addEventListener("focus", () => { lastFocusedControl = button; }, { signal });
        button.addEventListener("blur", () => {
          queueMicrotask(() => {
            if (lastFocusedControl === button && button.getClientRects().length)
              lastFocusedControl = undefined;
          });
        }, { signal });
      }
      const focusedControl = () => document.activeElement === document.body &&
        lastFocusedControl && !lastFocusedControl.getClientRects().length
        ? lastFocusedControl : document.activeElement;
      function restoreHiddenFocus(focused) {
        if (focused !== previous && focused !== next) return;
        const target = strip.clientWidth > 0
          ? list.querySelector('[aria-current="location"]') || list.querySelector("a")
          : document.querySelector('[data-bijux-header-control="drawer-toggle"]');
        if (target?.getClientRects().length) {
          target.focus({ preventScroll: true });
          if (strip.clientWidth > 0) revealActive(list, ":focus");
        }
        lastFocusedControl = undefined;
      }
      signal.addEventListener("abort", () => {
        const focused = focusedControl();
        previous.hidden = next.hidden = true;
        previous.removeAttribute("aria-disabled");
        next.removeAttribute("aria-disabled");
        restoreHiddenFocus(focused);
      }, { once: true });
      function update() {
        if (signal.aborted) return;
        const focused = focusedControl();
        // Include the space currently reserved for controls without hiding a
        // focused action during scroll updates.
        const available = list.clientWidth +
          (previous.hidden ? 0 : previous.getBoundingClientRect().width) +
          (next.hidden ? 0 : next.getBoundingClientRect().width);
        const overflow = list.clientWidth > 0 && list.scrollWidth > available + 1;
        previous.hidden = next.hidden = !overflow;
        if (!overflow) {
          restoreHiddenFocus(focused);
          return;
        }
        const links = list.querySelectorAll("a");
        const bounds = list.getBoundingClientRect();
        const first = links[0]?.getBoundingClientRect();
        const last = links[links.length - 1]?.getBoundingClientRect();
        const fits = rect => rect && rect.left >= bounds.left - 1 && rect.right <= bounds.right + 1;
        previous.setAttribute("aria-disabled", String(fits(first)));
        next.setAttribute("aria-disabled", String(fits(last)));
      }
      function move(button, direction) {
        if (button.getAttribute("aria-disabled") === "true") return;
        const rtl = getComputedStyle(list).direction === "rtl";
        list.scrollBy({ left: direction * (rtl ? -1 : 1) * Math.max(44, list.clientWidth * 0.8), behavior: "instant" });
        update();
      }
      previous.addEventListener("click", () => move(previous, -1), { signal });
      next.addEventListener("click", () => move(next, 1), { signal });
      list.addEventListener("scroll", update, { signal });
      list.addEventListener("focusin", () => {
        revealActive(list, ":focus");
        update();
      }, { signal });
      window.addEventListener("resize", update, { signal });
      if (typeof ResizeObserver === "function") {
        const observer = new ResizeObserver(update);
        signal.addEventListener("abort", () => observer.disconnect(), { once: true });
        try {
          observer.observe(strip);
          for (const link of list.querySelectorAll("a")) observer.observe(link);
        } catch (error) { observer.disconnect(); throw error; }
      }
      document.fonts?.ready.then(update);
      update();
    }
  }

  shell.navReveal = {
    bind,
    runDesktopNavigationSync,
    runPhoneNavigationSync: runDesktopNavigationSync,
    bindMobileDrawerReveal() {},
  };
})();
