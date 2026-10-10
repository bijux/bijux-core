"""Validate shell-owned configuration without discarding author-owned options."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


def require(condition: bool, source: str, field: str, message: str) -> None:
    if not condition:
        raise RuntimeError(f"{source}: {field} {message}")


def mapping(value: object, source: str, field: str) -> dict:
    require(isinstance(value, dict), source, field, "must be a mapping")
    return value


def text(value: object, source: str, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), source, field, "must be a non-empty string")
    return value


def registry(links: object, source: str) -> list[dict]:
    """Validate source records before comparing them to the canonical registry."""
    require(isinstance(links, list) and bool(links), source, "extra.bijux.hub_links", "must be a non-empty list")
    keys = set()
    for index, value in enumerate(links, start=1):
        field = f"extra.bijux.hub_links[{index}]"
        link = mapping(value, source, field)
        key = text(link.get("key"), source, field + ".key")
        require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key)), source, field + ".key", "must be a repository identifier")
        require(key not in keys, source, field + ".key", f"'{key}' is duplicated")
        keys.add(key)
        text(link.get("label"), source, field + ".label")
        url = text(link.get("url"), source, field + ".url")
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.username is None and parsed.password is None
            parsed.port
        except ValueError:
            valid = False
        require(valid and not any(character.isspace() or ord(character) < 32 for character in url), source, field + ".url", "must be an absolute HTTP(S) URL without credentials or whitespace")
    return links


def validate_settings(config: object, source: str, role: str) -> dict:
    """Return validated Bijux settings for root, shared, or effective input.

    Unknown product fields are retained. This schema owns the documented Bijux
    fields and MkDocs hook shape; MkDocs owns plugin-specific configuration.
    """
    if role not in ("root", "shared", "effective"):
        raise ValueError(f"Unsupported shell configuration role: {role}")
    config = mapping(config, source, "configuration")
    extra = mapping(config.get("extra", {}), source, "extra")
    bijux = mapping(extra.get("bijux", {}), source, "extra.bijux")
    if role in ("root", "effective") or "repository" in bijux:
        repository = text(bijux.get("repository"), source, "extra.bijux.repository")
        require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", repository)), source, "extra.bijux.repository", "must be a repository identifier")
    if role != "root" or "nav_mode" in bijux:
        require(bijux.get("nav_mode") == "default", source, "extra.bijux.nav_mode", "must be 'default'")
    if role != "root" or "theme_key" in bijux:
        require(bijux.get("theme_key") == "bijux:theme", source, "extra.bijux.theme_key", "must be 'bijux:theme'")
    if "repository_facts" in bijux:
        require(type(bijux["repository_facts"]) is bool, source, "extra.bijux.repository_facts", "must be a Boolean; omit it for the disabled default")
    if "interactive_report_owner" in bijux:
        field = "extra.bijux.interactive_report_owner"
        owner = text(bijux["interactive_report_owner"], source, field)
        require(len(owner) <= 1024 and owner.endswith(".json") and not owner.startswith("/")
                and not any(part in {"", ".", ".."} for part in owner.split("/"))
                and not any(character.isspace() or ord(character) < 32 or character in "\\%" for character in owner),
                source, field, "must be a bounded canonical relative JSON source path")
        require(role != "shared", source, field, "belongs to the authored product configuration")
    if role == "root":
        require("hub_links" not in bijux, source, "extra.bijux.hub_links", "must be inherited from mkdocs.shared.yml")
    else:
        registry(bijux.get("hub_links"), source)
    if "hooks" in config:
        hooks = config["hooks"]
        require(isinstance(hooks, list), source, "hooks", "must be a list of authored hook paths")
        for index, hook in enumerate(hooks, start=1):
            text(hook, source, f"hooks[{index}]")
    return bijux


def validate_canonical_registry(actual: list[dict], expected: list[dict], source: str) -> None:
    registry(expected, "canonical hub registry")
    missing = [entry["key"] for entry in expected if not any(link["key"] == entry["key"] for link in actual)]
    suffix = "; missing required keys: " + ", ".join(missing) if missing else ""
    require(actual == expected, source, "extra.bijux.hub_links", "must exactly match the canonical shared hub" + suffix)
