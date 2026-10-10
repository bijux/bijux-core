"""Admit an explicit standard candidate or independently fetched accepted GitHub source."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

OFFICIAL_ORIGINS = {"https://github.com/bijux/bijux-std.git", "git@github.com:bijux/bijux-std.git"}
PIN_PATH = ".github/standards/bijux-std.sha"


def git(source: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(source), *arguments], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def admit_source(source: Path, target: Path, repository: str, sha: str, *, candidate: bool = False) -> dict:
    source, target = source.resolve(), target.resolve()
    if source != Path(__file__).resolve().parents[3]:
        raise ValueError("workflow authority must use the explicitly selected source's own verifier")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("workflow source requires a full lowercase Git SHA")
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise ValueError("workflow source authority must be an exact repository root")
    if git(source, "rev-parse", "HEAD") != sha:
        raise ValueError("workflow source HEAD differs from requested full SHA")
    if candidate:
        if repository != "bijux-std" or source != target:
            raise ValueError("candidate source qualification is restricted to the owning bijux-std checkout")
        return {"mode": "candidate-only", "sha": sha, "dirty": bool(git(source, "status", "--porcelain", "--untracked-files=all"))}
    if Path(git(target, "rev-parse", "--show-toplevel")).resolve() != target:
        raise ValueError("workflow target must be an explicit product repository root")
    # Fetching must affect only the owning artifact cache, never the product checkout.
    cache = target / "artifacts"
    if cache.is_symlink() or source == target or not source.is_relative_to(cache):
        raise ValueError("accepted workflow source must reside in the owning artifacts cache")
    if source.is_relative_to(target / ".github"):
        raise ValueError("accepted workflow source must not be product managed content")
    origin = git(source, "remote", "get-url", "origin")
    if origin not in OFFICIAL_ORIGINS:
        raise ValueError("accepted workflow source requires the official bijux-std GitHub origin")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("accepted workflow source has modified or untracked inputs")
    pin = target / PIN_PATH
    git(target, "ls-files", "--error-unmatch", PIN_PATH)
    if pin.is_symlink() or pin.read_text().strip() != sha:
        raise ValueError("accepted workflow source differs from the product full source pin")
    environment = os.environ.copy()
    environment.pop("BIJUX_STD_ALLOW_LOCAL_SOURCE", None)
    environment["BIJUX_STD_GIT_URL"] = origin
    try:
        subprocess.run(["bash", str(source / "shared/bijux-checks/scripts/verify-accepted-source.sh"), str(source), sha],
                       env=environment, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"independent accepted-source verification failed: {error.stderr.strip()}") from error
    if pin.read_text().strip() != sha:
        raise ValueError("product source pin changed during independent source verification")
    return {"mode": "accepted-GitHub-source", "sha": sha, "origin": origin}
