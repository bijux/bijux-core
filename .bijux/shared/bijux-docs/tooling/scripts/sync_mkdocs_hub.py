#!/usr/bin/env python3
"""Synchronize the canonical Bijux hub into an inherited MkDocs config."""

from __future__ import annotations

import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration.ordered_assets import project_required_lists
from configuration.branding import project_theme_logo
from configuration.prior_assets import prior_javascript


def load_hub_links(shared_root: Path) -> list[dict[str, str]]:
    path = shared_root / "config/hub-links.json"
    links = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(links, list) or not links:
        raise RuntimeError(f"{path}: expected a non-empty list")

    keys: set[str] = set()
    for index, link in enumerate(links, start=1):
        if not isinstance(link, dict):
            raise RuntimeError(f"{path}: entry {index} must be an object")
        if set(link) != {"key", "label", "url"}:
            raise RuntimeError(f"{path}: entry {index} must contain key, label, and url")
        if not all(isinstance(link[field], str) and link[field] for field in link):
            raise RuntimeError(f"{path}: entry {index} contains an empty value")
        if link["key"] in keys:
            raise RuntimeError(f"{path}: duplicate key {link['key']}")
        if not link["url"].startswith("https://"):
            raise RuntimeError(f"{path}: entry {index} URL must use https")
        keys.add(link["key"])
    return links


def render_hub_links(links: list[dict[str, str]]) -> list[str]:
    rendered = ["    hub_links:\n"]
    for link in links:
        rendered.extend(
            (
                f"      - key: {link['key']}\n",
                f"        label: {link['label']}\n",
                f"        url: {link['url']}\n",
            )
        )
    return rendered


def leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def bijux_mapping_bounds(lines: list[str], config_path: Path) -> tuple[int, int]:
    extra_index = next((index for index, line in enumerate(lines) if line == "extra:\n"), None)
    if extra_index is None:
        raise RuntimeError(f"{config_path}: missing top-level extra mapping")

    extra_end = next(
        (
            index
            for index in range(extra_index + 1, len(lines))
            if lines[index].strip() and leading_spaces(lines[index]) == 0
        ),
        len(lines),
    )
    bijux_index = next(
        (
            index
            for index in range(extra_index + 1, extra_end)
            if lines[index] == "  bijux:\n"
        ),
        None,
    )
    if bijux_index is None:
        raise RuntimeError(f"{config_path}: missing extra.bijux mapping")

    bijux_end = next(
        (
            index
            for index in range(bijux_index + 1, extra_end)
            if lines[index].strip() and leading_spaces(lines[index]) <= 2
        ),
        extra_end,
    )
    return bijux_index, bijux_end


def hub_mapping_bounds(
    lines: list[str],
    bijux_index: int,
    bijux_end: int,
) -> tuple[int | None, int]:
    hub_index = next(
        (
            index
            for index in range(bijux_index + 1, bijux_end)
            if lines[index] == "    hub_links:\n"
        ),
        None,
    )
    if hub_index is None:
        return None, bijux_end

    hub_end = next(
        (
            index
            for index in range(hub_index + 1, bijux_end)
            if lines[index].strip() and leading_spaces(lines[index]) <= 4
        ),
        bijux_end,
    )
    return hub_index, hub_end


def shared_hub_content(original: str, config_path: Path, links: list[dict[str, str]]) -> str:
    lines = original.splitlines(keepends=True)
    bijux_index, bijux_end = bijux_mapping_bounds(lines, config_path)
    hub_index, hub_end = hub_mapping_bounds(lines, bijux_index, bijux_end)

    replacement = render_hub_links(links)
    if hub_index is None:
        insert_index = next(
            (
                index + 1
                for index in range(bijux_index + 1, bijux_end)
                if lines[index].startswith("    theme_key:")
            ),
            bijux_end,
        )
        updated = lines[:insert_index] + replacement + lines[insert_index:]
    else:
        updated = lines[:hub_index] + replacement + lines[hub_end:]

    return "".join(updated)

def synchronize_shared_config(config_path: Path, links: list[dict[str, str]]) -> bool:
    original = config_path.read_text(encoding="utf-8")
    updated = shared_hub_content(original, config_path, links)
    if updated == original:
        return False
    config_path.write_text(updated, encoding="utf-8")
    return True


def root_hub_content(original: str, config_path: Path) -> str:
    lines = original.splitlines(keepends=True)
    bijux_index, bijux_end = bijux_mapping_bounds(lines, config_path)
    hub_index, hub_end = hub_mapping_bounds(lines, bijux_index, bijux_end)
    if hub_index is None:
        return original
    return "".join(lines[:hub_index] + lines[hub_end:])


def remove_root_hub(config_path: Path) -> bool:
    original = config_path.read_text(encoding="utf-8")
    updated = root_hub_content(original, config_path)
    if updated == original:
        return False
    config_path.write_text(updated, encoding="utf-8")
    return True


def diagram_content(original: str) -> str:
    """Keep the named language while preventing Material's external renderer interception."""
    pattern = r"(?P<indent> +)- name: mermaid\s*\n(?P<body>(?:(?P=indent)  .*\n)*)"
    def replace_fence(match: re.Match[str]) -> str:
        indent, body = match.group('indent'), match.group('body')
        line = indent + '  class: bijux-diagram\n'
        if re.search(r'^ +class:', body, re.MULTILINE):
            body = re.sub(r'^ +class:[^\n]*\n', line, body, flags=re.MULTILINE)
        else:
            body = line + body
        return indent + '- name: mermaid\n' + body
    updated = re.sub(pattern, replace_fence, original)
    return updated

def synchronize_diagram_contract(config_path: Path) -> bool:
    original = config_path.read_text(encoding="utf-8")
    updated = diagram_content(original)
    if updated == original:
        return False
    config_path.write_text(updated, encoding="utf-8")
    return True


def implementation_exclusions(content: str, required: list[str], config_path: Path) -> str:
    """Preserve authored pathspec rules and end with the mandatory publication boundary."""
    lines = content.splitlines(keepends=True)
    indices = [index for index, line in enumerate(lines) if re.match(r'^exclude_docs\s*:', line)]
    if len(indices) > 1:
        raise RuntimeError(f'{config_path}: duplicate exclude_docs keys')
    start = indices[0] if indices else len(lines)
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].strip() and leading_spaces(lines[index]) == 0), len(lines))
    rules = ''
    if indices:
        value = lines[start].split(':', 1)[1].strip()
        if re.fullmatch(r'\|[-+]?(?:\s+#.*)?', value):
            nonempty = [line for line in lines[start + 1:end] if line.strip()]
            indent = min((leading_spaces(line) for line in nonempty), default=2)
            rules = ''.join(line[indent:] for line in lines[start + 1:end])
        elif value.startswith('"'):
            try:
                rules = json.loads(value)
            except ValueError as exc:
                raise RuntimeError(f'{config_path}: exclude_docs quoted scalar is unsupported') from exc
        elif value.startswith("'") and value.endswith("'"):
            rules = value[1:-1].replace("''", "'")
        elif not value or value.startswith('#'):
            rules = ''
        elif any(value.startswith(char) for char in ('>', '[', '{', '!', '*', '&')):
            raise RuntimeError(f'{config_path}: exclude_docs must be a literal or plain pathspec string')
        else:
            rules = re.split(r'\s+#', value, maxsplit=1)[0] + '\n'
    if not isinstance(rules, str):
        raise RuntimeError(f'{config_path}: exclude_docs must be a pathspec string')
    authored = [rule for rule in rules.splitlines() if rule.strip() not in required]
    replacement = ['exclude_docs: |\n'] + ['  ' + rule + '\n' for rule in [*authored, *required]]
    if not indices and lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    return ''.join(lines[:start] + replacement + lines[end:])


def plan_configs(repo_root: Path, shared_root: Path) -> dict[Path, tuple[str, str]]:
    """Resolve every configuration transformation before the first write."""
    links = load_hub_links(shared_root)
    baseline = json.loads((shared_root / "config/mkdocs-baseline.json").read_text())
    required = baseline["required_exclude_docs"]
    if not isinstance(required, list) or not required or not all(isinstance(rule, str) and rule.startswith("/") for rule in required):
        raise RuntimeError("Canonical implementation exclusion policy is missing or invalid")
    plans = {}
    for name in ("mkdocs.shared.yml", "mkdocs.yml"):
        path = repo_root / name
        if path.is_symlink():
            raise RuntimeError(f"{path}: configuration symlinks require explicit author review")
        with path.open(encoding="utf-8", newline="") as stream:
            original = stream.read()
        shared = name == "mkdocs.shared.yml"
        updated = project_theme_logo(original, baseline, path)
        updated = project_required_lists(updated, baseline, path, shared=shared,
                                         prior_javascript=lambda: prior_javascript(repo_root, shared_root))
        updated = shared_hub_content(updated, path, links) if shared else root_hub_content(updated, path)
        updated = diagram_content(updated)
        updated = implementation_exclusions(updated, required, path)
        plans[path] = (original, updated)
    return plans


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--check"]
    check = "--check" in sys.argv[1:]
    if len(args) > 2:
        raise RuntimeError("Usage: sync_mkdocs_hub.py [repository] [shared-root] [--check]")
    repo_root = Path(args[0]).resolve() if args else Path.cwd()
    shared_root = Path(args[1]).resolve() if len(args) > 1 else repo_root / ("shared/bijux-docs" if (repo_root / "shared/bijux-docs").is_dir() else ".bijux/shared/bijux-docs")
    plans = plan_configs(repo_root, shared_root)
    stale = [path for path, (original, updated) in plans.items() if original != updated]
    if check:
        if stale:
            raise RuntimeError("Canonical MkDocs configuration drift: " + ", ".join(str(path) for path in stale) + "; run make bijux-docs-sync from verified source")
        print("Canonical MkDocs configuration is current")
        return 0
    for path, (original, updated) in plans.items():
        if original != updated:
            with path.open("w", encoding="utf-8", newline="") as stream:
                stream.write(updated)
        print(f"Bijux MkDocs configuration {'updated' if original != updated else 'current'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
