(function () {
  const shell = (window.bijuxShell = window.bijuxShell || {});

  function syncDetailStripPresence() {
    const header = document.querySelector("[data-md-component='header']");
    if (!header) {
      return;
    }
    const hasVisibleDetailStrip = document.querySelector(
      "[data-bijux-detail-strip]:not([hidden]), [data-bijux-course-strip]:not([hidden])"
    );
    header.setAttribute(
      "data-bijux-detail-visible",
      hasVisibleDetailStrip ? "true" : "false"
    );
  }

  function syncDetailStripVisibility() {
    const navState = shell.navState;
    if (!navState) {
      return;
    }

    const activeSitePath = navState.syncSiteTabActiveState();
    for (const strip of document.querySelectorAll("[data-bijux-detail-strip]")) {
      const rootPath = navState.normalizePath(
        strip.getAttribute("data-bijux-detail-root-path") || "/"
      );
      strip.hidden = rootPath !== activeSitePath;
    }
  }

  function syncDetailStripActiveState() {
    const navState = shell.navState;
    if (!navState) {
      return;
    }

    const currentPath = navState.normalizeCurrentPath(window.location.pathname);
    const strips = document.querySelectorAll("[data-bijux-detail-strip]:not([hidden])");

    for (const strip of strips) {
      const authoredActiveLink = strip.querySelector(
        "a[data-bijux-detail-path][aria-current], .bijux-tabs__item--active a[data-bijux-detail-path]"
      );

      for (const item of strip.querySelectorAll(".bijux-tabs__item")) {
        item.classList.remove("bijux-tabs__item--active");
      }

      for (const link of strip.querySelectorAll("a[data-bijux-detail-path]")) {
        link.removeAttribute("aria-current");
      }

      const matchedLink = navState.bestMatchingLink(
        strip,
        "data-bijux-detail-path",
        currentPath,
        "a[data-bijux-detail-path]"
      );

      let activeLink = matchedLink;

      if (!activeLink && authoredActiveLink) {
        activeLink = {
          path: navState.normalizePath(
            authoredActiveLink.getAttribute("data-bijux-detail-path") || "/"
          ),
          node: authoredActiveLink,
        };
      }

      if (!activeLink) {
        const parentPath = navState.normalizePath(
          strip.getAttribute("data-bijux-detail-root-path") || "/"
        );
        const homeLink = strip.querySelector(
          `a[data-bijux-detail-path="${parentPath}"]`
        );
        if (homeLink) {
          activeLink = {
            path: parentPath,
            node: homeLink,
          };
        }
      }

      if (!activeLink) {
        const firstLink = strip.querySelector("a[data-bijux-detail-path]");
        if (firstLink) {
          activeLink = {
            path: navState.normalizePath(
              firstLink.getAttribute("data-bijux-detail-path") || "/"
            ),
            node: firstLink,
          };
        }
      }

      if (activeLink) {
        activeLink.node
          .closest(".bijux-tabs__item")
          ?.classList.add("bijux-tabs__item--active");
        activeLink.node.setAttribute("aria-current", activeLink.path === currentPath ? "page" : "location");
      }
    }
  }

  function activeDetailPath() {
    const navState = shell.navState;
    if (!navState) {
      return null;
    }

    const activeStrip = document.querySelector("[data-bijux-detail-strip]:not([hidden])");
    if (!activeStrip) {
      return null;
    }

    const activeLink = navState.bestMatchingLink(
      activeStrip,
      "data-bijux-detail-path",
      navState.normalizeCurrentPath(window.location.pathname),
      "a[data-bijux-detail-path]"
    );
    if (activeLink) {
      return activeLink.path;
    }

    const authoredActiveLink = activeStrip.querySelector(
      "a[data-bijux-detail-path][aria-current], .bijux-tabs__item--active a[data-bijux-detail-path]"
    );
    if (authoredActiveLink) {
      return navState.normalizePath(
        authoredActiveLink.getAttribute("data-bijux-detail-path") || "/"
      );
    }

    return null;
  }

  function syncCourseStripVisibility() {
    const navState = shell.navState;
    if (!navState) {
      return;
    }

    const currentPath = navState.normalizeCurrentPath(window.location.pathname);
    const activeProgramPath = activeDetailPath();
    for (const strip of document.querySelectorAll("[data-bijux-course-strip]")) {
      const rootPath = navState.normalizePath(
        strip.getAttribute("data-bijux-course-root-path") || "/"
      );
      const activeCourseLink = navState.bestMatchingLink(
        strip,
        "data-bijux-course-path",
        currentPath,
        "a[data-bijux-course-path]"
      );
      strip.hidden = rootPath !== activeProgramPath && !activeCourseLink;
    }
  }

  function syncCourseStripActiveState() {
    const navState = shell.navState;
    if (!navState) {
      return;
    }

    const currentPath = navState.normalizeCurrentPath(window.location.pathname);
    const strips = document.querySelectorAll("[data-bijux-course-strip]:not([hidden])");

    for (const strip of strips) {
      const authoredActiveLink = strip.querySelector(
        "a[data-bijux-course-path][aria-current], .bijux-tabs__item--active a[data-bijux-course-path]"
      );

      for (const item of strip.querySelectorAll(".bijux-tabs__item")) {
        item.classList.remove("bijux-tabs__item--active");
      }

      for (const link of strip.querySelectorAll("a[data-bijux-course-path]")) {
        link.removeAttribute("aria-current");
      }

      let activeLink = navState.bestMatchingLink(
        strip,
        "data-bijux-course-path",
        currentPath,
        "a[data-bijux-course-path]"
      );

      if (!activeLink && authoredActiveLink) {
        activeLink = {
          path: navState.normalizePath(
            authoredActiveLink.getAttribute("data-bijux-course-path") || "/"
          ),
          node: authoredActiveLink,
        };
      }

      if (activeLink) {
        activeLink.node
          .closest(".bijux-tabs__item")
          ?.classList.add("bijux-tabs__item--active");
        activeLink.node.setAttribute("aria-current", activeLink.path === currentPath ? "page" : "location");
      }
    }
  }

  function bindDetailSelectNavigation() {
    for (const select of document.querySelectorAll("[data-bijux-detail-select]")) {
      if (select.dataset.bijuxDetailSelectBound === "true") {
        continue;
      }

      select.dataset.bijuxDetailSelectBound = "true";
      select.addEventListener("change", () => {
        if (!select.value) {
          return;
        }
        window.location.href = select.value;
      });
    }
  }

  function syncDetailSelectState() {
    const navState = shell.navState;
    if (!navState) {
      return;
    }

    const strips = document.querySelectorAll(
      "[data-bijux-detail-strip]:not([hidden]), [data-bijux-course-strip]:not([hidden])"
    );

    for (const strip of strips) {
      const activeLink = strip.querySelector(
        "a[data-bijux-detail-path][aria-current], a[data-bijux-course-path][aria-current]"
      );

      if (!activeLink) {
        continue;
      }

      const activePath = navState.normalizePath(
        activeLink.getAttribute("data-bijux-detail-path") ||
          activeLink.getAttribute("data-bijux-course-path") ||
          "/"
      );

      const select = strip.querySelector("[data-bijux-detail-select]");
      if (!select) {
        continue;
      }

      for (const option of select.options) {
        const optionPath = navState.normalizePath(
          option.getAttribute("data-bijux-detail-path") ||
            option.getAttribute("data-bijux-course-path") ||
            option.value ||
            "/"
        );
        option.selected = optionPath === activePath;
      }
    }
  }

  function runDetailTabsSync() {
    syncDetailStripVisibility();
    syncDetailStripActiveState();
    syncCourseStripVisibility();
    syncCourseStripActiveState();
    syncDetailStripPresence();
    syncDetailSelectState();
    bindDetailSelectNavigation();
  }

  function runDesktopNavigationSync() {
    syncDetailStripVisibility();
    syncDetailStripActiveState();
    syncCourseStripVisibility();
    syncCourseStripActiveState();
    syncDetailStripPresence();
    syncDetailSelectState();
  }

  function runPhoneNavigationSync() {
    syncDetailStripVisibility();
    syncDetailStripActiveState();
    syncCourseStripVisibility();
    syncCourseStripActiveState();
    syncDetailStripPresence();
    syncDetailSelectState();
  }

  shell.detailTabs = {
    syncDetailStripPresence,
    syncDetailStripVisibility,
    syncDetailStripActiveState,
    activeDetailPath,
    syncCourseStripVisibility,
    syncCourseStripActiveState,
    syncDetailSelectState,
    bindDetailSelectNavigation,
    runDesktopNavigationSync,
    runPhoneNavigationSync,
    runDetailTabsSync,
  };
})();
