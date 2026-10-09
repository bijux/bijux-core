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
    for (const container of document.querySelectorAll(".bijux-hub-strip, .bijux-site-tabs .bijux-tabs__list, [data-bijux-detail-strip]:not([hidden]) .bijux-tabs__list, [data-bijux-course-strip]:not([hidden]) .bijux-tabs__list")) {
      revealActive(container, ".bijux-tabs__item--active a");
    }
  }

  shell.navReveal = {
    runDesktopNavigationSync,
    runPhoneNavigationSync: runDesktopNavigationSync,
    bindMobileDrawerReveal() {},
  };
})();
