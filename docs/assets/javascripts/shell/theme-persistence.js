(function () {
  const MD_PALETTE_KEY = "__palette";

  function resolveThemeKey() {
    return (
      document
        .querySelector("[data-bijux-theme-key]")
        ?.getAttribute("data-bijux-theme-key") || "bijux:theme"
    );
  }

  function safeGetGlobalTheme(themeKey) {
    try {
      const raw = localStorage.getItem(themeKey);
      return raw && raw.length <= 2048 ? raw : null;
    } catch (error) {
      return null;
    }
  }

  function safeSetGlobalTheme(themeKey, scheme) {
    try {
      localStorage.setItem(themeKey, scheme);
    } catch (error) {
      // Ignore storage write failures for private mode or policy-restricted browsers.
    }
  }

  function paletteOptions() {
    return Array.from(
      document.querySelectorAll("input[name='__palette'][data-md-color-scheme]")
    );
  }

  function optionSignature(option) {
    return {
      media: option.getAttribute("data-md-color-media") || "",
      scheme: option.getAttribute("data-md-color-scheme") || "",
      primary: option.getAttribute("data-md-color-primary") || "",
      accent: option.getAttribute("data-md-color-accent") || "",
    };
  }

  function findOptionBySignature(signature) {
    const options = paletteOptions();
    return (
      options.find((option) => {
        const current = optionSignature(option);
        return (
          current.media === (signature.media || "") &&
          current.scheme === (signature.scheme || "") &&
          current.primary === (signature.primary || "") &&
          current.accent === (signature.accent || "")
        );
      }) || null
    );
  }

  function modeFromOption(option) {
    const media = option.getAttribute("data-md-color-media") || "";
    const scheme = option.getAttribute("data-md-color-scheme") || "";

    if (media === "(prefers-color-scheme)") {
      return "auto";
    }

    if (media.includes("dark") || scheme === "slate") {
      return "dark";
    }

    return "light";
  }

  function optionByMode(mode) {
    const options = paletteOptions();

    if (mode === "auto") {
      return (
        options.find((option) => {
          return (
            (option.getAttribute("data-md-color-media") || "") ===
            "(prefers-color-scheme)"
          );
        }) || null
      );
    }

    if (mode === "dark") {
      return (
        options.find((option) => {
          const media = option.getAttribute("data-md-color-media") || "";
          const scheme = option.getAttribute("data-md-color-scheme") || "";
          return media === "(prefers-color-scheme: dark)" || scheme === "slate";
        }) || null
      );
    }

    return (
      options.find((option) => {
        const media = option.getAttribute("data-md-color-media") || "";
        const scheme = option.getAttribute("data-md-color-scheme") || "";
        return media === "(prefers-color-scheme: light)" || (media === "" && scheme === "default");
      }) || null
    );
  }

  function selectedOption() {
    return paletteOptions().find((option) => option.checked) || null;
  }

  function currentMode() {
    const option = selectedOption();
    if (!option) {
      return "auto";
    }
    return modeFromOption(option);
  }

  function nextMode(mode) {
    if (mode === "auto") {
      return "light";
    }

    if (mode === "light") {
      return "dark";
    }

    return "auto";
  }

  function modeLabel(mode) {
    if (mode === "light") {
      return "Light";
    }

    if (mode === "dark") {
      return "Dark";
    }

    return "Auto";
  }

  function activeSchemeFromDom() {
    return document.body?.getAttribute("data-md-color-scheme") || null;
  }

  function applyThemeAttributes(option) {
    const attrs = ["scheme", "primary", "accent", "media"];
    for (const key of attrs) {
      const value = option.getAttribute(`data-md-color-${key}`);
      if (value === null || value === "") {
        document.body.removeAttribute(`data-md-color-${key}`);
        continue;
      }
      document.body.setAttribute(`data-md-color-${key}`, value);
    }
  }

  function writeMaterialPalette(option, index) {
    const color = optionSignature(option);
    if (!color.scheme) {
      color.scheme = "default";
    }
    if (!color.primary) {
      color.primary = "teal";
    }
    if (!color.accent) {
      color.accent = "cyan";
    }

    if (typeof window.__md_set === "function") {
      // Material restores its native palette by indexing the current option list.
      try { window.__md_set(MD_PALETTE_KEY, { index, color }); } catch (_) {}
    }
  }

  function persistThemeChoice(themeKey, option) {
    safeSetGlobalTheme(
      themeKey,
      JSON.stringify({
        version: 2,
        mode: modeFromOption(option),
        signature: optionSignature(option),
      })
    );
  }

  function captureScrollPosition() {
    return {
      x: window.scrollX || window.pageXOffset || 0,
      y: window.scrollY || window.pageYOffset || 0,
    };
  }

  function restoreScrollPosition(position) {
    if (!position) {
      return;
    }
    window.scrollTo(position.x, position.y);
  }

  function applyOption(themeKey, option, persistGlobal) {
    const index = paletteOptions().indexOf(option);
    if (index < 0) {
      return false;
    }

    const scrollBeforeThemeChange = captureScrollPosition();

    option.checked = true;
    const effective = modeFromOption(option) === "auto" ? optionByMode(window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light") || option : option;
    applyThemeAttributes(effective);
    writeMaterialPalette(option, index);

    if (persistGlobal) {
      persistThemeChoice(themeKey, option);
    }

    window.dispatchEvent(
      new CustomEvent("bijux:theme-change", {
        detail: {
          mode: modeFromOption(option),
          scheme: option.getAttribute("data-md-color-scheme") || "default",
          scroll: scrollBeforeThemeChange,
        },
      })
    );

    // Keep the reader anchored while the palette and theme subscribers restyle.
    restoreScrollPosition(scrollBeforeThemeChange);
    requestAnimationFrame(() => restoreScrollPosition(scrollBeforeThemeChange));
    setTimeout(() => restoreScrollPosition(scrollBeforeThemeChange), 80);

    return true;
  }

  function refreshThemeToggleButtons() {
    const mode = currentMode();
    const modeName = modeLabel(mode);
    const nextModeName = modeLabel(nextMode(mode));

    for (const button of document.querySelectorAll("[data-bijux-theme-toggle]")) {
      button.hidden = false;
      button.setAttribute(
        "aria-label",
        `Theme mode: ${modeName}. Switch to ${nextModeName}.`
      );
      button.setAttribute(
        "title",
        `Theme mode: ${modeName}. Switch to ${nextModeName}.`
      );
      button.setAttribute("data-bijux-theme-mode", mode);
    }
  }

  function parseStoredChoice(rawValue) {
    if (!rawValue || rawValue.length > 2048) {
      return null;
    }

    try {
      const parsed = JSON.parse(rawValue);
      if (!parsed || typeof parsed !== "object" || parsed.version !== 2 || !["auto", "light", "dark"].includes(parsed.mode)) {
        return null;
      }
      return parsed;
    } catch (error) {
      return ["slate", "default"].includes(rawValue) ? { version: 1, scheme: rawValue } : null;
    }
  }

  function initializeGlobalTheme(themeKey) {
    const savedChoice = parseStoredChoice(safeGetGlobalTheme(themeKey));

    if (savedChoice) {
      if (savedChoice.signature) {
        const signedOption = findOptionBySignature(savedChoice.signature);
        if (signedOption) {
          applyOption(themeKey, signedOption, false);
          return;
        }
      }

      if (savedChoice.mode) {
        const modeOption = optionByMode(savedChoice.mode);
        if (modeOption) {
          applyOption(themeKey, modeOption, false);
          return;
        }
      }

      if (savedChoice.scheme) {
        const legacyMode = savedChoice.scheme === "slate" ? "dark" : "light";
        const legacyOption = optionByMode(legacyMode);
        if (legacyOption) {
          applyOption(themeKey, legacyOption, false);
          return;
        }
      }
    }

    const selectedOption = paletteOptions().find((option) => option.checked);
    if (selectedOption) {
      persistThemeChoice(themeKey, selectedOption);
      return;
    }

    const activeScheme = activeSchemeFromDom();
    if (activeScheme) {
      const inferredMode = activeScheme === "slate" ? "dark" : "light";
      const inferredOption = optionByMode(inferredMode);
      if (inferredOption) {
        persistThemeChoice(themeKey, inferredOption);
      }
    }
  }

  function bindPaletteChanges(themeKey) {
    for (const option of paletteOptions()) {
      if (option.dataset.bijuxThemeBound === "true") {
        continue;
      }

      option.dataset.bijuxThemeBound = "true";
      option.addEventListener("change", () => {
        if (!option.checked) {
          return;
        }
        applyOption(themeKey, option, true);
        refreshThemeToggleButtons();
      });
    }
  }

  function bindThemeToggle(themeKey) {
    for (const button of document.querySelectorAll("[data-bijux-theme-toggle]")) {
      if (button.dataset.bijuxThemeToggleBound === "true") {
        continue;
      }

      button.dataset.bijuxThemeToggleBound = "true";
      button.addEventListener("click", () => {
        const targetMode = nextMode(currentMode());
        const targetOption = optionByMode(targetMode);
        if (!targetOption) {
          return;
        }
        targetOption.checked = true;
        targetOption.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }
  }

  function bindCrossTabSync(themeKey) {
    if (window.__bijuxThemeStorageBound === true) {
      return;
    }

    window.__bijuxThemeStorageBound = true;
    window.addEventListener("storage", (event) => {
      if (event.key !== themeKey || !event.newValue) {
        return;
      }
      const savedChoice = parseStoredChoice(event.newValue);
      if (!savedChoice) {
        return;
      }

      if (savedChoice.signature) {
        const signedOption = findOptionBySignature(savedChoice.signature);
        if (signedOption) {
          applyOption(themeKey, signedOption, false);
          refreshThemeToggleButtons();
          return;
        }
      }

      if (savedChoice.mode) {
        const modeOption = optionByMode(savedChoice.mode);
        applyOption(themeKey, modeOption, false);
        refreshThemeToggleButtons();
      }
    });
  }

  function init() {
    const themeKey = resolveThemeKey();
    bindPaletteChanges(themeKey);
    bindThemeToggle(themeKey);
    initializeGlobalTheme(themeKey);
    bindCrossTabSync(themeKey);
    refreshThemeToggleButtons();
  }

  if (window.document$ && typeof window.document$.subscribe === "function") window.document$.subscribe(init);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
