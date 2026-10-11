#!/usr/bin/env python3
"""Observe locked renderer source bytes for review; never create admission."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys

SOURCE_PATHS = (
    "shared/bijux-docs/tooling/security/renderer_fingerprints.py",
    "tests/bijux-docs/generated/requirements.lock.txt",
    "tests/bijux-docs/generated/build.py",
    "makes/bijux-docs.mk",
    ".github/workflows/bijux-std.yml",
    "shared/bijux-docs/tooling/security/runtime_fingerprints.py",
)
VOLATILE_METADATA = {"RECORD", "INSTALLER", "direct_url.json", "REQUESTED"}
PIN = re.compile(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)")


class ObservationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservationError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def regular(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), f"Regular file required: {path}")
    for parent in path.parents:
        require(not parent.is_symlink(), f"Symlink parent forbidden: {path}")
    data = path.read_bytes()
    require(path.read_bytes() == data, f"Input changed during capture: {path}")
    return data


def locked_packages(data: bytes) -> list[tuple[str, str]]:
    packages = {}
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        require(match is not None, "Renderer lock must contain exact unambiguous pins")
        name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        require(name not in packages, f"Duplicate renderer lock package: {name}")
        packages[name] = version
    require(bool(packages), "Renderer lock cannot be empty")
    return sorted(packages.items())


def distribution_records(distribution) -> list[dict]:
    """Hash installed package data/code and stable metadata, including native code.

    Python -m entry points use the package, not generated ../bin wrappers.
    Install records/cache paths are installation state rather than producer code.
    """
    records = []
    names = set()
    base = Path(distribution.locate_file("")).absolute()
    listed = distribution.files
    require(listed is not None, "Installed distribution must expose a file inventory")
    for file in listed:
        name = str(file)
        relative = PurePosixPath(name)
        if relative.suffix == ".pyc" or "__pycache__" in relative.parts:
            continue
        if ".." in relative.parts:
            require(relative.parts[:3] == ("..", "..", "..") and len(relative.parts) == 5
                    and relative.parts[3] == "bin", "Unknown distribution path escape")
            continue
        require(not relative.is_absolute() and "\\" not in name and bool(name)
                and name == relative.as_posix(), "Noncanonical distribution path")
        if relative.parent.name.endswith(".dist-info") and relative.name in VOLATILE_METADATA:
            continue
        require(name not in names, "Duplicate installed distribution record")
        names.add(name)
        path = Path(distribution.locate_file(file)).absolute()
        require(path == base / Path(name), "Installed distribution path escaped its root")
        data = regular(path)
        records.append({"path": name, "bytes": len(data), "sha256": sha(data)})
    require(bool(records), "Installed distribution has no producer files")
    return sorted(records, key=lambda record: record["path"])


def observe_packages(lock: bytes, lookup=importlib.metadata.distribution) -> list[dict]:
    packages = []
    for name, version in locked_packages(lock):
        try:
            distribution = lookup(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ObservationError(f"Locked renderer package is not installed: {name}") from error
        require(distribution.version == version, f"Installed renderer version differs: {name}")
        actual_name = re.sub(r"[-_.]+", "-", distribution.metadata["Name"]).lower()
        require(actual_name == name, f"Installed renderer package differs: {name}")
        records = distribution_records(distribution)
        packages.append({"name": name, "version": version, "files_count": len(records),
                         "files_sha256": sha(canonical(records)), "files": records})
    return packages


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def source_snapshot(root: Path) -> dict:
    require(Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root,
            "Select the repository root")
    require(not git(root, "status", "--porcelain", "--untracked-files=no"),
            "Tracked source must be clean before observation")
    source = {"sha": git(root, "rev-parse", "HEAD"),
              "tree": git(root, "rev-parse", "HEAD^{tree}"), "files": []}
    for name in SOURCE_PATHS:
        data = regular(root / name)
        committed = subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{name}"])
        require(data == committed, f"Source differs from committed tree: {name}")
        source["files"].append({"path": name, "sha256": sha(data)})
    return source


def output_path(root: Path, value: str) -> Path:
    raw = Path(value)
    require(not raw.is_absolute() and ".." not in raw.parts and str(raw) == value
            and raw.parts[:1] == ("artifacts",),
            "Select a report under repository root artifacts/")
    output = root / raw
    require(output.name not in {"", "."} and output != root / "artifacts", "Select a report file")
    for path in (output, *output.parents):
        require(not path.is_symlink(), "Symlink output forbidden")
        if path == root:
            break
    require(not output.exists(), "Preserve the existing observation; select a new output")
    return output


def runtime_snapshot(packages):
    path = Path(__file__).with_name("runtime_fingerprints.py")
    captured = regular(path)
    spec = importlib.util.spec_from_file_location("bijux_runtime_observation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(captured == regular(path), "Runtime observer source changed during load")
    return module.snapshot(packages)


def observe(root: Path) -> dict:
    before = source_snapshot(root)
    require(Path(__file__).absolute() == root / SOURCE_PATHS[0],
            "Invoke the committed repository observer")
    lock = regular(root / SOURCE_PATHS[1])
    packages = observe_packages(lock)
    runtime = runtime_snapshot(packages)
    # A second capture detects source, installed code, inventory and version races.
    require(packages == observe_packages(lock), "Installed renderer changed during observation")
    require(runtime == runtime_snapshot(packages), "Physical renderer runtime changed during observation")
    require(before == source_snapshot(root), "Source changed during renderer observation")
    return {"schema": 1, "scope": "observed-locked-renderer-source", "verification_only": True,
            "admission_created": False, "source": before, "lock_sha256": sha(lock),
            "platform": {"system": platform.system(), "machine": platform.machine(),
                         "python": platform.python_version(), "implementation": sys.implementation.name,
                         "cache_tag": sys.implementation.cache_tag},
            "packages": packages, "runtime": runtime,
            "hosted_context": {key: os.environ.get(key) for key in (
                "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                "RUNNER_OS", "ImageOS")},
            "limitations": ["Observed environment is not an accepted renderer profile.",
                            "Review exact hosted source and locked distributions before source admission.",
                            "Fixture renderer inventory does not admit absent consumer plugins or hooks."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        root = Path.cwd().resolve()
        output = output_path(root, args.output)
        report = observe(root)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Recheck confinement immediately before exclusive creation.
        output_path(root, args.output)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"scope": report["scope"], "admission_created": False,
                          "packages": len(report["packages"])}))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
