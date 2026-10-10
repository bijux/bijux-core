#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path.cwd()
MANIFEST_PATH = ROOT / ".github/standards/repo-config.manifest.json"

BASE_PROTECTED_PATHS = {
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug-report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/feature-request.yml",
    ".github/PULL_REQUEST_TEMPLATE/default.md",
    ".github/PULL_REQUEST_TEMPLATE/release-change.md",
    ".github/automation-identity.md",
    ".github/required-status-checks.md",
    ".github/rulesets/main-branch-protection.json",
    ".github/scripts/check_pinned_actions.py",
    ".github/scripts/check_protected_github_changes.py",
    ".github/scripts/wait_for_ci.py",
    ".github/workflows/bijux-std.yml",
    ".github/workflows/automerge-pr.yml",
    ".github/bijux-std-shared.sha256",
    ".github/release.env",
    ".github/dependabot.yml",
    ".github/labeler.yml",
    ".github/codecov.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/verify.yml",
    ".github/standards/bijux-std.sha",
}

ALLOWED_CONTROL_PATHS = {
    ".github/standards/bijux-std.sha",
    ".github/standards/repo-config.manifest.json",
    ".github/standards/workflow-inventory.json",
    ".github/scripts/build_repo_manifest.py",
    ".github/scripts/check_protected_github_changes.py",
    ".github/scripts/render_repo_configs.py",
    ".github/scripts/sync_github_standards.py",
    ".github/bijux-std-shared.sha256",
    ".bijux/shared/shared-dir-sha256.txt",
    "shared/shared-dir-sha256.txt",
}


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def workflow_paths_from_manifest() -> set[str]:
    manifest = load_manifest()
    entries = manifest.get("workflow_inventory", {}).get("managed_workflows", [])
    paths: set[str] = set()
    for entry in entries:
        source = entry.get("source")
        runtime = entry.get("consumer_runtime")
        if isinstance(source, str) and source:
            paths.add(source)
            if source.startswith("shared/"):
                paths.add(f".bijux/{source}")
        if isinstance(runtime, str) and runtime:
            paths.add(runtime)
    return paths


def protected_paths() -> set[str]:
    owned_package = {f".github/scripts/workflow_execution/{name}.py" for name in (
        "__init__", "source_loading", "schema", "yaml_io", "events", "refs", "dependency_prs",
        "publication", "canonical_sources", "source_authority", "verification",
    )}
    owned_package.update(path.relative_to(ROOT).as_posix()
                         for path in (ROOT / ".github/scripts/workflow_execution").glob("*.py"))
    snapshots = {f".github/standards/workflow-sources/{name}" for name in (
        "bijux-std.yml", "automerge-pr.yml", "source-manifest.json",
    )}
    return BASE_PROTECTED_PATHS.union(workflow_paths_from_manifest(), owned_package, snapshots,
                                     {".github/scripts/check_workflow_projection.py"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate protected .github changes")
    parser.add_argument("--changed-file", action="append", default=[], help="Changed file path (repeatable)")
    parser.add_argument("--changed-file-list", help="Path to newline-delimited changed files")
    args = parser.parse_args()

    changed = set(args.changed_file)
    if args.changed_file_list:
        changed.update(
            line.strip()
            for line in Path(args.changed_file_list).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    protected_changed = sorted(path for path in changed if path in protected_paths())
    if not protected_changed:
        return 0

    controls_changed = sorted(path for path in changed if path in ALLOWED_CONTROL_PATHS)
    if controls_changed:
        return 0

    print("Protected .github files changed without approved generator/sync controls:")
    for path in protected_changed:
        print(f"  - {path}")
    print("Required: include at least one control path change in the same PR:")
    for path in sorted(ALLOWED_CONTROL_PATHS):
        print(f"  - {path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
