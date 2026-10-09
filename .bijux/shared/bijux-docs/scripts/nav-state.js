(function () {
  const shell = (window.bijuxShell = window.bijuxShell || {});

  function siteBasePath() {
    const scopePath = window.__md_scope?.pathname;
    if (!scopePath) {
      return "";
    }

    const path = scopePath.replace(/\/+$/, "");
    return path === "/" ? "" : path;
  }

  function normalizePath(target) {
    const url = new URL(target, window.location.href);
    let path = url.pathname.replace(/\/+$/, "");
    return path || "/";
  }

  function normalizeCurrentPath(target) {
    const basePath = siteBasePath();
    let path = normalizePath(target);
    if (basePath && (path === basePath || path.startsWith(`${basePath}/`))) {
      path = path.slice(basePath.length) || "/";
    }
    return path || "/";
  }

  function bestMatchingLink(container, attribute, currentPath, selector) {
    let bestMatch = null;
    const query = selector || `[${attribute}]`;

    for (const link of container.querySelectorAll(query)) {
      const linkPath = normalizePath(link.getAttribute(attribute) || "/");
      const isMatch =
        currentPath === linkPath ||
        (linkPath !== "/" && currentPath.startsWith(`${linkPath}/`));

      if (isMatch && (!bestMatch || linkPath.length > bestMatch.path.length)) {
        bestMatch = { node: link, path: linkPath };
      }
    }

    return bestMatch;
  }

  function bestSitePath() {
    const siteTabs = document.querySelector(".bijux-site-tabs");
    if (!siteTabs) {
      return null;
    }

    const currentPath = normalizeCurrentPath(window.location.pathname);
    const matchedLink = bestMatchingLink(
      siteTabs,
      "data-bijux-site-path",
      currentPath
    );

    if (matchedLink) {
      return matchedLink.path;
    }

    const authoredActiveLink = siteTabs.querySelector(
      "[data-bijux-site-path][aria-current='page'], .bijux-tabs__item--active [data-bijux-site-path]"
    );
    if (authoredActiveLink) {
      return normalizePath(
        authoredActiveLink.getAttribute("data-bijux-site-path") || "/"
      );
    }

    return null;
  }

  function syncSiteTabActiveState() {
    const activeSitePath = bestSitePath();

    for (const item of document.querySelectorAll(
      ".bijux-site-tabs .bijux-tabs__item"
    )) {
      item.classList.remove("md-tabs__item--active", "bijux-tabs__item--active");
    }

    for (const link of document.querySelectorAll(
      ".bijux-site-tabs [data-bijux-site-path]"
    )) {
      link.removeAttribute("aria-current");
    }

    if (!activeSitePath) {
      return null;
    }

    for (const link of document.querySelectorAll(
      ".bijux-site-tabs [data-bijux-site-path]"
    )) {
      const linkPath = normalizePath(
        link.getAttribute("data-bijux-site-path") || "/"
      );

      if (linkPath === activeSitePath) {
        link
          .closest(".bijux-tabs__item")
          ?.classList.add("md-tabs__item--active", "bijux-tabs__item--active");
        link.setAttribute("aria-current", linkPath === normalizeCurrentPath(window.location.pathname) ? "page" : "location");
      }
    }

    return activeSitePath;
  }

  shell.navState = {
    siteBasePath,
    normalizePath,
    normalizeCurrentPath,
    bestMatchingLink,
    bestSitePath,
    syncSiteTabActiveState,
  };
})();
