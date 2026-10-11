#!/usr/bin/env python3
"""Inspect, migrate, and materialize governed artifact alias symlinks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Iterable


ROOT_ALIAS_LAYOUT = {
    ".venv": Path("artifacts/root/check-venv"),
    ".tox": Path("artifacts/root/tox"),
    ".hypothesis": Path("artifacts/root/hypothesis"),
    ".benchmarks": Path("artifacts/root/benchmarks"),
}

PACKAGE_ALIAS_LAYOUT = {
    "artifacts": Path("artifacts/{package}"),
    ".venv": Path("artifacts/{package}/venv"),
    ".hypothesis": Path("artifacts/{package}/hypothesis"),
    ".benchmarks": Path("artifacts/{package}/benchmarks"),
}

PRESERVED_LOCAL_DIRECTORY_ALIASES = frozenset(
    {
        ".venv",
        ".tox",
        ".hypothesis",
        ".benchmarks",
    }
)


@dataclass(frozen=True)
class AliasBinding:
    """One public compatibility path and its canonical artifact destination."""

    alias_path: Path
    target_path: Path


@dataclass(frozen=True)
class AliasInspection:
    """Observed state for one artifact alias binding."""

    binding: AliasBinding
    state: str
    size_bytes: int | None = None
    detail: str = ""


def _relative_target(*, link_path: Path, target_path: Path) -> str:
    return os.path.relpath(target_path, start=link_path.parent)


def _path_size(path: Path) -> int:
    """Return a non-following byte count for a file or directory tree."""
    if path.is_symlink():
        return path.lstat().st_size
    if path.is_file():
        return path.stat().st_size

    total = path.stat().st_size
    for child in path.iterdir():
        total += _path_size(child)
    return total


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable size unit")


def _should_preserve_existing_directory(*, link_path: Path) -> bool:
    return link_path.name in PRESERVED_LOCAL_DIRECTORY_ALIASES


def _root_bindings(*, repo_root: Path) -> list[AliasBinding]:
    return [
        AliasBinding(repo_root / alias_name, repo_root / target_rel)
        for alias_name, target_rel in ROOT_ALIAS_LAYOUT.items()
    ]


def _package_bindings(*, repo_root: Path, package_dir: Path) -> list[AliasBinding]:
    package_name = package_dir.name
    return [
        AliasBinding(
            package_dir / alias_name,
            repo_root / Path(str(target_template).format(package=package_name)),
        )
        for alias_name, target_template in PACKAGE_ALIAS_LAYOUT.items()
    ]


def _repository_bindings(*, repo_root: Path, packages_dir: Path) -> list[AliasBinding]:
    bindings = _root_bindings(repo_root=repo_root)
    for package_dir in _discover_package_dirs(packages_dir=packages_dir):
        bindings.extend(
            _package_bindings(repo_root=repo_root, package_dir=package_dir)
        )
    return bindings


def _inspect_binding(binding: AliasBinding) -> AliasInspection:
    alias_path = binding.alias_path
    expected_target = _relative_target(
        link_path=alias_path,
        target_path=binding.target_path,
    )
    if alias_path.is_symlink():
        current_target = os.readlink(alias_path)
        if current_target == expected_target:
            return AliasInspection(binding=binding, state="governed")
        return AliasInspection(
            binding=binding,
            state="conflicting-symlink",
            detail=f"points to {current_target}",
        )
    if alias_path.is_dir():
        return AliasInspection(
            binding=binding,
            state="legacy-directory",
            size_bytes=_path_size(alias_path),
        )
    if alias_path.exists():
        return AliasInspection(
            binding=binding,
            state="conflicting-path",
            size_bytes=_path_size(alias_path),
        )
    return AliasInspection(binding=binding, state="missing")


def _inspect_bindings(bindings: Iterable[AliasBinding]) -> list[AliasInspection]:
    return [_inspect_binding(binding) for binding in bindings]


def _print_inspections(
    *, repo_root: Path, inspections: Iterable[AliasInspection]
) -> None:
    for inspection in inspections:
        binding = inspection.binding
        alias_display = binding.alias_path.relative_to(repo_root)
        target_display = binding.target_path.relative_to(repo_root)
        fields = [
            inspection.state,
            str(alias_display),
            f"target={target_display}",
        ]
        if inspection.size_bytes is not None:
            fields.append(f"size={_human_size(inspection.size_bytes)}")
            fields.append(f"bytes={inspection.size_bytes}")
        if inspection.detail:
            fields.append(inspection.detail)
        print("\t".join(fields))


def _target_is_empty_directory(target_path: Path) -> bool:
    return target_path.is_dir() and not target_path.is_symlink() and not any(
        target_path.iterdir()
    )


def _recovery_path(*, repo_root: Path, target_path: Path) -> Path:
    artifact_root = repo_root / "artifacts"
    try:
        target_rel = target_path.relative_to(artifact_root)
    except ValueError as exc:
        raise RuntimeError(
            f"canonical artifact destination is outside artifacts: {target_path}"
        ) from exc
    return artifact_root / "recovery" / "artifact-aliases" / target_rel


def _migrate_legacy_directories(
    *,
    repo_root: Path,
    inspections: list[AliasInspection],
) -> None:
    conflicts = [
        inspection
        for inspection in inspections
        if inspection.state in {"conflicting-path", "conflicting-symlink"}
    ]
    if conflicts:
        conflict_names = ", ".join(
            str(inspection.binding.alias_path.relative_to(repo_root))
            for inspection in conflicts
        )
        raise RuntimeError(
            f"artifact alias conflicts require inspection: {conflict_names}"
        )

    legacy = [
        inspection
        for inspection in inspections
        if inspection.state == "legacy-directory"
    ]
    occupied = [
        inspection
        for inspection in legacy
        if (
            inspection.binding.target_path.exists()
            or inspection.binding.target_path.is_symlink()
        )
        and not _target_is_empty_directory(inspection.binding.target_path)
    ]
    blocked_recovery_paths = [
        _recovery_path(
            repo_root=repo_root,
            target_path=inspection.binding.target_path,
        ).relative_to(repo_root)
        for inspection in occupied
        if _recovery_path(
            repo_root=repo_root,
            target_path=inspection.binding.target_path,
        ).exists()
        or _recovery_path(
            repo_root=repo_root,
            target_path=inspection.binding.target_path,
        ).is_symlink()
    ]
    if blocked_recovery_paths:
        joined = ", ".join(str(path) for path in blocked_recovery_paths)
        raise RuntimeError(
            "artifact recovery destinations already exist; no paths were moved: "
            f"{joined}"
        )

    for inspection in legacy:
        binding = inspection.binding
        binding.target_path.parent.mkdir(parents=True, exist_ok=True)
        recovery_path: Path | None = None
        if _target_is_empty_directory(binding.target_path):
            binding.target_path.rmdir()
        elif binding.target_path.exists() or binding.target_path.is_symlink():
            recovery_path = _recovery_path(
                repo_root=repo_root,
                target_path=binding.target_path,
            )
            recovery_path.parent.mkdir(parents=True, exist_ok=True)
            preserved_size = _path_size(binding.target_path)
            binding.target_path.replace(recovery_path)
            print(
                "preserved\t"
                f"{binding.target_path.relative_to(repo_root)}\t"
                f"recovery={recovery_path.relative_to(repo_root)}\t"
                f"size={_human_size(preserved_size)}"
            )
        try:
            binding.alias_path.replace(binding.target_path)
        except OSError:
            if recovery_path is not None:
                recovery_path.replace(binding.target_path)
            raise
        expected_target = _relative_target(
            link_path=binding.alias_path,
            target_path=binding.target_path,
        )
        try:
            binding.alias_path.symlink_to(expected_target)
        except OSError:
            binding.target_path.replace(binding.alias_path)
            if recovery_path is not None:
                recovery_path.replace(binding.target_path)
            raise
        print(
            "migrated\t"
            f"{binding.alias_path.relative_to(repo_root)}\t"
            f"target={binding.target_path.relative_to(repo_root)}\t"
            f"size={_human_size(inspection.size_bytes or 0)}"
        )


def _materialize_alias(*, link_path: Path, target_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.mkdir(parents=True, exist_ok=True)
    expected_target = _relative_target(link_path=link_path, target_path=target_path)

    if link_path.is_symlink():
        current_target = os.readlink(link_path)
        if current_target == expected_target:
            return
        link_path.unlink()
    elif link_path.exists():
        if link_path.is_dir() and _should_preserve_existing_directory(
            link_path=link_path
        ):
            return
        raise RuntimeError(
            f"refusing to replace non-symlink path '{link_path}' with alias to "
            f"'{expected_target}'"
        )

    link_path.symlink_to(expected_target)


def _materialize_root_aliases(*, repo_root: Path) -> None:
    for binding in _root_bindings(repo_root=repo_root):
        _materialize_alias(
            link_path=binding.alias_path,
            target_path=binding.target_path,
        )


def _materialize_package_aliases(*, repo_root: Path, package_dir: Path) -> None:
    for binding in _package_bindings(repo_root=repo_root, package_dir=package_dir):
        _materialize_alias(
            link_path=binding.alias_path,
            target_path=binding.target_path,
        )


def _discover_package_dirs(*, packages_dir: Path) -> list[Path]:
    if not packages_dir.is_dir():
        return []
    return sorted(
        child
        for child in packages_dir.iterdir()
        if child.is_dir() and (child / "pyproject.toml").is_file()
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize repository and package artifact alias symlinks."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    root_parser = subparsers.add_parser(
        "root",
        help="materialize root aliases and every package alias under packages/",
    )
    root_parser.add_argument("--repo-root", required=True, type=Path)
    root_parser.add_argument("--packages-dir", type=Path)

    package_parser = subparsers.add_parser(
        "package",
        help="materialize aliases for one package root",
    )
    package_parser.add_argument("--repo-root", required=True, type=Path)
    package_parser.add_argument("--package-dir", required=True, type=Path)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="report repository and package artifact alias state without changes",
    )
    inspect_parser.add_argument("--repo-root", required=True, type=Path)
    inspect_parser.add_argument("--packages-dir", type=Path)

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="move legacy directories into artifacts and materialize aliases",
    )
    migrate_parser.add_argument("--repo-root", required=True, type=Path)
    migrate_parser.add_argument("--packages-dir", type=Path)
    migrate_parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the reported moves; without this flag migration is inspection-only",
    )

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()

    if args.command == "root":
        packages_dir = (
            args.packages_dir.resolve()
            if args.packages_dir is not None
            else repo_root / "packages"
        )
        _materialize_root_aliases(repo_root=repo_root)
        for package_dir in _discover_package_dirs(packages_dir=packages_dir):
            _materialize_package_aliases(repo_root=repo_root, package_dir=package_dir)
        return 0

    if args.command == "package":
        _materialize_package_aliases(
            repo_root=repo_root,
            package_dir=args.package_dir.resolve(),
        )
        return 0

    if args.command in {"inspect", "migrate"}:
        packages_dir = (
            args.packages_dir.resolve()
            if args.packages_dir is not None
            else repo_root / "packages"
        )
        bindings = _repository_bindings(
            repo_root=repo_root,
            packages_dir=packages_dir,
        )
        inspections = _inspect_bindings(bindings)
        _print_inspections(repo_root=repo_root, inspections=inspections)
        if args.command == "migrate" and args.apply:
            _migrate_legacy_directories(
                repo_root=repo_root,
                inspections=inspections,
            )
            _materialize_root_aliases(repo_root=repo_root)
            for package_dir in _discover_package_dirs(packages_dir=packages_dir):
                _materialize_package_aliases(
                    repo_root=repo_root,
                    package_dir=package_dir,
                )
        elif args.command == "migrate":
            print("inspection-only\trun again with --apply to migrate")
        return 0

    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
