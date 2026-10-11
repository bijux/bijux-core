"""Closed repository-owned execution policy for canonical workflow projection."""
from __future__ import annotations

import copy
from pathlib import PurePosixPath
from typing import Any, Literal, TypedDict


class PublicationEntrypoint(TypedDict, total=False):
    mode: Literal["canonical", "manual-only"]
    refs: Literal["canonical", "main-only"]
    controller: Literal["iac"]


class WorkflowExecutionPolicy(TypedDict, total=False):
    schema: int
    automatic_runs: Literal["canonical", "repository-policy-only"]
    dependency_pull_requests: Literal["canonical", "skip-managed-jobs"]
    publication_entrypoints: dict[str, PublicationEntrypoint]


PUBLICATION_ENTRYPOINTS = frozenset(
    {"deploy-docs", "release-github", "release-ghcr", "release-crates", "release-pypi"}
)


def require_closed_object(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with string keys")
    unknown = set(value) - keys
    if unknown:
        raise ValueError(f"{label} has unknown fields: {sorted(unknown)}")
    return value


def _choice(value: Any, choices: set[str], label: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{label} must be one of {sorted(choices)}")


def validate_inventory(inventory: Any) -> set[str]:
    inventory = require_closed_object(inventory, {"version", "managed_workflows"}, "workflow_inventory")
    if type(inventory.get("version")) is not int or inventory["version"] != 1:
        raise ValueError("workflow_inventory.version must be integer 1")
    entries = inventory.get("managed_workflows")
    if not isinstance(entries, list):
        raise ValueError("workflow_inventory.managed_workflows must be an array")
    known: set[str] = set()
    sources: set[str] = set()
    runtimes: set[str] = set()
    for entry in entries:
        entry = require_closed_object(entry, {"id", "source", "consumer_runtime"}, "managed workflow")
        identity = entry.get("id")
        if not isinstance(identity, str) or not identity or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in identity
        ) or identity.startswith("-") or identity.endswith("-"):
            raise ValueError("managed workflow id must be a durable lowercase workflow name")
        source, runtime = entry.get("source"), entry.get("consumer_runtime")
        expected_source = f"shared/bijux-gh/workflows/{identity}.yml"
        expected_runtime = f".github/workflows/{identity}.yml"
        if source != expected_source or runtime != expected_runtime:
            raise ValueError(f"managed workflow {identity} must use its canonical source/runtime paths")
        if not isinstance(source, str) or PurePosixPath(source).is_absolute():
            raise ValueError("managed workflow source must be relative")
        if identity in known or source in sources or runtime in runtimes:
            raise ValueError(f"duplicate managed workflow: {identity}")
        known.add(identity)
        sources.add(source)
        runtimes.add(runtime)
    return known


def validate_policy(repository: dict, known_workflows: set[str]) -> WorkflowExecutionPolicy | None:
    if "workflow_execution_policy" not in repository:
        return None
    name = repository.get("name")
    policy = require_closed_object(repository["workflow_execution_policy"], {
        "schema", "automatic_runs", "dependency_pull_requests", "publication_entrypoints",
    }, f"{name}.workflow_execution_policy")
    if type(policy.get("schema")) is not int or policy["schema"] != 1:
        raise ValueError(f"{name}.workflow_execution_policy.schema must be integer 1")
    for key, choices in [
        ("automatic_runs", {"canonical", "repository-policy-only"}),
        ("dependency_pull_requests", {"canonical", "skip-managed-jobs"}),
    ]:
        if key in policy:
            _choice(policy[key], choices, f"{name}.{key}")
            if name == "bijux-std" and policy[key] != "canonical":
                raise ValueError("bijux-std must retain its mandatory workflow qualification")
    allowlist = repository.get("workflow_allowlist", [])
    if not isinstance(allowlist, list) or any(not isinstance(item, str) for item in allowlist):
        raise ValueError("workflow_allowlist must be an array of managed workflow names")
    if len(set(allowlist)) != len(allowlist) or set(allowlist) - known_workflows:
        raise ValueError("workflow_allowlist must contain distinct canonical inventory names")
    if policy.get("automatic_runs") == "repository-policy-only" and "github-policy" not in allowlist:
        raise ValueError("repository-policy-only requires enabled canonical github-policy")
    if "publication_entrypoints" in policy:
        publication = require_closed_object(policy["publication_entrypoints"], set(PUBLICATION_ENTRYPOINTS), "publication_entrypoints")
        for identity, entry in publication.items():
            if identity not in known_workflows or identity not in allowlist:
                raise ValueError(f"publication entrypoint {identity} is not an enabled managed workflow")
            entry = require_closed_object(entry, {"mode", "refs", "controller"} if identity == "deploy-docs" else {"mode", "controller"}, identity)
            _choice(entry.get("mode"), {"canonical", "manual-only"}, f"{identity}.mode")
            if "controller" in entry:
                _choice(entry["controller"], {"iac"}, f"{identity}.controller")
                if entry["mode"] != "manual-only":
                    raise ValueError("IaC controller requires manual-only publication")
            if "refs" in entry:
                _choice(entry["refs"], {"canonical", "main-only"}, f"{identity}.refs")
                if entry["refs"] == "main-only" and entry["mode"] != "manual-only":
                    raise ValueError("main-only docs requires manual-only mode")
    # Callers cannot accidentally rewrite the canonical configuration while projecting it.
    return copy.deepcopy(policy)


def validate_manifest(manifest: dict, repositories: list[str]) -> dict[str, WorkflowExecutionPolicy | None]:
    entries = manifest.get("repositories")
    if not isinstance(entries, list):
        raise ValueError("manifest.repositories must be an array")
    by_name: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError("manifest repository must have a string name")
        name = entry["name"]
        if name in by_name:
            raise ValueError(f"duplicate manifest repository: {name}")
        by_name[name] = entry
    selected = []
    for name in repositories:
        if name not in by_name:
            raise KeyError(f"Repository '{name}' not found in manifest")
        selected.append(by_name[name])
    inventory = manifest.get("workflow_inventory")
    if "workflow_inventory" not in manifest:
        if any("workflow_execution_policy" in entry for entry in selected):
            raise ValueError("execution policy requires canonical workflow_inventory")
        known: set[str] = set()
    else:
        known = validate_inventory(inventory)
    return {entry["name"]: validate_policy(entry, known) for entry in selected}
