"""Canonical documentation deployment ownership for the governed family."""
from __future__ import annotations

import copy


FOUNDATION_DOCS = {
    "bijux-iac": {"repository": "bijux.github.io", "path": "/infrastructure/"},
    "bijux-std": {"repository": "bijux.github.io", "path": "/standards/"},
}
DOCUMENTATION_REPOSITORIES = frozenset({
    "bijux-iac", "bijux-std", "bijux.github.io", "bijux-masterclass",
    "bijux-core", "bijux-atlas", "bijux-gnss", "bijux-genomics",
    "bijux-canon", "bijux-proteomics", "bijux-pollenomics", "bijux-phylogenetics",
})


def validate_destination(repository: str, value: object) -> dict:
    if repository not in DOCUMENTATION_REPOSITORIES:
        raise ValueError("documentation destination requires a governed repository")
    owned = {
        "repository": repository,
        "path": "/" if repository == "bijux.github.io" else f"/{repository}/",
    }
    admitted = [owned]
    if repository in FOUNDATION_DOCS:
        admitted.append(FOUNDATION_DOCS[repository])
    if not isinstance(value, dict) or value not in admitted:
        raise ValueError(f"{repository}: documentation destination must identify its owned site or declared Hub section")
    return copy.deepcopy(value)


def documentation_destination(repository: dict) -> dict:
    name = repository.get("name")
    entry = repository.get("workflow_execution_policy", {}).get("publication_entrypoints", {}).get("deploy-docs")
    if (not isinstance(entry, dict) or set(entry) != {"mode", "controller", "refs", "destination"}
            or entry.get("mode") != "manual-only" or entry.get("controller") != "iac"
            or entry.get("refs") != "main-only" or "deploy-docs" not in repository.get("workflow_allowlist", [])):
        raise ValueError(f"{name}: explicit manual documentation destination is required")
    return validate_destination(name, entry["destination"])
