#!/usr/bin/env python3
"""Render repository badge surfaces from package-catalog metadata."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any, cast


TOKEN_RE = re.compile(r"{{\s*(?P<name>[a-z0-9_]+)\s*}}")
BADGE_GROUPS: tuple[str, ...] = (
    "family-pypi-badge",
    "family-ghcr-badge",
    "family-docs-badge",
)


@dataclass(frozen=True)
class PackageBadgeRecord:
    """Rendered badge metadata for one public package."""

    package_slug: str
    distribution_name: str
    docs_url: str
    package_pypi_url: str
    package_ghcr_url: str
    distribution_shields_slug: str
    pypi_badge_label: str
    docs_badge_label: str
    docs_badge_alt: str


@dataclass(frozen=True)
class BadgeTarget:
    """README-like surface that consumes generated badge content."""

    path: Path
    kind: str
    package_slug: str | None = None


class BadgeRenderer:
    """Catalog-driven badge renderer shared by Python repositories."""

    def __init__(self, repo_root: Path, workspace_key: str) -> None:
        self.repo_root = repo_root.resolve()
        self.workspace_key = workspace_key
        self.workspace = self._workspace_metadata()
        self.repository = cast(str, self.workspace["repository"])
        self.marker_prefix = cast(
            str,
            self.workspace.get("badge_marker", f"{self.repository}-badges"),
        )
        self.start_marker = f"<!-- {self.marker_prefix}:generated:start -->"
        self.end_marker = f"<!-- {self.marker_prefix}:generated:end -->"
        self.badge_source_path = self.repo_root / cast(
            str,
            self.workspace.get("badge_catalog", "docs/badges.md"),
        )
        self.badge_block_re = re.compile(
            rf"<!-- {re.escape(self.marker_prefix)}:(?P<name>[a-z0-9-]+):start -->\n"
            rf"(?P<body>.*?)\n"
            rf"<!-- {re.escape(self.marker_prefix)}:(?P=name):end -->",
            re.DOTALL,
        )

    def _workspace_metadata(self) -> dict[str, Any]:
        with (self.repo_root / "pyproject.toml").open("rb") as handle:
            document = tomllib.load(handle)
        return cast(dict[str, Any], document["tool"][self.workspace_key])

    def _package_dirs(self) -> dict[str, str]:
        configured = self.workspace.get("package_dirs")
        if isinstance(configured, dict):
            return cast(dict[str, str], configured)
        packages = cast(list[str], self.workspace["packages"])
        return {package: f"packages/{package}" for package in packages}

    def _package_project(self, package_slug: str) -> dict[str, Any]:
        path = self.repo_root / self._package_dirs()[package_slug] / "pyproject.toml"
        with path.open("rb") as handle:
            document = tomllib.load(handle)
        return cast(dict[str, Any], document["project"])

    def _package_slugs(self, key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
        configured = self.workspace.get(key)
        if configured is None:
            return fallback
        return tuple(cast(list[str], configured))

    def target_package_slugs(self) -> tuple[str, ...]:
        docs_package = cast(str, self.workspace["docs_package"])
        packages = tuple(cast(list[str], self.workspace["packages"]))
        return self._package_slugs(
            "badge_target_packages",
            tuple(package for package in packages if package != docs_package),
        )

    def family_package_slugs(self) -> tuple[str, ...]:
        return self._package_slugs("badge_packages", self.target_package_slugs())

    def docs_package_slugs(self) -> tuple[str, ...]:
        return self._package_slugs(
            "docs_badge_packages",
            self.family_package_slugs(),
        )

    @staticmethod
    def _shield_text(value: str) -> str:
        return value.replace("-", "--").replace(" ", "%20")

    def _short_family_label(self, distribution_name: str) -> str:
        prefix = cast(
            str,
            self.workspace.get("badge_family_prefix", f"{self.repository}-"),
        )
        if distribution_name.startswith(prefix):
            return distribution_name.removeprefix(prefix)
        return distribution_name

    def _package_record(self, package_slug: str) -> PackageBadgeRecord:
        project = self._package_project(package_slug)
        distribution_name = str(project["name"])
        docs_url = str(project.get("urls", {}).get("Documentation", ""))
        label_text = self._short_family_label(distribution_name)
        return PackageBadgeRecord(
            package_slug=package_slug,
            distribution_name=distribution_name,
            docs_url=docs_url,
            package_pypi_url=f"https://pypi.org/project/{distribution_name}/",
            package_ghcr_url=(
                f"https://github.com/bijux/{self.repository}/pkgs/container/"
                f"{self.repository}%2F{distribution_name}"
            ),
            distribution_shields_slug=self._shield_text(distribution_name),
            pypi_badge_label=self._shield_text(label_text),
            docs_badge_label=self._shield_text(label_text),
            docs_badge_alt=f"{distribution_name} docs",
        )

    def records(self, package_slugs: tuple[str, ...]) -> tuple[PackageBadgeRecord, ...]:
        return tuple(self._package_record(slug) for slug in package_slugs)

    def public_package_records(self) -> tuple[PackageBadgeRecord, ...]:
        return self.records(self.target_package_slugs())

    def family_badge_records(self) -> tuple[PackageBadgeRecord, ...]:
        return self.records(self.family_package_slugs())

    def docs_badge_records(self) -> tuple[PackageBadgeRecord, ...]:
        return self.records(self.docs_package_slugs())

    def load_badge_catalog(self) -> dict[str, str]:
        text = self.badge_source_path.read_text(encoding="utf-8")
        catalog = {
            match.group("name"): match.group("body").strip()
            for match in self.badge_block_re.finditer(text)
        }
        if not catalog:
            raise ValueError(f"No badge blocks found in {self.badge_source_path}")
        return catalog

    @staticmethod
    def _render_template(template: str, context: dict[str, str]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group("name")
            try:
                return context[key]
            except KeyError as exc:
                raise KeyError(f"Missing badge token {key!r}") from exc

        return TOKEN_RE.sub(replace, template)

    @staticmethod
    def _record_context(record: PackageBadgeRecord) -> dict[str, str]:
        return {
            "distribution_name": record.distribution_name,
            "distribution_shields_slug": record.distribution_shields_slug,
            "docs_badge_alt": record.docs_badge_alt,
            "docs_badge_label": record.docs_badge_label,
            "docs_url": record.docs_url,
            "package_ghcr_url": record.package_ghcr_url,
            "package_pypi_url": record.package_pypi_url,
            "pypi_badge_label": record.pypi_badge_label,
        }

    def _render_badge_group(
        self,
        template: str,
        records: tuple[PackageBadgeRecord, ...],
    ) -> str:
        return "\n".join(
            self._render_template(template, self._record_context(record))
            for record in records
        )

    @staticmethod
    def _prioritize_record(
        records: tuple[PackageBadgeRecord, ...],
        current: PackageBadgeRecord,
    ) -> tuple[PackageBadgeRecord, ...]:
        return (current,) + tuple(
            record for record in records if record.package_slug != current.package_slug
        )

    def _group_records(
        self,
        template_name: str,
        *,
        current: PackageBadgeRecord | None,
    ) -> tuple[PackageBadgeRecord, ...]:
        if template_name == "family-docs-badge":
            records = self.docs_badge_records()
            include_current = bool(
                self.workspace.get("badge_include_current_docs", True)
            )
        else:
            records = self.family_badge_records()
            include_current = True
        if current is None:
            return records
        if include_current or any(
            record.package_slug == current.package_slug for record in records
        ):
            return self._prioritize_record(records, current)
        return records

    def _render_badge_groups(
        self,
        catalog: dict[str, str],
        *,
        current: PackageBadgeRecord | None = None,
    ) -> list[str]:
        return [
            self._render_badge_group(
                catalog[template_name],
                self._group_records(template_name, current=current),
            )
            for template_name in BADGE_GROUPS
        ]

    def iter_badge_targets(self) -> tuple[BadgeTarget, ...]:
        targets = [
            BadgeTarget(path=self.repo_root / "README.md", kind="repository"),
            BadgeTarget(path=self.repo_root / "docs/index.md", kind="repository"),
        ]
        package_dirs = self._package_dirs()
        targets.extend(
            BadgeTarget(
                path=self.repo_root / package_dirs[slug] / "README.md",
                kind="package",
                package_slug=slug,
            )
            for slug in self.target_package_slugs()
        )
        catalog = self.load_badge_catalog()
        if "maintainer-summary" in catalog:
            docs_package = cast(str, self.workspace["docs_package"])
            targets.append(
                BadgeTarget(
                    path=self.repo_root / package_dirs[docs_package] / "README.md",
                    kind="maintainer",
                )
            )
        return tuple(targets)

    def render_badge_block(self, target: BadgeTarget) -> str:
        catalog = self.load_badge_catalog()
        public_records = self.public_package_records()
        if target.kind == "repository":
            sections = [
                self._render_template(
                    catalog["repository-summary"],
                    {"public_package_count": str(len(public_records))},
                ),
                *self._render_badge_groups(catalog),
            ]
        elif target.kind == "maintainer":
            sections = [catalog["maintainer-summary"]]
        elif target.kind == "package" and target.package_slug is not None:
            current = next(
                record
                for record in public_records
                if record.package_slug == target.package_slug
            )
            sections = [
                self._render_template(
                    catalog["package-summary"],
                    self._record_context(current),
                ),
                *self._render_badge_groups(catalog, current=current),
            ]
        else:
            raise ValueError(f"Unsupported badge target: {target}")
        return "\n\n".join(section for section in sections if section)

    def _managed_block(self, rendered_badges: str) -> str:
        return f"{self.start_marker}\n{rendered_badges.rstrip()}\n{self.end_marker}"

    def render_target_text(self, target: BadgeTarget, current_text: str) -> str:
        managed_block = self._managed_block(self.render_badge_block(target))
        if self.start_marker in current_text and self.end_marker in current_text:
            start = current_text.index(self.start_marker)
            end = current_text.index(self.end_marker) + len(self.end_marker)
            updated = current_text[:start] + managed_block + current_text[end:]
            return updated if updated.endswith("\n") else updated + "\n"

        lines = current_text.splitlines()
        start_index = next(
            (index for index, line in enumerate(lines) if line.startswith("[![")),
            None,
        )
        if start_index is None:
            raise ValueError(f"Unable to locate badge block in {target.path}")
        probe = start_index - 1
        while probe >= 0 and not lines[probe].strip():
            probe -= 1
        if probe >= 0 and lines[probe].strip() == "## Package Family":
            start_index = probe
        end_index = start_index
        while end_index < len(lines):
            line = lines[end_index]
            if line.startswith("[![") or not line.strip():
                end_index += 1
                continue
            if line.strip() == "## Package Family":
                end_index += 1
                continue
            break
        replacement = [*managed_block.splitlines(), ""]
        return "\n".join(lines[:start_index] + replacement + lines[end_index:]) + "\n"

    def synchronize_badges(self, *, check: bool) -> list[Path]:
        changed: list[Path] = []
        for target in self.iter_badge_targets():
            current_text = target.path.read_text(encoding="utf-8")
            expected_text = self.render_target_text(target, current_text)
            if expected_text == current_text:
                continue
            changed.append(target.path)
            if not check:
                target.path.write_text(expected_text, encoding="utf-8")
        return changed

    def main(self, argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            description="Synchronize package-catalog badge templates."
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        subparsers.add_parser("sync", help="Render managed badge surfaces.")
        subparsers.add_parser("check", help="Fail when badge surfaces are stale.")
        args = parser.parse_args(argv)
        check = args.command == "check"
        changed = self.synchronize_badges(check=check)
        if check and changed:
            for path in changed:
                print(path.relative_to(self.repo_root))
            return 1
        return 0
