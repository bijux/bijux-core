"""Capture the finite canonical inputs required for repository governance projection."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from .schema import validate_inventory
from .source_loading import MODULE_ORDER, load_script

SNAPSHOT_DIRECTORY = ".github/standards/workflow-sources"
BASE_WORKFLOWS = ("bijux-std", "automerge-pr")


def read_owned(root: Path, relative: str) -> bytes:
    """Reject path aliases rather than silently expanding the source authority."""
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError(f"canonical source path must be bounded: {relative}")
    root = root.resolve()
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"canonical source path must not be a symlink: {relative}")
    return current.read_bytes()


def owning_scripts(source_root: Path):
    """Load current owning generator bytes with explicit source selection restored afterwards."""
    source_root = source_root.resolve()
    previous = os.environ.get("BIJUX_STD_REPO")
    os.environ["BIJUX_STD_REPO"] = str(source_root)
    try:
        sync = load_script(source_root / ".github/scripts/sync_github_standards.py", "bijux_canonical_sync")
        renderer = load_script(source_root / ".github/scripts/render_repo_configs.py", "bijux_canonical_renderer")
    finally:
        if previous is None:
            os.environ.pop("BIJUX_STD_REPO", None)
        else:
            os.environ["BIJUX_STD_REPO"] = previous
    return sync, renderer


def capture_sources(source_root: Path) -> dict[str, bytes]:
    """Derive snapshot bytes; this function neither writes nor certifies acceptance."""
    sync, _ = owning_scripts(source_root)
    manifest_path = ".github/standards/repo-config.manifest.json"
    manifest = json.loads(read_owned(source_root, manifest_path))
    validate_inventory(manifest["workflow_inventory"])
    standalone = json.loads(read_owned(source_root, ".github/standards/workflow-inventory.json"))
    if standalone != manifest["workflow_inventory"]:
        raise ValueError("canonical workflow inventory differs from manifest inventory")
    paths = {source for source, _ in sync.BASE_FILE_MAPPINGS
             if not source.startswith(SNAPSHOT_DIRECTORY + "/")
             and source != ".github/bijux-std-shared.sha256"}
    paths.update(entry["source"] for entry in manifest["workflow_inventory"]["managed_workflows"])
    paths.update(f".github/scripts/workflow_execution/{name}.py" for name in (*MODULE_ORDER, "__init__"))
    paths.update({manifest_path, ".github/scripts/check_workflow_projection.py",
                  "shared/bijux-checks/scripts/verify-accepted-source.sh",
                  "shared/bijux-gh/rulesets/main-branch-protection.json",
                  "shared/bijux-gh/required-status-checks.md"})
    inputs = {relative: read_owned(source_root, relative) for relative in sorted(paths)}
    record = {"schema": 1, "inputs": {relative: hashlib.sha256(body).hexdigest()
                                       for relative, body in inputs.items()}}
    result = {f"{SNAPSHOT_DIRECTORY}/{name}.yml": inputs[f".github/workflows/{name}.yml"]
              for name in BASE_WORKFLOWS}
    result[f"{SNAPSHOT_DIRECTORY}/source-manifest.json"] = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    return result


def validate_source_snapshots(source_root: Path) -> None:
    for relative, expected in capture_sources(source_root).items():
        if read_owned(source_root, relative) != expected:
            raise ValueError(f"stale canonical source snapshot: {relative}")
