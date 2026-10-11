#!/usr/bin/env python3
"""Authorize an immutable manual publication request before publisher jobs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

PUBLISHERS = {"deploy-docs", "release-github", "release-ghcr", "release-crates", "release-pypi"}
PR_ONLY_CHECKS = {"policy / pr approval"}


def api(path: str):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def check_runs(repository: str, commit: str) -> list[dict]:
    pages = json.loads(subprocess.check_output([
        "gh", "api", "--paginate", "--slurp", f"repos/{repository}/commits/{commit}/check-runs?per_page=100",
    ], text=True))
    if not isinstance(pages, list) or not all(isinstance(page, dict) and isinstance(page.get("check_runs"), list) for page in pages):
        raise ValueError("malformed exact-commit check response")
    return [run for page in pages for run in page["check_runs"]]


def require_green_checks(contexts: set[str], commit: str, runs: list[dict]) -> None:
    latest = {}
    for run in runs:
        if not isinstance(run, dict) or type(run.get("id")) is not int or not isinstance(run.get("name"), str):
            raise ValueError("malformed check run")
        if run.get("head_sha") != commit or run.get("app", {}).get("id") != 15368:
            continue
        if run["id"] > latest.get(run["name"], {}).get("id", -1):
            latest[run["name"]] = run
    failures = [context for context in sorted(contexts)
                if latest.get(context, {}).get("status") != "completed" or latest[context].get("conclusion") != "success"]
    if failures:
        raise ValueError(f"unhealthy or missing exact-commit checks: {failures}")


def admit(environment: dict[str, str]) -> dict:
    repository = environment.get("PUBLICATION_REPOSITORY", "")
    event = environment.get("PUBLICATION_EVENT", "")
    ref = environment.get("PUBLICATION_REF", "")
    actor = environment.get("PUBLICATION_ACTOR", "")
    triggering_actor = environment.get("PUBLICATION_TRIGGERING_ACTOR", "")
    actor_id = environment.get("PUBLICATION_ACTOR_ID", "")
    trusted = environment.get("PUBLICATION_CONTROLLER_ACTOR_ID", "")
    commit = environment.get("PUBLICATION_COMMIT", "")
    workflow = environment.get("PUBLICATION_WORKFLOW", "")
    tag = environment.get("PUBLICATION_TAG", "")
    if (event != "workflow_dispatch" or ref != "refs/heads/main" or not trusted.isdecimal()
            or actor_id != trusted or triggering_actor != actor or not actor.endswith("[bot]") or not repository.startswith("bijux/")):
        raise ValueError("publication requires authenticated IaC App dispatch on main")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or workflow not in PUBLISHERS:
        raise ValueError("publication requires an immutable commit and a canonical publisher")
    manifest = json.loads(Path(".github/standards/repo-config.manifest.json").read_text())
    entry = next((repo for repo in manifest["repositories"] if "bijux/" + repo["name"] == repository), None)
    if entry is None or workflow not in entry.get("workflow_allowlist", []):
        raise ValueError("publisher is not an applicable repository capability")
    identity = api(f"users/{actor}")
    if identity.get("type") != "Bot" or str(identity.get("id")) != trusted:
        raise ValueError("controller identity is not the configured App bot")
    accepted = api(f"repos/{repository}/commits/main")
    if accepted.get("sha") != commit or environment.get("PUBLICATION_RUN_SHA") != commit:
        raise ValueError("request and workflow must identify the same current accepted main commit")
    if workflow != "deploy-docs":
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag):
            raise ValueError("release publication requires an explicit version tag")
        if api(f"repos/{repository}/commits/{tag}").get("sha") != commit:
            raise ValueError("release tag does not resolve to the accepted requested commit")
    rules = api(f"repos/{repository}/rules/branches/main")
    if not isinstance(rules, list):
        raise ValueError("malformed effective protection response")
    required = [check for rule in rules if rule.get("type") == "required_status_checks"
                for check in rule.get("parameters", {}).get("required_status_checks", [])]
    if not required or any(check.get("integration_id") != 15368 for check in required):
        raise ValueError("publication requires declared GitHub Actions check bindings")
    contexts = {check["context"] for check in required} - PR_ONLY_CHECKS
    if not {"policy / github", "std / standard", "std / report"}.issubset(contexts):
        raise ValueError("publication requires the common protection checks")
    require_green_checks(contexts, commit, check_runs(repository, commit))
    return {"repository": repository, "workflow": workflow, "commit": commit, "tag": tag,
            "controller_actor_id": trusted, "required_commit_checks": sorted(contexts)}


if __name__ == "__main__":
    receipt = admit(dict(os.environ))
    path = Path("artifacts/publication/admission.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("Authenticated exact-commit publication admitted")
