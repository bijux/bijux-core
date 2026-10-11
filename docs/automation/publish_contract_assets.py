from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

CONTRACT_ASSETS = [
    "schemas/output-envelope-v1.schema.json",
    "schemas/error-envelope-v1.schema.json",
    "schemas/plugin-manifest-v2.schema.json",
    "official_product_namespace_registry.json",
    "product_mount_metadata_contract.json",
]

MARKDOWN_LINK = re.compile(r"(?<!!)(\[[^\]]+\]\()([^)]+)(\))")
HTML_LINK = re.compile(r"""(href\s*=\s*["'])([^"']+)(["'])""", re.IGNORECASE)


def _nav_pages(nav: object) -> set[str]:
    pages: set[str] = set()
    if isinstance(nav, str) and nav.endswith(".md"):
        pages.add(nav)
    elif isinstance(nav, list):
        for entry in nav:
            pages.update(_nav_pages(entry))
    elif isinstance(nav, dict):
        for entry in nav.values():
            pages.update(_nav_pages(entry))
    return pages


def _source_target(source_path: str, raw_target: str) -> tuple[str, str] | None:
    if "\\" in raw_target or any(ord(char) < 32 or ord(char) == 127 for char in raw_target):
        return None
    target = raw_target.strip().strip("<>")
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    path = unquote(parsed.path)
    if "\\" in path or any(ord(char) < 32 or ord(char) == 127 for char in path):
        return None
    if path.startswith("/"):
        source_target = posixpath.normpath(path.lstrip("/"))
    else:
        source_target = posixpath.normpath(
            posixpath.join(posixpath.dirname(source_path), path)
        )

    # Source routing may inspect only the repository's owned documentation tree.
    if source_target == ".." or source_target.startswith("../"):
        return None

    if path.endswith("/"):
        source_target = posixpath.join(source_target, "index.md")
    elif not source_target.endswith(".md"):
        return None
    return source_target, parsed.fragment


def _source_url(config: object, source_target: str, fragment: str) -> str:
    repo_url = str(config["repo_url"]).rstrip("/")
    edit_uri = str(config.get("edit_uri", "edit/main/docs/"))
    branch_match = re.match(r"edit/([^/]+)/", edit_uri)
    branch = branch_match.group(1) if branch_match else "main"
    url = f"{repo_url}/blob/{branch}/docs/{source_target}"
    if fragment:
        url = urlunsplit(("", "", url, "", fragment))
    return url


def _published_target(
    config: object, source_path: str, raw_target: str, published: set[str]
) -> str:
    resolved = _source_target(source_path, raw_target)
    if resolved is None:
        return raw_target
    source_target, fragment = resolved
    if source_target in published:
        return raw_target

    workspace_root = Path(__file__).resolve().parents[2]
    if not (workspace_root / "docs" / source_target).is_file():
        return raw_target
    return _source_url(config, source_target, fragment)


def _published_html_target(
    config: object, source_path: str, raw_target: str, published: set[str]
) -> str:
    resolved = _source_target(source_path, raw_target)
    if resolved is None:
        return raw_target
    source_target, fragment = resolved
    if source_target not in published:
        return _published_target(config, source_path, raw_target, published)

    source_output = (
        posixpath.dirname(source_path)
        if source_path.endswith("/index.md") or source_path == "index.md"
        else source_path.removesuffix(".md")
    )
    target_output = (
        posixpath.dirname(source_target)
        if source_target.endswith("/index.md") or source_target == "index.md"
        else source_target.removesuffix(".md")
    )
    relative = posixpath.relpath(target_output, source_output)
    url = "./" if relative == "." else f"{relative}/"
    return f"{url}#{fragment}" if fragment else url


def on_page_markdown(markdown, page, config, **kwargs):
    """Route unpublished repository references to their GitHub source."""

    published = _nav_pages(config["nav"])
    source_path = page.file.src_uri

    def replace_markdown(match: re.Match[str]) -> str:
        target = _published_target(config, source_path, match.group(2), published)
        return f"{match.group(1)}{target}{match.group(3)}"

    def replace_html(match: re.Match[str]) -> str:
        target = _published_html_target(config, source_path, match.group(2), published)
        return f"{match.group(1)}{target}{match.group(3)}"

    markdown = MARKDOWN_LINK.sub(replace_markdown, markdown)
    return HTML_LINK.sub(replace_html, markdown)


def on_post_build(config, **kwargs) -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    source_root = workspace_root / "contracts"

    site_dir = Path(config["site_dir"])
    if not site_dir.is_absolute():
        site_dir = (workspace_root / site_dir).resolve()
    target_root = site_dir / "contracts"

    for rel_path in CONTRACT_ASSETS:
        source = source_root / rel_path
        target = target_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
