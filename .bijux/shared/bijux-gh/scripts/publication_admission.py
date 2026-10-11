#!/usr/bin/env python3
"""Authorize an immutable manual publication request before publisher jobs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen
from urllib.parse import urlparse

PUBLISHERS = {"deploy-docs", "release-github", "release-ghcr", "release-crates", "release-pypi"}
PR_ONLY_CHECKS = {"policy / pr approval"}
SHA = re.compile(r"[0-9a-f]{40}")
# Exact merge identity uses the supported API contract that exposes merge_commit_sha.
API_VERSION = "2022-11-28"
PUBLIC_REPOSITORY_IDS: dict[str, int] = {}


def api(path: str):
    return json.loads(subprocess.check_output(["gh", "api", "--header", "X-GitHub-Api-Version: " + API_VERSION, path], text=True))


def public_pages(path: str) -> list:
    """Read public foundation evidence without widening the publisher App token."""
    if not (path.startswith(("repos/bijux/bijux-std/", "repos/bijux/bijux-iac/"))
            or path in {"repos/bijux/bijux-std", "repos/bijux/bijux-iac", "users/bijux-publication[bot]"}):
        raise ValueError("public source reads are restricted to foundation evidence")
    url, pages, seen = "https://api.github.com/" + path, [], set()
    endpoint = urlparse(url).path
    admitted_paths = {endpoint}
    for name, identifier in PUBLIC_REPOSITORY_IDS.items():
        prefix = "/repos/" + name + "/"
        if endpoint.startswith(prefix):
            admitted_paths.add("/repositories/" + str(identifier) + "/" + endpoint.removeprefix(prefix))
    while url:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.path not in admitted_paths or url in seen:
            raise ValueError("public source pagination must retain its exact GitHub endpoint")
        seen.add(url)
        request = Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION})
        with urlopen(request, timeout=30) as response:
            if response.geturl() != url:
                raise ValueError("public source evidence must not redirect")
            pages.append(json.load(response))
            links = re.findall(r'<([^>]+)>;\s*rel="next"', response.headers.get("Link", ""))
            if len(links) > 1:
                raise ValueError("public source pagination is ambiguous")
            url = links[0] if links else ""
    return pages


def public_api(path: str):
    pages = public_pages(path)
    if len(pages) != 1:
        raise ValueError("public source singleton response unexpectedly paginates")
    result = pages[0]
    if path in {"repos/bijux/bijux-std", "repos/bijux/bijux-iac"}:
        name = path.removeprefix("repos/")
        if (not isinstance(result, dict) or result.get("full_name") != name or result.get("visibility") != "public"
                or type(result.get("id")) is not int or result["id"] <= 0):
            raise ValueError("public foundation metadata must bind its exact repository identity")
        PUBLIC_REPOSITORY_IDS[name] = result["id"]
    return result


def public_check_runs(repository: str, commit: str) -> list[dict]:
    pages = public_pages(f"repos/{repository}/commits/{commit}/check-runs?per_page=100")
    if not all(isinstance(page, dict) and isinstance(page.get("check_runs"), list) for page in pages):
        raise ValueError("malformed public exact-commit check response")
    return [run for page in pages for run in page["check_runs"]]


def public_associated_pulls(repository: str, commit: str) -> list[dict]:
    pages = public_pages(f"repos/{repository}/commits/{commit}/pulls?per_page=100")
    if not all(isinstance(page, list) for page in pages):
        raise ValueError("malformed public accepted-commit pull request response")
    return [pull for page in pages for pull in page]


def check_runs(repository: str, commit: str) -> list[dict]:
    pages = json.loads(subprocess.check_output([
        "gh", "api", "--header", "X-GitHub-Api-Version: " + API_VERSION,
        "--paginate", "--slurp", f"repos/{repository}/commits/{commit}/check-runs?per_page=100",
    ], text=True))
    if not isinstance(pages, list) or not all(isinstance(page, dict) and isinstance(page.get("check_runs"), list) for page in pages):
        raise ValueError("malformed exact-commit check response")
    return [run for page in pages for run in page["check_runs"]]


def associated_pulls(repository: str, commit: str) -> list[dict]:
    pages = json.loads(subprocess.check_output([
        "gh", "api", "--header", "X-GitHub-Api-Version: " + API_VERSION,
        "--paginate", "--slurp", f"repos/{repository}/commits/{commit}/pulls?per_page=100",
    ], text=True))
    if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
        raise ValueError("malformed accepted-commit pull request response")
    return [pull for page in pages for pull in page]


def accepted_pull_head(repository: str, commit: str, accepted: dict, *, reader=None, pulls_reader=None) -> tuple[int, str]:
    """Bind current main to its own normal merge, never an older successful PR."""
    parents = accepted.get("parents")
    if (not isinstance(parents, list) or len(parents) != 2
            or any(not isinstance(parent, dict) or not SHA.fullmatch(parent.get("sha", "")) for parent in parents)
            or parents[0]["sha"] == parents[1]["sha"]):
        raise ValueError("accepted publication requires a normal two-parent PR merge")
    head = parents[1]["sha"]

    def matches(pull: dict) -> bool:
        if not isinstance(pull, dict):
            raise ValueError("malformed associated pull request")
        user, base, branch = pull.get("user", {}), pull.get("base", {}), pull.get("head", {})
        return (type(pull.get("number")) is int and pull["number"] > 0
                and pull.get("state") == "closed" and isinstance(pull.get("merged_at"), str) and bool(pull["merged_at"])
                and pull.get("merge_commit_sha") == commit and branch.get("sha") == head
                and base.get("ref") == "main" and base.get("sha") == parents[0]["sha"]
                and base.get("repo", {}).get("full_name") == repository
                and branch.get("repo", {}).get("full_name") == repository
                and user.get("type") == "User" and isinstance(user.get("login"), str)
                and bool(user["login"]) and not user["login"].endswith("[bot]"))

    reader = reader or api
    pulls_reader = pulls_reader or associated_pulls
    matches_found = [pull for pull in pulls_reader(repository, commit) if matches(pull)]
    if len(matches_found) != 1:
        raise ValueError("accepted main must have one exact merged human pull request")
    number = matches_found[0]["number"]
    fresh = reader(f"repos/{repository}/pulls/{number}")
    if not matches(fresh) or fresh.get("number") != number or fresh.get("merged") is not True:
        raise ValueError("accepted pull request identity changed during admission")
    return number, head


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


def admit(environment: dict[str, str], *, public_source: bool = False) -> dict:
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
    if public_source and (repository not in {"bijux/bijux-std", "bijux/bijux-iac"} or workflow != "deploy-docs"):
        raise ValueError("public source admission is restricted to foundation documentation")
    reader = public_api if public_source else api
    runs_reader = public_check_runs if public_source else check_runs
    pulls_reader = public_associated_pulls if public_source else associated_pulls
    if public_source and reader(f"repos/{repository}").get("visibility") != "public":
        raise ValueError("routed foundation evidence must be public")
    manifest = json.loads(Path(".github/standards/repo-config.manifest.json").read_text())
    entry = next((repo for repo in manifest["repositories"] if "bijux/" + repo["name"] == repository), None)
    if entry is None or workflow not in entry.get("workflow_allowlist", []):
        raise ValueError("publisher is not an applicable repository capability")
    deployment = entry.get("workflow_execution_policy", {}).get("publication_entrypoints", {}).get("deploy-docs", {})
    destination = deployment.get("destination")
    if (workflow == "deploy-docs" and not public_source and destination is not None
            and destination.get("repository") != entry["name"]):
        raise ValueError("routed documentation must publish through its declared controller destination")
    identity = reader(f"users/{actor}")
    if identity.get("type") != "Bot" or str(identity.get("id")) != trusted:
        raise ValueError("controller identity is not the configured App bot")
    accepted = reader(f"repos/{repository}/commits/main")
    if accepted.get("sha") != commit or environment.get("PUBLICATION_RUN_SHA") != commit:
        raise ValueError("request and workflow must identify the same current accepted main commit")
    if workflow != "deploy-docs":
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag):
            raise ValueError("release publication requires an explicit version tag")
        if reader(f"repos/{repository}/commits/{tag}").get("sha") != commit:
            raise ValueError("release tag does not resolve to the accepted requested commit")
    rules = reader(f"repos/{repository}/rules/branches/main")
    if not isinstance(rules, list):
        raise ValueError("malformed effective protection response")
    required = [check for rule in rules if rule.get("type") == "required_status_checks"
                for check in rule.get("parameters", {}).get("required_status_checks", [])]
    if not required or any(check.get("integration_id") != 15368 for check in required):
        raise ValueError("publication requires declared GitHub Actions check bindings")
    contexts = {check["context"] for check in required}
    if not {"policy / github", "std / standard", "std / report"}.issubset(contexts):
        raise ValueError("publication requires the common protection checks")
    policy = entry.get("workflow_execution_policy", {})
    number, verification_commit = None, commit
    if policy.get("main_verification") == "accepted-pull-request":
        if policy.get("dependency_pull_requests") != "notification-only" or policy.get("dependency_merge") != "owner-consolidation":
            raise ValueError("accepted PR publication requires the declared owner-consolidation policy")
        if not PR_ONLY_CHECKS.issubset(contexts):
            raise ValueError("accepted PR publication requires the owner approval binding")
        number, verification_commit = accepted_pull_head(repository, commit, accepted, reader=reader, pulls_reader=pulls_reader)
    else:
        contexts -= PR_ONLY_CHECKS
    require_green_checks(contexts, verification_commit, runs_reader(repository, verification_commit))
    if reader(f"repos/{repository}/commits/main").get("sha") != commit:
        raise ValueError("accepted main moved during publication admission")
    return {"repository": repository, "workflow": workflow, "commit": commit, "tag": tag,
            "controller_actor_id": trusted, "required_commit_checks": sorted(contexts),
            "verification_commit": verification_commit, "accepted_pull_request": number}


if __name__ == "__main__":
    receipt = admit(dict(os.environ))
    path = Path("artifacts/publication/admission.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("Authenticated exact-commit publication admitted")
