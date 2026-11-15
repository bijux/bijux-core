#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import copy
import os
import shlex
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

# Bootstrap only the adjacent finite package loader from its captured source bytes.
_POLICY_LOADER_PATH = Path(__file__).resolve().with_name("workflow_execution") / "source_loading.py"
_POLICY_LOADER_SOURCE = _POLICY_LOADER_PATH.read_bytes()
_POLICY_LOADER = ModuleType("bijux_workflow_source_loading")
_POLICY_LOADER.__file__ = str(_POLICY_LOADER_PATH)
exec(compile(_POLICY_LOADER_SOURCE, str(_POLICY_LOADER_PATH), "exec"), _POLICY_LOADER.__dict__)
WORKFLOW_EXECUTION = _POLICY_LOADER.load_package(_POLICY_LOADER_SOURCE)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_std_repo() -> Path:
    env_path = os.environ.get("BIJUX_STD_REPO")
    if env_path:
        candidate = Path(env_path).resolve()
        if (candidate / ".github/standards/workflow-inventory.json").exists():
            return candidate
        raise FileNotFoundError(f"BIJUX_STD_REPO does not contain workflow inventory: {candidate}")

    # Only self-resolve when the script is executed from the canonical bijux-std repo.
    if (
        SCRIPT_REPO_ROOT.name == "bijux-std"
        and (SCRIPT_REPO_ROOT / ".github/standards/workflow-inventory.json").exists()
    ):
        return SCRIPT_REPO_ROOT

    sibling = ROOT / "bijux-std"
    if (sibling / ".github/standards/workflow-inventory.json").exists():
        return sibling

    raise FileNotFoundError("Unable to resolve bijux-std repository root")


STD_REPO = resolve_std_repo()
WORKFLOW_INVENTORY_PATH = STD_REPO / ".github/standards/workflow-inventory.json"
MANAGED_REPOSITORIES = [
    "bijux-atlas",
    "bijux-canon",
    "bijux-core",
    "bijux-genomics",
    "bijux-iac",
    "bijux-masterclass",
    "bijux-ontology",
    "bijux-phylogenetics",
    "bijux-pollenomics",
    "bijux-proteomics",
    "bijux-ro-crate-node",
    "bijux-gnss",
    "bijux-std",
    "bijux.github.io",
]


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


def load_workflow_inventory() -> dict[str, Any]:
    inventory = json.loads(WORKFLOW_INVENTORY_PATH.read_text(encoding="utf-8"))
    if inventory.get("version") != 1:
        raise ValueError("Unsupported workflow inventory version")
    return inventory


def workflow_ids(inventory: dict[str, Any]) -> set[str]:
    return {entry["id"] for entry in inventory["managed_workflows"]}


def release_env_value(entries: list[dict], key: str, default: bool = False) -> bool:
    for entry in entries:
        if entry.get("key") == key:
            if entry.get("type") == "bool":
                return bool(entry.get("value"))
            break
    return default


def derive_workflow_allowlist(repo_name: str, release_env: list[dict], wrappers: dict, inventory: dict[str, Any], policy: dict | None = None) -> list[str]:
    known = workflow_ids(inventory)
    allow: set[str] = {"github-policy", "pr-approval-policy", "deploy-docs"}

    if policy and policy.get("dependency_pull_requests") == "notification-only":
        allow.add("dependency-notice")

    if release_env_value(release_env, "BIJUX_RELEASE_ENABLED"):
        allow.add("release-github")

    if release_env_value(release_env, "BIJUX_CRATES_RELEASE_ENABLED"):
        allow.add("release-crates")
    if release_env_value(release_env, "BIJUX_GHCR_RELEASE_ENABLED"):
        allow.add("release-ghcr")
    if release_env_value(release_env, "BIJUX_PYPI_ENABLED"):
        allow.add("release-pypi")
    if any(
        release_env_value(release_env, key)
        for key in (
            "BIJUX_RELEASE_ENABLED",
            "BIJUX_GHCR_RELEASE_ENABLED",
            "BIJUX_PYPI_ENABLED",
        )
    ):
        allow.add("release-artifacts")

    wrapper_uses_to_workflow_id = {
        "./.github/workflows/ci-package.yml": "ci-package",
        "./.github/workflows/reusable-ci-python-packages.yml": "reusable-ci-python-packages",
        "./.github/workflows/reusable-verify-python-packages.yml": "reusable-verify-python-packages",
        "./.github/workflows/reusable-ci-rust-stack.yml": "reusable-ci-rust-stack",
    }
    workflow_dependencies = {
        "ci-package": {"reusable-ci-python-packages"},
    }
    for wrapper in wrappers.values():
        jobs = wrapper.get("jobs", {}) if isinstance(wrapper, dict) else {}
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses")
            if not isinstance(uses, str):
                continue
            workflow_id = wrapper_uses_to_workflow_id.get(uses)
            if workflow_id:
                allow.add(workflow_id)
                allow.update(workflow_dependencies.get(workflow_id, set()))

    return sorted(workflow_id for workflow_id in allow if workflow_id in known)


def normalize_release_env_json_entry(key: str, value: Any) -> Any:
    if key != "BIJUX_PYPI_PACKAGE_MATRIX_JSON" or not isinstance(value, list):
        return value

    normalized_packages: list[Any] = []
    for item in value:
        if not isinstance(item, dict):
            normalized_packages.append(item)
            continue

        normalized_item = dict(item)
        if normalized_item.get("publish_auth") == "token":
            normalized_item.pop("publish_auth")
        normalized_packages.append(normalized_item)
    return normalized_packages


def parse_release_env(path: Path) -> list[dict]:
    entries: list[dict] = []
    if not path.exists():
        return entries

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        value = raw_value.strip()

        if value in {"true", "false"}:
            entries.append({"key": key, "type": "bool", "value": value == "true"})
            continue

        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            inner = value[1:-1]
            try:
                parsed_json = json.loads(inner)
            except json.JSONDecodeError:
                entries.append({"key": key, "type": "string", "value": inner})
            else:
                parsed_json = normalize_release_env_json_entry(key, parsed_json)
                entries.append({"key": key, "type": "json", "value": parsed_json})
            continue

        try:
            shell_parts = shlex.split(value, posix=True)
        except ValueError:
            parsed_value = value
        else:
            parsed_value = " ".join(shell_parts) if len(shell_parts) > 1 else (shell_parts[0] if shell_parts else "")

        entries.append({"key": key, "type": "string", "value": parsed_value})

    return entries


def parse_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None

    try:
        result = subprocess.run(
            [
                "ruby",
                "-ryaml",
                "-rjson",
                "-e",
                "puts JSON.generate(YAML.safe_load(File.read(ARGV[0]), aliases: false))",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ruby is required to parse YAML for manifest generation") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown parse error"
        raise RuntimeError(f"failed to parse YAML file {path}: {stderr}") from exc
    parsed = json.loads(result.stdout)
    return normalize_yaml_keys(parsed)


def normalize_yaml_keys(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = key
            if key == "true":
                normalized_key = "on"
            elif key == "false":
                normalized_key = "off"
            normalized[normalized_key] = normalize_yaml_keys(item)
        return normalized
    if isinstance(value, list):
        return [normalize_yaml_keys(item) for item in value]
    return value


def parse_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()



def node_workspace_profiles() -> dict[str, dict]:
    source = json.loads((STD_REPO / '.github/standards/node-workspaces.json').read_text())
    if (set(source) != {'version','repositories'} or type(source.get('version')) is not int
            or source['version'] != 1 or not isinstance(source.get('repositories'), list)):
        raise ValueError('Invalid canonical Node workspace registry')
    profiles = {}
    for entry in source['repositories']:
        if not isinstance(entry, dict) or entry.get('name') not in MANAGED_REPOSITORIES or entry['name'] in profiles:
            raise ValueError('Node workspace must identify one distinct governed repository')
        profiles[entry['name']] = copy.deepcopy(entry)
    WORKFLOW_EXECUTION.validate_manifest({'workflow_inventory':load_workflow_inventory(),
                                         'repositories':list(profiles.values())}, list(profiles))
    return profiles


def repository_profiles() -> dict[str, dict]:
    """Read reviewed capability records without adopting consumer-owned CI."""
    path = STD_REPO / ".github/standards/repository-profiles.json"
    if not path.exists():
        return {}
    source = json.loads(path.read_text(encoding="utf-8"))
    if (set(source) != {"version", "repositories"} or type(source.get("version")) is not int
            or source["version"] != 1 or not isinstance(source.get("repositories"), list)):
        raise ValueError("Invalid canonical repository profile registry")
    profiles = {}
    for entry in source["repositories"]:
        if not isinstance(entry, dict) or entry.get("name") not in MANAGED_REPOSITORIES or entry["name"] in profiles:
            raise ValueError("Repository profile must identify one distinct governed repository")
        profiles[entry["name"]] = copy.deepcopy(entry)
    WORKFLOW_EXECUTION.validate_manifest(
        {"workflow_inventory": load_workflow_inventory(), "repositories": list(profiles.values())},
        list(profiles),
    )
    return profiles


def reviewed_profiles() -> dict[str, dict]:
    profiles = node_workspace_profiles()
    additional = repository_profiles()
    if profiles.keys() & additional.keys():
        raise ValueError("Repository must belong to one canonical profile registry")
    return {**profiles, **additional}


def register_repository_profiles() -> None:
    """Register reviewed profiles while preserving unrelated repository declarations."""
    path = STD_REPO / ".github/standards/repo-config.manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    profiles = reviewed_profiles()
    manifest["repositories"] = [
        entry for entry in manifest["repositories"] if entry["name"] not in profiles
    ] + list(profiles.values())
    manifest["workflow_inventory"] = load_workflow_inventory()
    WORKFLOW_EXECUTION.validate_manifest(manifest, MANAGED_REPOSITORIES)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def register_node_workspaces() -> None:
    """Regenerate reviewed Node declarations without recapturing unrelated checkouts."""
    path = STD_REPO / '.github/standards/repo-config.manifest.json'
    manifest = json.loads(path.read_text())
    profiles = node_workspace_profiles()
    entries = [entry for entry in manifest['repositories'] if entry['name'] not in profiles]
    manifest['repositories'] = entries + list(profiles.values())
    manifest['workflow_inventory'] = load_workflow_inventory()
    WORKFLOW_EXECUTION.validate_manifest(manifest, MANAGED_REPOSITORIES)
    path.write_text(json.dumps(manifest, indent=2)+'\n')

def main() -> None:
    inventory = load_workflow_inventory()
    existing_path = STD_REPO / ".github/standards/repo-config.manifest.json"
    existing = json.loads(existing_path.read_text(encoding="utf-8")) if existing_path.exists() else {"repositories": []}
    # Reviewed policy is canonical configuration; consumer workflow bytes never select it.
    existing_entries = {entry["name"]: entry for entry in existing["repositories"]}
    existing_names = list(existing_entries)
    retained = WORKFLOW_EXECUTION.validate_manifest(existing, existing_names)
    for name, policy in retained.items():
        if policy is not None and name not in MANAGED_REPOSITORIES:
            raise ValueError(f"reviewed workflow policy belongs to unmanaged repository: {name}")
    WORKFLOW_EXECUTION.validate_inventory(inventory)
    manifest: dict = {"version": 2, "workflow_inventory": inventory, "repositories": []}

    profiles = reviewed_profiles()
    for repo_name in MANAGED_REPOSITORIES:
        if repo_name in profiles:
            manifest['repositories'].append(profiles[repo_name])
            continue
        repo_path = resolve_repository_checkout(repo_name)
        repo_entry: dict = {"name": repo_name}
        if retained.get(repo_name) is not None:
            repo_entry["workflow_execution_policy"] = retained[repo_name]
        checks = existing_entries.get(repo_name, {}).get("additional_required_status_checks")
        if checks is not None:
            repo_entry["additional_required_status_checks"] = checks
        release_env = parse_release_env(repo_path / ".github/release.env")
        repo_entry["release_env"] = release_env

        dependabot = parse_yaml(repo_path / ".github/dependabot.yml")
        if dependabot is not None:
            repo_entry["dependabot"] = dependabot

        wrappers: dict = {}
        ci_wrapper = parse_yaml(repo_path / ".github/workflows/ci.yml")
        if ci_wrapper is not None:
            wrappers["ci"] = ci_wrapper

        verify_wrapper = parse_yaml(repo_path / ".github/workflows/verify.yml")
        if verify_wrapper is not None:
            wrappers["verify"] = verify_wrapper

        if wrappers:
            repo_entry["workflow_wrappers"] = wrappers
        repo_entry["workflow_allowlist"] = derive_workflow_allowlist(repo_name, release_env, wrappers, inventory, retained.get(repo_name))

        pinned_sha = parse_text(repo_path / ".github/standards/bijux-std.sha")
        if pinned_sha:
            repo_entry["pinned_std_sha"] = pinned_sha

        manifest["repositories"].append(repo_entry)

    WORKFLOW_EXECUTION.validate_manifest(manifest, MANAGED_REPOSITORIES)
    out_path = STD_REPO / ".github/standards/repo-config.manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Capture canonical repository configuration")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--node-workspaces-only", action="store_true")
    mode.add_argument("--repository-profiles-only", action="store_true")
    args=parser.parse_args()
    if args.node_workspaces_only:
        register_node_workspaces()
    elif args.repository_profiles_only:
        register_repository_profiles()
    else:
        main()
