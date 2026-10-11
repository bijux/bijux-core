#!/usr/bin/env python3
"""Validate rendered docs navigation state for the shared handbook chrome."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


class NavigationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.site_paths: list[str] = []
        self.site_active_count = 0
        self.detail_paths: list[str] = []
        self.detail_active_count = 0
        self.course_paths: list[str] = []
        self.course_active_count = 0
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href")
        if href is not None:
            self.links.append(href)

        site_path = attributes.get("data-bijux-site-path")
        if site_path is not None:
            self.site_paths.append(site_path)
            if attributes.get("aria-current") in {"page", "location"}:
                self.site_active_count += 1

        detail_path = attributes.get("data-bijux-detail-path")
        if detail_path is not None:
            self.detail_paths.append(detail_path)
            if attributes.get("aria-current") in {"page", "location"}:
                self.detail_active_count += 1

        course_path = attributes.get("data-bijux-course-path")
        if course_path is not None:
            self.course_paths.append(course_path)
            if attributes.get("aria-current") in {"page", "location"}:
                self.course_active_count += 1


def has_visible_detail_strip(html: str) -> bool:
    return bool(
        re.search(r"data-bijux-detail-strip(?:(?!hidden).)*>", html, flags=re.DOTALL)
    )


def has_visible_course_strip(html: str) -> bool:
    return bool(
        re.search(r"data-bijux-course-strip(?:(?!hidden).)*>", html, flags=re.DOTALL)
    )


def validate_unique(paths: list[str], label: str, path: pathlib.Path) -> list[str]:
    issues: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()

    for entry in paths:
        if entry in seen:
            duplicates.add(entry)
        seen.add(entry)

    for duplicate in sorted(duplicates):
        issues.append(f"{path}: duplicate {label} path {duplicate}")

    return issues


def validate_file(path: pathlib.Path) -> list[str]:
    html = path.read_text(encoding="utf-8")
    parser = NavigationParser()
    parser.feed(html)

    issues: list[str] = []
    issues.extend(validate_unique(parser.site_paths, "site-tab", path))
    issues.extend(validate_unique(parser.detail_paths, "detail-strip", path))
    issues.extend(validate_unique(parser.course_paths, "course-strip", path))

    if parser.site_paths and parser.site_active_count != 1:
        issues.append(
            f"{path}: expected exactly one active site tab, found {parser.site_active_count}"
        )

    if parser.detail_paths and has_visible_detail_strip(html) and parser.detail_active_count != 1:
        issues.append(
            f"{path}: expected exactly one active detail tab, found {parser.detail_active_count}"
        )

    if parser.course_paths and has_visible_course_strip(html) and parser.course_active_count != 1:
        issues.append(
            f"{path}: expected exactly one active course tab, found {parser.course_active_count}"
        )

    return issues


def local_link_target(
    source: pathlib.Path, site_dir: pathlib.Path, site_url: str, href: str
) -> pathlib.Path | None:
    if "{{" in href or "}}" in href:
        return None
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None

    path = unquote(parsed.path)
    if path.startswith("/"):
        site_prefix = urlsplit(site_url).path.rstrip("/") + "/"
        if site_prefix != "/" and path.startswith(site_prefix):
            path = path[len(site_prefix) :]
        else:
            path = path.lstrip("/")
        target = site_dir / path
    else:
        target = source.parent / path

    if path.endswith("/"):
        target /= "index.html"
    return target.resolve()


def validate_local_links(site_dir: pathlib.Path, site_url: str) -> list[str]:
    issues: list[str] = []
    site_root = site_dir.resolve()

    for source in sorted(site_root.rglob("*.html")):
        parser = NavigationParser()
        parser.feed(source.read_text(encoding="utf-8"))
        for href in parser.links:
            target = local_link_target(source, site_root, site_url, href)
            if target is None or not target.is_relative_to(site_root):
                continue
            if not target.exists():
                issues.append(
                    f"{source.relative_to(site_root)}: local link has no published "
                    f"target: {href}"
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=pathlib.Path)
    parser.add_argument("--site-url", default="https://bijux.io/bijux-core/")
    args = parser.parse_args()

    sample_paths = [
        args.site_dir / "index.html",
        args.site_dir / "bijux-core" / "architecture" / "system-overview" / "index.html",
        args.site_dir / "bijux-cli" / "interfaces" / "cli-surface" / "index.html",
        args.site_dir / "bijux-dag" / "operations" / "first-run-tutorial" / "index.html",
        args.site_dir / "bijux-dev" / "governance" / "test-policy" / "index.html",
    ]

    issues: list[str] = []
    for path in sample_paths:
        if not path.is_file():
            issues.append(f"{path}: missing rendered page for navigation sanity checks")
            continue
        issues.extend(validate_file(path))
    issues.extend(validate_local_links(args.site_dir, args.site_url))

    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1

    print(f"Navigation sanity OK for {args.site_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
