#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_std_repo() -> Path:
    env_path = os.environ.get("BIJUX_STD_REPO")
    if env_path:
        candidate = Path(env_path).resolve()
        if (candidate / ".github/standards/repo-config.manifest.json").exists():
            return candidate
        raise FileNotFoundError(f"BIJUX_STD_REPO does not contain standards manifest: {candidate}")

    # Only self-resolve when the script is executed from the canonical bijux-std repo.
    if (
        SCRIPT_REPO_ROOT.name == "bijux-std"
        and (SCRIPT_REPO_ROOT / ".github/standards/repo-config.manifest.json").exists()
    ):
        return SCRIPT_REPO_ROOT

    sibling = ROOT / "bijux-std"
    if (sibling / ".github/standards/repo-config.manifest.json").exists():
        return sibling

    raise FileNotFoundError("Unable to resolve bijux-std repository root")


STD_REPO = resolve_std_repo()
PIN_PATH = ".github/standards/bijux-std.sha"
MANIFEST_PATH = STD_REPO / ".github/standards/repo-config.manifest.json"

DEFAULT_REPOS = [
    "bijux-atlas",
    "bijux-canon",
    "bijux-core",
    "bijux-genomics",
    "bijux-iac",
    "bijux-masterclass",
    "bijux-phylogenetics",
    "bijux-pollenomics",
    "bijux-proteomics",
    "bijux-gnss",
    "bijux.github.io",
]

BASE_FILE_MAPPINGS: list[tuple[str, str]] = [
    (".github/CODEOWNERS", ".github/CODEOWNERS"),
    (".github/ISSUE_TEMPLATE/bug-report.yml", ".github/ISSUE_TEMPLATE/bug-report.yml"),
    (".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE/config.yml"),
    (".github/ISSUE_TEMPLATE/feature-request.yml", ".github/ISSUE_TEMPLATE/feature-request.yml"),
    (".github/PULL_REQUEST_TEMPLATE/default.md", ".github/PULL_REQUEST_TEMPLATE/default.md"),
    (".github/PULL_REQUEST_TEMPLATE/release-change.md", ".github/PULL_REQUEST_TEMPLATE/release-change.md"),
    (".github/automation-identity.md", ".github/automation-identity.md"),
    (".github/required-status-checks.md", ".github/required-status-checks.md"),
    (".github/rulesets/main-branch-protection.json", ".github/rulesets/main-branch-protection.json"),
    (".github/scripts/build_repo_manifest.py", ".github/scripts/build_repo_manifest.py"),
    (".github/scripts/check_pinned_actions.py", ".github/scripts/check_pinned_actions.py"),
    (".github/scripts/check_protected_github_changes.py", ".github/scripts/check_protected_github_changes.py"),
    (".github/scripts/check_workflow_prerequisites.py", ".github/scripts/check_workflow_prerequisites.py"),
    (".github/scripts/render_repo_configs.py", ".github/scripts/render_repo_configs.py"),
    (".github/scripts/sync_github_standards.py", ".github/scripts/sync_github_standards.py"),
    (".github/scripts/wait_for_ci.py", ".github/scripts/wait_for_ci.py"),
    (".github/standards/workflow-inventory.json", ".github/standards/workflow-inventory.json"),
    (".github/standards/repo-config.manifest.json", ".github/standards/repo-config.manifest.json"),
    (".github/workflows/bijux-std.yml", ".github/workflows/bijux-std.yml"),
    (".github/workflows/automerge-pr.yml", ".github/workflows/automerge-pr.yml"),
    (".github/bijux-std-shared.sha256", ".github/bijux-std-shared.sha256"),
]

LEGACY_MANAGED_RUNTIME_PATHS = {
    ".github/workflows/build-release-artifacts.yml",
    ".github/workflows/release-artifacts.yml",
}

LEGACY_MANAGED_SHARED_PATHS = {
    ".bijux/shared/bijux-gh/workflows/build-release-artifacts.yml",
    ".bijux/shared/bijux-gh/workflows/release-artifacts.yml",
}


def repository_checkout_variable(repo_name: str) -> str:
    suffix = "".join(character.upper() if character.isalnum() else "_" for character in repo_name)
    return f"BIJUX_REPOSITORY_PATH_{suffix}"


def resolve_repository_checkout(repo_name: str) -> Path:
    variable = repository_checkout_variable(repo_name)
    configured_path = os.environ.get(variable)
    repo_path = Path(configured_path).expanduser().resolve() if configured_path else ROOT / repo_name
    if not repo_path.is_dir():
        raise FileNotFoundError(
            f"Repository checkout for '{repo_name}' not found at {repo_path}. "
            f"Set {variable} to its checkout path."
        )
    return repo_path


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def verify_shared_checksums(repo_dir: Path) -> None:
    checksum_file = repo_dir / ".github/bijux-std-shared.sha256"
    if not checksum_file.exists():
        raise FileNotFoundError(f"Missing checksum file: {checksum_file}")

    failures: list[str] = []
    for raw_line in checksum_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            failures.append(f"Malformed checksum line: {raw_line}")
            continue
        expected, relative_path = parts
        path = repo_dir / relative_path
        if not path.exists():
            failures.append(f"Missing managed file: {relative_path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            failures.append(f"Checksum mismatch: {relative_path}")

    if failures:
        details = "\n".join(f"  - {item}" for item in failures)
        raise RuntimeError(
            "Managed shared checksums verification failed:\n"
            f"{details}"
        )


def refresh_shared_checksums(repo_dir: Path) -> None:
    """Rebind managed checksums after repository-specific rendering."""
    checksum_file = repo_dir / ".github/bijux-std-shared.sha256"
    if not checksum_file.exists():
        raise FileNotFoundError(f"Missing checksum file: {checksum_file}")

    refreshed: list[str] = []
    for raw_line in checksum_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Malformed checksum line: {raw_line}")
        relative_path = parts[1]
        path = repo_dir / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"Missing managed file: {relative_path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        refreshed.append(f"{digest}  {relative_path}")
    checksum_file.write_text("\n".join(refreshed) + "\n", encoding="utf-8")


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def find_repo_config(manifest: dict[str, Any], repo_name: str) -> dict[str, Any]:
    for repo in manifest["repositories"]:
        if repo["name"] == repo_name:
            return repo
    raise KeyError(f"Repository '{repo_name}' not found in manifest")


def inventory_entries(manifest: dict[str, Any]) -> list[dict[str, str]]:
    return manifest.get("workflow_inventory", {}).get("managed_workflows", [])


def copy_file_mapping(source_relative: str, destination_relative: str, repo_dir: Path) -> None:
    source = STD_REPO / source_relative
    destination = repo_dir / destination_relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def copy_repo_files(target_repo: str, repo_config: dict[str, Any], manifest: dict[str, Any]) -> None:
    repo_dir = resolve_repository_checkout(target_repo)
    for source_relative, destination_relative in BASE_FILE_MAPPINGS:
        copy_file_mapping(source_relative, destination_relative, repo_dir)

    allowlist = set(repo_config.get("workflow_allowlist", []))
    managed_runtime_paths: dict[str, str] = {}
    managed_shared_paths: set[str] = set()
    for workflow in inventory_entries(manifest):
        workflow_id = workflow["id"]
        source_relative = workflow["source"]
        shared_destination = f".bijux/{source_relative}"
        runtime_destination = workflow["consumer_runtime"]

        copy_file_mapping(source_relative, shared_destination, repo_dir)
        managed_shared_paths.add(shared_destination)
        managed_runtime_paths[runtime_destination] = workflow_id
        if workflow_id in allowlist:
            copy_file_mapping(source_relative, runtime_destination, repo_dir)

    for runtime_path, workflow_id in sorted(managed_runtime_paths.items()):
        if workflow_id in allowlist:
            continue
        path = repo_dir / runtime_path
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    for runtime_path in sorted(LEGACY_MANAGED_RUNTIME_PATHS):
        if runtime_path in managed_runtime_paths:
            continue
        path = repo_dir / runtime_path
        if path.exists():
            path.unlink()

    for shared_path in sorted(LEGACY_MANAGED_SHARED_PATHS):
        if shared_path in managed_shared_paths:
            continue
        path = repo_dir / shared_path
        if path.exists():
            path.unlink()

    if repo_dir.name != "bijux-std" and (repo_dir / ".bijux/shared").exists():
        for legacy_name in ("bijux-docs", "bijux-makes-py", "bijux-checks", "bijux-gh"):
            legacy_shared_path = repo_dir / "shared" / legacy_name
            if legacy_shared_path.exists():
                shutil.rmtree(legacy_shared_path)
        legacy_shared_root = repo_dir / "shared"
        if legacy_shared_root.exists() and not any(legacy_shared_root.iterdir()):
            legacy_shared_root.rmdir()


def sync_repo_files(target_repo: str, manifest: dict[str, Any]) -> None:
    repo_config = find_repo_config(manifest, target_repo)
    copy_repo_files(target_repo, repo_config, manifest)


def copy_shared_files(target_repo: str) -> None:
    manifest = load_manifest()
    sync_repo_files(target_repo, manifest)


def write_std_pin(repo_name: str, std_sha: str) -> None:
    pin_file = resolve_repository_checkout(repo_name) / PIN_PATH
    pin_file.parent.mkdir(parents=True, exist_ok=True)
    pin_file.write_text(f"{std_sha}\n", encoding="utf-8")


def has_changes(repo_name: str) -> bool:
    status = run(["git", "status", "--short"], cwd=resolve_repository_checkout(repo_name))
    return bool(status)


def stage_managed_paths(repo_dir: Path) -> None:
    paths: list[str] = [".github"]
    if (repo_dir / ".bijux/shared").exists():
        paths.append(".bijux/shared")
    if (repo_dir / "shared").exists():
        paths.append("shared")
    run(["git", "add", *paths], cwd=repo_dir)


def ensure_branch(repo_dir: Path, branch_name: str) -> None:
    existing = run(["git", "branch", "--list", branch_name], cwd=repo_dir)
    if existing:
        run(["git", "checkout", branch_name], cwd=repo_dir)
    else:
        run(["git", "checkout", "-b", branch_name], cwd=repo_dir)


def create_pr(repo_dir: Path, args: argparse.Namespace, branch_name: str) -> dict | None:
    if not args.open_pr:
        return None

    run(["git", "push", "-u", "origin", branch_name], cwd=repo_dir)
    pr_json = run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            args.base_branch,
            "--head",
            branch_name,
            "--title",
            args.pr_title,
            "--body",
            args.pr_body,
            "--json",
            "number,url",
        ],
        cwd=repo_dir,
    )
    return json.loads(pr_json)


def observe_merge(repo_dir: Path, pr_number: int) -> dict:
    info = json.loads(
        run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "number,url,state,mergeStateStatus,isDraft",
            ],
            cwd=repo_dir,
        )
    )
    if info.get("state") == "MERGED":
        return {"status": "merged", "details": info}
    if info.get("state") == "CLOSED":
        return {"status": "closed", "details": info}
    return {"status": "waiting_external", "details": info}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync shared .github standards into consumer repositories")
    parser.add_argument("--repo", action="append", default=[], help="Repository name (repeatable)")
    parser.add_argument("--create-branch", action="store_true", help="Create per-repo branch before commit")
    parser.add_argument("--open-pr", action="store_true", help="Push and open PR for each changed repository")
    parser.add_argument("--track-merge-status", action="store_true", help="Observe each opened PR once")
    parser.add_argument("--advance-std-sha", action="store_true", help="Write current bijux-std commit SHA pin into each target repo")
    parser.add_argument("--base-branch", default="main", help="PR base branch")
    parser.add_argument("--branch-prefix", default="chore/github-standards-sync", help="Branch prefix")
    parser.add_argument("--commit-message", default="chore(github): sync shared standards and generated config", help="Commit message")
    parser.add_argument("--pr-title", default="chore(github): sync shared standards and generated config", help="PR title")
    parser.add_argument("--pr-body", default="Synchronize shared .github templates from bijux-std and regenerate repository-local config files.", help="PR body")
    args = parser.parse_args()

    repos = args.repo or DEFAULT_REPOS
    std_sha = run(["git", "rev-parse", "HEAD"], cwd=STD_REPO)

    render_script = STD_REPO / ".github/scripts/render_repo_configs.py"
    subprocess.run(["python3", str(render_script), "--repo", "bijux-std"], check=True)
    refresh_shared_checksums(STD_REPO)
    verify_shared_checksums(STD_REPO)

    pr_records: list[tuple[str, int, str]] = []
    changed_repos: list[str] = []

    for repo in repos:
        repo_dir = resolve_repository_checkout(repo)
        copy_shared_files(repo)
        subprocess.run(["python3", str(render_script), "--repo", repo], check=True)
        refresh_shared_checksums(repo_dir)

        if args.advance_std_sha:
            write_std_pin(repo, std_sha)

        verify_shared_checksums(repo_dir)

        if not has_changes(repo):
            continue

        changed_repos.append(repo)
        branch_name = f"{args.branch_prefix}/{repo}"
        if args.create_branch:
            ensure_branch(repo_dir, branch_name)

        stage_managed_paths(repo_dir)
        run(["git", "commit", "-m", args.commit_message], cwd=repo_dir)

        pr_info = create_pr(repo_dir, args, branch_name)
        if pr_info:
            pr_records.append((repo, pr_info["number"], pr_info["url"]))

    print("changed_repositories:")
    for repo in changed_repos:
        print(f"  - {repo}")

    if args.track_merge_status and pr_records:
        print("merge_status:")
        for repo, pr_number, pr_url in pr_records:
            result = observe_merge(resolve_repository_checkout(repo), pr_number)
            print(f"  - {repo}: {result['status']} ({pr_url})")


if __name__ == "__main__":
    main()
