#!/usr/bin/env python3
"""Verify product governance against its independently fetched accepted standard."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


OFFICIAL_ORIGIN = "https://github.com/bijux/bijux-std.git"
OFFICIAL_ORIGINS = {OFFICIAL_ORIGIN, "git@github.com:bijux/bijux-std.git"}
PIN_PATH = ".github/standards/bijux-std.sha"


def git(root: Path, *arguments: str) -> str:
    """Run a Git operation scoped to the explicitly selected checkout."""
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def accepted_source(target: Path, sha: str) -> Path:
    """Admit an exact official source inside the owning artifact cache."""
    artifacts = target / "artifacts"
    if artifacts.is_symlink():
        raise ValueError("the owning artifacts cache must not be a symlink")
    supplied = os.environ.get("BIJUX_STD_ROOT")
    source = Path(supplied).resolve() if supplied else (artifacts / "standards/accepted-source" / sha).resolve()
    if source == target or not source.is_relative_to(artifacts):
        raise ValueError("accepted governance source must reside in the owning artifacts cache")
    if not supplied and not source.exists():
        source.mkdir(parents=True)
        git(source, "init", "--quiet")
        git(source, "remote", "add", "origin", OFFICIAL_ORIGIN)
        git(source, "fetch", "--quiet", "--depth", "1", "origin", sha)
        git(source, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("accepted governance source must be an exact repository root")
    if git(source, "remote", "get-url", "origin") not in OFFICIAL_ORIGINS:
        raise ValueError("accepted governance source requires the official GitHub origin")
    if git(source, "rev-parse", "HEAD") != sha:
        raise ValueError("accepted governance source HEAD differs from the tracked full pin")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("accepted governance source has modified or untracked inputs")
    git(source, "fetch", "--quiet", "--depth", "1", "origin", sha)
    if git(source, "rev-parse", "FETCH_HEAD^{commit}") != sha:
        raise ValueError("independently fetched governance source differs from the tracked pin")
    git(source, "diff", "--quiet", sha, "--")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("accepted governance source changed during admission")
    return source


def verify(target: Path, repository: str) -> None:
    """Delegate read-only projection to the admitted source's own verifier."""
    target = target.resolve()
    if Path(git(target, "rev-parse", "--show-toplevel")).resolve() != target:
        raise ValueError("governance target must be an explicit product repository root")
    pin = target / PIN_PATH
    if pin.is_symlink() or not pin.is_file():
        raise ValueError("governance verification requires a regular tracked source pin")
    git(target, "ls-files", "--error-unmatch", PIN_PATH)
    sha = pin.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("governance verification requires a full lowercase source SHA")
    source = accepted_source(target, sha)
    verifier = source / ".github/scripts/check_workflow_projection.py"
    if not verifier.is_file():
        raise ValueError("accepted source has no canonical governance projection verifier")
    environment = os.environ.copy()
    environment.pop("BIJUX_STD_ALLOW_LOCAL_SOURCE", None)
    environment["BIJUX_STD_GIT_URL"] = git(source, "remote", "get-url", "origin")
    subprocess.run(
        [sys.executable, str(verifier), "--target", str(target), "--repo", repository, "--source-sha", sha],
        env=environment,
        check=True,
    )
    if pin.read_text(encoding="utf-8").strip() != sha:
        raise ValueError("product source pin changed during governance verification")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    arguments = parser.parse_args()
    verify(arguments.target, arguments.repo)


if __name__ == "__main__":
    main()
