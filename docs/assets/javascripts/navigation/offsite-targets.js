// Repository navigation opens offsite pages separately; shared code owns link decoration.
document$.subscribe(() => {
  for (const link of document.querySelectorAll("a[href]")) {
    const href = link.getAttribute("href");
    if (!href || href.startsWith("#")) continue;
    let destination;
    try {
      destination = new URL(href, window.location.href);
    } catch {
      continue;
    }
    if (["http:", "https:"].includes(destination.protocol) && destination.origin !== window.location.origin) {
      link.setAttribute("target", "_blank");
      const relationships = new Set((link.getAttribute("rel") || "").split(/\s+/).filter(Boolean));
      relationships.add("noreferrer");
      link.setAttribute("rel", Array.from(relationships).join(" "));
    }
  }
});
