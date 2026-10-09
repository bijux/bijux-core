"""Verify the source candidate and package identity used by a Python SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

_DESCRIBE = re.compile(r"v(\d+)\.(\d+)\.(\d+)-(\d+)-g([0-9a-f]{7,40})")
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.stdout.strip()


def _regular(root: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Invalid SBOM source path: {relative}")
    root = root.resolve(strict=True)
    candidate = root / path
    if not candidate.resolve(strict=True).is_relative_to(root):
        raise ValueError(f"SBOM source escapes candidate root: {relative}")
    member = candidate
    while member != root:
        if member.is_symlink():
            raise ValueError(f"SBOM source cannot use a symlink: {relative}")
        member = member.parent
    if not candidate.is_file():
        raise ValueError(f"SBOM source must be a regular file: {relative}")
    return candidate


def _snapshot(root: Path, snapshot: Path) -> dict[str, Any]:
    if not snapshot.is_file() or snapshot.is_symlink():
        raise ValueError("Missing regular SBOM source snapshot provenance")
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "bijux-sbom-snapshot-v1"
    ):
        raise ValueError("Invalid SBOM source snapshot schema")
    if (
        not isinstance(payload.get("source_repository"), str)
        or not payload["source_repository"].strip()
    ):
        raise ValueError("Missing SBOM source repository identity")
    commit = payload.get("source_commit")
    hashes = payload.get("input_sha256")
    if not isinstance(commit, str) or not _SHA.fullmatch(commit):
        raise ValueError("Invalid SBOM source commit")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("Missing SBOM source input digests")
    for relative, expected in hashes.items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or not _DIGEST.fullmatch(expected)
        ):
            raise ValueError("Invalid SBOM source input digest")
        actual = hashlib.sha256(_regular(root, relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"SBOM source input changed: {relative}")
    return payload


def _source_identity(root: Path, snapshot: Path) -> tuple[str, str, bool]:
    try:
        git_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        git_root = None
    if git_root == root.resolve():
        if _git(root, "status", "--porcelain", "--untracked-files=no"):
            raise ValueError("SBOM Git candidate has tracked changes")
        commit = _git(root, "rev-parse", "HEAD")
        describe = _git(
            root, "describe", "--dirty", "--tags", "--long", "--match", "v[0-9]*"
        )
        return commit, describe, True
    payload = _snapshot(root, snapshot)
    return payload["source_commit"], payload["source_describe"], False


def _version(commit: str, describe: str) -> str:
    match = _DESCRIBE.fullmatch(describe) if isinstance(describe, str) else None
    if not match or not commit.startswith(match.group(5)):
        raise ValueError("Unsupported or mismatched clean SBOM Git description")
    major, minor, patch, distance = (int(match.group(index)) for index in range(1, 5))
    if distance == 0:
        return f"{major}.{minor}.{patch}"
    return f"{major}.{minor}.{patch + 1}.dev{distance}"


def verify_candidate(
    root: Path,
    snapshot: Path,
    *,
    expected_sha: str,
    expected_version: str,
    required_inputs: tuple[str, ...],
) -> str:
    root = root.resolve(strict=True)
    if not _SHA.fullmatch(expected_sha) and not re.fullmatch(
        r"[0-9a-f]{7,39}", expected_sha
    ):
        raise ValueError("Invalid SBOM candidate SHA")
    if not required_inputs or len(set(required_inputs)) != len(required_inputs):
        raise ValueError("Missing or duplicate SBOM candidate inputs")
    commit, describe, live_git = _source_identity(root, snapshot)
    if not commit.startswith(expected_sha):
        raise ValueError("SBOM candidate SHA differs from source")
    version = _version(commit, describe)
    if version != expected_version:
        raise ValueError("SBOM version differs from natural source version")
    if live_git:
        for relative in required_inputs:
            path = _regular(root, relative)
            recorded = subprocess.run(
                ["git", "-C", str(root), "show", f"HEAD:{relative}"],
                check=True,
                capture_output=True,
                timeout=15,
            ).stdout
            if path.read_bytes() != recorded:
                raise ValueError(f"SBOM input differs from Git candidate: {relative}")
    else:
        hashes = _snapshot(root, snapshot)["input_sha256"]
        if not set(required_inputs).issubset(hashes):
            raise ValueError("SBOM snapshot omits required candidate inputs")
    return version


def identify(path: Path, package: str, version: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("components"), list):
        raise ValueError("Invalid CycloneDX SBOM document")
    if not package.strip():
        raise ValueError("Missing SBOM package identity")
    metadata = payload.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Invalid CycloneDX metadata")
    component = {"type": "library", "name": package}
    if version.strip() and version != "0.0.0":
        component["version"] = version
    metadata["component"] = component
    staged = path.with_suffix(path.suffix + ".new")
    staged.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    staged.replace(path)


def summarize(output: Path, sources: tuple[Path, ...]) -> None:
    if len(sources) != 2 or len(set(sources)) != 2:
        raise ValueError("A current production and development SBOM are required")
    lines = []
    for source in sources:
        if not source.is_file() or not source.stat().st_size:
            raise ValueError(f"Missing current-candidate SBOM: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(
            payload.get("components"), list
        ):
            raise ValueError(f"Invalid current-candidate SBOM: {source}")
        lines.append(f"{source.name}  components={len(payload['components'])}")
    staged = output.with_suffix(output.suffix + ".new")
    staged.write_text("\n".join(lines) + "\n", encoding="utf-8")
    staged.replace(output)
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    version = sub.add_parser("version")
    version.add_argument("--root", type=Path, required=True)
    version.add_argument("--snapshot", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--snapshot", type=Path, required=True)
    verify.add_argument("--sha", required=True)
    verify.add_argument("--version", required=True)
    for name in (
        "root-project",
        "lockfile",
        "make-source",
        "package-project",
        "helper-source",
    ):
        verify.add_argument(f"--{name}", required=True)
    verify.add_argument("--input", action="append", default=[])
    identify_parser = sub.add_parser("identify")
    identify_parser.add_argument("path", type=Path)
    identify_parser.add_argument("package")
    identify_parser.add_argument("version")
    summary = sub.add_parser("summary")
    summary.add_argument("output", type=Path)
    summary.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "version":
            commit, describe, _ = _source_identity(args.root, args.snapshot)
            print(_version(commit, describe))
        elif args.command == "verify":
            required = tuple(
                dict.fromkeys(
                    (
                        args.root_project,
                        args.lockfile,
                        args.make_source,
                        args.package_project,
                        args.helper_source,
                    )
                )
            )
            if len(args.input) != len(set(args.input)) or set(args.input) & set(
                required
            ):
                raise ValueError("Duplicate SBOM candidate input")
            verify_candidate(
                args.root,
                args.snapshot,
                expected_sha=args.sha,
                expected_version=args.version,
                required_inputs=required + tuple(args.input),
            )
        elif args.command == "identify":
            identify(args.path, args.package, args.version)
        else:
            summarize(args.output, tuple(args.sources))
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as error:
        parser.exit(2, f"SBOM provenance refusal: {error}\n")


if __name__ == "__main__":
    main()
