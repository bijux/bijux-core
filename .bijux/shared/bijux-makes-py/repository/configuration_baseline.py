#!/usr/bin/env python3
"""Validate repository-owned Python configuration against the shared baseline."""

from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Iterable


DEPENDENCY_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)(?:\[[^]]+\])?(?P<constraints>[^;]*)(?:;.*)?$"
)
CLAUSE_RE = re.compile(r"^(?P<operator>>=|>|<=|<|==)(?P<version>[0-9]+(?:\.[0-9]+)*)$")


@dataclass(frozen=True, order=True)
class Version:
    """Comparable numeric version used by configuration envelopes."""

    parts: tuple[int, ...]

    @classmethod
    def parse(cls, value: str) -> Version:
        parts = tuple(int(part) for part in value.split("."))
        return cls(parts + (0,) * (4 - len(parts)))


@dataclass(frozen=True)
class Envelope:
    """Inclusive lower and exclusive upper compatibility boundary."""

    lower: Version
    upper: Version


def normalize_name(value: str) -> str:
    """Normalize a Python distribution name."""
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_envelope(value: str, *, field: str) -> Envelope:
    """Parse a bounded compatibility range."""
    lower: Version | None = None
    upper: Version | None = None
    for raw_clause in value.replace(" ", "").split(","):
        match = CLAUSE_RE.fullmatch(raw_clause)
        if match is None:
            continue
        version = Version.parse(match.group("version"))
        if match.group("operator") == ">=":
            lower = version
        elif match.group("operator") == "<":
            upper = version
    if lower is None or upper is None:
        raise ValueError(f"{field} must declare a >= lower bound and < upper bound")
    return Envelope(lower=lower, upper=upper)


def iter_dependency_strings(value: Any) -> Iterable[str]:
    """Yield dependency declarations from nested TOML collections."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_dependency_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_dependency_strings(item)


def iter_pyprojects(repo_root: Path) -> Iterable[Path]:
    """Yield project manifests without traversing generated or environment trees."""
    excluded = {
        ".git",
        ".venv",
        ".tox",
        "artifacts",
        "build",
        "dist",
        "node_modules",
        "site",
    }
    for current_root, directories, files in os.walk(repo_root):
        directories[:] = [name for name in directories if name not in excluded]
        if "pyproject.toml" in files:
            yield Path(current_root) / "pyproject.toml"


class BaselineValidator:
    """Validate one repository without modifying repository-owned files."""

    def __init__(self, repo_root: Path, baseline_path: Path) -> None:
        self.repo_root = repo_root.resolve()
        with baseline_path.open("rb") as handle:
            self.baseline = tomllib.load(handle)
        self.errors: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def validate_python_projects(self) -> None:
        expected = self.baseline["python"]["requires"]
        baseline_tools = {
            normalize_name(name): parse_envelope(specifier, field=f"baseline tool {name}")
            for name, specifier in self.baseline["tools"].items()
            if name not in {"tox", "tox-gh-actions"}
        }
        for path in sorted(iter_pyprojects(self.repo_root)):
            with path.open("rb") as handle:
                document = tomllib.load(handle)
            project = document.get("project")
            if not isinstance(project, dict):
                continue
            relative = path.relative_to(self.repo_root)
            actual = project.get("requires-python")
            self.require(
                actual == expected,
                f"{relative}: project.requires-python must be {expected!r}, got {actual!r}",
            )
            for dependency in iter_dependency_strings(project):
                match = DEPENDENCY_RE.fullmatch(dependency.strip())
                if match is None:
                    continue
                name = normalize_name(match.group("name"))
                if name not in baseline_tools:
                    continue
                constraints = match.group("constraints").strip()
                try:
                    declared = parse_envelope(constraints, field=f"{relative}: {name}")
                except ValueError as exc:
                    self.errors.append(str(exc))
                    continue
                allowed = baseline_tools[name]
                self.require(
                    declared.lower >= allowed.lower and declared.upper <= allowed.upper,
                    f"{relative}: {name} range {constraints!r} falls outside the shared compatibility envelope",
                )

    def validate_openapi_tooling(self) -> None:
        path = self.repo_root / "configs/package.json"
        if not path.is_file():
            return
        document = json.loads(path.read_text(encoding="utf-8"))
        policy = self.baseline["openapi"]
        dependencies = document.get("devDependencies") or {}
        self.require(
            document.get("name") == policy["package-name"],
            f"configs/package.json: name must be {policy['package-name']!r}",
        )
        self.require(
            (document.get("engines") or {}).get("node") == policy["node"],
            f"configs/package.json: engines.node must be {policy['node']!r}",
        )
        self.require(
            dependencies.get("@openapitools/openapi-generator-cli") == policy["generator"],
            "configs/package.json: OpenAPI Generator must match the shared policy",
        )
        self.require(
            dependencies.get("@redocly/cli") == policy["redocly"],
            "configs/package.json: Redocly must match the shared policy",
        )

    def validate_tox(self) -> None:
        path = self.repo_root / "tox.ini"
        if not path.is_file():
            return
        config = configparser.ConfigParser(interpolation=None)
        config.read(path, encoding="utf-8")
        policy = self.baseline["tox"]
        tox_section = config["tox"]
        testenv = config["testenv"]
        self.require(
            tox_section.get("minversion") == policy["minversion"],
            f"tox.ini: tox.minversion must be {policy['minversion']}",
        )
        self.require(
            tox_section.getboolean("isolated_build", fallback=False),
            "tox.ini: tox.isolated_build must be true",
        )
        self.require(
            tox_section.getboolean("skip_missing_interpreters", fallback=False),
            "tox.ini: tox.skip_missing_interpreters must be true",
        )
        self.require(
            tox_section.get("toxworkdir") == policy["workdir"],
            f"tox.ini: tox.toxworkdir must be {policy['workdir']}",
        )
        self.require(
            testenv.get("basepython") == policy["basepython"],
            f"tox.ini: testenv.basepython must be {policy['basepython']}",
        )
        self.require(testenv.get("package") == "skip", "tox.ini: testenv.package must be skip")
        self.require(
            testenv.getboolean("skip_install", fallback=False),
            "tox.ini: testenv.skip_install must be true",
        )
        setenv = testenv.get("setenv", "")
        for variable in policy["required-setenv"]:
            self.require(
                re.search(rf"(?m)^\s*{re.escape(variable)}\s*=", setenv) is not None,
                f"tox.ini: testenv.setenv must define {variable}",
            )
        declared_requirements = {}
        for dependency in tox_section.get("requires", "").splitlines():
            match = DEPENDENCY_RE.fullmatch(dependency.strip())
            if match:
                declared_requirements[normalize_name(match.group("name"))] = match.group(
                    "constraints"
                ).strip()
        for name in ("tox", "tox-gh-actions"):
            expected = self.baseline["tools"][name]
            actual = declared_requirements.get(name)
            self.require(
                actual == expected,
                f"tox.ini: {name} requirement must be {expected!r}, got {actual!r}",
            )

    def validate(self) -> list[str]:
        self.validate_python_projects()
        self.validate_openapi_tooling()
        self.validate_tox()
        return self.errors


def default_baseline_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config/python-baseline.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=default_baseline_path())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validator = BaselineValidator(args.repo_root, args.baseline)
    errors = validator.validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Python configuration baseline validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
